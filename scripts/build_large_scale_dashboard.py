#!/usr/bin/env python3
"""Build a disposable SQLite database for the large-scale metrics dashboard."""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sqlite3
import tempfile
from collections.abc import Iterator, Mapping, Sequence
from contextlib import closing
from pathlib import Path
from typing import Any
from urllib.parse import quote


LOGGER = logging.getLogger(__name__)
SUPPORTED_SCHEMA_VERSIONS = frozenset(range(2, 11))
DATESTAMP_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}$")
TIERS = ("full", "diff", "incr")

RUN_COLUMNS = (
    "datestamp",
    "schema_version",
    "run_date",
    "test_name",
    "dataset_id",
    "advertise_class",
    "passed",
    "completed",
    "exit_code",
    "failure_count",
    "aborted_phase",
    "source_file_count",
    "source_bytes",
    "source_allocated_bytes",
    "source_entry_count",
    "full_elapsed_s",
    "diff_elapsed_s",
    "incr_elapsed_s",
    "overall_elapsed_s",
    "full_size_bytes",
    "diff_size_bytes",
    "incr_size_bytes",
    "dar_backup_peak_rss_mib",
    "dar_peak_rss_mib",
    "par2_peak_rss_mib",
    "manager_peak_rss_mib",
    "slice_size_bytes",
    "par2_ratio_percent",
    "bitrot_mode",
    "bitrot_percent",
    "full_restore_mode",
    "full_restore_status",
    "host_profile_id",
    "logical_cpu_count",
    "host_memory_bytes",
    "disk_free_start_bytes",
    "disk_free_end_bytes",
    "dar_backup_version",
    "dar_version",
    "par2_version",
    "image_reference",
    "image_id",
    "image_revision",
    "image_version",
    "harness_git_commit",
    "harness_git_dirty",
    "backup_definition_sha256",
    "raw_json",
)

ENGINE_BACKUP_COLUMNS = (
    "id",
    "backup_definition",
    "backup_type",
    "archive_name",
    "dar_backup_version",
    "dar_version",
    "run_started_at",
    "run_finished_at",
    "duration_secs",
    "dar_duration_secs",
    "verify_duration_secs",
    "par2_duration_secs",
    "status",
    "dar_exit_code",
    "failed_phase",
    "error_summary",
    "catalog_updated",
    "verify_passed",
    "restore_test_passed",
    "par2_passed",
    "archive_size_bytes",
    "num_slices",
    "par2_size_bytes",
    "files_verified",
    "backup_dir_free_bytes",
    "hostname",
    "run_id",
    "prereq_status",
    "postreq_status",
    "inodes_saved",
    "hard_links_treated",
    "inodes_changed_during_backup",
    "bytes_wasted",
    "inodes_metadata_only",
    "inodes_not_saved",
    "inodes_failed",
    "inodes_excluded",
    "inodes_deleted",
    "inodes_total",
    "ea_saved",
    "fsa_saved",
)

ENGINE_RESTORE_SAMPLE_COLUMNS = (
    "id",
    "run_id",
    "backup_definition",
    "archive_name",
    "file_path",
    "file_size_bytes",
    "result",
    "fail_reason_id",
    "fail_detail",
    "tested_at",
)

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE dashboard_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE runs (
    datestamp TEXT PRIMARY KEY,
    schema_version INTEGER NOT NULL,
    run_date TEXT NOT NULL,
    test_name TEXT,
    dataset_id TEXT,
    advertise_class TEXT,
    passed INTEGER NOT NULL CHECK (passed IN (0, 1)),
    completed INTEGER CHECK (completed IN (0, 1)),
    exit_code INTEGER,
    failure_count INTEGER NOT NULL CHECK (failure_count >= 0),
    aborted_phase TEXT,
    source_file_count INTEGER,
    source_bytes INTEGER,
    source_allocated_bytes INTEGER,
    source_entry_count INTEGER,
    full_elapsed_s INTEGER,
    diff_elapsed_s INTEGER,
    incr_elapsed_s INTEGER,
    overall_elapsed_s INTEGER,
    full_size_bytes INTEGER,
    diff_size_bytes INTEGER,
    incr_size_bytes INTEGER,
    dar_backup_peak_rss_mib REAL,
    dar_peak_rss_mib REAL,
    par2_peak_rss_mib REAL,
    manager_peak_rss_mib REAL,
    slice_size_bytes INTEGER,
    par2_ratio_percent INTEGER,
    bitrot_mode TEXT,
    bitrot_percent INTEGER,
    full_restore_mode TEXT,
    full_restore_status TEXT,
    host_profile_id TEXT,
    logical_cpu_count INTEGER,
    host_memory_bytes INTEGER,
    disk_free_start_bytes INTEGER,
    disk_free_end_bytes INTEGER,
    dar_backup_version TEXT,
    dar_version TEXT,
    par2_version TEXT,
    image_reference TEXT,
    image_id TEXT,
    image_revision TEXT,
    image_version TEXT,
    harness_git_commit TEXT,
    harness_git_dirty INTEGER CHECK (harness_git_dirty IN (0, 1)),
    backup_definition_sha256 TEXT,
    raw_json TEXT NOT NULL
);

CREATE TABLE phases (
    datestamp TEXT NOT NULL REFERENCES runs(datestamp) ON DELETE CASCADE,
    phase_name TEXT NOT NULL,
    status TEXT,
    duration_s REAL,
    resource_sample_count INTEGER NOT NULL CHECK (resource_sample_count >= 0),
    peak_named_process_rss_mib REAL,
    PRIMARY KEY (datestamp, phase_name)
);

CREATE TABLE phase_process_memory (
    datestamp TEXT NOT NULL,
    phase_name TEXT NOT NULL,
    process_name TEXT NOT NULL,
    peak_rss_mib REAL,
    PRIMARY KEY (datestamp, phase_name, process_name),
    FOREIGN KEY (datestamp, phase_name)
        REFERENCES phases(datestamp, phase_name) ON DELETE CASCADE
);

CREATE TABLE artifacts (
    datestamp TEXT NOT NULL REFERENCES runs(datestamp) ON DELETE CASCADE,
    tier TEXT NOT NULL CHECK (tier IN ('full', 'diff', 'incr')),
    archive_bytes INTEGER,
    slice_count INTEGER,
    smallest_slice_bytes INTEGER,
    largest_slice_bytes INTEGER,
    par2_file_count INTEGER,
    par2_bytes INTEGER,
    PRIMARY KEY (datestamp, tier)
);

CREATE TABLE mutations (
    datestamp TEXT NOT NULL REFERENCES runs(datestamp) ON DELETE CASCADE,
    tier TEXT NOT NULL CHECK (tier IN ('diff', 'incr')),
    modified_file_count INTEGER,
    modified_apparent_bytes INTEGER,
    created_file_count INTEGER,
    created_apparent_bytes INTEGER,
    deleted_file_count INTEGER,
    PRIMARY KEY (datestamp, tier)
);

CREATE TABLE check_results (
    datestamp TEXT NOT NULL REFERENCES runs(datestamp) ON DELETE CASCADE,
    check_path TEXT NOT NULL,
    value_type TEXT NOT NULL,
    value_json TEXT NOT NULL,
    PRIMARY KEY (datestamp, check_path)
);

CREATE TABLE bitrot_phases (
    datestamp TEXT NOT NULL REFERENCES runs(datestamp) ON DELETE CASCADE,
    tier TEXT NOT NULL CHECK (tier IN ('full', 'diff', 'incr')),
    seed TEXT,
    mode TEXT,
    corruption_percent INTEGER,
    edge_percent INTEGER,
    length_bytes INTEGER,
    region_count INTEGER,
    buffer_bytes INTEGER,
    injection_elapsed_ms INTEGER,
    repair_elapsed_ms INTEGER,
    dar_detected_corruption TEXT,
    dar_verify_after_repair TEXT,
    status TEXT,
    PRIMARY KEY (datestamp, tier)
);

CREATE TABLE bitrot_segments (
    datestamp TEXT NOT NULL,
    tier TEXT NOT NULL,
    segment_index INTEGER NOT NULL,
    region_index INTEGER,
    slice_name TEXT,
    slice_number INTEGER,
    slice_bytes INTEGER,
    offset_bytes INTEGER,
    length_bytes INTEGER,
    par2_data_blocks_found INTEGER,
    par2_data_blocks_total INTEGER,
    par2_data_blocks_damaged INTEGER,
    repair_elapsed_ms INTEGER,
    repair_status TEXT,
    PRIMARY KEY (datestamp, tier, segment_index),
    FOREIGN KEY (datestamp, tier)
        REFERENCES bitrot_phases(datestamp, tier) ON DELETE CASCADE
);

CREATE TABLE engine_backup_runs (
    source_id INTEGER PRIMARY KEY,
    backup_definition TEXT,
    backup_type TEXT,
    archive_name TEXT,
    dar_backup_version TEXT,
    dar_version TEXT,
    run_started_at TEXT,
    run_finished_at TEXT,
    duration_secs REAL,
    dar_duration_secs REAL,
    verify_duration_secs REAL,
    par2_duration_secs REAL,
    status TEXT,
    dar_exit_code INTEGER,
    failed_phase TEXT,
    error_summary TEXT,
    catalog_updated INTEGER,
    verify_passed INTEGER,
    restore_test_passed INTEGER,
    par2_passed INTEGER,
    archive_size_bytes INTEGER,
    num_slices INTEGER,
    par2_size_bytes INTEGER,
    files_verified INTEGER,
    backup_dir_free_bytes INTEGER,
    hostname TEXT,
    run_id TEXT NOT NULL UNIQUE,
    prereq_status TEXT,
    postreq_status TEXT,
    inodes_saved INTEGER,
    hard_links_treated INTEGER,
    inodes_changed_during_backup INTEGER,
    bytes_wasted INTEGER,
    inodes_metadata_only INTEGER,
    inodes_not_saved INTEGER,
    inodes_failed INTEGER,
    inodes_excluded INTEGER,
    inodes_deleted INTEGER,
    inodes_total INTEGER,
    ea_saved INTEGER,
    fsa_saved INTEGER
);

CREATE TABLE engine_restore_fail_reasons (
    source_id INTEGER PRIMARY KEY,
    code TEXT NOT NULL UNIQUE
);

CREATE TABLE engine_restore_samples (
    source_id INTEGER PRIMARY KEY,
    run_id TEXT NOT NULL,
    backup_definition TEXT,
    archive_name TEXT,
    file_path TEXT,
    file_size_bytes INTEGER,
    result TEXT,
    fail_reason_id INTEGER,
    fail_detail TEXT,
    tested_at TEXT
);

CREATE INDEX runs_date_idx ON runs(run_date);
CREATE INDEX runs_dataset_idx ON runs(dataset_id);
CREATE INDEX phases_name_idx ON phases(phase_name);
CREATE INDEX engine_backup_started_idx ON engine_backup_runs(run_started_at);
CREATE INDEX engine_restore_run_idx ON engine_restore_samples(run_id);

CREATE VIEW run_performance AS
SELECT
    runs.datestamp,
    runs.run_date,
    runs.test_name,
    runs.dataset_id,
    runs.advertise_class,
    runs.passed,
    runs.completed,
    ROUND(runs.source_bytes / 1073741824.0, 3) AS source_gib,
    runs.source_bytes,
    runs.source_file_count,
    ROUND(runs.full_size_bytes / 1073741824.0, 3) AS full_archive_gib,
    runs.full_elapsed_s AS full_backup_seconds,
    CASE WHEN runs.full_elapsed_s > 0
        THEN ROUND(runs.source_bytes / 1048576.0 / runs.full_elapsed_s, 2)
    END AS full_throughput_mib_s,
    full_restore.duration_s AS full_restore_seconds,
    CASE WHEN full_restore.duration_s > 0
        THEN ROUND(runs.source_bytes / 1048576.0 / full_restore.duration_s, 2)
    END AS full_restore_throughput_mib_s,
    ROUND(runs.overall_elapsed_s / 60.0, 2) AS overall_minutes,
    runs.dar_backup_peak_rss_mib,
    runs.dar_peak_rss_mib,
    runs.par2_peak_rss_mib,
    runs.manager_peak_rss_mib,
    ROUND(runs.slice_size_bytes / 1073741824.0, 3) AS slice_size_gib,
    runs.par2_ratio_percent,
    runs.bitrot_mode,
    runs.full_restore_status,
    runs.image_version,
    runs.harness_git_dirty
FROM runs
LEFT JOIN phases AS full_restore
  ON full_restore.datestamp = runs.datestamp
 AND full_restore.phase_name = 'full_restore';

CREATE VIEW artifact_summary AS
SELECT
    artifacts.datestamp,
    artifacts.tier,
    ROUND(artifacts.archive_bytes / 1073741824.0, 3) AS archive_gib,
    artifacts.slice_count,
    ROUND(artifacts.largest_slice_bytes / 1073741824.0, 3) AS largest_slice_gib,
    artifacts.par2_file_count,
    ROUND(artifacts.par2_bytes / 1073741824.0, 3) AS par2_gib,
    CASE WHEN artifacts.archive_bytes > 0
        THEN ROUND(100.0 * artifacts.par2_bytes / artifacts.archive_bytes, 3)
    END AS par2_overhead_percent
FROM artifacts;

CREATE VIEW memory_trends AS
SELECT datestamp, 'dar-backup' AS process_name,
       dar_backup_peak_rss_mib AS peak_rss_mib FROM runs
 WHERE dar_backup_peak_rss_mib IS NOT NULL
UNION ALL
SELECT datestamp, 'dar', dar_peak_rss_mib FROM runs
 WHERE dar_peak_rss_mib IS NOT NULL
UNION ALL
SELECT datestamp, 'par2', par2_peak_rss_mib FROM runs
 WHERE par2_peak_rss_mib IS NOT NULL
UNION ALL
SELECT datestamp, 'manager', manager_peak_rss_mib FROM runs
 WHERE manager_peak_rss_mib IS NOT NULL;

CREATE VIEW engine_run_performance AS
SELECT
    run_started_at,
    backup_type,
    status,
    ROUND(archive_size_bytes / 1073741824.0, 3) AS archive_gib,
    ROUND(duration_secs, 3) AS total_seconds,
    ROUND(dar_duration_secs, 3) AS dar_seconds,
    ROUND(verify_duration_secs, 3) AS verify_seconds,
    ROUND(par2_duration_secs, 3) AS par2_seconds,
    CASE WHEN duration_secs > 0
        THEN ROUND(archive_size_bytes / 1048576.0 / duration_secs, 2)
    END AS archive_throughput_mib_s,
    num_slices,
    files_verified,
    inodes_saved,
    inodes_failed,
    run_id
FROM engine_backup_runs;
"""


def _require_mapping(value: object, label: str) -> Mapping[str, Any]:
    """Return a mapping or reject a structurally invalid value.

    Args:
        value: Candidate mapping value.
        label: Human-readable field label for diagnostics.

    Returns:
        The validated mapping.

    Raises:
        ValueError: If ``value`` is not a mapping.
    """
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _nested(record: Mapping[str, Any], *path: str) -> Any:
    """Read an optional nested value while validating intermediate objects.

    Args:
        record: Source result object.
        path: Ordered object keys to traverse.

    Returns:
        The nested value, or ``None`` when a key is absent.

    Raises:
        ValueError: If an intermediate value is not an object.
    """
    current: Any = record
    traversed: list[str] = []
    for key in path:
        if not isinstance(current, Mapping):
            label = ".".join(traversed) or "record"
            raise ValueError(f"{label} must be an object")
        if key not in current:
            return None
        current = current[key]
        traversed.append(key)
    return current


def _required_string(record: Mapping[str, Any], key: str) -> str:
    """Return a required non-empty string field.

    Args:
        record: Source result object.
        key: Top-level field name.

    Returns:
        The validated string.

    Raises:
        ValueError: If the field is absent, empty, or not text.
    """
    value = record.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _required_integer(record: Mapping[str, Any], key: str) -> int:
    """Return a required integer field.

    Args:
        record: Source result object.
        key: Top-level field name.

    Returns:
        The validated integer.

    Raises:
        ValueError: If the field is absent or not an integer.
    """
    value = record.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key} must be an integer")
    return value


def _required_boolean(record: Mapping[str, Any], key: str) -> bool:
    """Return a required Boolean field.

    Args:
        record: Source result object.
        key: Top-level field name.

    Returns:
        The validated Boolean.

    Raises:
        ValueError: If the field is absent or not Boolean.
    """
    value = record.get(key)
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be a Boolean")
    return value


def _optional_integer(value: object, label: str) -> int | None:
    """Return an optional integer field.

    Args:
        value: Candidate integer or ``None``.
        label: Human-readable field label for diagnostics.

    Returns:
        The integer or ``None``.

    Raises:
        ValueError: If a non-null value is not an integer.
    """
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an integer or null")
    return value


def _optional_number(value: object, label: str) -> float | int | None:
    """Return an optional real-number field.

    Args:
        value: Candidate number or ``None``.
        label: Human-readable field label for diagnostics.

    Returns:
        The number or ``None``.

    Raises:
        ValueError: If a non-null value is not numeric.
    """
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        raise ValueError(f"{label} must be a number or null")
    return value


def _optional_string(value: object, label: str) -> str | None:
    """Return an optional string field.

    Args:
        value: Candidate string or ``None``.
        label: Human-readable field label for diagnostics.

    Returns:
        The string or ``None``.

    Raises:
        ValueError: If a non-null value is not text.
    """
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a string or null")
    return value


def _optional_boolean_as_integer(value: object, label: str) -> int | None:
    """Convert an optional Boolean field to SQLite's integer representation.

    Args:
        value: Candidate Boolean or ``None``.
        label: Human-readable field label for diagnostics.

    Returns:
        One, zero, or ``None``.

    Raises:
        ValueError: If a non-null value is not Boolean.
    """
    if value is None:
        return None
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be a Boolean or null")
    return int(value)


def load_result_records(results_jsonl: Path) -> list[dict[str, Any]]:
    """Load and validate the identity fields of every JSONL result record.

    Args:
        results_jsonl: Existing large-scale result history.

    Returns:
        Validated records in source order.

    Raises:
        OSError: If the history cannot be read.
        ValueError: If the path or any JSONL record is invalid.
    """
    if not isinstance(results_jsonl, Path):
        raise ValueError("results_jsonl must be a pathlib.Path")
    if not results_jsonl.is_file():
        raise ValueError(f"results JSONL is not a file: {results_jsonl}")

    records: list[dict[str, Any]] = []
    seen_datestamps: set[str] = set()
    with results_jsonl.open("r", encoding="utf-8") as source:
        for line_number, line in enumerate(source, start=1):
            if not line.strip():
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(
                    f"invalid JSON on {results_jsonl}:{line_number}: {error.msg}"
                ) from error
            record = dict(_require_mapping(parsed, f"record on line {line_number}"))
            schema_version = _required_integer(record, "schema_version")
            if schema_version not in SUPPORTED_SCHEMA_VERSIONS:
                supported = f"{min(SUPPORTED_SCHEMA_VERSIONS)}-{max(SUPPORTED_SCHEMA_VERSIONS)}"
                raise ValueError(
                    f"unsupported schema_version {schema_version} on line "
                    f"{line_number}; supported versions are {supported}"
                )
            datestamp = _required_string(record, "datestamp")
            if DATESTAMP_PATTERN.fullmatch(datestamp) is None:
                raise ValueError(
                    f"datestamp on line {line_number} has an invalid format: "
                    f"{datestamp!r}"
                )
            if datestamp in seen_datestamps:
                raise ValueError(f"duplicate datestamp on line {line_number}: {datestamp}")
            _required_string(record, "date")
            _required_boolean(record, "passed")
            failure_count = _required_integer(record, "failures")
            if failure_count < 0:
                raise ValueError(f"failures must not be negative on line {line_number}")
            seen_datestamps.add(datestamp)
            records.append(record)

    if not records:
        raise ValueError(f"results JSONL contains no records: {results_jsonl}")
    return records


def _run_values(record: Mapping[str, Any]) -> dict[str, object]:
    """Extract one stable dashboard run row from a versioned result record.

    Args:
        record: Validated large-scale result record.

    Returns:
        Mapping keyed by ``RUN_COLUMNS``.

    Raises:
        ValueError: If a known field has an invalid type or structure.
    """
    _require_mapping(record, "record")
    memory = _nested(record, "memory_mib")
    if memory is None:
        memory = _nested(record, "memory_mb")
    memory_mapping = {} if memory is None else _require_mapping(memory, "memory")

    source = _nested(record, "workload", "source")
    source_mapping = {} if source is None else _require_mapping(source, "workload.source")
    configuration = _nested(record, "configuration")
    configuration_mapping = (
        {} if configuration is None else _require_mapping(configuration, "configuration")
    )
    environment = _nested(record, "environment")
    environment_mapping = (
        {} if environment is None else _require_mapping(environment, "environment")
    )
    full_restore = _nested(record, "checks", "full_restore")
    full_restore_mapping = (
        {} if full_restore is None else _require_mapping(full_restore, "checks.full_restore")
    )

    source_file_count = source_mapping.get(
        "regular_file_count", record.get("source_file_count")
    )
    source_bytes = source_mapping.get("apparent_bytes", record.get("source_bytes"))
    dataset_id = _nested(record, "workload", "dataset_id")
    disk_free = environment_mapping.get("disk_free_bytes")
    disk_free_mapping = (
        {} if disk_free is None else _require_mapping(disk_free, "environment.disk_free_bytes")
    )

    values: dict[str, object] = {
        "datestamp": _required_string(record, "datestamp"),
        "schema_version": _required_integer(record, "schema_version"),
        "run_date": _required_string(record, "date"),
        "test_name": _optional_string(record.get("test_name"), "test_name"),
        "dataset_id": _optional_string(dataset_id, "workload.dataset_id"),
        "advertise_class": _optional_string(
            record.get("advertise_class"), "advertise_class"
        ),
        "passed": int(_required_boolean(record, "passed")),
        "completed": _optional_boolean_as_integer(record.get("completed"), "completed"),
        "exit_code": _optional_integer(record.get("exit_code"), "exit_code"),
        "failure_count": _required_integer(record, "failures"),
        "aborted_phase": _optional_string(record.get("aborted_phase"), "aborted_phase"),
        "source_file_count": _optional_integer(source_file_count, "source_file_count"),
        "source_bytes": _optional_integer(source_bytes, "source_bytes"),
        "source_allocated_bytes": _optional_integer(
            source_mapping.get("allocated_bytes"), "workload.source.allocated_bytes"
        ),
        "source_entry_count": _optional_integer(
            source_mapping.get("entry_count"), "workload.source.entry_count"
        ),
        "full_elapsed_s": _optional_integer(record.get("full_elapsed_s"), "full_elapsed_s"),
        "diff_elapsed_s": _optional_integer(record.get("diff_elapsed_s"), "diff_elapsed_s"),
        "incr_elapsed_s": _optional_integer(record.get("incr_elapsed_s"), "incr_elapsed_s"),
        "overall_elapsed_s": _optional_integer(
            record.get("overall_elapsed_s"), "overall_elapsed_s"
        ),
        "full_size_bytes": _optional_integer(record.get("full_size_bytes"), "full_size_bytes"),
        "diff_size_bytes": _optional_integer(record.get("diff_size_bytes"), "diff_size_bytes"),
        "incr_size_bytes": _optional_integer(record.get("incr_size_bytes"), "incr_size_bytes"),
        "dar_backup_peak_rss_mib": _optional_number(
            memory_mapping.get("dar_backup"), "memory.dar_backup"
        ),
        "dar_peak_rss_mib": _optional_number(memory_mapping.get("dar"), "memory.dar"),
        "par2_peak_rss_mib": _optional_number(memory_mapping.get("par2"), "memory.par2"),
        "manager_peak_rss_mib": _optional_number(
            memory_mapping.get("manager"), "memory.manager"
        ),
        "slice_size_bytes": _optional_integer(
            _nested(configuration_mapping, "slice_size", "bytes"),
            "configuration.slice_size.bytes",
        ),
        "par2_ratio_percent": _optional_integer(
            _nested(configuration_mapping, "par2", "error_correction_percent"),
            "configuration.par2.error_correction_percent",
        ),
        "bitrot_mode": _optional_string(
            _nested(configuration_mapping, "bitrot", "mode"),
            "configuration.bitrot.mode",
        ),
        "bitrot_percent": _optional_integer(
            _nested(configuration_mapping, "bitrot", "corruption_percent"),
            "configuration.bitrot.corruption_percent",
        ),
        "full_restore_mode": _optional_string(
            full_restore_mapping.get("mode"), "checks.full_restore.mode"
        ),
        "full_restore_status": _optional_string(
            full_restore_mapping.get("overall"), "checks.full_restore.overall"
        ),
        "host_profile_id": _optional_string(
            environment_mapping.get("host_profile_id"), "environment.host_profile_id"
        ),
        "logical_cpu_count": _optional_integer(
            environment_mapping.get("logical_cpu_count"), "environment.logical_cpu_count"
        ),
        "host_memory_bytes": _optional_integer(
            environment_mapping.get("memory_bytes"), "environment.memory_bytes"
        ),
        "disk_free_start_bytes": _optional_integer(
            disk_free_mapping.get("start"), "environment.disk_free_bytes.start"
        ),
        "disk_free_end_bytes": _optional_integer(
            disk_free_mapping.get("end"), "environment.disk_free_bytes.end"
        ),
        "dar_backup_version": _optional_string(
            record.get("dar_backup_version"), "dar_backup_version"
        ),
        "dar_version": _optional_string(record.get("dar_version"), "dar_version"),
        "par2_version": _optional_string(record.get("par2_version"), "par2_version"),
        "image_reference": _optional_string(
            record.get("image_reference"), "image_reference"
        ),
        "image_id": _optional_string(record.get("image_id"), "image_id"),
        "image_revision": _optional_string(record.get("image_revision"), "image_revision"),
        "image_version": _optional_string(record.get("image_version"), "image_version"),
        "harness_git_commit": _optional_string(
            record.get("harness_git_commit"), "harness_git_commit"
        ),
        "harness_git_dirty": _optional_boolean_as_integer(
            record.get("harness_git_dirty"), "harness_git_dirty"
        ),
        "backup_definition_sha256": _optional_string(
            record.get("backup_definition_sha256"), "backup_definition_sha256"
        ),
        "raw_json": json.dumps(record, sort_keys=True, separators=(",", ":")),
    }
    return values


def _json_scalar_type(value: object) -> str:
    """Return a stable JSON-oriented type label.

    Args:
        value: Scalar or structured JSON-compatible value.

    Returns:
        One of ``null``, ``boolean``, ``integer``, ``real``, ``string``,
        ``array``, or ``object``.

    Raises:
        ValueError: If the value cannot be represented by the supported labels.
    """
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "real"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, Mapping):
        return "object"
    raise ValueError(f"unsupported JSON value type: {type(value).__name__}")


def _flatten_check_values(
    value: object, prefix: tuple[str, ...] = ()
) -> Iterator[tuple[str, object]]:
    """Yield dotted paths for scalar leaves in the checks object.

    Args:
        value: Current checks value.
        prefix: Parent object keys already traversed.

    Returns:
        Iterator of dotted paths and JSON-compatible leaf values.

    Raises:
        ValueError: If an object key is empty or not text.
    """
    if isinstance(value, Mapping):
        for key, nested_value in value.items():
            if not isinstance(key, str) or not key:
                raise ValueError("checks object keys must be non-empty strings")
            yield from _flatten_check_values(nested_value, (*prefix, key))
        return
    if not prefix:
        raise ValueError("checks must be an object")
    yield ".".join(prefix), value


def _insert_record_details(
    database: sqlite3.Connection, record: Mapping[str, Any]
) -> None:
    """Insert normalized child rows for one result record.

    Args:
        database: Writable dashboard connection.
        record: Validated large-scale result record.

    Returns:
        None.

    Raises:
        ValueError: If a known nested section has an invalid structure.
        sqlite3.Error: If a row cannot be inserted.
    """
    if not isinstance(database, sqlite3.Connection):
        raise ValueError("database must be a sqlite3.Connection")
    datestamp = _required_string(record, "datestamp")

    phases = record.get("phases")
    if phases is not None:
        for phase_name, phase_value in _require_mapping(phases, "phases").items():
            if not isinstance(phase_name, str) or not phase_name:
                raise ValueError("phase names must be non-empty strings")
            phase = _require_mapping(phase_value, f"phases.{phase_name}")
            resources_value = phase.get("resources")
            resources = (
                {}
                if resources_value is None
                else _require_mapping(resources_value, f"phases.{phase_name}.resources")
            )
            sample_count = _optional_integer(
                resources.get("sample_count"),
                f"phases.{phase_name}.resources.sample_count",
            )
            database.execute(
                """INSERT INTO phases (
                       datestamp, phase_name, status, duration_s,
                       resource_sample_count, peak_named_process_rss_mib
                   ) VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    datestamp,
                    phase_name,
                    _optional_string(phase.get("status"), f"phases.{phase_name}.status"),
                    _optional_number(
                        phase.get("duration_s"), f"phases.{phase_name}.duration_s"
                    ),
                    sample_count or 0,
                    _optional_number(
                        resources.get("peak_named_process_rss_mib"),
                        f"phases.{phase_name}.resources.peak_named_process_rss_mib",
                    ),
                ),
            )
            process_memory_value = resources.get("peak_process_rss_mib")
            process_memory = (
                {}
                if process_memory_value is None
                else _require_mapping(
                    process_memory_value,
                    f"phases.{phase_name}.resources.peak_process_rss_mib",
                )
            )
            for process_name, peak_rss in process_memory.items():
                if not isinstance(process_name, str) or not process_name:
                    raise ValueError("process names must be non-empty strings")
                database.execute(
                    """INSERT INTO phase_process_memory (
                           datestamp, phase_name, process_name, peak_rss_mib
                       ) VALUES (?, ?, ?, ?)""",
                    (
                        datestamp,
                        phase_name,
                        process_name,
                        _optional_number(
                            peak_rss,
                            f"phases.{phase_name}.resources.peak_process_rss_mib."
                            f"{process_name}",
                        ),
                    ),
                )

    artifacts = record.get("artifacts")
    if artifacts is not None:
        artifact_mapping = _require_mapping(artifacts, "artifacts")
        for tier in TIERS:
            artifact_value = artifact_mapping.get(tier)
            if artifact_value is None:
                continue
            artifact = _require_mapping(artifact_value, f"artifacts.{tier}")
            database.execute(
                """INSERT INTO artifacts VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    datestamp,
                    tier,
                    _optional_integer(
                        artifact.get("archive_bytes"), f"artifacts.{tier}.archive_bytes"
                    ),
                    _optional_integer(
                        artifact.get("slice_count"), f"artifacts.{tier}.slice_count"
                    ),
                    _optional_integer(
                        artifact.get("smallest_slice_bytes"),
                        f"artifacts.{tier}.smallest_slice_bytes",
                    ),
                    _optional_integer(
                        artifact.get("largest_slice_bytes"),
                        f"artifacts.{tier}.largest_slice_bytes",
                    ),
                    _optional_integer(
                        artifact.get("par2_file_count"),
                        f"artifacts.{tier}.par2_file_count",
                    ),
                    _optional_integer(
                        artifact.get("par2_bytes"), f"artifacts.{tier}.par2_bytes"
                    ),
                ),
            )

    mutations = _nested(record, "workload", "mutations")
    if mutations is not None:
        mutation_mapping = _require_mapping(mutations, "workload.mutations")
        for tier in ("diff", "incr"):
            mutation_value = mutation_mapping.get(tier)
            if mutation_value is None:
                continue
            mutation = _require_mapping(
                mutation_value, f"workload.mutations.{tier}"
            )
            database.execute(
                """INSERT INTO mutations VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    datestamp,
                    tier,
                    _optional_integer(
                        mutation.get("modified_file_count"),
                        f"workload.mutations.{tier}.modified_file_count",
                    ),
                    _optional_integer(
                        mutation.get("modified_apparent_bytes"),
                        f"workload.mutations.{tier}.modified_apparent_bytes",
                    ),
                    _optional_integer(
                        mutation.get("created_file_count"),
                        f"workload.mutations.{tier}.created_file_count",
                    ),
                    _optional_integer(
                        mutation.get("created_apparent_bytes"),
                        f"workload.mutations.{tier}.created_apparent_bytes",
                    ),
                    _optional_integer(
                        mutation.get("deleted_file_count"),
                        f"workload.mutations.{tier}.deleted_file_count",
                    ),
                ),
            )

    checks = record.get("checks")
    if checks is not None:
        _require_mapping(checks, "checks")
        for check_path, value in _flatten_check_values(checks):
            database.execute(
                "INSERT INTO check_results VALUES (?, ?, ?, ?)",
                (
                    datestamp,
                    check_path,
                    _json_scalar_type(value),
                    json.dumps(value, separators=(",", ":")),
                ),
            )

    bitrot_evidence = record.get("bitrot_evidence")
    if bitrot_evidence is not None:
        bitrot_mapping = _require_mapping(bitrot_evidence, "bitrot_evidence")
        for tier in TIERS:
            evidence_value = bitrot_mapping.get(tier)
            if evidence_value is None:
                continue
            evidence = _require_mapping(evidence_value, f"bitrot_evidence.{tier}")
            seed_value = evidence.get("seed")
            if seed_value is not None and (
                isinstance(seed_value, bool) or not isinstance(seed_value, (int, str))
            ):
                raise ValueError(f"bitrot_evidence.{tier}.seed must be text or integer")
            database.execute(
                """INSERT INTO bitrot_phases VALUES (
                       ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                   )""",
                (
                    datestamp,
                    tier,
                    None if seed_value is None else str(seed_value),
                    _optional_string(evidence.get("mode"), f"bitrot_evidence.{tier}.mode"),
                    _optional_integer(
                        evidence.get("corruption_percent"),
                        f"bitrot_evidence.{tier}.corruption_percent",
                    ),
                    _optional_integer(
                        evidence.get("edge_percent"),
                        f"bitrot_evidence.{tier}.edge_percent",
                    ),
                    _optional_integer(
                        evidence.get("length_bytes"),
                        f"bitrot_evidence.{tier}.length_bytes",
                    ),
                    _optional_integer(
                        evidence.get("region_count"),
                        f"bitrot_evidence.{tier}.region_count",
                    ),
                    _optional_integer(
                        evidence.get("buffer_bytes"),
                        f"bitrot_evidence.{tier}.buffer_bytes",
                    ),
                    _optional_integer(
                        evidence.get("injection_elapsed_ms"),
                        f"bitrot_evidence.{tier}.injection_elapsed_ms",
                    ),
                    _optional_integer(
                        evidence.get("repair_elapsed_ms"),
                        f"bitrot_evidence.{tier}.repair_elapsed_ms",
                    ),
                    _optional_string(
                        evidence.get("dar_detected_corruption"),
                        f"bitrot_evidence.{tier}.dar_detected_corruption",
                    ),
                    _optional_string(
                        evidence.get("dar_verify_after_repair"),
                        f"bitrot_evidence.{tier}.dar_verify_after_repair",
                    ),
                    _optional_string(
                        evidence.get("status"), f"bitrot_evidence.{tier}.status"
                    ),
                ),
            )
            segments_value = evidence.get("segments", [])
            if not isinstance(segments_value, list):
                raise ValueError(f"bitrot_evidence.{tier}.segments must be an array")
            for segment_value in segments_value:
                segment = _require_mapping(
                    segment_value, f"bitrot_evidence.{tier}.segments[]"
                )
                segment_index = _optional_integer(
                    segment.get("segment_index"),
                    f"bitrot_evidence.{tier}.segments[].segment_index",
                )
                if segment_index is None:
                    raise ValueError(
                        f"bitrot_evidence.{tier}.segments[].segment_index is required"
                    )
                database.execute(
                    """INSERT INTO bitrot_segments VALUES (
                           ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                       )""",
                    (
                        datestamp,
                        tier,
                        segment_index,
                        _optional_integer(
                            segment.get("region_index"), "bitrot segment region_index"
                        ),
                        _optional_string(segment.get("slice"), "bitrot segment slice"),
                        _optional_integer(
                            segment.get("slice_number"), "bitrot segment slice_number"
                        ),
                        _optional_integer(
                            segment.get("slice_bytes"), "bitrot segment slice_bytes"
                        ),
                        _optional_integer(
                            segment.get("offset_bytes"), "bitrot segment offset_bytes"
                        ),
                        _optional_integer(
                            segment.get("length_bytes"), "bitrot segment length_bytes"
                        ),
                        _optional_integer(
                            segment.get("par2_data_blocks_found"),
                            "bitrot segment par2_data_blocks_found",
                        ),
                        _optional_integer(
                            segment.get("par2_data_blocks_total"),
                            "bitrot segment par2_data_blocks_total",
                        ),
                        _optional_integer(
                            segment.get("par2_data_blocks_damaged"),
                            "bitrot segment par2_data_blocks_damaged",
                        ),
                        _optional_integer(
                            segment.get("repair_elapsed_ms"),
                            "bitrot segment repair_elapsed_ms",
                        ),
                        _optional_string(
                            segment.get("repair_status"), "bitrot segment repair_status"
                        ),
                    ),
                )


def _validate_source_columns(
    database: sqlite3.Connection, table: str, required_columns: Sequence[str]
) -> None:
    """Require an operational metrics table and its expected columns.

    Args:
        database: Read-only operational metrics connection.
        table: Fixed table name to inspect.
        required_columns: Columns required by the dashboard importer.

    Returns:
        None.

    Raises:
        ValueError: If inputs are invalid or the table schema is incompatible.
        sqlite3.Error: If schema inspection fails.
    """
    if not isinstance(database, sqlite3.Connection):
        raise ValueError("database must be a sqlite3.Connection")
    allowed_tables = {
        "backup_runs",
        "restore_test_fail_reasons",
        "restore_test_samples",
    }
    if table not in allowed_tables:
        raise ValueError(f"unsupported operational metrics table: {table!r}")
    if not required_columns:
        raise ValueError("required_columns must not be empty")
    available = {
        str(row[1]) for row in database.execute(f'PRAGMA table_info("{table}")')
    }
    if not available:
        raise ValueError(f"operational metrics database is missing table {table!r}")
    missing = sorted(set(required_columns) - available)
    if missing:
        raise ValueError(
            f"operational metrics table {table!r} is missing column(s): "
            f"{', '.join(missing)}"
        )


def _copy_operational_metrics(
    source: sqlite3.Connection, destination: sqlite3.Connection
) -> tuple[int, int]:
    """Copy stable operational backup and restore metrics into the dashboard.

    Args:
        source: Read-only operational metrics connection.
        destination: Writable dashboard connection.

    Returns:
        Counts of copied backup runs and restore samples.

    Raises:
        ValueError: If the operational database schema is incompatible.
        sqlite3.Error: If reading or writing metrics fails.
    """
    if not isinstance(source, sqlite3.Connection):
        raise ValueError("source must be a sqlite3.Connection")
    if not isinstance(destination, sqlite3.Connection):
        raise ValueError("destination must be a sqlite3.Connection")

    _validate_source_columns(source, "backup_runs", ENGINE_BACKUP_COLUMNS)
    _validate_source_columns(
        source, "restore_test_fail_reasons", ("id", "code")
    )
    _validate_source_columns(
        source, "restore_test_samples", ENGINE_RESTORE_SAMPLE_COLUMNS
    )

    backup_select = ", ".join(f'"{column}"' for column in ENGINE_BACKUP_COLUMNS)
    backup_count = int(
        source.execute('SELECT COUNT(*) FROM "backup_runs"').fetchone()[0]
    )
    backup_placeholders = ", ".join("?" for _ in ENGINE_BACKUP_COLUMNS)
    destination.executemany(
        f"INSERT INTO engine_backup_runs VALUES ({backup_placeholders})",
        source.execute(
            f'SELECT {backup_select} FROM "backup_runs" ORDER BY "id"'
        ),
    )

    destination.executemany(
        "INSERT INTO engine_restore_fail_reasons VALUES (?, ?)",
        source.execute(
            'SELECT "id", "code" FROM "restore_test_fail_reasons" ORDER BY "id"'
        ),
    )

    sample_select = ", ".join(
        f'"{column}"' for column in ENGINE_RESTORE_SAMPLE_COLUMNS
    )
    sample_count = int(
        source.execute('SELECT COUNT(*) FROM "restore_test_samples"').fetchone()[0]
    )
    sample_placeholders = ", ".join("?" for _ in ENGINE_RESTORE_SAMPLE_COLUMNS)
    destination.executemany(
        f"INSERT INTO engine_restore_samples VALUES ({sample_placeholders})",
        source.execute(
            f'SELECT {sample_select} FROM "restore_test_samples" ORDER BY "id"'
        ),
    )
    return backup_count, sample_count


def _open_immutable_database(path: Path) -> sqlite3.Connection:
    """Open an existing SQLite database in immutable read-only mode.

    Args:
        path: Existing operational metrics database.

    Returns:
        Read-only SQLite connection.

    Raises:
        ValueError: If the path is not an existing file.
        sqlite3.Error: If SQLite cannot open or validate the database.
    """
    if not isinstance(path, Path):
        raise ValueError("path must be a pathlib.Path")
    if not path.is_file():
        raise ValueError(f"operational metrics database is not a file: {path}")
    uri_path = quote(str(path.resolve()), safe="/")
    database = sqlite3.connect(
        f"file:{uri_path}?mode=ro&immutable=1", uri=True
    )
    try:
        integrity = database.execute("PRAGMA integrity_check").fetchone()
    except sqlite3.Error:
        database.close()
        raise
    if integrity is None or integrity[0] != "ok":
        database.close()
        detail = "unknown" if integrity is None else str(integrity[0])
        raise ValueError(
            f"operational metrics database failed integrity_check: {detail}"
        )
    return database


def build_dashboard_database(
    results_jsonl: Path,
    output_database: Path,
    operational_metrics_database: Path | None = None,
) -> dict[str, int]:
    """Build and atomically publish a normalized dashboard database.

    Args:
        results_jsonl: Canonical large-scale JSONL history.
        output_database: Disposable SQLite database to create or replace.
        operational_metrics_database: Optional dar-backup metrics database.

    Returns:
        Imported run, engine-run, and restore-sample counts.

    Raises:
        OSError: If files or the output directory cannot be accessed.
        ValueError: If paths or source data are invalid.
        sqlite3.Error: If database construction fails.
    """
    if not isinstance(output_database, Path):
        raise ValueError("output_database must be a pathlib.Path")
    if output_database.exists() and output_database.is_dir():
        raise ValueError(f"output database path is a directory: {output_database}")
    if operational_metrics_database is not None and not isinstance(
        operational_metrics_database, Path
    ):
        raise ValueError("operational_metrics_database must be a pathlib.Path or None")

    records = load_result_records(results_jsonl)
    output_parent = output_database.parent
    output_parent.mkdir(parents=True, exist_ok=True)
    output_resolved = output_database.resolve(strict=False)
    if results_jsonl.resolve() == output_resolved:
        raise ValueError("output database must not replace the results JSONL")
    if (
        operational_metrics_database is not None
        and operational_metrics_database.resolve(strict=False) == output_resolved
    ):
        raise ValueError("output database must not replace the operational metrics database")

    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output_database.name}.",
        suffix=".tmp",
        dir=output_parent,
    )
    os.close(file_descriptor)
    temporary_path = Path(temporary_name)
    engine_run_count = 0
    restore_sample_count = 0
    try:
        with closing(sqlite3.connect(temporary_path)) as destination:
            with destination:
                destination.executescript(SCHEMA_SQL)
                run_placeholders = ", ".join(
                    f":{column}" for column in RUN_COLUMNS
                )
                run_columns_sql = ", ".join(RUN_COLUMNS)
                for record in records:
                    destination.execute(
                        f"INSERT INTO runs ({run_columns_sql}) "
                        f"VALUES ({run_placeholders})",
                        _run_values(record),
                    )
                    _insert_record_details(destination, record)

                if operational_metrics_database is not None:
                    with closing(
                        _open_immutable_database(operational_metrics_database)
                    ) as source:
                        engine_run_count, restore_sample_count = (
                            _copy_operational_metrics(source, destination)
                        )

                metadata = {
                    "dashboard_schema_version": "1",
                    "result_record_count": str(len(records)),
                    "engine_run_count": str(engine_run_count),
                    "restore_sample_count": str(restore_sample_count),
                }
                destination.executemany(
                    "INSERT INTO dashboard_metadata (key, value) VALUES (?, ?)",
                    sorted(metadata.items()),
                )
                destination.execute("ANALYZE")
        temporary_path.chmod(0o644)
        os.replace(temporary_path, output_database)
    finally:
        temporary_path.unlink(missing_ok=True)

    return {
        "result_record_count": len(records),
        "engine_run_count": engine_run_count,
        "restore_sample_count": restore_sample_count,
    }


def parse_args(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse dashboard-builder command-line arguments.

    Args:
        arguments: Optional arguments excluding the executable name.

    Returns:
        Parsed command-line namespace.

    Raises:
        SystemExit: If argparse rejects the command line.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-jsonl", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--operational-metrics-db", type=Path)
    return parser.parse_args(arguments)


def main(arguments: Sequence[str] | None = None) -> int:
    """Build the dashboard database from command-line arguments.

    Args:
        arguments: Optional arguments excluding the executable name.

    Returns:
        Zero on success and two for invalid input or database failures.

    Raises:
        SystemExit: Only when argparse rejects the command line.
    """
    args = parse_args(arguments)
    try:
        counts = build_dashboard_database(
            args.results_jsonl,
            args.output,
            args.operational_metrics_db,
        )
    except (OSError, ValueError, sqlite3.Error) as error:
        LOGGER.error("Unable to build large-scale metrics dashboard: %s", error)
        return 2
    LOGGER.info(
        "Dashboard database written to %s (%d result records, %d engine runs, "
        "%d restore samples)",
        args.output,
        counts["result_record_count"],
        counts["engine_run_count"],
        counts["restore_sample_count"],
    )
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    raise SystemExit(main())
