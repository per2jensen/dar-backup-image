#!/usr/bin/env python3
"""Generate the README release table from canonical build history."""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import stat
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse


LOGGER = logging.getLogger(__name__)
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_HISTORY_PATH = REPOSITORY_ROOT / "doc" / "build-history.json"
DEFAULT_README_PATH = REPOSITORY_ROOT / "README.md"
DEFAULT_RELEASE_LIMIT = 5
START_MARKER = "<!-- BEGIN GENERATED RELEASE TABLE -->"
END_MARKER = "<!-- END GENERATED RELEASE TABLE -->"
RELEASE_TAG_PATTERN = re.compile(
    r"^\d+(?:\.\d+){2,3}(?:-rc[1-9]\d*)?$"
)


def _required_string(
    entry: Mapping[str, Any], key: str, entry_index: int
) -> str:
    """Return a required non-empty string from a build-history entry.

    Args:
        entry: Build-history entry being validated.
        key: Required field name.
        entry_index: Zero-based entry index used in error messages.

    Returns:
        The validated string value.

    Raises:
        ValueError: If the field is absent, empty, or not a string.
    """
    value = entry.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"Build-history entry {entry_index} field {key!r} must be a "
            "non-empty string"
        )
    return value.strip()


def _required_build_number(entry: Mapping[str, Any], entry_index: int) -> int:
    """Return a valid non-negative build number from one history entry.

    Args:
        entry: Build-history entry being validated.
        entry_index: Zero-based entry index used in error messages.

    Returns:
        The validated build number.

    Raises:
        ValueError: If the build number is absent or invalid.
    """
    value = entry.get("build_number")
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(
            f"Build-history entry {entry_index} field 'build_number' must be "
            "a non-negative integer"
        )
    return value


def _release_date(created: str, entry_index: int) -> str:
    """Convert an ISO-8601 build timestamp to a UTC calendar date.

    Args:
        created: Timestamp stored in the history entry.
        entry_index: Zero-based entry index used in error messages.

    Returns:
        UTC date formatted as ``YYYY-MM-DD``.

    Raises:
        ValueError: If the timestamp is malformed or lacks a timezone.
    """
    normalized = created[:-1] + "+00:00" if created.endswith("Z") else created
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise ValueError(
            f"Build-history entry {entry_index} has invalid 'created' "
            f"timestamp {created!r}"
        ) from error
    if parsed.tzinfo is None:
        raise ValueError(
            f"Build-history entry {entry_index} 'created' timestamp must "
            "include a timezone"
        )
    return parsed.astimezone(timezone.utc).date().isoformat()


def _validate_markdown_text(value: str, field: str, entry_index: int) -> str:
    """Validate text before inserting it into one Markdown table cell.

    Args:
        value: Cell value to validate.
        field: Source field name used in error messages.
        entry_index: Zero-based entry index used in error messages.

    Returns:
        The unchanged validated value.

    Raises:
        ValueError: If the value would break Markdown table structure.
    """
    if "|" in value or "\n" in value or "\r" in value:
        raise ValueError(
            f"Build-history entry {entry_index} field {field!r} contains "
            "unsupported Markdown table characters"
        )
    return value


def _validate_url(value: str, entry_index: int) -> str:
    """Validate a Docker Hub link before placing it in Markdown.

    Args:
        value: URL from the build-history entry.
        entry_index: Zero-based entry index used in error messages.

    Returns:
        The unchanged validated URL.

    Raises:
        ValueError: If the URL is not an absolute HTTPS URL.
    """
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError(
            f"Build-history entry {entry_index} field 'dockerhub_tag_url' "
            "must be an absolute HTTPS URL"
        )
    return _validate_markdown_text(value, "dockerhub_tag_url", entry_index)


def load_history(path: Path) -> list[dict[str, Any]]:
    """Load build-history entries from a JSON array.

    Args:
        path: Build-history JSON file.

    Returns:
        Decoded history entries in file order.

    Raises:
        OSError: If the history file cannot be read.
        ValueError: If the JSON is malformed or not an array of objects.
    """
    if path is None:
        raise ValueError("history path must not be None")
    try:
        decoded = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"Malformed build-history JSON in {path}: {error}") from error
    if not isinstance(decoded, list):
        raise ValueError(f"Build history in {path} must be a JSON array")

    entries: list[dict[str, Any]] = []
    for entry_index, entry in enumerate(decoded):
        if not isinstance(entry, dict):
            raise ValueError(
                f"Build-history entry {entry_index} must be a JSON object"
            )
        entries.append(entry)
    return entries


def select_releases(
    entries: Sequence[Mapping[str, Any]], limit: int
) -> list[dict[str, Any]]:
    """Select and validate the newest stable and release-candidate entries.

    Args:
        entries: Complete build-history entries.
        limit: Maximum number of releases to return.

    Returns:
        Validated release dictionaries sorted by descending build number.

    Raises:
        ValueError: If inputs or selected release metadata are invalid.
    """
    if entries is None:
        raise ValueError("entries must not be None")
    if not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0:
        raise ValueError("release limit must be a positive integer")

    candidates: list[tuple[int, int, Mapping[str, Any], str]] = []
    seen_tags: set[str] = set()
    for entry_index, entry in enumerate(entries):
        tag_value = entry.get("tag")
        if not isinstance(tag_value, str):
            raise ValueError(
                f"Build-history entry {entry_index} field 'tag' must be a string"
            )
        tag = tag_value.strip()
        if not RELEASE_TAG_PATTERN.fullmatch(tag):
            continue
        if tag in seen_tags:
            raise ValueError(f"Duplicate release tag in build history: {tag}")
        seen_tags.add(tag)
        build_number = _required_build_number(entry, entry_index)
        candidates.append((build_number, entry_index, entry, tag))

    if not candidates:
        raise ValueError("Build history contains no release entries")

    candidates.sort(key=lambda candidate: candidate[0], reverse=True)
    releases: list[dict[str, Any]] = []
    for build_number, entry_index, entry, tag in candidates[:limit]:
        dar_backup_version = _validate_markdown_text(
            _required_string(entry, "dar_backup_version", entry_index),
            "dar_backup_version",
            entry_index,
        )
        dar_version = _validate_markdown_text(
            _required_string(entry, "dar_version", entry_index),
            "dar_version",
            entry_index,
        )
        git_revision = _validate_markdown_text(
            _required_string(entry, "git_revision", entry_index),
            "git_revision",
            entry_index,
        )
        created = _required_string(entry, "created", entry_index)
        dockerhub_url = _validate_url(
            _required_string(entry, "dockerhub_tag_url", entry_index), entry_index
        )
        releases.append(
            {
                "build_number": build_number,
                "tag": _validate_markdown_text(tag, "tag", entry_index),
                "dar_backup_version": dar_backup_version,
                "dar_version": dar_version,
                "release_date": _release_date(created, entry_index),
                "git_revision": git_revision,
                "dockerhub_tag_url": dockerhub_url,
            }
        )
    return releases


def render_release_table(releases: Sequence[Mapping[str, Any]]) -> str:
    """Render validated release metadata as a Markdown table.

    Args:
        releases: Stable or release-candidate entries in desired display order.

    Returns:
        Complete Markdown table without surrounding markers.

    Raises:
        ValueError: If no release entries are supplied.
    """
    if not releases:
        raise ValueError("at least one release is required to render the table")
    lines = [
        "| Tag | `dar-backup` | `dar` | Release date | Git Revision | "
        "Docker Hub | Note |",
        "|---|---|---|---|---|---|---|",
    ]
    for release in releases:
        tag = release["tag"]
        lines.append(
            f"| {tag} | {release['dar_backup_version']} | "
            f"{release['dar_version']} | {release['release_date']} | "
            f"{release['git_revision']} | "
            f"[tag:{tag}]({release['dockerhub_tag_url']}) | - |"
        )
    return "\n".join(lines)


def replace_generated_table(readme: str, table: str) -> str:
    """Replace the exactly bounded generated table in README content.

    Args:
        readme: Existing README text.
        table: Newly rendered Markdown table.

    Returns:
        Updated README text.

    Raises:
        ValueError: If markers are missing, duplicated, or reversed.
    """
    if not isinstance(readme, str):
        raise ValueError("README content must be a string")
    if not table:
        raise ValueError("generated table must not be empty")
    if readme.count(START_MARKER) != 1 or readme.count(END_MARKER) != 1:
        raise ValueError(
            "README must contain exactly one generated release-table marker pair"
        )
    start_index = readme.index(START_MARKER)
    end_index = readme.index(END_MARKER)
    if end_index <= start_index:
        raise ValueError("README generated release-table markers are reversed")
    end_index += len(END_MARKER)
    replacement = f"{START_MARKER}\n{table}\n{END_MARKER}"
    return readme[:start_index] + replacement + readme[end_index:]


def _atomic_write(path: Path, content: str) -> None:
    """Atomically replace a text file while retaining its permission mode.

    Args:
        path: Existing destination file.
        content: Complete replacement text.

    Raises:
        OSError: If the temporary file cannot be written or replaced.
        ValueError: If an argument is invalid.
    """
    if path is None:
        raise ValueError("destination path must not be None")
    if not isinstance(content, str):
        raise ValueError("replacement content must be a string")
    file_mode = stat.S_IMODE(path.stat().st_mode)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            temporary_file.write(content)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.chmod(temporary_path, file_mode)
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def update_readme(
    history_path: Path, readme_path: Path, limit: int, check: bool
) -> bool:
    """Regenerate or verify the README release table.

    Args:
        history_path: Canonical build-history JSON file.
        readme_path: README containing generated-table markers.
        limit: Maximum number of stable or release-candidate entries to display.
        check: When true, report drift without writing.

    Returns:
        ``True`` when the existing README differs from generated content.

    Raises:
        OSError: If an input cannot be read or output cannot be written.
        ValueError: If history, markers, or arguments are invalid.
    """
    if readme_path is None:
        raise ValueError("README path must not be None")
    history = load_history(history_path)
    releases = select_releases(history, limit)
    table = render_release_table(releases)
    original = readme_path.read_text(encoding="utf-8")
    updated = replace_generated_table(original, table)
    changed = updated != original
    if changed and not check:
        _atomic_write(readme_path, updated)
    return changed


def _build_parser() -> argparse.ArgumentParser:
    """Build the standalone generator's command-line parser.

    Returns:
        Configured argument parser.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--history", type=Path, default=DEFAULT_HISTORY_PATH, help="build history JSON"
    )
    parser.add_argument(
        "--readme", type=Path, default=DEFAULT_README_PATH, help="README to update"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_RELEASE_LIMIT,
        help="number of stable or release-candidate entries to display",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit nonzero when the generated table differs; do not write",
    )
    return parser


def main() -> int:
    """Run the README release-table generator.

    Returns:
        Zero when updated/current, one for detected drift, or two for bad input.
    """
    arguments = _build_parser().parse_args()
    try:
        changed = update_readme(
            arguments.history, arguments.readme, arguments.limit, arguments.check
        )
    except (OSError, ValueError) as error:
        LOGGER.error("Unable to generate README release table: %s", error)
        return 2

    if arguments.check and changed:
        LOGGER.error(
            "README release table is stale; run scripts/update_readme_releases.py"
        )
        return 1
    if changed:
        LOGGER.info("Updated release table in %s", arguments.readme)
    else:
        LOGGER.info("README release table is current")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    raise SystemExit(main())
