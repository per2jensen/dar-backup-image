#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Select and resolve immutable refresh source from build history."""

from __future__ import annotations

import argparse
import json
import logging
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


logging.basicConfig(level=logging.INFO, format="%(message)s")
LOGGER = logging.getLogger(__name__)

TAG_PATTERN = re.compile(
    r"^(?P<base>[0-9]+\.[0-9]+\.[0-9]+)"
    r"(?:-(?P<refresh>[1-9][0-9]*))?$"
)
REVISION_PATTERN = re.compile(r"^[0-9a-f]{7,40}$")
FULL_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")


@dataclass(frozen=True)
class RefreshSource:
    """Resolved source selection for one image refresh.

    Attributes:
        raw_tag: Version tag from the latest build-history record.
        base_version: Stable version underlying the release or refresh tag.
        refresh_number: Numeric refresh suffix, or zero for a base release.
        next_refresh_number: Next unused numeric refresh suffix.
        next_refresh_version: Complete version containing the next suffix.
        recorded_revision: Git revision stored in build history.
        application_sha: Full commit SHA resolved from the recorded revision.
        release_tag_sha: Full commit SHA targeted by the stable release tag.
        tag_matches_source: Whether the release tag identifies the recorded source.
    """

    raw_tag: str
    base_version: str
    refresh_number: int
    next_refresh_number: int
    next_refresh_version: str
    recorded_revision: str
    application_sha: str
    release_tag_sha: str
    tag_matches_source: bool


def load_latest_record(path: Path) -> dict[str, Any]:
    """Load the final object from canonical build history.

    Args:
        path: Build-history JSON file.

    Returns:
        Final build-history record.

    Raises:
        OSError: If the history file cannot be read.
        ValueError: If the document is malformed, empty, or has a non-object tail.
    """
    if path is None:
        raise ValueError("history path must not be None")
    try:
        decoded = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"malformed build-history JSON in {path}: {error}") from error
    if not isinstance(decoded, list) or not decoded:
        raise ValueError("build history must be a non-empty JSON array")
    latest = decoded[-1]
    if not isinstance(latest, dict):
        raise ValueError("latest build-history record must be a JSON object")
    return latest


def required_string(record: dict[str, Any], field: str) -> str:
    """Return one required, unpadded string field.

    Args:
        record: Latest build-history record.
        field: Required field name.

    Returns:
        Validated string value.

    Raises:
        ValueError: If the field is absent, empty, non-string, or padded.
    """
    value = record.get(field)
    if not isinstance(value, str) or not value:
        raise ValueError(f"latest build-history field {field!r} must be a string")
    if value != value.strip():
        raise ValueError(f"latest build-history field {field!r} must be unpadded")
    return value


def version_parts_from_tag(tag: str) -> tuple[str, int]:
    """Extract a stable base and refresh number from a version tag.

    Args:
        tag: Version stored by the latest build-history record.

    Returns:
        Stable ``x.y.z`` base version and numeric refresh suffix. The suffix is
        zero for a base release.

    Raises:
        ValueError: If the tag is neither stable nor a canonical numeric refresh.
    """
    match = TAG_PATTERN.fullmatch(tag)
    if match is None:
        raise ValueError(
            f"latest build-history tag {tag!r} must be x.y.z or x.y.z-N"
        )
    refresh = match.group("refresh")
    return match.group("base"), int(refresh) if refresh is not None else 0


def resolve_commit(repository: Path, revision: str) -> str:
    """Resolve one validated revision to an immutable full commit SHA.

    Args:
        repository: Git worktree containing complete repository history.
        revision: Commit or tag expression to resolve.

    Returns:
        Full 40-character commit SHA.

    Raises:
        OSError: If Git cannot be executed.
        ValueError: If the revision cannot be resolved to one commit.
    """
    if repository is None:
        raise ValueError("repository path must not be None")
    if not revision:
        raise ValueError("revision must not be empty")
    result = subprocess.run(
        [
            "git",
            "-C",
            str(repository),
            "rev-parse",
            "--verify",
            f"{revision}^{{commit}}",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    resolved = result.stdout.strip()
    if result.returncode != 0 or not FULL_SHA_PATTERN.fullmatch(resolved):
        diagnostic = result.stderr.strip() or "revision did not resolve to a commit"
        raise ValueError(f"cannot resolve Git revision {revision!r}: {diagnostic}")
    return resolved


def latest_refresh_tag_number(repository: Path, base_version: str) -> int:
    """Return the highest canonical refresh suffix present in Git tags.

    Args:
        repository: Complete Git checkout containing refresh tags.
        base_version: Stable ``x.y.z`` version whose tags should be examined.

    Returns:
        Highest positive suffix, or zero when no refresh tag exists.

    Raises:
        OSError: If Git cannot be executed.
        ValueError: If Git cannot list tags.
    """
    result = subprocess.run(
        [
            "git",
            "-C",
            str(repository),
            "tag",
            "--list",
            f"v{base_version}-*",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        diagnostic = result.stderr.strip() or "Git could not list refresh tags"
        raise ValueError(f"cannot list Git refresh tags: {diagnostic}")

    pattern = re.compile(rf"^v{re.escape(base_version)}-([1-9][0-9]*)$")
    suffixes = [
        int(match.group(1))
        for tag in result.stdout.splitlines()
        if (match := pattern.fullmatch(tag)) is not None
    ]
    return max(suffixes, default=0)


def select_refresh_source(history_path: Path, repository: Path) -> RefreshSource:
    """Select the exact application commit recorded by the latest build.

    Args:
        history_path: Canonical build-history JSON file.
        repository: Complete Git checkout used to resolve commits and tags.

    Returns:
        Validated, fully resolved refresh source metadata.

    Raises:
        OSError: If history or Git cannot be read.
        ValueError: If metadata is invalid or revisions cannot be resolved.
    """
    record = load_latest_record(history_path)
    raw_tag = required_string(record, "tag")
    recorded_revision = required_string(record, "git_revision")
    if not REVISION_PATTERN.fullmatch(recorded_revision):
        raise ValueError(
            "latest build-history field 'git_revision' must contain "
            "7 to 40 lowercase hexadecimal characters"
        )

    base_version, refresh_number = version_parts_from_tag(raw_tag)
    application_sha = resolve_commit(repository, recorded_revision)
    release_tag_sha = resolve_commit(repository, f"v{base_version}")
    latest_tag_number = latest_refresh_tag_number(repository, base_version)
    next_refresh_number = max(refresh_number, latest_tag_number) + 1
    return RefreshSource(
        raw_tag=raw_tag,
        base_version=base_version,
        refresh_number=refresh_number,
        next_refresh_number=next_refresh_number,
        next_refresh_version=f"{base_version}-{next_refresh_number}",
        recorded_revision=recorded_revision,
        application_sha=application_sha,
        release_tag_sha=release_tag_sha,
        tag_matches_source=application_sha == release_tag_sha,
    )


def parse_args() -> argparse.Namespace:
    """Parse refresh-source selection arguments.

    Returns:
        Parsed history and repository paths.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history", required=True, type=Path)
    parser.add_argument("--repository", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    """Resolve refresh source and emit its metadata as JSON.

    Returns:
        Zero on success, otherwise two.
    """
    arguments = parse_args()
    try:
        selection = select_refresh_source(arguments.history, arguments.repository)
    except (OSError, ValueError) as error:
        LOGGER.error("ERROR: %s", error)
        return 2

    json.dump(asdict(selection), sys.stdout, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
