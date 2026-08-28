#!/usr/bin/env python3
"""Build and append structured results for the large-scale test harness."""

from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
import re
import shlex
from typing import Any, Mapping, Sequence


LOGGER = logging.getLogger(__name__)
VALID_STATUSES = {"passed", "failed", "skipped", "not_run"}
VALID_FULL_RESTORE_MODES = {"auto", "forced", "disabled"}
VALID_RESTORE_METADATA_PROFILES = {"portable-posix-v1"}
VALID_RESTORE_FILESYSTEMS = {"ext4", "btrfs", "zfs"}
VALID_FULL_RESTORE_REASONS = {
    "not_evaluated",
    "source_within_threshold",
    "source_exceeds_threshold",
    "forced_by_user",
    "disabled_by_user",
}
TREND_WINDOW = 5
REGRESSION_FACTOR = 1.5
ADVERTISE_MIN_SOURCE_BYTES = 100 * 1024**3
PHASE_NAME_PATTERN = re.compile(r"^[a-z0-9_]+$")
DATASET_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
BACKUP_KINDS = ("full", "diff", "incr")
COARSE_SAMPLE_INTERVAL_SECONDS = 5


def _required(environment: Mapping[str, str], key: str) -> str:
    """Return a required, non-empty environment value.

    Args:
        environment: Environment values supplied by the test harness.
        key: Name of the required value.

    Returns:
        The validated environment value.

    Raises:
        ValueError: If the value is absent or empty.
    """
    value = environment.get(key, "")
    if not value:
        raise ValueError(f"Required result value {key!r} is missing or empty")
    return value


def _required_int(environment: Mapping[str, str], key: str) -> int:
    """Return a required environment value parsed as an integer.

    Args:
        environment: Environment values supplied by the test harness.
        key: Name of the required integer value.

    Returns:
        The parsed integer.

    Raises:
        ValueError: If the value is absent, empty, or not an integer.
    """
    value = _required(environment, key)
    try:
        return int(value)
    except ValueError as error:
        raise ValueError(f"Result value {key!r} must be an integer, got {value!r}") from error


def _optional_int(environment: Mapping[str, str], key: str) -> int | None:
    """Return an optional environment value parsed as an integer.

    Args:
        environment: Environment values supplied by the test harness.
        key: Name of the optional integer value.

    Returns:
        The parsed integer, or ``None`` when the value is empty.

    Raises:
        ValueError: If a non-empty value is not an integer.
    """
    value = environment.get(key, "")
    if not value:
        return None
    try:
        return int(value)
    except ValueError as error:
        raise ValueError(f"Result value {key!r} must be an integer, got {value!r}") from error


def _optional_float(environment: Mapping[str, str], key: str) -> float | None:
    """Return an optional environment value parsed as a float.

    Args:
        environment: Environment values supplied by the test harness.
        key: Name of the optional floating-point value.

    Returns:
        The parsed float, or ``None`` when the value is empty or ``N/A``.

    Raises:
        ValueError: If a non-empty value is not numeric.
    """
    value = environment.get(key, "")
    if not value or value == "N/A":
        return None
    try:
        return float(value)
    except ValueError as error:
        raise ValueError(f"Result value {key!r} must be numeric, got {value!r}") from error


def _required_bool(environment: Mapping[str, str], key: str) -> bool:
    """Return a required environment value parsed as a boolean.

    Args:
        environment: Environment values supplied by the test harness.
        key: Name of the required boolean value.

    Returns:
        The parsed boolean.

    Raises:
        ValueError: If the value is not ``0`` or ``1``.
    """
    value = _required(environment, key)
    if value == "1":
        return True
    if value == "0":
        return False
    raise ValueError(f"Result value {key!r} must be '0' or '1', got {value!r}")


def _optional_string(environment: Mapping[str, str], key: str) -> str | None:
    """Return a non-empty optional environment value.

    Args:
        environment: Environment values supplied by the test harness.
        key: Name of the optional value.

    Returns:
        The value, or ``None`` when it is empty.
    """
    value = environment.get(key, "")
    return value or None


def _optional_json_object(
    environment: Mapping[str, str], key: str
) -> dict[str, Any] | None:
    """Load an optional JSON object from a path supplied in the environment.

    Args:
        environment: Environment values supplied by the test harness.
        key: Name of the environment value containing the JSON file path.

    Returns:
        The decoded object, or ``None`` when no path or file is available.

    Raises:
        OSError: If an existing evidence file cannot be read.
        ValueError: If existing evidence is malformed or not an object.
    """
    value = environment.get(key, "")
    if not value:
        return None
    path = Path(value)
    if not path.exists():
        return None
    try:
        decoded = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"Malformed JSON evidence in {path}: {error}") from error
    if not isinstance(decoded, dict):
        raise ValueError(f"JSON evidence in {path} must be an object")
    return decoded


def _read_phase_durations(environment: Mapping[str, str]) -> dict[str, float]:
    """Read completed major-phase durations from the harness journal.

    Args:
        environment: Environment values supplied by the test harness.

    Returns:
        Phase names mapped to elapsed seconds with millisecond precision.

    Raises:
        OSError: If an existing journal cannot be read.
        ValueError: If journal evidence is malformed or internally inconsistent.
    """
    value = environment.get("LST_PHASE_JOURNAL_FILE", "")
    if not value:
        return {}
    path = Path(value)
    if not path.exists():
        return {}

    starts: dict[str, int] = {}
    durations: dict[str, float] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        parts = line.split("\t")
        if len(parts) != 3:
            raise ValueError(f"Malformed phase journal line {line_number} in {path}")
        event, phase, timestamp_value = parts
        if event not in {"start", "end"} or not PHASE_NAME_PATTERN.fullmatch(phase):
            raise ValueError(f"Invalid phase journal line {line_number} in {path}")
        try:
            timestamp_ns = int(timestamp_value)
        except ValueError as error:
            raise ValueError(
                f"Invalid phase timestamp on line {line_number} in {path}"
            ) from error
        if timestamp_ns <= 0:
            raise ValueError(f"Phase timestamp must be positive on line {line_number}")
        if event == "start":
            if phase in starts or phase in durations:
                raise ValueError(f"Duplicate phase start for {phase!r} in {path}")
            starts[phase] = timestamp_ns
            continue
        started_ns = starts.pop(phase, None)
        if started_ns is None or timestamp_ns < started_ns:
            raise ValueError(f"Unmatched phase end for {phase!r} in {path}")
        durations[phase] = round((timestamp_ns - started_ns) / 1_000_000_000, 3)
    if starts:
        unfinished = ", ".join(sorted(starts))
        raise ValueError(f"Phase journal contains unfinished phase(s): {unfinished}")
    return durations


def _read_resource_summary(
    environment: Mapping[str, str],
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Summarize coarse named-process RSS samples by major harness phase.

    Args:
        environment: Environment values supplied by the test harness.

    Returns:
        Per-phase resource aggregates and run-level telemetry evidence.

    Raises:
        OSError: If an existing resource log cannot be read.
        ValueError: If a recognized resource sample is malformed.
    """
    interval = _required_int(environment, "LST_METRICS_SAMPLE_INTERVAL_SECONDS")
    if interval != COARSE_SAMPLE_INTERVAL_SECONDS:
        raise ValueError(
            "LST_METRICS_SAMPLE_INTERVAL_SECONDS must remain at the coarse "
            f"{COARSE_SAMPLE_INTERVAL_SECONDS}-second dashboard interval"
        )
    value = environment.get("LST_RESOURCE_LOG_FILE", "")
    path = Path(value) if value else None
    phase_resources: dict[str, dict[str, Any]] = {}
    sample_epochs: list[int] = []

    if path is not None and path.exists():
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            tokens: dict[str, str] = {}
            for token in line.split():
                if "=" not in token:
                    continue
                key, token_value = token.split("=", 1)
                tokens[key] = token_value
            phase = tokens.get("phase", "")
            if not phase or not PHASE_NAME_PATTERN.fullmatch(phase):
                continue
            phase_summary = phase_resources.setdefault(
                phase,
                {
                    "sample_count": 0,
                    "peak_named_process_rss_mib": None,
                    "peak_process_rss_mib": {},
                },
            )
            if tokens.get("sample") == "resource":
                try:
                    epoch_ms = int(tokens["epoch_ms"])
                    named_rss_kib = int(tokens["named_process_rss_kib"])
                except (KeyError, ValueError) as error:
                    raise ValueError(
                        f"Malformed resource summary on line {line_number} in {path}"
                    ) from error
                if epoch_ms <= 0 or named_rss_kib <= 0:
                    raise ValueError(
                        f"Resource values must be positive on line {line_number} in {path}"
                    )
                sample_epochs.append(epoch_ms)
                phase_summary["sample_count"] += 1
                peak_mib = round(named_rss_kib / 1024, 1)
                current_peak = phase_summary["peak_named_process_rss_mib"]
                if current_peak is None or peak_mib > current_peak:
                    phase_summary["peak_named_process_rss_mib"] = peak_mib
                continue
            command = tokens.get("cmd", "")
            if command not in {"dar-backup", "dar", "par2", "manager"}:
                continue
            try:
                rss_kib = int(tokens["rss"])
            except (KeyError, ValueError) as error:
                raise ValueError(
                    f"Malformed process RSS sample on line {line_number} in {path}"
                ) from error
            peak_by_process = phase_summary["peak_process_rss_mib"]
            peak_mib = round(rss_kib / 1024, 1)
            previous = peak_by_process.get(command)
            if previous is None or peak_mib > previous:
                peak_by_process[command] = peak_mib

    sample_count = len(sample_epochs)
    telemetry = {
        "resource_monitor_status": "collected" if sample_count else "unavailable",
        "sampling_interval_s": interval,
        "sample_count": sample_count,
        "first_sample_epoch_ms": min(sample_epochs) if sample_epochs else None,
        "last_sample_epoch_ms": max(sample_epochs) if sample_epochs else None,
        "phase_sample_counts": {
            phase: summary["sample_count"]
            for phase, summary in sorted(phase_resources.items())
        },
        "scope": "named process RSS sampled at a coarse interval",
    }
    return phase_resources, telemetry


def _definition_performance_options(environment: Mapping[str, str]) -> dict[str, list[str]]:
    """Extract non-path performance options from the effective definition.

    Args:
        environment: Environment values supplied by the test harness.

    Returns:
        Recognized compression, block-size, and threading option declarations.

    Raises:
        OSError: If an existing effective definition cannot be read.
        ValueError: If the effective definition contains malformed quoting.
    """
    value = environment.get("LST_EFFECTIVE_DEFINITION_FILE", "")
    result = {"compression": [], "compression_block": [], "threading": []}
    if not value:
        return result
    path = Path(value)
    if not path.exists():
        return result
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        try:
            tokens = shlex.split(line, comments=True, posix=True)
        except ValueError as error:
            raise ValueError(
                f"Malformed effective definition line {line_number} in {path}: {error}"
            ) from error
        if not tokens:
            continue
        option = tokens[0]
        declaration = " ".join(tokens)
        if "compression-block" in option:
            result["compression_block"].append(declaration)
        elif "thread" in option:
            result["threading"].append(declaration)
        elif option == "-z" or option.startswith(("-z", "--compression")):
            result["compression"].append(declaration)
    return result


def _artifact_summary(
    environment: Mapping[str, str], kind: str, recorded_bytes: int | None
) -> dict[str, Any]:
    """Summarize archive slices and PAR2 files for one backup kind.

    Args:
        environment: Environment values supplied by the test harness.
        kind: Lowercase backup kind: full, diff, or incr.
        recorded_bytes: Existing exact archive-byte measurement.

    Returns:
        Dashboard-scale archive and redundancy artifact evidence.

    Raises:
        ValueError: If the backup kind is unsupported.
        OSError: If a matching artifact cannot be inspected.
    """
    if kind not in BACKUP_KINDS:
        raise ValueError(f"Unsupported artifact kind: {kind!r}")
    definition_name = environment.get("LST_DEFINITION_NAME", "")
    backup_value = environment.get("LST_BACKUP_DIR", "")
    par2_value = environment.get("LST_PAR2_DIR", "")
    archive_sizes: list[int] = []
    par2_sizes: list[int] = []
    prefix = f"{definition_name}_{kind.upper()}_"
    if definition_name and backup_value and Path(backup_value).is_dir():
        archive_sizes = [
            path.stat().st_size
            for path in Path(backup_value).glob(f"{prefix}*.dar")
            if path.is_file()
        ]
    if definition_name and par2_value and Path(par2_value).is_dir():
        par2_sizes = [
            path.stat().st_size
            for path in Path(par2_value).glob(f"{prefix}*.par2")
            if path.is_file()
        ]
    return {
        "archive_bytes": recorded_bytes,
        "slice_count": len(archive_sizes) if archive_sizes else None,
        "smallest_slice_bytes": min(archive_sizes) if archive_sizes else None,
        "largest_slice_bytes": max(archive_sizes) if archive_sizes else None,
        "par2_file_count": len(par2_sizes) if par2_sizes else None,
        "par2_bytes": sum(par2_sizes) if par2_sizes else None,
    }


def _aggregate_status(statuses: Sequence[str]) -> str:
    """Collapse related check statuses into one major-phase status.

    Args:
        statuses: Valid check statuses contributing to a phase.

    Returns:
        Failed, not_run, passed, or skipped using conservative precedence.

    Raises:
        ValueError: If no statuses are supplied or a status is invalid.
    """
    if not statuses:
        raise ValueError("statuses must not be empty")
    invalid = set(statuses) - VALID_STATUSES
    if invalid:
        raise ValueError(f"Invalid aggregate status values: {sorted(invalid)}")
    if "failed" in statuses:
        return "failed"
    if "not_run" in statuses:
        return "not_run"
    if "passed" in statuses:
        return "passed"
    if "skipped" in statuses:
        return "skipped"
    raise ValueError("Unable to aggregate statuses")


def _status(environment: Mapping[str, str], key: str) -> str:
    """Return and validate a check status.

    Args:
        environment: Environment values supplied by the test harness.
        key: Name of the status value.

    Returns:
        A validated status string.

    Raises:
        ValueError: If the status is not one of the supported values.
    """
    value = _required(environment, key)
    if value not in VALID_STATUSES:
        allowed = ", ".join(sorted(VALID_STATUSES))
        raise ValueError(f"Result value {key!r} must be one of {allowed}, got {value!r}")
    return value


def _choice(
    environment: Mapping[str, str], key: str, allowed_values: set[str]
) -> str:
    """Return and validate a required value from a finite vocabulary.

    Args:
        environment: Environment values supplied by the test harness.
        key: Name of the required value.
        allowed_values: Accepted exact string values.

    Returns:
        The validated value.

    Raises:
        ValueError: If the value is absent or outside the allowed vocabulary.
    """
    if not allowed_values:
        raise ValueError("allowed_values must not be empty")
    value = _required(environment, key)
    if value not in allowed_values:
        allowed = ", ".join(sorted(allowed_values))
        raise ValueError(f"Result value {key!r} must be one of {allowed}, got {value!r}")
    return value


def build_record(environment: Mapping[str, str]) -> dict[str, Any]:
    """Build one schema-v10 result record with legacy history compatibility.

    Args:
        environment: Environment values exported by ``large_scale_test.sh``.

    Returns:
        A validated JSON-serializable result record.

    Raises:
        ValueError: If a required value is missing or invalid.
    """
    if environment is None:
        raise ValueError("environment must not be None")

    completed = _required_bool(environment, "LST_COMPLETED")
    failures = _required_int(environment, "LST_FAILURES")
    exit_code = _required_int(environment, "LST_EXIT_CODE")
    advertise_requested = _required_bool(environment, "LST_ADVERTISE_REQUESTED")
    source_bytes = _optional_int(environment, "LST_SOURCE_BYTES")
    pitr_execution = _status(environment, "LST_PITR_EXECUTION_STATUS")
    pitr_structure = _status(environment, "LST_PITR_STRUCTURE_STATUS")
    pitr_checksums = _status(environment, "LST_PITR_CHECKSUM_STATUS")
    pitr_permissions = _status(environment, "LST_PITR_PERMISSION_STATUS")
    pitr_overall = _status(environment, "LST_PITR_OVERALL_STATUS")
    full_restore_mode = _choice(
        environment, "LST_FULL_RESTORE_MODE", VALID_FULL_RESTORE_MODES
    )
    full_restore_threshold_bytes = _required_int(
        environment, "LST_FULL_RESTORE_THRESHOLD_BYTES"
    )
    full_restore_performed = _required_bool(
        environment, "LST_FULL_RESTORE_PERFORMED"
    )
    full_restore_reason = _choice(
        environment, "LST_FULL_RESTORE_DECISION_REASON", VALID_FULL_RESTORE_REASONS
    )
    full_restore_execution = _status(
        environment, "LST_FULL_RESTORE_EXECUTION_STATUS"
    )
    full_restore_content = _status(environment, "LST_FULL_RESTORE_CONTENT_STATUS")
    full_restore_metadata = _status(environment, "LST_FULL_RESTORE_METADATA_STATUS")
    full_restore_overall = _status(environment, "LST_FULL_RESTORE_OVERALL_STATUS")
    full_restore_file_count = _optional_int(
        environment, "LST_FULL_RESTORE_FILE_COUNT"
    )
    full_restore_bytes = _optional_int(environment, "LST_FULL_RESTORE_BYTES")
    full_restore_entry_count = _optional_int(
        environment, "LST_FULL_RESTORE_ENTRY_COUNT"
    )
    full_restore_ownership_count = _optional_int(
        environment, "LST_FULL_RESTORE_OWNERSHIP_COUNT"
    )
    full_restore_permission_count = _optional_int(
        environment, "LST_FULL_RESTORE_PERMISSION_COUNT"
    )
    full_restore_posix_acl_count = _optional_int(
        environment, "LST_FULL_RESTORE_POSIX_ACL_COUNT"
    )
    full_restore_xattr_count = _optional_int(
        environment, "LST_FULL_RESTORE_XATTR_COUNT"
    )
    full_restore_hard_link_group_count = _optional_int(
        environment, "LST_FULL_RESTORE_HARD_LINK_GROUP_COUNT"
    )
    restore_metadata_profile = _choice(
        environment,
        "LST_RESTORE_METADATA_PROFILE",
        VALID_RESTORE_METADATA_PROFILES,
    )
    source_filesystem_type = _choice(
        environment, "LST_SOURCE_FILESYSTEM_TYPE", VALID_RESTORE_FILESYSTEMS
    )
    restore_filesystem_type = _choice(
        environment, "LST_RESTORE_FILESYSTEM_TYPE", VALID_RESTORE_FILESYSTEMS
    )
    source_filesystem_device = _required_int(
        environment, "LST_SOURCE_FILESYSTEM_DEVICE"
    )
    restore_filesystem_device = _required_int(
        environment, "LST_RESTORE_FILESYSTEM_DEVICE"
    )
    if full_restore_threshold_bytes <= 0:
        raise ValueError("LST_FULL_RESTORE_THRESHOLD_BYTES must be positive")
    valid_reasons_by_mode = {
        "auto": {"not_evaluated", "source_within_threshold", "source_exceeds_threshold"},
        "forced": {"not_evaluated", "forced_by_user"},
        "disabled": {"disabled_by_user"},
    }
    if full_restore_reason not in valid_reasons_by_mode[full_restore_mode]:
        raise ValueError(
            f"Full restore mode {full_restore_mode!r} is inconsistent with "
            f"decision {full_restore_reason!r}"
        )
    if not full_restore_performed and full_restore_overall == "passed":
        raise ValueError("A full restore cannot pass when it was not performed")
    if full_restore_performed and full_restore_overall == "skipped":
        raise ValueError("A performed full restore cannot have skipped overall status")
    if full_restore_performed and full_restore_reason in {
        "source_exceeds_threshold",
        "disabled_by_user",
        "not_evaluated",
    }:
        raise ValueError(
            f"Full restore decision {full_restore_reason!r} cannot be performed"
        )
    if source_filesystem_device < 0 or restore_filesystem_device < 0:
        raise ValueError("Filesystem device numbers must not be negative")
    if source_filesystem_device != restore_filesystem_device:
        raise ValueError(
            "Source and restore directories must be on the same filesystem device"
        )
    if source_filesystem_type != restore_filesystem_type:
        raise ValueError(
            "Source and restore filesystem types must match for same-filesystem evidence"
        )
    if full_restore_overall == "passed" and any(
        status != "passed"
        for status in (
            full_restore_execution,
            full_restore_content,
            full_restore_metadata,
        )
    ):
        raise ValueError(
            "A passed full restore requires passed execution, content comparison, "
            "and portable metadata comparison"
        )
    full_restore_counts = {
        "LST_FULL_RESTORE_FILE_COUNT": full_restore_file_count,
        "LST_FULL_RESTORE_BYTES": full_restore_bytes,
        "LST_FULL_RESTORE_ENTRY_COUNT": full_restore_entry_count,
        "LST_FULL_RESTORE_OWNERSHIP_COUNT": full_restore_ownership_count,
        "LST_FULL_RESTORE_PERMISSION_COUNT": full_restore_permission_count,
        "LST_FULL_RESTORE_POSIX_ACL_COUNT": full_restore_posix_acl_count,
        "LST_FULL_RESTORE_XATTR_COUNT": full_restore_xattr_count,
        "LST_FULL_RESTORE_HARD_LINK_GROUP_COUNT": (
            full_restore_hard_link_group_count
        ),
    }
    for key, value in full_restore_counts.items():
        if value is not None and value < 0:
            raise ValueError(f"{key} must not be negative")
    if full_restore_overall == "passed":
        missing_counts = [
            key for key, value in full_restore_counts.items() if value is None
        ]
        if missing_counts:
            raise ValueError(
                "A passed full restore requires all portable metadata counts: "
                + ", ".join(missing_counts)
            )
        if full_restore_entry_count != full_restore_ownership_count:
            raise ValueError(
                "A passed full restore must compare numeric ownership for every entry"
            )
        if (
            full_restore_entry_count is None
            or full_restore_file_count is None
            or full_restore_entry_count < full_restore_file_count
        ):
            raise ValueError(
                "A passed full restore cannot contain more regular files than entries"
            )
        if (
            full_restore_permission_count is None
            or full_restore_permission_count > full_restore_entry_count
        ):
            raise ValueError(
                "A passed full restore cannot compare more permission modes than entries"
            )
        if full_restore_posix_acl_count is None or full_restore_posix_acl_count < 2:
            raise ValueError(
                "A passed full restore requires both access and default POSIX ACL fixtures"
            )
        if full_restore_xattr_count is None or full_restore_xattr_count < 3:
            raise ValueError(
                "A passed full restore requires all portable extended-attribute fixtures"
            )
        if (
            full_restore_hard_link_group_count is None
            or full_restore_hard_link_group_count < 1
        ):
            raise ValueError(
                "A passed full restore requires a verified hard-link fixture group"
            )
    if pitr_overall == "passed" and any(
        status != "passed"
        for status in (
            pitr_execution,
            pitr_structure,
            pitr_checksums,
            pitr_permissions,
        )
    ):
        raise ValueError(
            "A passed PITR restore requires passed execution, structure, "
            "content checksums, and permission modes"
        )
    aborted_phase = None if completed else _required(environment, "LST_CURRENT_PHASE")
    passed = completed and exit_code == 0 and failures == 0
    advertise = (
        advertise_requested
        and passed
        and source_bytes is not None
        and source_bytes >= ADVERTISE_MIN_SOURCE_BYTES
    )

    source_file_count = _optional_int(environment, "LST_SOURCE_FILE_COUNT")
    full_size_bytes = _optional_int(environment, "LST_FULL_BYTES")
    diff_size_bytes = _optional_int(environment, "LST_DIFF_BYTES")
    incr_size_bytes = _optional_int(environment, "LST_INCR_BYTES")
    overall_elapsed_s = _required_int(environment, "LST_OVERALL_ELAPSED")
    slice_size_bytes = _required_int(environment, "LST_SLICE_SIZE_BYTES")
    par2_ratio = _required_int(environment, "LST_PAR2_RATIO")
    command_timeout_s = _required_int(environment, "LST_COMMAND_TIMEOUT_SECONDS")
    min_free_multiplier = _required_int(environment, "LST_MIN_FREE_MULTIPLIER")
    bitrot_enabled = _required_bool(environment, "LST_BITROT_ENABLED")
    bitrot_percent = _required_int(environment, "LST_BITROT_PERCENT")
    if slice_size_bytes <= 0:
        raise ValueError("LST_SLICE_SIZE_BYTES must be positive")
    if not 1 <= par2_ratio <= 100:
        raise ValueError("LST_PAR2_RATIO must be between 1 and 100")
    if command_timeout_s <= 0 or min_free_multiplier <= 0:
        raise ValueError("Timeout and free-space multiplier must be positive")
    if not 1 <= bitrot_percent <= 100:
        raise ValueError("LST_BITROT_PERCENT must be between 1 and 100")

    backup_statuses = {
        kind: _status(environment, f"LST_{kind.upper()}_BACKUP_STATUS")
        for kind in BACKUP_KINDS
    }
    archive_statuses = {
        kind: _status(environment, f"LST_{kind.upper()}_ARCHIVE_STATUS")
        for kind in BACKUP_KINDS
    }
    par2_file_statuses = {
        kind: _status(environment, f"LST_{kind.upper()}_PAR2_FILES_STATUS")
        for kind in BACKUP_KINDS
    }
    par2_verify_statuses = {
        kind: _status(environment, f"LST_{kind.upper()}_PAR2_VERIFY_STATUS")
        for kind in BACKUP_KINDS
    }
    bitrot_statuses = {
        kind: _status(environment, f"LST_{kind.upper()}_BITROT_STATUS")
        for kind in BACKUP_KINDS
    }
    checks = {
        "manager_database": _status(environment, "LST_MANAGER_DB_STATUS"),
        "backup": backup_statuses,
        "archive_integrity": archive_statuses,
        "par2_files": par2_file_statuses,
        "par2_verify": par2_verify_statuses,
        "bitrot_repair": bitrot_statuses,
        "delta_contents": {
            "diff": _status(environment, "LST_DIFF_CONTENTS_STATUS"),
            "incr": _status(environment, "LST_INCR_CONTENTS_STATUS"),
        },
        "pitr_restore": {
            "execution": pitr_execution,
            "structure": pitr_structure,
            "content_checksums": pitr_checksums,
            "permission_modes": pitr_permissions,
            "overall": pitr_overall,
        },
        "full_restore": {
            "mode": full_restore_mode,
            "threshold_bytes": full_restore_threshold_bytes,
            "source_bytes": source_bytes,
            "performed": full_restore_performed,
            "decision_reason": full_restore_reason,
            "execution": full_restore_execution,
            "content_comparison": full_restore_content,
            "portable_metadata": full_restore_metadata,
            "overall": full_restore_overall,
            "restored_file_count": full_restore_file_count,
            "restored_bytes": full_restore_bytes,
            "restored_entry_count": full_restore_entry_count,
            "ownership_entry_count": full_restore_ownership_count,
            "permission_entry_count": full_restore_permission_count,
            "posix_acl_count": full_restore_posix_acl_count,
            "portable_xattr_count": full_restore_xattr_count,
            "hard_link_group_count": full_restore_hard_link_group_count,
            "metadata_profile": restore_metadata_profile,
            "source_filesystem": source_filesystem_type,
            "restore_filesystem": restore_filesystem_type,
            "source_filesystem_device": source_filesystem_device,
            "restore_filesystem_device": restore_filesystem_device,
            "same_filesystem": True,
        },
    }

    workload_values = {
        "allocated_bytes": _optional_int(environment, "LST_SOURCE_ALLOCATED_BYTES"),
        "directory_count": _optional_int(environment, "LST_SOURCE_DIRECTORY_COUNT"),
        "symlink_count": _optional_int(environment, "LST_SOURCE_SYMLINK_COUNT"),
        "other_entry_count": _optional_int(
            environment, "LST_SOURCE_OTHER_ENTRY_COUNT"
        ),
        "hard_link_group_count": _optional_int(
            environment, "LST_SOURCE_HARD_LINK_GROUP_COUNT"
        ),
        "zero_file_count": _optional_int(environment, "LST_SOURCE_ZERO_FILE_COUNT"),
        "small_file_count": _optional_int(environment, "LST_SOURCE_SMALL_FILE_COUNT"),
        "medium_file_count": _optional_int(
            environment, "LST_SOURCE_MEDIUM_FILE_COUNT"
        ),
        "large_file_count": _optional_int(environment, "LST_SOURCE_LARGE_FILE_COUNT"),
        "max_file_bytes": _optional_int(environment, "LST_SOURCE_MAX_FILE_BYTES"),
    }
    mutation_values = {
        kind: {
            "modified_file_count": _optional_int(
                environment, f"LST_{kind.upper()}_MODIFIED_FILE_COUNT"
            ),
            "modified_apparent_bytes": _optional_int(
                environment, f"LST_{kind.upper()}_MODIFIED_APPARENT_BYTES"
            ),
            "created_file_count": _optional_int(
                environment, f"LST_{kind.upper()}_CREATED_FILE_COUNT"
            ),
            "created_apparent_bytes": _optional_int(
                environment, f"LST_{kind.upper()}_CREATED_BYTES"
            ),
            "deleted_file_count": _optional_int(
                environment, f"LST_{kind.upper()}_DELETED_FILE_COUNT"
            ),
        }
        for kind in ("diff", "incr")
    }
    numeric_evidence = [
        value for value in workload_values.values() if value is not None
    ] + [
        value
        for mutation in mutation_values.values()
        for value in mutation.values()
        if value is not None
    ]
    if any(value < 0 for value in numeric_evidence):
        raise ValueError("Workload measurements must not be negative")
    file_size_buckets = [
        workload_values["zero_file_count"],
        workload_values["small_file_count"],
        workload_values["medium_file_count"],
        workload_values["large_file_count"],
    ]
    if source_file_count is not None and all(
        value is not None for value in file_size_buckets
    ):
        bucket_total = sum(value for value in file_size_buckets if value is not None)
        if bucket_total != source_file_count:
            raise ValueError(
                "Source file-size buckets must sum to LST_SOURCE_FILE_COUNT"
            )
    entry_components = [
        source_file_count,
        workload_values["directory_count"],
        workload_values["symlink_count"],
        workload_values["other_entry_count"],
    ]
    selected_entry_count = (
        sum(value for value in entry_components if value is not None)
        if all(value is not None for value in entry_components)
        else None
    )
    dataset_id = _optional_string(environment, "LST_DATASET_ID")
    if dataset_id is not None and not DATASET_ID_PATTERN.fullmatch(dataset_id):
        raise ValueError("LST_DATASET_ID contains unsupported characters")
    workload = {
        "dataset_id": dataset_id,
        "source": {
            "regular_file_count": source_file_count,
            "directory_count": workload_values["directory_count"],
            "symlink_count": workload_values["symlink_count"],
            "other_entry_count": workload_values["other_entry_count"],
            "entry_count": selected_entry_count,
            "apparent_bytes": source_bytes,
            "allocated_bytes": workload_values["allocated_bytes"],
            "hard_link_group_count": workload_values["hard_link_group_count"],
            "file_sizes": {
                "zero_bytes": workload_values["zero_file_count"],
                "one_byte_through_1_mib": workload_values["small_file_count"],
                "over_1_mib_through_100_mib": workload_values["medium_file_count"],
                "over_100_mib": workload_values["large_file_count"],
                "maximum_bytes": workload_values["max_file_bytes"],
            },
        },
        "mutations": mutation_values,
    }

    definition_hash = _optional_string(environment, "LST_BACKUP_DEFINITION_SHA256")
    configuration = {
        "slice_size": {
            "display": _required(environment, "LST_SLICE_SIZE"),
            "bytes": slice_size_bytes,
            "source": _choice(
                environment, "LST_SLICE_SIZE_SOURCE", {"definition", "fallback"}
            ),
        },
        "performance_options": _definition_performance_options(environment),
        "par2": {
            "error_correction_percent": par2_ratio,
            "memory_limit_bytes": None,
            "memory_limit_source": "not_configured_by_harness",
        },
        "bitrot": {
            "enabled": bitrot_enabled,
            "mode": _choice(
                environment,
                "LST_BITROT_MODE",
                {"contiguous", "fragmented", "edges"},
            ),
            "corruption_percent": bitrot_percent,
        },
        "command_timeout_s": command_timeout_s,
        "minimum_free_space_multiplier": min_free_multiplier,
        "full_restore_mode": full_restore_mode,
        "full_restore_threshold_bytes": full_restore_threshold_bytes,
        "backup_definition_sha256": definition_hash,
    }

    host_cpu_count = _optional_int(environment, "LST_HOST_LOGICAL_CPU_COUNT")
    host_memory_bytes = _optional_int(environment, "LST_HOST_MEMORY_BYTES")
    disk_free_start = _optional_int(environment, "LST_DISK_FREE_BYTES_START")
    disk_free_end = _optional_int(environment, "LST_DISK_FREE_BYTES_END")
    for key, value in {
        "LST_HOST_LOGICAL_CPU_COUNT": host_cpu_count,
        "LST_HOST_MEMORY_BYTES": host_memory_bytes,
        "LST_DISK_FREE_BYTES_START": disk_free_start,
        "LST_DISK_FREE_BYTES_END": disk_free_end,
    }.items():
        if value is not None and value < 0:
            raise ValueError(f"{key} must not be negative")
    host_profile_material = {
        "os": _required(environment, "LST_OS_DESC"),
        "kernel": _required(environment, "LST_KERNEL"),
        "logical_cpu_count": host_cpu_count,
        "memory_bytes": host_memory_bytes,
        "filesystem": source_filesystem_type,
    }
    host_profile_id = hashlib.sha256(
        json.dumps(host_profile_material, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    environment_record = {
        "host_profile_id": host_profile_id,
        "os_desc": host_profile_material["os"],
        "kernel": host_profile_material["kernel"],
        "logical_cpu_count": host_cpu_count,
        "memory_bytes": host_memory_bytes,
        "container_limits": {
            "configured": False,
            "memory_bytes": None,
            "logical_cpu_count": None,
        },
        "source_filesystem": source_filesystem_type,
        "restore_filesystem": restore_filesystem_type,
        "disk_free_bytes": {"start": disk_free_start, "end": disk_free_end},
        "image": {
            "reference": _required(environment, "LST_IMAGE_REFERENCE"),
            "id": _required(environment, "LST_IMAGE_ID"),
            "repo_digest": _optional_string(environment, "LST_IMAGE_REPO_DIGEST"),
            "revision": _optional_string(environment, "LST_IMAGE_REVISION"),
            "version": _optional_string(environment, "LST_IMAGE_VERSION"),
        },
        "harness": {
            "git_commit": _required(environment, "LST_HARNESS_GIT_COMMIT"),
            "git_dirty": _required_bool(environment, "LST_HARNESS_GIT_DIRTY"),
            "script_version": _required_int(environment, "LST_SCRIPT_VERSION"),
        },
        "tools": {
            "dar_backup": _required(environment, "LST_DAR_BACKUP_VER"),
            "dar": _required(environment, "LST_DAR_VER"),
            "par2": _required(environment, "LST_PAR2_VER"),
            "python": _required(environment, "LST_PYTHON_VER"),
        },
    }

    phase_durations = _read_phase_durations(environment)
    phase_resources, telemetry = _read_resource_summary(environment)
    verification_statuses = {
        kind: _aggregate_status(
            (
                archive_statuses[kind],
                par2_file_statuses[kind],
                par2_verify_statuses[kind],
                bitrot_statuses[kind],
            )
        )
        for kind in BACKUP_KINDS
    }
    phase_statuses = {
        "setup": checks["manager_database"],
        "full_backup": backup_statuses["full"],
        "full_verification": verification_statuses["full"],
        "diff_backup": backup_statuses["diff"],
        "diff_verification": _aggregate_status(
            (verification_statuses["diff"], checks["delta_contents"]["diff"])
        ),
        "incr_backup": backup_statuses["incr"],
        "incr_verification": _aggregate_status(
            (verification_statuses["incr"], checks["delta_contents"]["incr"])
        ),
        "pitr_restore": pitr_overall,
        "full_restore": full_restore_overall,
    }
    legacy_phase_durations: dict[str, float | None] = {
        "full_backup": (
            float(_required_int(environment, "LST_FULL_ELAPSED"))
            if backup_statuses["full"] != "not_run"
            else None
        ),
        "diff_backup": (
            float(_required_int(environment, "LST_DIFF_ELAPSED"))
            if backup_statuses["diff"] != "not_run"
            else None
        ),
        "incr_backup": (
            float(_required_int(environment, "LST_INCR_ELAPSED"))
            if backup_statuses["incr"] != "not_run"
            else None
        ),
    }
    phases: dict[str, Any] = {}
    for phase_name, phase_status in phase_statuses.items():
        resources = phase_resources.get(
            phase_name,
            {
                "sample_count": 0,
                "peak_named_process_rss_mib": None,
                "peak_process_rss_mib": {},
            },
        )
        phases[phase_name] = {
            "status": phase_status,
            "duration_s": phase_durations.get(
                phase_name, legacy_phase_durations.get(phase_name)
            ),
            "resources": resources,
        }
    phases["overall"] = {
        "status": "passed" if passed else "failed",
        "duration_s": float(overall_elapsed_s),
        "resources": {
            "sample_count": telemetry["sample_count"],
            "peak_process_rss_mib": {
                "dar-backup": _optional_float(environment, "LST_DB_MIB"),
                "dar": _optional_float(environment, "LST_DAR_MIB"),
                "par2": _optional_float(environment, "LST_PAR2_MIB"),
                "manager": _optional_float(environment, "LST_MGR_MIB"),
            },
        },
    }
    artifacts = {
        "full": _artifact_summary(environment, "full", full_size_bytes),
        "diff": _artifact_summary(environment, "diff", diff_size_bytes),
        "incr": _artifact_summary(environment, "incr", incr_size_bytes),
    }
    telemetry.update(
        {
            "phase_journal_status": "collected" if phase_durations else "unavailable",
            "structured_result_status": "complete" if completed else "aborted",
            "failure_count": failures,
            "exit_code": exit_code,
            "aborted_phase": aborted_phase,
        }
    )

    return {
        "schema_version": 10,
        "datestamp": _required(environment, "LST_DATESTAMP"),
        "date": _required(environment, "LST_DATE"),
        # Stable publication envelope; all other engineering fields may evolve.
        "advertise": advertise,
        "test_name": _required(environment, "LST_TEST_NAME"),
        "advertise_class": _required(environment, "LST_ADVERTISE_CLASS"),
        # Retained unchanged for schema-v2 consumers.
        "git_commit": _required(environment, "LST_GIT_COMMIT"),
        "dar_backup_version": _required(environment, "LST_DAR_BACKUP_VER"),
        "dar_version": _required(environment, "LST_DAR_VER"),
        "par2_version": _required(environment, "LST_PAR2_VER"),
        "python_version": _required(environment, "LST_PYTHON_VER"),
        "os_desc": _required(environment, "LST_OS_DESC"),
        "kernel": _required(environment, "LST_KERNEL"),
        "full_elapsed_s": _required_int(environment, "LST_FULL_ELAPSED"),
        "full_size_gib": _optional_float(environment, "LST_FULL_GIB"),
        "diff_elapsed_s": _required_int(environment, "LST_DIFF_ELAPSED"),
        "diff_size_gib": _optional_float(environment, "LST_DIFF_GIB"),
        "incr_elapsed_s": _required_int(environment, "LST_INCR_ELAPSED"),
        "incr_size_gib": _optional_float(environment, "LST_INCR_GIB"),
        "memory_mib": {
            "dar_backup": _optional_float(environment, "LST_DB_MIB"),
            "dar": _optional_float(environment, "LST_DAR_MIB"),
            "par2": _optional_float(environment, "LST_PAR2_MIB"),
            "manager": _optional_float(environment, "LST_MGR_MIB"),
        },
        "failures": failures,
        "passed": passed,
        # Schema-v3 provenance and exact measurements.
        "script_version": _required_int(environment, "LST_SCRIPT_VERSION"),
        "harness_git_commit": _required(environment, "LST_HARNESS_GIT_COMMIT"),
        "harness_git_dirty": _required_bool(environment, "LST_HARNESS_GIT_DIRTY"),
        "image_reference": _required(environment, "LST_IMAGE_REFERENCE"),
        "image_id": _required(environment, "LST_IMAGE_ID"),
        "image_repo_digest": _optional_string(environment, "LST_IMAGE_REPO_DIGEST"),
        "image_revision": _optional_string(environment, "LST_IMAGE_REVISION"),
        "image_version": _optional_string(environment, "LST_IMAGE_VERSION"),
        "source_file_count": source_file_count,
        "source_bytes": source_bytes,
        "backup_definition_sha256": definition_hash,
        "full_size_bytes": full_size_bytes,
        "diff_size_bytes": diff_size_bytes,
        "incr_size_bytes": incr_size_bytes,
        "overall_elapsed_s": overall_elapsed_s,
        "completed": completed,
        "aborted_phase": aborted_phase,
        "exit_code": exit_code,
        "configuration": configuration,
        "workload": workload,
        "environment": environment_record,
        "phases": phases,
        "artifacts": artifacts,
        "checks": checks,
        "telemetry": telemetry,
        # Schema-v4 reproducible random corruption and per-slice PAR2 metrics.
        "bitrot_seed": _optional_int(environment, "LST_BITROT_SEED"),
        "bitrot_evidence": _optional_json_object(
            environment, "LST_BITROT_EVIDENCE_FILE"
        ),
    }


def load_history(path: Path) -> list[dict[str, Any]]:
    """Load valid JSON objects from a JSONL history file.

    Args:
        path: JSONL history file to read.

    Returns:
        Valid object records in file order. Malformed lines are logged and skipped.

    Raises:
        OSError: If an existing history file cannot be read.
    """
    if not path.exists():
        return []

    records: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as history_file:
        for line_number, line in enumerate(history_file, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                value = json.loads(stripped)
            except json.JSONDecodeError as error:
                LOGGER.warning(
                    "Skipping malformed JSONL record at %s:%d: %s",
                    path,
                    line_number,
                    error,
                )
                continue
            if not isinstance(value, dict):
                LOGGER.warning(
                    "Skipping non-object JSONL record at %s:%d",
                    path,
                    line_number,
                )
                continue
            records.append(value)
    return records


def _trailing_average(
    records: Sequence[Mapping[str, Any]], key: str, memory_key: str | None = None
) -> float | None:
    """Calculate an average from compatible numeric history values.

    Args:
        records: Historical result records.
        key: Top-level numeric key to average.
        memory_key: Optional key under the current ``memory_mib`` or legacy
            ``memory_mb`` object instead of ``key``.

    Returns:
        The average, or ``None`` when no compatible values exist.
    """
    values: list[float] = []
    for record in records:
        if memory_key is None:
            value = record.get(key)
        else:
            memory = record.get("memory_mib")
            if not isinstance(memory, Mapping):
                memory = record.get("memory_mb", {})
            value = memory.get(memory_key) if isinstance(memory, Mapping) else None
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            values.append(float(value))
    return sum(values) / len(values) if values else None


def regression_warnings(
    record: Mapping[str, Any], history: Sequence[Mapping[str, Any]]
) -> list[str]:
    """Build warnings for large runtime or memory regressions.

    Args:
        record: Current result record.
        history: Previous result records.

    Returns:
        Human-readable warning messages.
    """
    passed_history = [item for item in history if item.get("passed") is True]
    recent = passed_history[-TREND_WINDOW:]
    if not recent:
        return []

    comparisons = [
        (
            "FULL elapsed (s)",
            record.get("full_elapsed_s"),
            _trailing_average(recent, "full_elapsed_s"),
        )
    ]
    current_memory = record.get("memory_mib")
    if not isinstance(current_memory, Mapping):
        current_memory = record.get("memory_mb", {})
    for tool in ("dar_backup", "dar", "par2", "manager"):
        current = (
            current_memory.get(tool) if isinstance(current_memory, Mapping) else None
        )
        comparisons.append(
            (
                f"Peak {tool} memory (MiB)",
                current,
                _trailing_average(recent, "", memory_key=tool),
            )
        )

    warnings: list[str] = []
    for label, current, baseline in comparisons:
        if not isinstance(current, (int, float)) or isinstance(current, bool):
            continue
        if baseline is None or baseline <= 0 or current <= baseline * REGRESSION_FACTOR:
            continue
        warnings.append(
            f"{label} ({current:.1f}) is {current / baseline:.1f}x the trailing "
            f"{len(recent)}-run average ({baseline:.1f}) — worth a look before "
            "tagging a release."
        )
    return warnings


def append_record(path: Path, record: Mapping[str, Any]) -> None:
    """Append one compact JSON object to a JSONL history file.

    Args:
        path: Destination JSONL file.
        record: JSON-serializable result record.

    Raises:
        OSError: If the destination cannot be created or written.
        TypeError: If the record is not JSON serializable.
        ValueError: If a required argument is invalid.
    """
    if path is None:
        raise ValueError("path must not be None")
    if record is None:
        raise ValueError("record must not be None")

    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(record, separators=(",", ":"), ensure_ascii=False)
    with path.open("a", encoding="utf-8") as output_file:
        output_file.write(encoded + "\n")


def write_result(
    record: Mapping[str, Any], results_dir: Path, repo_dir: Path | None
) -> list[str]:
    """Append a result locally and optionally mirror it into the repository.

    Args:
        record: JSON-serializable result record.
        results_dir: Persistent local results directory.
        repo_dir: Repository root for the tracked mirror, or ``None``.

    Returns:
        Regression warnings calculated from the pre-append local history.

    Raises:
        OSError: If a destination cannot be created or written.
        TypeError: If the record is not JSON serializable.
        ValueError: If a required argument is invalid.
    """
    if record is None:
        raise ValueError("record must not be None")
    if results_dir is None:
        raise ValueError("results_dir must not be None")

    results_path = results_dir / "large-scale-results.jsonl"
    history = load_history(results_path)
    warnings = regression_warnings(record, history)
    append_record(results_path, record)

    if repo_dir is not None:
        repo_path = repo_dir / "doc" / "test-report" / "large-scale-results.jsonl"
        if repo_path.parent.is_dir() and repo_path.resolve() != results_path.resolve():
            append_record(repo_path, record)
    return warnings


def main() -> int:
    """Build and persist a result from the current process environment.

    Returns:
        Zero after both result destinations have been handled successfully.

    Raises:
        OSError: If a result destination cannot be read or written.
        TypeError: If the result cannot be serialized.
        ValueError: If required result state is invalid.
    """
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
    record = build_record(os.environ)
    results_dir = Path(_required(os.environ, "LST_RESULTS_DIR"))
    repo_value = os.environ.get("LST_REPO_DIR", "")
    repo_dir = Path(repo_value) if repo_value else None
    for warning in write_result(record, results_dir, repo_dir):
        print(f"WARN  {warning}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
