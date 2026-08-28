#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2025-2026 Per Jensen
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This file is part of dar-backup-image:
# https://github.com/per2jensen/dar-backup-image
#
# License terms and warranty disclaimer:
# https://github.com/per2jensen/dar-backup-image/blob/main/LICENSE
"""Validate an existing release before GitHub Release finalization."""

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

VERSION_PATTERN = re.compile(
    r"^[0-9]+\.[0-9]+\.[0-9]+(?:\.[0-9]+)?"
    r"(?:-[0-9A-Za-z]+(?:[.-][0-9A-Za-z]+)*)?$"
)
REVISION_PATTERN = re.compile(r"^[0-9a-f]{7,40}$")
FULL_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
REPOSITORY_PATTERN = re.compile(
    r"^[a-z0-9]+(?:[._-][a-z0-9]+)*(?:/[a-z0-9]+(?:[._-][a-z0-9]+)*)+$"
)
GITHUB_REPOSITORY_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


@dataclass(frozen=True)
class FinalizationSelection:
    """Validated metadata required to finalize one existing release.

    Args:
        version: Existing release version without a leading ``v``.
        source_sha: Full immutable application-source commit.
        housekeeping_sha: Audit commit recorded by the annotated release tag.
        image_digest: Fully qualified signed Docker image digest.
        dar_backup_version: Expected ``dar-backup --version`` value.
        dar_version: DAR version recorded for release notes.
        rekor_url: Transparency-log URL recorded during publication.
        sbom_file: Repository-relative CycloneDX evidence path.
        sarif_file: Repository-relative Grype evidence path.
    """

    version: str
    source_sha: str
    housekeeping_sha: str
    image_digest: str
    dar_backup_version: str
    dar_version: str
    rekor_url: str
    sbom_file: str
    sarif_file: str


def parse_args() -> argparse.Namespace:
    """Parse finalization-selection arguments.

    Returns:
        Parsed command-line arguments.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history", required=True, type=Path)
    parser.add_argument("--repository", required=True, type=Path)
    parser.add_argument("--version", required=True)
    parser.add_argument("--dockerhub-repository", required=True)
    parser.add_argument("--github-repository", required=True)
    return parser.parse_args()


def load_history(path: Path) -> list[dict[str, Any]]:
    """Load and validate a build-history JSON array.

    Args:
        path: Build-history file to read.

    Returns:
        History entries as JSON objects.

    Raises:
        OSError: If the file cannot be read.
        ValueError: If the JSON document is malformed or has an invalid shape.
    """
    if path is None:
        raise ValueError("history path must not be None")
    try:
        decoded = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"malformed build-history JSON in {path}: {error}") from error
    if not isinstance(decoded, list):
        raise ValueError("build history must be a JSON array")
    if not all(isinstance(entry, dict) for entry in decoded):
        raise ValueError("every build-history entry must be a JSON object")
    return decoded


def required_string(record: dict[str, Any], field: str) -> str:
    """Return a required non-empty, unpadded string field.

    Args:
        record: Build-history record containing the field.
        field: Field name to validate.

    Returns:
        Validated string value.

    Raises:
        ValueError: If the field is absent, empty, non-string, or padded.
    """
    value = record.get(field)
    if not isinstance(value, str) or not value:
        raise ValueError(f"build-history field {field!r} must be a non-empty string")
    if value != value.strip():
        raise ValueError(f"build-history field {field!r} must be unpadded")
    if "\n" in value or "\r" in value:
        raise ValueError(f"build-history field {field!r} must not contain newlines")
    return value


def select_unique_record(
    history: list[dict[str, Any]], version: str
) -> dict[str, Any]:
    """Select exactly one history record for a release version.

    Args:
        history: Complete build history.
        version: Requested existing version.

    Returns:
        The unique matching record.

    Raises:
        ValueError: If the version is missing or duplicated.
    """
    matches = [record for record in history if record.get("tag") == version]
    if len(matches) != 1:
        raise ValueError(
            f"release version {version!r} must have exactly one build-history record; "
            f"found {len(matches)}"
        )
    return matches[0]


def run_git(repository: Path, arguments: list[str]) -> str:
    """Run Git and return stripped standard output.

    Args:
        repository: Git worktree containing complete history and tags.
        arguments: Git arguments after ``git -C <repository>``.

    Returns:
        Stripped standard output.

    Raises:
        OSError: If Git cannot be executed.
        ValueError: If Git exits unsuccessfully.
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(repository), *arguments],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as error:
        raise OSError(f"unable to execute Git in {repository}: {error}") from error
    if result.returncode != 0:
        diagnostic = result.stderr.strip() or "Git command failed"
        raise ValueError(diagnostic)
    return result.stdout.strip()


def resolve_commit(repository: Path, revision: str) -> str:
    """Resolve one revision to a full commit SHA.

    Args:
        repository: Complete Git worktree.
        revision: Validated revision expression.

    Returns:
        Full 40-character commit SHA.

    Raises:
        OSError: If Git cannot be executed.
        ValueError: If the revision does not resolve to exactly one commit.
    """
    resolved = run_git(repository, ["rev-parse", "--verify", f"{revision}^{{commit}}"])
    if not FULL_SHA_PATTERN.fullmatch(resolved):
        raise ValueError(f"Git revision {revision!r} did not resolve to a full commit")
    return resolved


def nested_object(record: dict[str, Any], field: str) -> dict[str, Any]:
    """Return a required nested JSON object.

    Args:
        record: Build-history record containing the object.
        field: Object field name.

    Returns:
        Validated nested object.

    Raises:
        ValueError: If the field is not a JSON object.
    """
    value = record.get(field)
    if not isinstance(value, dict):
        raise ValueError(f"build-history field {field!r} must be a JSON object")
    return value


def validate_evidence_path(
    repository: Path,
    raw_path: str,
    required_directory: Path,
) -> str:
    """Validate one existing repository-relative evidence path.

    Args:
        repository: Checkout containing committed evidence.
        raw_path: Candidate path from build history.
        required_directory: Directory beneath which the file must reside.

    Returns:
        Normalized POSIX path relative to the repository.

    Raises:
        OSError: If the file cannot be inspected.
        ValueError: If the path escapes its evidence directory or is empty.
    """
    candidate = Path(raw_path)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError(f"unsafe evidence path: {raw_path!r}")
    if candidate.parent == Path("."):
        candidate = required_directory / candidate
    try:
        candidate.relative_to(required_directory)
    except ValueError as error:
        raise ValueError(
            f"evidence path {candidate} must be below {required_directory}"
        ) from error
    absolute = repository / candidate
    if not absolute.is_file() or absolute.stat().st_size == 0:
        raise ValueError(f"committed evidence file is missing or empty: {candidate}")
    return candidate.as_posix()


def tag_metadata(repository: Path, version: str) -> tuple[str, str, str, str]:
    """Read and validate the annotated release tag metadata.

    Args:
        repository: Complete Git worktree.
        version: Release version without a leading ``v``.

    Returns:
        Tag target, application source, housekeeping commit, and image digest.

    Raises:
        OSError: If Git cannot be executed.
        ValueError: If the tag is absent, lightweight, or malformed.
    """
    tag_ref = f"refs/tags/v{version}"
    object_type = run_git(repository, ["cat-file", "-t", tag_ref])
    if object_type != "tag":
        raise ValueError(f"release tag v{version} must be annotated")
    target = resolve_commit(repository, tag_ref)
    message = run_git(repository, ["for-each-ref", "--format=%(contents)", tag_ref])

    fields: dict[str, str] = {}
    for label in ("Application source", "Housekeeping commit", "Image digest"):
        match = re.search(rf"^{re.escape(label)}: (.+)$", message, re.MULTILINE)
        if match is None:
            raise ValueError(f"release tag v{version} is missing {label!r} metadata")
        fields[label] = match.group(1)
    if not FULL_SHA_PATTERN.fullmatch(fields["Application source"]):
        raise ValueError("release tag application source is not a full commit SHA")
    if not FULL_SHA_PATTERN.fullmatch(fields["Housekeeping commit"]):
        raise ValueError("release tag housekeeping commit is not a full commit SHA")
    return (
        target,
        fields["Application source"],
        fields["Housekeeping commit"],
        fields["Image digest"],
    )


def validate_housekeeping_commit(repository: Path, housekeeping_sha: str) -> None:
    """Require the recorded housekeeping commit to belong to the current branch.

    Args:
        repository: Complete Git worktree checked out from main.
        housekeeping_sha: Full audit commit from the tag annotation.

    Raises:
        OSError: If Git cannot be executed.
        ValueError: If the commit is missing or is not an ancestor of ``HEAD``.
    """
    resolve_commit(repository, housekeeping_sha)
    try:
        subprocess.run(
            [
                "git",
                "-C",
                str(repository),
                "merge-base",
                "--is-ancestor",
                housekeeping_sha,
                "HEAD",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as error:
        raise ValueError(
            f"housekeeping commit {housekeeping_sha} is not an ancestor of current main"
        ) from error


def validate_housekeeping_contents(
    repository: Path,
    housekeeping_sha: str,
    history_path: Path,
    version: str,
    current_record: dict[str, Any],
    evidence_paths: tuple[str, str],
) -> None:
    """Require current metadata and evidence to match the tagged audit commit.

    Args:
        repository: Complete Git worktree checked out from main.
        housekeeping_sha: Audit commit recorded by the release tag.
        history_path: Canonical build-history path.
        version: Requested release version.
        current_record: Matching record read from current main.
        evidence_paths: SBOM and SARIF paths selected from that record.

    Raises:
        OSError: If Git cannot be executed.
        ValueError: If history or evidence differs from the audit commit.
    """
    repository_root = repository.resolve()
    absolute_history = history_path.resolve()
    try:
        relative_history = absolute_history.relative_to(repository_root)
    except ValueError as error:
        raise ValueError(
            "build-history path must be inside the Git repository"
        ) from error

    historical_text = run_git(
        repository,
        ["show", f"{housekeeping_sha}:{relative_history.as_posix()}"],
    )
    try:
        historical_data = json.loads(historical_text)
    except json.JSONDecodeError as error:
        raise ValueError(
            "tagged housekeeping commit contains malformed history"
        ) from error
    if not isinstance(historical_data, list) or not all(
        isinstance(entry, dict) for entry in historical_data
    ):
        raise ValueError("tagged housekeeping commit contains invalid history")
    historical_record = select_unique_record(historical_data, version)
    if historical_record != current_record:
        raise ValueError("current release record differs from its housekeeping commit")

    for evidence_path in evidence_paths:
        historical_blob = run_git(
            repository,
            ["rev-parse", f"{housekeeping_sha}:{evidence_path}"],
        )
        current_blob = run_git(repository, ["rev-parse", f"HEAD:{evidence_path}"])
        if historical_blob != current_blob:
            raise ValueError(
                "current evidence differs from the housekeeping commit: "
                f"{evidence_path}"
            )


def select_finalization(
    history_path: Path,
    repository: Path,
    version: str,
    dockerhub_repository: str,
    github_repository: str,
) -> FinalizationSelection:
    """Validate and select one existing release for finalization.

    Args:
        history_path: Canonical build-history file from current main.
        repository: Complete Git worktree containing release tags.
        version: Existing release version without a leading ``v``.
        dockerhub_repository: Expected Docker Hub repository.
        github_repository: Expected GitHub ``owner/repository`` name.

    Returns:
        Validated finalization metadata.

    Raises:
        OSError: If history, evidence, or Git cannot be read.
        ValueError: If any release record, tag, digest, or path is inconsistent.
    """
    if not VERSION_PATTERN.fullmatch(version):
        raise ValueError(f"unsupported release version: {version!r}")
    if not REPOSITORY_PATTERN.fullmatch(dockerhub_repository):
        raise ValueError(f"invalid Docker Hub repository: {dockerhub_repository!r}")
    if not GITHUB_REPOSITORY_PATTERN.fullmatch(github_repository):
        raise ValueError(f"invalid GitHub repository: {github_repository!r}")

    if repository is None:
        raise ValueError("repository path must not be None")
    if history_path is None:
        raise ValueError("history path must not be None")
    resolved_history_path = (
        history_path.resolve()
        if history_path.is_absolute()
        else (repository / history_path).resolve()
    )

    history = load_history(resolved_history_path)
    record = select_unique_record(history, version)
    recorded_revision = required_string(record, "git_revision")
    if not REVISION_PATTERN.fullmatch(recorded_revision):
        raise ValueError(
            "build-history git_revision must contain 7 to 40 hex characters"
        )
    source_sha = resolve_commit(repository, recorded_revision)

    digest = required_string(record, "digest")
    if not DIGEST_PATTERN.fullmatch(digest):
        raise ValueError("build-history digest must be a sha256 digest")
    image_digest = f"{dockerhub_repository}@{digest}"

    cosign = nested_object(record, "cosign")
    if cosign.get("signed") is not True:
        raise ValueError("build-history record does not mark the image as signed")
    if required_string(cosign, "image_digest") != image_digest:
        raise ValueError("build-history cosign digest does not match the image digest")
    rekor_url = required_string(cosign, "rekor_log_entry")

    sbom = nested_object(record, "sbom")
    sbom_file = validate_evidence_path(
        repository,
        required_string(sbom, "file"),
        Path("doc/sbom"),
    )
    expected_url = (
        f"https://github.com/{github_repository}/releases/download/"
        f"v{version}/{Path(sbom_file).name}"
    )
    if required_string(sbom, "release_asset_url") != expected_url:
        raise ValueError("build-history SBOM release asset URL is inconsistent")

    grype = nested_object(record, "grype_scan")
    sarif_file = validate_evidence_path(
        repository,
        required_string(grype, "file"),
        Path("doc/sarif"),
    )

    tag_target, tag_source, housekeeping_sha, tag_digest = tag_metadata(
        repository, version
    )
    if tag_target != source_sha or tag_source != source_sha:
        raise ValueError("release tag does not identify the recorded source commit")
    if tag_digest != image_digest:
        raise ValueError("release tag image digest does not match build history")
    validate_housekeeping_commit(repository, housekeeping_sha)
    validate_housekeeping_contents(
        repository,
        housekeeping_sha,
        resolved_history_path,
        version,
        record,
        (sbom_file, sarif_file),
    )

    return FinalizationSelection(
        version=version,
        source_sha=source_sha,
        housekeeping_sha=housekeeping_sha,
        image_digest=image_digest,
        dar_backup_version=required_string(record, "dar_backup_version"),
        dar_version=required_string(record, "dar_version"),
        rekor_url=rekor_url,
        sbom_file=sbom_file,
        sarif_file=sarif_file,
    )


def main() -> int:
    """Validate one release and emit its finalization metadata as JSON.

    Returns:
        Zero on success, otherwise two.
    """
    arguments = parse_args()
    try:
        selection = select_finalization(
            arguments.history,
            arguments.repository,
            arguments.version,
            arguments.dockerhub_repository,
            arguments.github_repository,
        )
    except (OSError, ValueError) as error:
        LOGGER.error("ERROR: %s", error)
        return 2

    json.dump(asdict(selection), sys.stdout, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
