#!/opt/venv/bin/python3
"""Build and display the documentation preserved in dar-backup images."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import logging
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from email import policy
from email.message import Message
from email.parser import BytesParser
from importlib import metadata as importlib_metadata
from pathlib import Path, PurePosixPath
from typing import Any, Sequence, TextIO


LOGGER = logging.getLogger("dar-backup-image-docs")
DEFAULT_DOCS_DIR = Path("/usr/share/doc/dar-backup")
PACKAGE_NAME = "dar-backup"
PACKAGE_DOC_PREFIXES = (("dar_backup", "doc"), ("dar_backup", "docs"))
TEXT_DOCUMENT_SUFFIXES = {".md", ".rst", ".txt"}
DOCUMENT_BASENAME_PREFIXES = (
    "authors",
    "changelog",
    "changes",
    "copying",
    "history",
    "license",
    "notice",
    "readme",
)


def _sha256_bytes(content: bytes) -> str:
    """Calculate a SHA-256 digest for in-memory content.

    Args:
        content: Bytes to hash.

    Returns:
        Lowercase hexadecimal SHA-256 digest.
    """
    return hashlib.sha256(content).hexdigest()


def _sha256_file(path: Path) -> str:
    """Calculate a SHA-256 digest without loading a whole file into memory.

    Args:
        path: Regular file to hash.

    Returns:
        Lowercase hexadecimal SHA-256 digest.

    Raises:
        OSError: If the file cannot be read.
    """
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical_distribution_name(name: str) -> str:
    """Normalize a Python distribution name for reliable comparison.

    Args:
        name: Distribution name from metadata.

    Returns:
        PEP 503-style normalized name.
    """
    return re.sub(r"[-_.]+", "-", name).lower()


def _validate_distribution_member(member_name: str) -> PurePosixPath:
    """Validate that an installed distribution member is a safe relative path.

    Args:
        member_name: Path recorded in the installed distribution's RECORD.

    Returns:
        Validated relative path.

    Raises:
        ValueError: If the member is absolute or contains unsafe components.
    """
    member_path = PurePosixPath(member_name)
    if member_path.is_absolute() or not member_path.parts:
        raise ValueError(f"Unsafe distribution member path: {member_name!r}")
    if any(part in {"", ".", ".."} for part in member_path.parts):
        raise ValueError(f"Unsafe distribution member path: {member_name!r}")
    return member_path


def _metadata_value(message: Message, field_name: str) -> str:
    """Read and validate a required installed metadata field.

    Args:
        message: Parsed Core Metadata message.
        field_name: Required metadata header name.

    Returns:
        Stripped field value.

    Raises:
        ValueError: If the field is absent or empty.
    """
    value = message.get(field_name)
    if value is None or not str(value).strip():
        raise ValueError(f"Installed METADATA field {field_name!r} is missing or empty")
    return str(value).strip()


def _metadata_description(message: Message) -> str:
    """Decode the Markdown description stored in installed Core Metadata.

    Args:
        message: Parsed Core Metadata message.

    Returns:
        Description text, or an empty string when the distribution has none.

    Raises:
        ValueError: If the description payload is multipart or not UTF-8 text.
    """
    payload = message.get_payload(decode=True)
    if isinstance(payload, bytes):
        try:
            return payload.decode(message.get_content_charset() or "utf-8")
        except UnicodeDecodeError as error:
            raise ValueError("Installed METADATA description is not valid UTF-8 text") from error

    raw_payload = message.get_payload()
    if isinstance(raw_payload, list):
        raise ValueError("Installed METADATA unexpectedly contains a multipart payload")
    return str(raw_payload or "")


def _find_metadata_member(
    files: Sequence[importlib_metadata.PackagePath],
) -> importlib_metadata.PackagePath:
    """Locate the single Core Metadata file in an installed distribution.

    Args:
        files: Paths recorded by the installed distribution.

    Returns:
        Path record for ``*.dist-info/METADATA``.

    Raises:
        ValueError: If exactly one metadata member is not present.
    """
    matches = [
        entry
        for entry in files
        if len(PurePosixPath(str(entry)).parts) == 2
        and PurePosixPath(str(entry)).parts[0].endswith(".dist-info")
        and PurePosixPath(str(entry)).name == "METADATA"
    ]
    if len(matches) != 1:
        raise ValueError(
            f"Expected exactly one *.dist-info/METADATA member, found {len(matches)}"
        )
    return matches[0]


def _verify_recorded_hash(
    entry: importlib_metadata.PackagePath, content: bytes
) -> None:
    """Verify installed bytes against their RECORD hash when available.

    Args:
        entry: Installed distribution path with optional RECORD metadata.
        content: Bytes read from the installed file.

    Raises:
        ValueError: If the hash algorithm is unsupported or the digest differs.
    """
    recorded_hash = entry.hash
    if recorded_hash is None:
        return
    try:
        digest = hashlib.new(recorded_hash.mode, content).digest()
    except ValueError as error:
        raise ValueError(
            f"Unsupported RECORD hash algorithm for {entry}: {recorded_hash.mode}"
        ) from error
    encoded = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    if encoded != recorded_hash.value:
        raise ValueError(f"Installed distribution RECORD hash mismatch: {entry}")


def _documentation_destination(member_path: PurePosixPath) -> tuple[str, Path] | None:
    """Classify an installed documentation file and choose its destination.

    Args:
        member_path: Validated distribution-relative path.

    Returns:
        A ``(kind, destination)`` tuple for documentation, or None otherwise.
    """
    parts = member_path.parts
    for prefix in PACKAGE_DOC_PREFIXES:
        if len(parts) > len(prefix) and tuple(parts[: len(prefix)]) == prefix:
            relative_parts = parts[len(prefix) :]
            return "package-document", Path("doc", *relative_parts)

    if any(part.lower() in {"doc", "docs"} for part in parts[:-1]):
        return "embedded-document", Path("distribution-files", *parts)

    if member_path.name.lower().startswith(DOCUMENT_BASENAME_PREFIXES):
        return "embedded-document", Path("distribution-files", *parts)
    return None


def _license_destination(member_path: PurePosixPath) -> Path | None:
    """Choose a stable destination for a dist-info license file.

    Args:
        member_path: Validated distribution-relative path.

    Returns:
        License destination relative to the bundle, or None when not a license.
    """
    parts = member_path.parts
    if len(parts) < 3 or not parts[0].endswith(".dist-info"):
        return None
    if parts[1].lower() != "licenses":
        return None
    return Path("licenses", *parts[2:])


def _safe_output_path(root: Path, relative_path: Path) -> Path:
    """Resolve a relative output path while enforcing bundle containment.

    Args:
        root: Bundle root directory.
        relative_path: Candidate path relative to the root.

    Returns:
        Absolute output path contained by the root.

    Raises:
        ValueError: If the path is absolute or escapes the bundle root.
    """
    if relative_path.is_absolute() or ".." in relative_path.parts:
        raise ValueError(f"Unsafe documentation output path: {relative_path}")
    resolved_root = root.resolve()
    resolved_output = (root / relative_path).resolve()
    if resolved_output != resolved_root and resolved_root not in resolved_output.parents:
        raise ValueError(f"Documentation output escapes bundle: {relative_path}")
    return resolved_output


def _write_file(root: Path, relative_path: Path, content: bytes) -> dict[str, Any]:
    """Write one bundle file and return its integrity fields.

    Args:
        root: Temporary bundle root.
        relative_path: Destination relative to the root.
        content: Exact bytes to write.

    Returns:
        Manifest fields containing path, size, and SHA-256.

    Raises:
        OSError: If directories or the output file cannot be created.
        ValueError: If the destination is unsafe.
    """
    destination = _safe_output_path(root, relative_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(content)
    return {
        "path": relative_path.as_posix(),
        "size_bytes": len(content),
        "sha256": _sha256_bytes(content),
    }


def _topic_name(path: Path, used_topics: set[str]) -> str:
    """Create a deterministic, unique command topic for one text document.

    Args:
        path: Documentation path relative to the bundle.
        used_topics: Topics already allocated in this bundle.

    Returns:
        Unique topic accepted by the ``docs`` command.
    """
    base_topic = re.sub(r"[^a-z0-9]+", "-", path.stem.lower()).strip("-") or "document"
    topic = base_topic
    suffix = 2
    while topic in used_topics:
        topic = f"{base_topic}-{suffix}"
        suffix += 1
    used_topics.add(topic)
    return topic


def _is_displayable_document(path: Path, content: bytes) -> bool:
    """Check whether an embedded document can be printed safely as UTF-8 text.

    Args:
        path: Documentation destination path.
        content: Embedded file content.

    Returns:
        True for supported text formats containing valid UTF-8.
    """
    if path.suffix.lower() not in TEXT_DOCUMENT_SUFFIXES:
        return False
    try:
        content.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def _project_urls(message: Message) -> dict[str, str]:
    """Convert repeated Project-URL metadata headers into a mapping.

    Args:
        message: Parsed installed Core Metadata.

    Returns:
        Mapping of link labels to URLs; malformed values are omitted.
    """
    urls: dict[str, str] = {}
    for raw_value in message.get_all("Project-URL", []):
        label, separator, url = str(raw_value).partition(",")
        if separator and label.strip() and url.strip():
            urls[label.strip()] = url.strip()
    return urls


def _render_index(version: str, documentation: Sequence[dict[str, Any]]) -> bytes:
    """Render a human-readable Markdown index for the documentation bundle.

    Args:
        version: dar-backup distribution version.
        documentation: Displayable documentation manifest entries.

    Returns:
        UTF-8 encoded Markdown index.
    """
    lines = [
        "# Bundled dar-backup documentation",
        "",
        f"This image contains documentation from dar-backup {version}.",
        "",
        "Use `docs <topic>` to print a document, or `docs --path` to locate all files.",
        "",
        "## Topics",
        "",
    ]
    for entry in documentation:
        lines.append(f"- `{entry['topic']}` — `{entry['path']}`")
    lines.extend(
        [
            "",
            "The files were copied from the installed distribution after RECORD verification.",
            "See `MANIFEST.json` for their complete integrity record.",
            "",
        ]
    )
    return "\n".join(lines).encode("utf-8")


def _verify_manifest_files(bundle_root: Path, manifest: dict[str, Any]) -> None:
    """Verify every integrity-protected file recorded by a manifest.

    Args:
        bundle_root: Documentation bundle root.
        manifest: Parsed manifest object.

    Raises:
        ValueError: If manifest records are malformed or integrity checks fail.
        OSError: If a recorded file cannot be read.
    """
    records = manifest.get("files")
    if not isinstance(records, list) or not records:
        raise ValueError("Documentation manifest has no integrity file records")
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("Documentation manifest contains a malformed file record")
        relative_value = record.get("path")
        expected_hash = record.get("sha256")
        expected_size = record.get("size_bytes")
        if not isinstance(relative_value, str) or not relative_value:
            raise ValueError("Documentation manifest file path is missing")
        if not isinstance(expected_hash, str) or len(expected_hash) != 64:
            raise ValueError(f"Documentation manifest SHA-256 is invalid: {relative_value}")
        if not isinstance(expected_size, int) or expected_size < 0:
            raise ValueError(f"Documentation manifest size is invalid: {relative_value}")
        path = _safe_output_path(bundle_root, Path(relative_value))
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"Bundled documentation file is missing or unsafe: {relative_value}")
        actual_size = path.stat().st_size
        actual_hash = _sha256_file(path)
        if actual_size != expected_size or actual_hash != expected_hash:
            raise ValueError(f"Bundled documentation integrity check failed: {relative_value}")


def build_documentation_bundle(
    distribution: importlib_metadata.Distribution,
    output_dir: Path,
    expected_version: str | None = None,
    image_readme_path: Path | None = None,
) -> dict[str, Any]:
    """Build an atomic documentation bundle from an installed distribution.

    Args:
        distribution: Already-installed dar-backup distribution to inspect.
        output_dir: New stable directory to create.
        expected_version: Optional build pin that must match the installation.
        image_readme_path: Optional image-repository README to preserve offline.

    Returns:
        Generated documentation manifest.

    Raises:
        ValueError: If provenance, metadata, paths, or documentation are invalid.
        OSError: If files cannot be read, written, or atomically installed.
    """
    if output_dir.exists():
        raise ValueError(f"Documentation output directory already exists: {output_dir}")
    distribution_files = distribution.files
    if distribution_files is None or not distribution_files:
        raise ValueError("Installed dar-backup distribution has no RECORD file list")

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary_dir = Path(
        tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=str(output_dir.parent))
    )
    try:
        metadata_entry = _find_metadata_member(distribution_files)
        metadata_path = Path(distribution.locate_file(metadata_entry))
        if not metadata_path.is_file() or metadata_path.is_symlink():
            raise ValueError(f"Installed METADATA is missing or unsafe: {metadata_path}")
        metadata_bytes = metadata_path.read_bytes()
        _verify_recorded_hash(metadata_entry, metadata_bytes)
        message = BytesParser(policy=policy.default).parsebytes(metadata_bytes)
        distribution_name = _metadata_value(message, "Name")
        installed_version = _metadata_value(message, "Version")

        if _canonical_distribution_name(distribution_name) != PACKAGE_NAME:
            raise ValueError(
                f"Expected installed {PACKAGE_NAME!r}, found {distribution_name!r}"
            )
        if distribution.version != installed_version:
            raise ValueError(
                "Installed distribution metadata versions disagree: "
                f"distribution={distribution.version!r}, metadata={installed_version!r}"
            )
        if expected_version is not None and installed_version != expected_version:
            raise ValueError(
                "Installed dar-backup version does not match build pin: "
                f"expected={expected_version!r}, installed={installed_version!r}"
            )

        files: list[dict[str, Any]] = []
        documentation: list[dict[str, Any]] = []
        used_topics = {"overview", "index"}

        raw_metadata_record = _write_file(
            temporary_dir, Path("METADATA"), metadata_bytes
        )
        raw_metadata_record.update(
            {"kind": "distribution-metadata", "source": str(metadata_entry)}
        )
        files.append(raw_metadata_record)

        description = _metadata_description(message)
        if description.strip():
            overview_record = _write_file(
                temporary_dir, Path("README.md"), description.encode("utf-8")
            )
            overview_record.update(
                {
                    "kind": "metadata-description",
                    "source": f"{metadata_entry}#Description",
                    "topic": "overview",
                }
            )
            documentation.append(overview_record)
            files.append(overview_record.copy())

        if image_readme_path is not None:
            if not image_readme_path.is_file() or image_readme_path.is_symlink():
                raise ValueError(
                    f"Image README does not exist or is unsafe: {image_readme_path}"
                )
            image_readme_content = image_readme_path.read_bytes()
            if not image_readme_content.strip():
                raise ValueError("Image README must not be empty")
            try:
                image_readme_content.decode("utf-8")
            except UnicodeDecodeError as error:
                raise ValueError("Image README is not valid UTF-8 text") from error
            image_record = _write_file(
                temporary_dir, Path("image", "README.md"), image_readme_content
            )
            image_record.update(
                {
                    "kind": "image-document",
                    "source": "build-context:README.md",
                    "topic": "image",
                }
            )
            used_topics.add("image")
            documentation.append(image_record)
            files.append(image_record.copy())

        seen_destinations = {record["path"] for record in files}
        for entry in sorted(distribution_files, key=str):
            if entry == metadata_entry:
                continue
            raw_member_path = PurePosixPath(str(entry))
            license_destination = _license_destination(raw_member_path)
            classification = _documentation_destination(raw_member_path)
            if license_destination is None and classification is None:
                continue
            member_path = _validate_distribution_member(str(entry))
            source_path = Path(distribution.locate_file(entry))
            if not source_path.is_file() or source_path.is_symlink():
                raise ValueError(
                    f"Installed documentation is missing or unsafe: {entry}"
                )
            content = source_path.read_bytes()
            _verify_recorded_hash(entry, content)

            if license_destination is not None:
                kind = "license"
                destination = license_destination
            else:
                if classification is None:
                    raise ValueError(
                        f"Internal documentation classification error: {member_path}"
                    )
                kind, destination = classification

            destination_text = destination.as_posix()
            if destination_text in seen_destinations:
                raise ValueError(
                    "Multiple installed files map to documentation path "
                    f"{destination_text!r}"
                )
            seen_destinations.add(destination_text)
            record = _write_file(temporary_dir, destination, content)
            record.update({"kind": kind, "source": str(entry)})
            if classification is not None and _is_displayable_document(
                destination, content
            ):
                record["topic"] = _topic_name(destination, used_topics)
                documentation.append(record.copy())
            files.append(record)

        if not documentation:
            raise ValueError(
                "The installed dar-backup distribution contains no displayable documentation"
            )

        documentation.sort(key=lambda item: str(item["topic"]))
        index_content = _render_index(installed_version, documentation)
        index_record = _write_file(temporary_dir, Path("INDEX.md"), index_content)
        index_record.update({"kind": "generated-index", "source": "MANIFEST.json"})
        files.append(index_record)

        manifest: dict[str, Any] = {
            "schema_version": 1,
            "distribution": {
                "name": distribution_name,
                "version": installed_version,
                "metadata_path": str(metadata_entry),
            },
            "project_urls": _project_urls(message),
            "documentation": documentation,
            "files": sorted(files, key=lambda item: str(item["path"])),
        }
        manifest_content = (
            json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        ).encode("utf-8")
        _write_file(temporary_dir, Path("MANIFEST.json"), manifest_content)
        _verify_manifest_files(temporary_dir, manifest)
        temporary_dir.rename(output_dir)
        return manifest
    finally:
        if temporary_dir.exists():
            shutil.rmtree(temporary_dir)


def _load_manifest(docs_dir: Path) -> dict[str, Any]:
    """Load and minimally validate the installed documentation manifest.

    Args:
        docs_dir: Documentation bundle root.

    Returns:
        Parsed manifest mapping.

    Raises:
        ValueError: If the manifest structure is invalid.
        OSError: If the manifest cannot be read.
        json.JSONDecodeError: If the manifest is malformed JSON.
    """
    manifest_path = _safe_output_path(docs_dir, Path("MANIFEST.json"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        raise ValueError("Unsupported or malformed documentation manifest")
    distribution = manifest.get("distribution")
    documentation = manifest.get("documentation")
    if not isinstance(distribution, dict) or not isinstance(documentation, list):
        raise ValueError("Documentation manifest is missing required sections")
    return manifest


def _write_stdout(content: str, stream: TextIO = sys.stdout) -> None:
    """Write command output with a predictable trailing newline.

    Args:
        content: Text to emit.
        stream: Destination text stream.
    """
    stream.write(content)
    if content and not content.endswith("\n"):
        stream.write("\n")


def _list_documentation(
    docs_dir: Path, manifest: dict[str, Any], stream: TextIO = sys.stdout
) -> None:
    """Print all displayable documentation topics.

    Args:
        docs_dir: Documentation bundle root.
        manifest: Parsed documentation manifest.
        stream: Destination text stream.

    Raises:
        ValueError: If manifest topic records are malformed.
    """
    distribution = manifest["distribution"]
    version = distribution.get("version", "unknown")
    lines = [
        f"Bundled dar-backup documentation ({version})",
        "",
        "Topics:",
        "  index                 INDEX.md",
    ]
    for record in manifest["documentation"]:
        if not isinstance(record, dict):
            raise ValueError("Documentation manifest contains a malformed topic record")
        topic = record.get("topic")
        path = record.get("path")
        if not isinstance(topic, str) or not isinstance(path, str):
            raise ValueError("Documentation manifest topic or path is invalid")
        lines.append(f"  {topic:<21} {path}")
    lines.extend(
        [
            "",
            "Command manuals (inside an interactive shell):",
            "  man dar",
            "  man par2",
            "",
            "Usage: docs <topic>",
            "       docs --path",
            "       docs --verify",
            f"Files: {docs_dir}",
        ]
    )
    _write_stdout("\n".join(lines), stream)


def _display_topic(
    docs_dir: Path,
    manifest: dict[str, Any],
    topic: str,
    stream: TextIO = sys.stdout,
) -> None:
    """Print one bundled documentation topic.

    Args:
        docs_dir: Documentation bundle root.
        manifest: Parsed documentation manifest.
        topic: Exact topic name shown by ``docs --list``.
        stream: Destination text stream.

    Raises:
        ValueError: If the topic is invalid, unknown, or points outside the bundle.
        OSError: If the selected document cannot be read.
    """
    if not topic or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", topic):
        raise ValueError(f"Invalid documentation topic: {topic!r}")
    relative_path: str | None = "INDEX.md" if topic == "index" else None
    if relative_path is None:
        for record in manifest["documentation"]:
            if isinstance(record, dict) and record.get("topic") == topic:
                candidate = record.get("path")
                if isinstance(candidate, str):
                    relative_path = candidate
                break
    if relative_path is None:
        raise ValueError(f"Unknown documentation topic: {topic!r}; use 'docs --list'")
    document_path = _safe_output_path(docs_dir, Path(relative_path))
    if not document_path.is_file() or document_path.is_symlink():
        raise ValueError(f"Bundled documentation file is missing or unsafe: {relative_path}")
    _write_stdout(document_path.read_text(encoding="utf-8"), stream)


def _first_command_line(command: Sequence[str]) -> str:
    """Run a version command and return its first non-empty output line.

    Args:
        command: Executable and arguments without shell interpretation.

    Returns:
        First non-empty combined output line, or ``unavailable`` on failure.
    """
    try:
        result = subprocess.run(
            list(command),
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired) as error:
        LOGGER.warning("Could not query %s: %s", command[0], error)
        return "unavailable"
    output = "\n".join((result.stdout, result.stderr))
    for line in output.splitlines():
        if line.strip():
            return line.strip()
    return "unavailable"


def _operating_system_name(os_release_path: Path = Path("/etc/os-release")) -> str:
    """Read the human-friendly operating system name.

    Args:
        os_release_path: Linux os-release file to inspect.

    Returns:
        PRETTY_NAME value, or the platform name when unavailable.
    """
    try:
        for line in os_release_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("PRETTY_NAME="):
                return line.partition("=")[2].strip().strip('"')
    except OSError as error:
        LOGGER.warning("Could not read %s: %s", os_release_path, error)
    return platform.platform()


def _show_info(
    docs_dir: Path, manifest: dict[str, Any], stream: TextIO = sys.stdout
) -> None:
    """Print preserved component versions, paths, provenance, and links.

    Args:
        docs_dir: Documentation bundle root.
        manifest: Parsed documentation manifest.
        stream: Destination text stream.

    Raises:
        ValueError: If required manifest fields are malformed.
    """
    distribution = manifest.get("distribution")
    files = manifest.get("files")
    urls = manifest.get("project_urls", {})
    if not isinstance(distribution, dict) or not isinstance(files, list):
        raise ValueError("Documentation manifest provenance is malformed")
    if not isinstance(urls, dict):
        raise ValueError("Documentation manifest project URLs are malformed")

    lines = [
        "dar-backup image information",
        "",
        f"dar-backup:       {distribution.get('version', 'unknown')}",
        f"DAR:              {_first_command_line(['/usr/local/bin/dar', '--version'])}",
        f"PAR2:             {_first_command_line(['/usr/bin/par2', '--version'])}",
        f"Python:           {platform.python_version()}",
        f"Operating system: {_operating_system_name()}",
        "",
        f"Documentation:    {docs_dir}",
        f"Protected files:  {len(files)}",
        f"Manifest:         {docs_dir / 'MANIFEST.json'}",
        "Usage:            run 'docs --list' or 'docs <topic>'",
    ]
    if urls:
        lines.extend(["", "Project links:"])
        for label, url in sorted(urls.items()):
            lines.append(f"  {label}: {url}")
    lines.extend(
        [
            "",
            "Image source: https://github.com/per2jensen/dar-backup-image",
            "Image registry: https://hub.docker.com/r/per2jensen/dar-backup",
        ]
    )
    _write_stdout("\n".join(lines), stream)


def _docs_parser() -> argparse.ArgumentParser:
    """Create the public documentation command argument parser.

    Returns:
        Configured argument parser.
    """
    parser = argparse.ArgumentParser(
        prog="docs",
        description="Display documentation preserved inside the dar-backup image.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--list", action="store_true", help="list bundled topics")
    mode.add_argument("--path", action="store_true", help="print the documentation path")
    mode.add_argument("--verify", action="store_true", help="verify all recorded SHA-256 hashes")
    parser.add_argument("topic", nargs="?", help="topic shown by --list")
    return parser


def run_docs_command(
    arguments: Sequence[str],
    docs_dir: Path = DEFAULT_DOCS_DIR,
    stream: TextIO = sys.stdout,
) -> int:
    """Run the public ``docs`` command.

    Args:
        arguments: Documentation command arguments.
        docs_dir: Installed documentation bundle path.
        stream: Destination text stream.

    Returns:
        Zero after a successful command.

    Raises:
        ValueError: If command arguments or manifest content are invalid.
        OSError: If documentation cannot be read.
        json.JSONDecodeError: If the manifest is malformed JSON.
    """
    parsed = _docs_parser().parse_args(list(arguments))
    if parsed.topic is not None and (parsed.list or parsed.path or parsed.verify):
        raise ValueError("A documentation topic cannot be combined with an option")
    if parsed.path:
        _write_stdout(str(docs_dir), stream)
        return 0

    manifest = _load_manifest(docs_dir)
    if parsed.verify:
        _verify_manifest_files(docs_dir, manifest)
        _write_stdout(
            f"Documentation integrity verified: {len(manifest['files'])} files", stream
        )
        return 0
    if parsed.topic is not None:
        _display_topic(docs_dir, manifest, parsed.topic, stream)
        return 0
    _list_documentation(docs_dir, manifest, stream)
    return 0


def run_info_command(
    arguments: Sequence[str],
    docs_dir: Path = DEFAULT_DOCS_DIR,
    stream: TextIO = sys.stdout,
) -> int:
    """Run the public ``info`` command.

    Args:
        arguments: Information command arguments; none are accepted.
        docs_dir: Installed documentation bundle path.
        stream: Destination text stream.

    Returns:
        Zero after printing information.

    Raises:
        ValueError: If arguments are supplied or the manifest is invalid.
        OSError: If the manifest cannot be read.
        json.JSONDecodeError: If the manifest is malformed JSON.
    """
    if arguments:
        raise ValueError("The info command does not accept arguments")
    manifest = _load_manifest(docs_dir)
    _show_info(docs_dir, manifest, stream)
    return 0


def _install_parser() -> argparse.ArgumentParser:
    """Create the internal build-time installer argument parser.

    Returns:
        Configured argument parser.
    """
    parser = argparse.ArgumentParser(prog="image_docs.py install")
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--expected-version")
    parser.add_argument("--image-readme", required=True, type=Path)
    return parser


def run_install_command(arguments: Sequence[str]) -> int:
    """Run the image build-time documentation installer.

    Args:
        arguments: Installer CLI arguments.

    Returns:
        Zero after a complete, verified installation.

    Raises:
        ValueError: If installed package provenance is inconsistent.
        OSError: If bundle files cannot be created.
        importlib_metadata.PackageNotFoundError: If dar-backup is not installed.
    """
    parsed = _install_parser().parse_args(list(arguments))
    distribution = importlib_metadata.distribution(PACKAGE_NAME)
    build_documentation_bundle(
        distribution=distribution,
        output_dir=parsed.output_dir,
        expected_version=parsed.expected_version,
        image_readme_path=parsed.image_readme,
    )
    return 0


def main(arguments: Sequence[str] | None = None) -> int:
    """Dispatch build-time and runtime documentation commands.

    Args:
        arguments: Optional argument sequence; defaults to process arguments.

    Returns:
        Process exit status.
    """
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
    argv = list(sys.argv[1:] if arguments is None else arguments)
    program_name = Path(sys.argv[0]).name
    try:
        if program_name == "dar-backup-image-info":
            return run_info_command(argv)
        if argv and argv[0] == "install":
            return run_install_command(argv[1:])
        if argv and argv[0] == "info":
            return run_info_command(argv[1:])
        return run_docs_command(argv)
    except (
        ValueError,
        OSError,
        json.JSONDecodeError,
        importlib_metadata.PackageNotFoundError,
    ) as error:
        LOGGER.error("%s", error)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
