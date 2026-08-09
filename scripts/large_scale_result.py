#!/usr/bin/env python3
"""Build and append structured results for the large-scale test harness."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Mapping, Sequence


LOGGER = logging.getLogger(__name__)
VALID_STATUSES = {"passed", "failed", "skipped", "not_run"}
TREND_WINDOW = 5
REGRESSION_FACTOR = 1.5


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


def build_record(environment: Mapping[str, str]) -> dict[str, Any]:
    """Build one backward-compatible schema-v4 result record.

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
    aborted_phase = None if completed else _required(environment, "LST_CURRENT_PHASE")

    return {
        "schema_version": 4,
        "datestamp": _required(environment, "LST_DATESTAMP"),
        "date": _required(environment, "LST_DATE"),
        # Retained unchanged for schema-v2 consumers.
        "git_commit": _required(environment, "LST_GIT_COMMIT"),
        "dar_backup_version": _required(environment, "LST_DAR_BACKUP_VER"),
        "dar_version": _required(environment, "LST_DAR_VER"),
        "par2_version": _required(environment, "LST_PAR2_VER"),
        "python_version": _required(environment, "LST_PYTHON_VER"),
        "os_desc": _required(environment, "LST_OS_DESC"),
        "kernel": _required(environment, "LST_KERNEL"),
        "full_elapsed_s": _required_int(environment, "LST_FULL_ELAPSED"),
        "full_size_gb": _optional_float(environment, "LST_FULL_GB"),
        "diff_elapsed_s": _required_int(environment, "LST_DIFF_ELAPSED"),
        "diff_size_gb": _optional_float(environment, "LST_DIFF_GB"),
        "incr_elapsed_s": _required_int(environment, "LST_INCR_ELAPSED"),
        "incr_size_gb": _optional_float(environment, "LST_INCR_GB"),
        "memory_mb": {
            "dar_backup": _optional_float(environment, "LST_DB_MB"),
            "dar": _optional_float(environment, "LST_DAR_MB"),
            "par2": _optional_float(environment, "LST_PAR2_MB"),
            "manager": _optional_float(environment, "LST_MGR_MB"),
        },
        "failures": failures,
        "passed": completed and exit_code == 0 and failures == 0,
        # Schema-v3 provenance and exact measurements.
        "script_version": _required_int(environment, "LST_SCRIPT_VERSION"),
        "harness_git_commit": _required(environment, "LST_HARNESS_GIT_COMMIT"),
        "harness_git_dirty": _required_bool(environment, "LST_HARNESS_GIT_DIRTY"),
        "image_reference": _required(environment, "LST_IMAGE_REFERENCE"),
        "image_id": _required(environment, "LST_IMAGE_ID"),
        "image_repo_digest": _optional_string(environment, "LST_IMAGE_REPO_DIGEST"),
        "image_revision": _optional_string(environment, "LST_IMAGE_REVISION"),
        "image_version": _optional_string(environment, "LST_IMAGE_VERSION"),
        "source_file_count": _optional_int(environment, "LST_SOURCE_FILE_COUNT"),
        "source_bytes": _optional_int(environment, "LST_SOURCE_BYTES"),
        "backup_definition_sha256": _optional_string(
            environment, "LST_BACKUP_DEFINITION_SHA256"
        ),
        "full_size_bytes": _optional_int(environment, "LST_FULL_BYTES"),
        "diff_size_bytes": _optional_int(environment, "LST_DIFF_BYTES"),
        "incr_size_bytes": _optional_int(environment, "LST_INCR_BYTES"),
        "overall_elapsed_s": _required_int(environment, "LST_OVERALL_ELAPSED"),
        "completed": completed,
        "aborted_phase": aborted_phase,
        "exit_code": exit_code,
        "checks": {
            "manager_database": _status(environment, "LST_MANAGER_DB_STATUS"),
            "backup": {
                "full": _status(environment, "LST_FULL_BACKUP_STATUS"),
                "diff": _status(environment, "LST_DIFF_BACKUP_STATUS"),
                "incr": _status(environment, "LST_INCR_BACKUP_STATUS"),
            },
            "archive_integrity": {
                "full": _status(environment, "LST_FULL_ARCHIVE_STATUS"),
                "diff": _status(environment, "LST_DIFF_ARCHIVE_STATUS"),
                "incr": _status(environment, "LST_INCR_ARCHIVE_STATUS"),
            },
            "par2_files": {
                "full": _status(environment, "LST_FULL_PAR2_FILES_STATUS"),
                "diff": _status(environment, "LST_DIFF_PAR2_FILES_STATUS"),
                "incr": _status(environment, "LST_INCR_PAR2_FILES_STATUS"),
            },
            "par2_verify": {
                "full": _status(environment, "LST_FULL_PAR2_VERIFY_STATUS"),
                "diff": _status(environment, "LST_DIFF_PAR2_VERIFY_STATUS"),
                "incr": _status(environment, "LST_INCR_PAR2_VERIFY_STATUS"),
            },
            "bitrot_repair": {
                "full": _status(environment, "LST_FULL_BITROT_STATUS"),
                "diff": _status(environment, "LST_DIFF_BITROT_STATUS"),
                "incr": _status(environment, "LST_INCR_BITROT_STATUS"),
            },
            "delta_contents": {
                "diff": _status(environment, "LST_DIFF_CONTENTS_STATUS"),
                "incr": _status(environment, "LST_INCR_CONTENTS_STATUS"),
            },
            "pitr_restore": {
                "execution": _status(environment, "LST_PITR_EXECUTION_STATUS"),
                "structure": _status(environment, "LST_PITR_STRUCTURE_STATUS"),
                "content_checksums": _status(environment, "LST_PITR_CHECKSUM_STATUS"),
                "overall": _status(environment, "LST_PITR_OVERALL_STATUS"),
            },
        },
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
        memory_key: Optional key under ``memory_mb`` instead of ``key``.

    Returns:
        The average, or ``None`` when no compatible values exist.
    """
    values: list[float] = []
    for record in records:
        if memory_key is None:
            value = record.get(key)
        else:
            memory = record.get("memory_mb", {})
            value = memory.get(memory_key) if isinstance(memory, dict) else None
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
    current_memory = record.get("memory_mb", {})
    for tool in ("dar_backup", "dar", "par2", "manager"):
        current = current_memory.get(tool) if isinstance(current_memory, dict) else None
        comparisons.append(
            (
                f"Peak {tool} memory (MB)",
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
