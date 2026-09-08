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

"""Build and append cross-filesystem test records to a JSONL history."""

from __future__ import annotations

import fcntl
import json
import logging
import os
from pathlib import Path
import re
from typing import Any, Mapping, Sequence


LOGGER = logging.getLogger(__name__)
SCHEMA_VERSION = 1
VALID_STATUSES = {"passed", "failed", "skipped", "not_run"}
VALID_OUTCOMES = {"success", "permission_denied", "failure", "not_run"}
DATASET_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
SCENARIOS = (("etc_to_home", "ETC"), ("home_to_data", "HOME"))
CHECK_NAMES = (
    "manager_database",
    "backup",
    "dar_integrity",
    "par2_files",
    "par2_verify",
    "source_stability",
    "restore_execution",
    "content",
    "metadata",
    "overall",
)


def _required(environment: Mapping[str, str], key: str) -> str:
    """Return a required environment value.

    Args:
        environment: Source environment mapping.
        key: Required variable name.

    Returns:
        Non-empty variable value.

    Raises:
        ValueError: If the variable is absent or empty.
    """
    value = environment.get(key, "")
    if not value:
        raise ValueError(f"Required result value {key!r} is missing or empty")
    return value


def _required_int(environment: Mapping[str, str], key: str) -> int:
    """Return a required integer environment value.

    Args:
        environment: Source environment mapping.
        key: Required variable name.

    Returns:
        Parsed integer.

    Raises:
        ValueError: If the value is absent or is not an integer.
    """
    value = _required(environment, key)
    try:
        return int(value)
    except ValueError as error:
        raise ValueError(f"Result value {key!r} must be an integer") from error


def _optional_int(environment: Mapping[str, str], key: str) -> int | None:
    """Return an optional integer environment value.

    Args:
        environment: Source environment mapping.
        key: Optional variable name.

    Returns:
        Parsed integer or ``None``.

    Raises:
        ValueError: If a non-empty value is not an integer.
    """
    value = environment.get(key, "")
    if not value:
        return None
    try:
        return int(value)
    except ValueError as error:
        raise ValueError(f"Result value {key!r} must be an integer") from error


def _optional_float(environment: Mapping[str, str], key: str) -> float | None:
    """Return an optional floating-point environment value.

    Args:
        environment: Source environment mapping.
        key: Optional variable name.

    Returns:
        Parsed float or ``None``.

    Raises:
        ValueError: If a non-empty value is not numeric.
    """
    value = environment.get(key, "")
    if not value:
        return None
    try:
        return float(value)
    except ValueError as error:
        raise ValueError(f"Result value {key!r} must be numeric") from error


def _required_bool(environment: Mapping[str, str], key: str) -> bool:
    """Return a required boolean encoded as zero or one.

    Args:
        environment: Source environment mapping.
        key: Required variable name.

    Returns:
        Parsed boolean.

    Raises:
        ValueError: If the value is not ``0`` or ``1``.
    """
    value = _required(environment, key)
    if value == "1":
        return True
    if value == "0":
        return False
    raise ValueError(f"Result value {key!r} must be '0' or '1'")


def _optional_string(environment: Mapping[str, str], key: str) -> str | None:
    """Return an optional non-empty string.

    Args:
        environment: Source environment mapping.
        key: Optional variable name.

    Returns:
        String value or ``None``.
    """
    return environment.get(key, "") or None


def _status(environment: Mapping[str, str], key: str) -> str:
    """Read and validate one lifecycle status.

    Args:
        environment: Source environment mapping.
        key: Required status variable.

    Returns:
        Validated status.

    Raises:
        ValueError: If the status is unknown.
    """
    value = _required(environment, key)
    if value not in VALID_STATUSES:
        raise ValueError(f"Result value {key!r} has invalid status {value!r}")
    return value


def _outcome(environment: Mapping[str, str], key: str) -> str:
    """Read and validate one backup outcome.

    Args:
        environment: Source environment mapping.
        key: Required outcome variable.

    Returns:
        Validated outcome.

    Raises:
        ValueError: If the outcome is unknown.
    """
    value = _required(environment, key)
    if value not in VALID_OUTCOMES:
        raise ValueError(f"Result value {key!r} has invalid outcome {value!r}")
    return value


def _filesystem(environment: Mapping[str, str], prefix: str) -> dict[str, Any] | None:
    """Build one optional filesystem identity.

    Args:
        environment: Source environment mapping.
        prefix: Variable prefix ending before ``_FSTYPE``.

    Returns:
        Filesystem type and device, or ``None`` when not measured.
    """
    filesystem_type = environment.get(f"{prefix}_FSTYPE", "")
    device = _optional_int(environment, f"{prefix}_DEVICE")
    if not filesystem_type and device is None:
        return None
    return {"type": filesystem_type or None, "device": device}


def _scenario(environment: Mapping[str, str], prefix: str) -> dict[str, Any]:
    """Build one nested scenario result.

    Args:
        environment: Source environment mapping.
        prefix: Scenario environment prefix.

    Returns:
        JSON-serializable scenario record.

    Raises:
        ValueError: If required state is missing or invalid.
    """
    checks = {
        name: _status(environment, f"CFT_{prefix}_CHECK_{name.upper()}")
        for name in CHECK_NAMES
    }
    return {
        "status": _status(environment, f"CFT_{prefix}_STATUS"),
        "expected_backup_outcome": _outcome(
            environment, f"CFT_{prefix}_EXPECTED_OUTCOME"
        ),
        "observed_backup_outcome": _outcome(
            environment, f"CFT_{prefix}_OBSERVED_OUTCOME"
        ),
        "failure_reason": _optional_string(
            environment, f"CFT_{prefix}_FAILURE_REASON"
        ),
        "selection": {
            "count": _required_int(environment, f"CFT_{prefix}_SELECTION_COUNT"),
            "definition_sha256": _optional_string(
                environment, f"CFT_{prefix}_DEFINITION_SHA256"
            ),
        },
        "source": {
            "entry_count": _optional_int(environment, f"CFT_{prefix}_SOURCE_ENTRIES"),
            "file_count": _optional_int(environment, f"CFT_{prefix}_SOURCE_FILES"),
            "bytes": _optional_int(environment, f"CFT_{prefix}_SOURCE_BYTES"),
            "filesystem": _filesystem(environment, f"CFT_{prefix}_SOURCE"),
        },
        "archive": {
            "bytes": _optional_int(environment, f"CFT_{prefix}_ARCHIVE_BYTES"),
            "slice_count": _optional_int(
                environment, f"CFT_{prefix}_ARCHIVE_SLICES"
            ),
            "filesystem": _filesystem(environment, f"CFT_{prefix}_ARCHIVE"),
        },
        "restore": {
            "filesystem": _filesystem(environment, f"CFT_{prefix}_RESTORE"),
            "entry_count": _optional_int(environment, f"CFT_{prefix}_RESTORE_ENTRIES"),
            "file_count": _optional_int(environment, f"CFT_{prefix}_RESTORE_FILES"),
            "bytes": _optional_int(environment, f"CFT_{prefix}_RESTORE_BYTES"),
            "xattr_count": _optional_int(environment, f"CFT_{prefix}_RESTORE_XATTRS"),
            "hard_link_group_count": _optional_int(
                environment, f"CFT_{prefix}_RESTORE_HARD_LINK_GROUPS"
            ),
        },
        "elapsed_seconds": {
            "backup": _optional_float(environment, f"CFT_{prefix}_BACKUP_SECONDS"),
            "verification": _optional_float(
                environment, f"CFT_{prefix}_VERIFY_SECONDS"
            ),
            "restore": _optional_float(environment, f"CFT_{prefix}_RESTORE_SECONDS"),
            "total": _optional_float(environment, f"CFT_{prefix}_TOTAL_SECONDS"),
        },
        "checks": checks,
    }


def build_record(environment: Mapping[str, str]) -> dict[str, Any]:
    """Build and validate one cross-filesystem result record.

    Args:
        environment: Harness result variables.

    Returns:
        JSON-serializable schema-v1 record.

    Raises:
        ValueError: If required state is missing or inconsistent.
    """
    if environment is None:
        raise ValueError("environment must not be None")
    dataset_id = _optional_string(environment, "CFT_DATASET_ID")
    if dataset_id is not None and DATASET_ID_PATTERN.fullmatch(dataset_id) is None:
        raise ValueError("CFT_DATASET_ID has an invalid format")
    scenarios = {
        name: _scenario(environment, prefix) for name, prefix in SCENARIOS
    }
    passed = _required_bool(environment, "CFT_PASSED")
    completed = _required_bool(environment, "CFT_COMPLETED")
    if passed and not completed:
        raise ValueError("a passed record must be completed")
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": _required(environment, "CFT_RUN_ID"),
        "started_at": _required(environment, "CFT_STARTED_AT"),
        "finished_at": _required(environment, "CFT_FINISHED_AT"),
        "completed": completed,
        "aborted_phase": _optional_string(environment, "CFT_ABORTED_PHASE"),
        "exit_code": _required_int(environment, "CFT_EXIT_CODE"),
        "passed": passed,
        "requested_scenario": _required(environment, "CFT_REQUESTED_SCENARIO"),
        "backup_identity": {
            "name": _required(environment, "CFT_BACKUP_USER"),
            "uid": _required_int(environment, "CFT_BACKUP_UID"),
            "gid": _required_int(environment, "CFT_BACKUP_GID"),
        },
        "dataset_id": dataset_id,
        "configuration": {
            "image": _required(environment, "CFT_IMAGE_REFERENCE"),
            "slice_size": _required(environment, "CFT_SLICE_SIZE"),
            "par2_ratio": _required_int(environment, "CFT_PAR2_RATIO"),
            "timeout_seconds": _required_int(environment, "CFT_TIMEOUT"),
            "keep_artifacts": _required_bool(environment, "CFT_KEEP"),
        },
        "elapsed_seconds": _optional_float(environment, "CFT_ELAPSED_SECONDS"),
        "harness": {
            "script_version": _required_int(environment, "CFT_SCRIPT_VERSION"),
            "git_commit": _required(environment, "CFT_GIT_COMMIT"),
            "git_dirty": _required_bool(environment, "CFT_GIT_DIRTY"),
        },
        "image": {
            "reference": _required(environment, "CFT_IMAGE_REFERENCE"),
            "id": _required(environment, "CFT_IMAGE_ID"),
            "repo_digest": _optional_string(environment, "CFT_IMAGE_REPO_DIGEST"),
            "revision": _optional_string(environment, "CFT_IMAGE_REVISION"),
            "version": _optional_string(environment, "CFT_IMAGE_VERSION"),
        },
        "scenarios": scenarios,
    }


def append_record(path: Path, record: Mapping[str, Any]) -> None:
    """Append one locked, durable JSON line.

    Args:
        path: Persistent JSONL destination.
        record: JSON-serializable object.

    Returns:
        None.

    Raises:
        OSError: If the destination cannot be written or synchronized.
        TypeError: If the record is not serializable.
        ValueError: If an argument is missing.
    """
    if path is None:
        raise ValueError("path must not be None")
    if record is None:
        raise ValueError("record must not be None")
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(record, separators=(",", ":"), ensure_ascii=False) + "\n"
    with path.open("a", encoding="utf-8") as output_file:
        fcntl.flock(output_file.fileno(), fcntl.LOCK_EX)
        try:
            output_file.write(encoded)
            output_file.flush()
            os.fsync(output_file.fileno())
        finally:
            fcntl.flock(output_file.fileno(), fcntl.LOCK_UN)


def main(argv: Sequence[str] | None = None) -> int:
    """Build a record from the environment and append it to JSONL.

    Args:
        argv: Optional argument vector containing the destination path.

    Returns:
        Zero after a successful durable append.

    Raises:
        OSError: If the result cannot be written.
        TypeError: If the result cannot be serialized.
        ValueError: If result state is invalid.
    """
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    append_record(args.output, build_record(os.environ))
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
    try:
        raise SystemExit(main())
    except (OSError, TypeError, ValueError) as error:
        LOGGER.error("Unable to write cross-filesystem result: %s", error)
        raise SystemExit(1) from error
