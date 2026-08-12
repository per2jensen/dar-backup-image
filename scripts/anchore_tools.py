#!/usr/bin/env python3
"""Install pinned Anchore tools and report when newer releases exist."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import logging
import os
import platform
import re
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path, PurePosixPath
from typing import Any, Sequence


LOGGER = logging.getLogger("anchore-tools")
TOOLS = ("syft", "grype")
VERSION_KEYS = {"SYFT_VERSION": "syft", "GRYPE_VERSION": "grype"}
VERSION_PATTERN = re.compile(r"v\d+\.\d+\.\d+")
CHECKSUM_PATTERN = re.compile(r"[0-9a-f]{64}")
ARCHITECTURES = {
    "x86_64": "amd64",
    "amd64": "amd64",
    "aarch64": "arm64",
    "arm64": "arm64",
}


def load_version_pins(path: Path) -> dict[str, str]:
    """Load and validate the exact Syft and Grype release tags.

    Args:
        path: Environment-style version file.

    Returns:
        Mapping from tool name to a validated release tag.

    Raises:
        OSError: If the version file cannot be read.
        ValueError: If the file is malformed, incomplete, or duplicated.
    """
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"Anchore version file is missing or unsafe: {path}")

    pins: dict[str, str] = {}
    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if not separator or key not in VERSION_KEYS:
            raise ValueError(f"Invalid Anchore version entry at {path}:{line_number}")
        tool = VERSION_KEYS[key]
        if tool in pins:
            raise ValueError(f"Duplicate {key} entry at {path}:{line_number}")
        if not VERSION_PATTERN.fullmatch(value):
            raise ValueError(f"Invalid {key} release tag: {value!r}")
        pins[tool] = value

    missing = sorted(set(TOOLS) - set(pins))
    if missing:
        raise ValueError(f"Anchore version file is missing pins for: {', '.join(missing)}")
    return pins


def _platform_asset_parts() -> tuple[str, str]:
    """Map the current host to Anchore release asset names.

    Returns:
        Supported Anchore operating-system and architecture names.

    Raises:
        ValueError: If the host platform is unsupported.
    """
    operating_system = platform.system().lower()
    if operating_system not in {"linux", "darwin"}:
        raise ValueError(f"Unsupported operating system: {operating_system}")
    machine = platform.machine().lower()
    architecture = ARCHITECTURES.get(machine)
    if architecture is None:
        raise ValueError(f"Unsupported architecture: {machine}")
    return operating_system, architecture


def download_bytes(
    url: str,
    *,
    attempts: int = 5,
    base_delay_seconds: float = 2.0,
) -> bytes:
    """Download bytes with bounded retries for transient HTTP failures.

    Args:
        url: HTTPS or HTTP URL to retrieve.
        attempts: Maximum number of requests.
        base_delay_seconds: Initial exponential-backoff delay.

    Returns:
        Downloaded response body.

    Raises:
        ValueError: If retry parameters or the URL are invalid.
        RuntimeError: If all attempts fail or a permanent HTTP error occurs.
    """
    if attempts < 1:
        raise ValueError("Download attempts must be at least one")
    if base_delay_seconds < 0:
        raise ValueError("Download delay cannot be negative")
    if not url.startswith(("https://", "http://")):
        raise ValueError(f"Unsupported download URL: {url!r}")

    request = urllib.request.Request(url, headers={"User-Agent": "dar-backup-image-ci"})
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            transient = error.code == 429 or 500 <= error.code <= 599
            if not transient or attempt == attempts:
                raise RuntimeError(
                    f"Download failed with HTTP {error.code}: {url}"
                ) from error
            LOGGER.warning(
                "Transient HTTP %s downloading %s (attempt %s/%s)",
                error.code,
                url,
                attempt,
                attempts,
            )
        except (urllib.error.URLError, TimeoutError) as error:
            if attempt == attempts:
                raise RuntimeError(f"Download failed after {attempts} attempts: {url}") from error
            LOGGER.warning(
                "Transient download failure for %s (attempt %s/%s): %s",
                url,
                attempt,
                attempts,
                error,
            )
        time.sleep(base_delay_seconds * (2 ** (attempt - 1)))

    raise RuntimeError(f"Download failed unexpectedly: {url}")


def _expected_checksum(checksums: bytes, archive_name: str) -> str:
    """Extract one exact archive checksum from an Anchore checksum file.

    Args:
        checksums: UTF-8 checksum-file bytes.
        archive_name: Exact release archive basename.

    Returns:
        Expected lowercase SHA-256 digest.

    Raises:
        ValueError: If decoding fails or exactly one valid entry is not found.
    """
    try:
        lines = checksums.decode("utf-8").splitlines()
    except UnicodeDecodeError as error:
        raise ValueError("Anchore checksum file is not valid UTF-8") from error

    matches: list[str] = []
    for line in lines:
        fields = line.split()
        if len(fields) == 2 and fields[1].lstrip("*") == archive_name:
            matches.append(fields[0].lower())
    if len(matches) != 1 or not CHECKSUM_PATTERN.fullmatch(matches[0]):
        raise ValueError(f"Expected one valid checksum for {archive_name}")
    return matches[0]


def _binary_version(binary_path: Path) -> str:
    """Read a Syft or Grype semantic version from its executable.

    Args:
        binary_path: Executable to query.

    Returns:
        Normalized release tag beginning with ``v``.

    Raises:
        OSError: If the executable cannot be started.
        RuntimeError: If version output is unsuccessful or malformed.
    """
    try:
        result = subprocess.run(
            [str(binary_path), "version"],
            capture_output=True,
            text=True,
            check=False,
            timeout=20,
        )
    except subprocess.TimeoutExpired as error:
        raise RuntimeError(f"Version check timed out: {binary_path}") from error
    if result.returncode != 0:
        raise RuntimeError(
            f"Version check failed for {binary_path}: {result.stderr.strip()}"
        )
    match = re.search(r"(?im)^Version:\s*v?(\d+\.\d+\.\d+)\s*$", result.stdout)
    if match is None:
        raise RuntimeError(f"Could not parse version output from {binary_path}")
    return f"v{match.group(1)}"


def install_archive(
    tool: str,
    version: str,
    archive: bytes,
    checksums: bytes,
    archive_name: str,
    bin_dir: Path,
) -> Path:
    """Verify and atomically install one Anchore release archive.

    Args:
        tool: Supported Anchore executable name.
        version: Expected release tag.
        archive: Downloaded tar.gz bytes.
        checksums: Downloaded checksum-file bytes.
        archive_name: Exact release archive basename.
        bin_dir: Destination executable directory.

    Returns:
        Installed executable path.

    Raises:
        OSError: If the destination cannot be written or queried.
        RuntimeError: If the installed executable reports the wrong version.
        ValueError: If inputs, checksum, or archive members are invalid.
    """
    if tool not in TOOLS:
        raise ValueError(f"Unsupported Anchore tool: {tool!r}")
    if not VERSION_PATTERN.fullmatch(version):
        raise ValueError(f"Invalid Anchore release tag: {version!r}")
    if not bin_dir.is_absolute():
        raise ValueError(f"Installation directory must be absolute: {bin_dir}")
    if bin_dir.is_symlink():
        raise ValueError(f"Installation directory cannot be a symlink: {bin_dir}")
    expected_checksum = _expected_checksum(checksums, archive_name)
    actual_checksum = hashlib.sha256(archive).hexdigest()
    if actual_checksum != expected_checksum:
        raise ValueError(f"SHA-256 mismatch for {archive_name}")

    try:
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as release:
            members = [
                member
                for member in release.getmembers()
                if member.isfile()
                and not PurePosixPath(member.name).is_absolute()
                and ".." not in PurePosixPath(member.name).parts
                and PurePosixPath(member.name).name == tool
            ]
            if len(members) != 1:
                raise ValueError(
                    f"Expected one safe {tool} executable in {archive_name}, found {len(members)}"
                )
            extracted = release.extractfile(members[0])
            if extracted is None:
                raise ValueError(f"Could not extract {tool} from {archive_name}")
            binary_content = extracted.read()
    except tarfile.TarError as error:
        raise ValueError(f"Invalid release archive: {archive_name}") from error
    if not binary_content:
        raise ValueError(f"Release executable is empty: {archive_name}")

    bin_dir.mkdir(parents=True, exist_ok=True)
    destination = bin_dir / tool
    temporary_path: Path | None = None
    try:
        descriptor, raw_temporary_path = tempfile.mkstemp(
            prefix=f".{tool}.", dir=bin_dir
        )
        temporary_path = Path(raw_temporary_path)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(binary_content)
            handle.flush()
            os.fsync(handle.fileno())
        temporary_path.chmod(0o755)
        reported_version = _binary_version(temporary_path)
        if reported_version != version:
            raise RuntimeError(
                f"{tool} reported {reported_version}, expected {version}"
            )
        os.replace(temporary_path, destination)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
    return destination


def install_tools(pins: dict[str, str], bin_dir: Path) -> None:
    """Install every pinned Anchore tool from checksum-verified assets.

    Args:
        pins: Validated tool-to-release mapping.
        bin_dir: Destination executable directory.

    Raises:
        OSError: If installation or version checks fail at the OS level.
        RuntimeError: If downloads or executable checks fail.
        ValueError: If pin, platform, checksum, or archive data is invalid.
    """
    operating_system, architecture = _platform_asset_parts()
    for tool in TOOLS:
        version = pins.get(tool)
        if version is None:
            raise ValueError(f"Missing version pin for {tool}")
        destination = bin_dir / tool
        if destination.is_file() and not destination.is_symlink():
            try:
                if _binary_version(destination) == version:
                    LOGGER.info("%s %s is already installed", tool, version)
                    continue
            except (OSError, RuntimeError) as error:
                LOGGER.warning("Replacing unusable %s executable: %s", tool, error)

        numeric_version = version.removeprefix("v")
        archive_name = (
            f"{tool}_{numeric_version}_{operating_system}_{architecture}.tar.gz"
        )
        checksum_name = f"{tool}_{numeric_version}_checksums.txt"
        release_url = f"https://github.com/anchore/{tool}/releases/download/{version}"
        LOGGER.info("Installing %s %s", tool, version)
        archive = download_bytes(f"{release_url}/{archive_name}")
        checksums = download_bytes(f"{release_url}/{checksum_name}")
        installed = install_archive(
            tool,
            version,
            archive,
            checksums,
            archive_name,
            bin_dir,
        )
        LOGGER.info("Installed %s", installed)


def _semantic_version(version: str) -> tuple[int, int, int]:
    """Convert a validated release tag into comparable integers.

    Args:
        version: Release tag in ``vX.Y.Z`` form.

    Returns:
        Major, minor, and patch components.

    Raises:
        ValueError: If the release tag is malformed.
    """
    if not VERSION_PATTERN.fullmatch(version):
        raise ValueError(f"Invalid semantic version: {version!r}")
    major, minor, patch = version[1:].split(".")
    return int(major), int(minor), int(patch)


def available_updates(
    pins: dict[str, str], latest_releases: dict[str, str]
) -> list[str]:
    """Describe stable releases that are newer than the configured pins.

    Args:
        pins: Validated tool-to-pinned-release mapping.
        latest_releases: Tool-to-latest-release mapping.

    Returns:
        Human-readable update messages; empty when every pin is current.

    Raises:
        ValueError: If a tool or release tag is missing or malformed.
    """
    updates: list[str] = []
    for tool in TOOLS:
        pinned = pins.get(tool)
        latest = latest_releases.get(tool)
        if pinned is None or latest is None:
            raise ValueError(f"Missing release comparison data for {tool}")
        if not VERSION_PATTERN.fullmatch(pinned):
            raise ValueError(f"Invalid pinned {tool} release tag: {pinned!r}")
        if not VERSION_PATTERN.fullmatch(latest):
            raise ValueError(f"Invalid latest {tool} release tag: {latest!r}")
        if _semantic_version(latest) > _semantic_version(pinned):
            updates.append(f"{tool}: pinned {pinned}, latest {latest}")
    return updates


def check_latest_releases(pins: dict[str, str]) -> list[str]:
    """Compare pinned tools with the latest stable GitHub releases.

    Args:
        pins: Validated tool-to-release mapping.

    Returns:
        Human-readable update messages; empty when every pin is current.

    Raises:
        RuntimeError: If release metadata cannot be downloaded.
        ValueError: If release metadata is malformed.
    """
    latest_releases: dict[str, str] = {}
    for tool in TOOLS:
        pinned = pins.get(tool)
        if pinned is None:
            raise ValueError(f"Missing version pin for {tool}")
        metadata_bytes = download_bytes(
            f"https://api.github.com/repos/anchore/{tool}/releases/latest"
        )
        try:
            metadata: Any = json.loads(metadata_bytes)
        except json.JSONDecodeError as error:
            raise ValueError(f"Invalid latest-release response for {tool}") from error
        latest = metadata.get("tag_name") if isinstance(metadata, dict) else None
        if not isinstance(latest, str) or not VERSION_PATTERN.fullmatch(latest):
            raise ValueError(f"Latest {tool} release tag is missing or invalid")
        LOGGER.info("%s pinned=%s latest=%s", tool, pinned, latest)
        latest_releases[tool] = latest
    return available_updates(pins, latest_releases)


def _parser() -> argparse.ArgumentParser:
    """Create the command-line parser.

    Returns:
        Configured argument parser.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--versions-file",
        type=Path,
        default=Path("config/anchore-tool-versions.env"),
        help="central Syft and Grype pin file",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    install_parser = subparsers.add_parser("install", help="install pinned tools")
    install_parser.add_argument("--bin-dir", type=Path, required=True)
    subparsers.add_parser("check-latest", help="fail when a newer release exists")
    subparsers.add_parser("validate", help="validate and print the configured pins")
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    """Run the Anchore tool manager.

    Args:
        arguments: Optional command arguments excluding the executable name.

    Returns:
        Zero on success, one when updates exist, or two on operational errors.
    """
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parsed = _parser().parse_args(arguments)
    try:
        pins = load_version_pins(parsed.versions_file)
        if parsed.command == "install":
            install_tools(pins, parsed.bin_dir)
            return 0
        if parsed.command == "check-latest":
            updates = check_latest_releases(pins)
            if updates:
                for update in updates:
                    LOGGER.error("Anchore tool update available: %s", update)
                    if os.environ.get("GITHUB_ACTIONS") == "true":
                        print(
                            f"::error title=Anchore tool update available::{update}",
                            file=sys.stderr,
                        )
                return 1
            LOGGER.info("Pinned Anchore tools are current")
            return 0
        for tool in TOOLS:
            print(f"{tool}={pins[tool]}")
        return 0
    except (OSError, RuntimeError, ValueError) as error:
        LOGGER.error("Anchore tool operation failed: %s", error)
        return 2


if __name__ == "__main__":
    sys.exit(main())
