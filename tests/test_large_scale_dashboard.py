# SPDX-FileCopyrightText: 2025-2026 Per Jensen
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This file is part of dar-backup-image:
# https://github.com/per2jensen/dar-backup-image
#
# License terms and warranty disclaimer:
# https://github.com/per2jensen/dar-backup-image/blob/main/LICENSE

"""Tests for the disposable large-scale Datasette database builder."""

from __future__ import annotations

import importlib.util
import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest


MODULE_PATH = Path(__file__).parents[1] / "scripts" / "build_large_scale_dashboard.py"
METADATA_PATH = Path(__file__).parents[1] / "dashboard" / "metadata.json"
MODULE_SPEC = importlib.util.spec_from_file_location(
    "build_large_scale_dashboard", MODULE_PATH
)
if MODULE_SPEC is None or MODULE_SPEC.loader is None:
    raise RuntimeError(f"Unable to load dashboard builder from {MODULE_PATH}")
DASHBOARD_MODULE = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(DASHBOARD_MODULE)
build_dashboard_database = DASHBOARD_MODULE.build_dashboard_database
ENGINE_BACKUP_COLUMNS = DASHBOARD_MODULE.ENGINE_BACKUP_COLUMNS
ENGINE_RESTORE_SAMPLE_COLUMNS = DASHBOARD_MODULE.ENGINE_RESTORE_SAMPLE_COLUMNS


def _schema_v10_record(datestamp: str = "2026-08-27_13-41-36") -> dict[str, Any]:
    """Build a compact valid schema-v10 dashboard fixture.

    Args:
        datestamp: Unique run timestamp used as the primary key.

    Returns:
        Result record containing every normalized dashboard section.

    Raises:
        ValueError: If ``datestamp`` is empty.
    """
    if not datestamp:
        raise ValueError("datestamp must not be empty")
    return {
        "schema_version": 10,
        "datestamp": datestamp,
        "date": "2026-08-27",
        "test_name": "Large scale torture test",
        "advertise_class": "dev",
        "passed": True,
        "completed": True,
        "exit_code": 0,
        "failures": 0,
        "aborted_phase": None,
        "source_file_count": 100,
        "source_bytes": 10 * 1024**3,
        "full_elapsed_s": 200,
        "diff_elapsed_s": 5,
        "incr_elapsed_s": 5,
        "overall_elapsed_s": 500,
        "full_size_bytes": 9 * 1024**3,
        "diff_size_bytes": 1024**2,
        "incr_size_bytes": 2 * 1024**2,
        "memory_mib": {
            "dar_backup": 30.0,
            "dar": 20.0,
            "par2": 50.0,
            "manager": 40.0,
        },
        "dar_backup_version": "1.1.11",
        "dar_version": "2.7.21",
        "par2_version": "par2cmdline version 0.8.1",
        "image_reference": "dar-backup:dev",
        "image_id": "sha256:image",
        "image_revision": "abc123",
        "image_version": "dev",
        "harness_git_commit": "abc123",
        "harness_git_dirty": False,
        "backup_definition_sha256": "definition-hash",
        "configuration": {
            "slice_size": {"bytes": 1024**3},
            "par2": {"error_correction_percent": 5},
            "bitrot": {"mode": "edges", "corruption_percent": 2},
        },
        "workload": {
            "dataset_id": "fixture-v1",
            "source": {
                "regular_file_count": 100,
                "apparent_bytes": 10 * 1024**3,
                "allocated_bytes": 9 * 1024**3,
                "entry_count": 110,
            },
            "mutations": {
                "diff": {
                    "modified_file_count": 10,
                    "modified_apparent_bytes": 5000,
                    "created_file_count": 2,
                    "created_apparent_bytes": 2000,
                    "deleted_file_count": 1,
                },
                "incr": {
                    "modified_file_count": 11,
                    "modified_apparent_bytes": 6000,
                    "created_file_count": 2,
                    "created_apparent_bytes": 2000,
                    "deleted_file_count": 1,
                },
            },
        },
        "environment": {
            "host_profile_id": "host-one",
            "logical_cpu_count": 8,
            "memory_bytes": 16 * 1024**3,
            "disk_free_bytes": {"start": 100 * 1024**3, "end": 70 * 1024**3},
        },
        "phases": {
            "full_backup": {
                "status": "passed",
                "duration_s": 199.5,
                "resources": {
                    "sample_count": 39,
                    "peak_named_process_rss_mib": 70.0,
                    "peak_process_rss_mib": {"dar": 20.0, "par2": 50.0},
                },
            },
            "full_restore": {
                "status": "passed",
                "duration_s": 250.0,
                "resources": {
                    "sample_count": 40,
                    "peak_named_process_rss_mib": 60.0,
                    "peak_process_rss_mib": {"manager": 40.0, "dar": 20.0},
                },
            },
        },
        "artifacts": {
            "full": {
                "archive_bytes": 9 * 1024**3,
                "slice_count": 9,
                "smallest_slice_bytes": 1024**3,
                "largest_slice_bytes": 1024**3,
                "par2_file_count": 72,
                "par2_bytes": 500 * 1024**2,
            },
            "diff": {
                "archive_bytes": 1024**2,
                "slice_count": 1,
                "smallest_slice_bytes": 1024**2,
                "largest_slice_bytes": 1024**2,
                "par2_file_count": 8,
                "par2_bytes": 50_000,
            },
            "incr": {
                "archive_bytes": 2 * 1024**2,
                "slice_count": 1,
                "smallest_slice_bytes": 2 * 1024**2,
                "largest_slice_bytes": 2 * 1024**2,
                "par2_file_count": 8,
                "par2_bytes": 100_000,
            },
        },
        "checks": {
            "backup": {"full": "passed", "diff": "passed", "incr": "passed"},
            "full_restore": {"mode": "forced", "overall": "passed"},
        },
        "bitrot_evidence": {
            "full": {
                "seed": 18_446_744_073_709_551_615,
                "mode": "edges",
                "corruption_percent": 2,
                "edge_percent": 1,
                "length_bytes": 200,
                "region_count": 1,
                "buffer_bytes": 1024,
                "injection_elapsed_ms": 2,
                "repair_elapsed_ms": 30,
                "dar_detected_corruption": "passed",
                "dar_verify_after_repair": "passed",
                "status": "passed",
                "segments": [
                    {
                        "segment_index": 0,
                        "region_index": 0,
                        "slice": "archive.1.dar",
                        "slice_number": 1,
                        "slice_bytes": 10_000,
                        "offset_bytes": 0,
                        "length_bytes": 200,
                        "par2_data_blocks_found": 1980,
                        "par2_data_blocks_total": 2000,
                        "par2_data_blocks_damaged": 20,
                        "repair_elapsed_ms": 25,
                        "repair_status": "passed",
                    }
                ],
            }
        },
    }


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    """Write isolated JSONL fixture records.

    Args:
        path: Destination fixture file.
        records: JSON-compatible records to serialize.

    Returns:
        None.

    Raises:
        OSError: If the fixture cannot be written.
        TypeError: If a record is not JSON serializable.
    """
    if not records:
        raise ValueError("records must not be empty")
    path.write_text(
        "".join(json.dumps(record) + "\n" for record in records),
        encoding="utf-8",
    )


def _create_operational_metrics_database(path: Path) -> None:
    """Create a compatible operational metrics fixture with one successful run.

    Args:
        path: SQLite fixture path to create.

    Returns:
        None.

    Raises:
        sqlite3.Error: If fixture construction fails.
    """
    backup_definitions = ", ".join(
        f'"{column}" {"INTEGER" if column == "id" else "TEXT"}'
        for column in ENGINE_BACKUP_COLUMNS
    )
    sample_definitions = ", ".join(
        f'"{column}" {"INTEGER" if column in {"id", "fail_reason_id"} else "TEXT"}'
        for column in ENGINE_RESTORE_SAMPLE_COLUMNS
    )
    with sqlite3.connect(path) as database:
        database.execute(f"CREATE TABLE backup_runs ({backup_definitions})")
        database.execute(
            "CREATE TABLE restore_test_fail_reasons (id INTEGER, code TEXT)"
        )
        database.execute(
            f"CREATE TABLE restore_test_samples ({sample_definitions})"
        )
        backup_values: dict[str, object] = {
            column: None for column in ENGINE_BACKUP_COLUMNS
        }
        backup_values.update(
            {
                "id": 1,
                "backup_type": "FULL",
                "archive_name": "fixture_FULL_2026-08-27",
                "status": "SUCCESS",
                "dar_exit_code": 0,
                "run_id": "run-one",
                "archive_size_bytes": 9 * 1024**3,
            }
        )
        placeholders = ", ".join("?" for _ in ENGINE_BACKUP_COLUMNS)
        database.execute(
            f"INSERT INTO backup_runs VALUES ({placeholders})",
            tuple(backup_values[column] for column in ENGINE_BACKUP_COLUMNS),
        )
        database.execute(
            "INSERT INTO restore_test_fail_reasons VALUES (?, ?)", (1, "mismatch")
        )
        sample_values: dict[str, object] = {
            column: None for column in ENGINE_RESTORE_SAMPLE_COLUMNS
        }
        sample_values.update(
            {"id": 1, "run_id": "run-one", "result": "PASS", "file_path": "a.bin"}
        )
        sample_placeholders = ", ".join(
            "?" for _ in ENGINE_RESTORE_SAMPLE_COLUMNS
        )
        database.execute(
            f"INSERT INTO restore_test_samples VALUES ({sample_placeholders})",
            tuple(sample_values[column] for column in ENGINE_RESTORE_SAMPLE_COLUMNS),
        )


def test_build_dashboard_schema_v10_normalizes_jsonl_and_operational_metrics(
    tmp_path: Path,
) -> None:
    """Rich JSONL and operational SQLite evidence share one dashboard database.

    Args:
        tmp_path: Isolated source and destination directory.
    """
    results_jsonl = tmp_path / "results.jsonl"
    operational_database = tmp_path / "operational.db"
    output_database = tmp_path / "dashboard.db"
    _write_jsonl(results_jsonl, [_schema_v10_record()])
    _create_operational_metrics_database(operational_database)

    counts = build_dashboard_database(
        results_jsonl, output_database, operational_database
    )

    assert counts == {
        "result_record_count": 1,
        "engine_run_count": 1,
        "restore_sample_count": 1,
    }
    with sqlite3.connect(output_database) as database:
        assert database.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        run = database.execute(
            """SELECT dataset_id, source_bytes, full_throughput_mib_s,
                      full_restore_throughput_mib_s
                 FROM run_performance"""
        ).fetchone()
        assert run == ("fixture-v1", 10 * 1024**3, 51.2, 40.96)
        assert database.execute("SELECT COUNT(*) FROM phases").fetchone() == (2,)
        assert database.execute("SELECT COUNT(*) FROM artifacts").fetchone() == (3,)
        assert database.execute("SELECT COUNT(*) FROM mutations").fetchone() == (2,)
        assert database.execute("SELECT COUNT(*) FROM check_results").fetchone() == (
            5,
        )
        assert database.execute("SELECT seed FROM bitrot_phases").fetchone() == (
            "18446744073709551615",
        )
        assert database.execute("SELECT COUNT(*) FROM bitrot_segments").fetchone() == (
            1,
        )
        assert database.execute(
            "SELECT backup_type, status FROM engine_backup_runs"
        ).fetchone() == ("FULL", "SUCCESS")
        assert database.execute(
            "SELECT result FROM engine_restore_samples"
        ).fetchone() == ("PASS",)
        metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
        charts = metadata["plugins"]["datasette-dashboards"]["large-scale"]["charts"]
        for chart_name, chart in charts.items():
            try:
                database.execute(chart["query"]).fetchall()
            except sqlite3.Error as error:
                pytest.fail(f"dashboard chart {chart_name!r} has invalid SQL: {error}")


def test_dashboard_metadata_uses_supported_renderers_and_valid_vega_lite_specs() -> (
    None
):
    """Every chart uses a renderer recognized by datasette-dashboards.

    Raises:
        AssertionError: If a chart uses an unsupported renderer or malformed
            Vega-Lite display specification.
    """
    metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    charts = metadata["plugins"]["datasette-dashboards"]["large-scale"]["charts"]
    supported_renderers = {"vega", "vega-lite", "metric", "table", "map"}
    unsupported_shorthand_renderers = {"line", "bar", "scatter"}

    for chart_name, chart in charts.items():
        library = chart["library"]
        assert library in supported_renderers, (
            f"dashboard chart {chart_name!r} uses unsupported renderer {library!r}"
        )
        assert library not in unsupported_shorthand_renderers
        if library != "vega-lite":
            continue
        assert chart["display"].get("mark") in {"line", "point", "bar"}
        encoding = chart["display"].get("encoding")
        assert isinstance(encoding, dict)
        assert {"x", "y"}.issubset(encoding)
        assert all(
            isinstance(channel, dict) and channel.get("field")
            for channel_name, channel in encoding.items()
            if channel_name != "tooltip"
        )


def test_dashboard_throughput_chart_excludes_failed_runs(tmp_path: Path) -> None:
    """The throughput chart plots successful runs and omits failed evidence.

    Args:
        tmp_path: Isolated source and destination directory.
    """
    results_jsonl = tmp_path / "results.jsonl"
    output_database = tmp_path / "dashboard.db"
    successful_record = _schema_v10_record("2026-08-27_13-41-36")
    failed_record = _schema_v10_record("2026-08-27_14-41-36")
    failed_record["passed"] = False
    failed_record["exit_code"] = 1
    failed_record["failures"] = 1
    _write_jsonl(results_jsonl, [successful_record, failed_record])
    build_dashboard_database(results_jsonl, output_database)
    metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    query = metadata["plugins"]["datasette-dashboards"]["large-scale"]["charts"][
        "throughput-trend"
    ]["query"]

    with sqlite3.connect(output_database) as database:
        rows = database.execute(query).fetchall()

    assert rows == [
        ("2026-08-27T13:41:36", "FULL backup", 51.2),
        ("2026-08-27T13:41:36", "Full restore", 40.96),
    ]


def test_build_dashboard_legacy_schema_preserves_available_top_level_metrics(
    tmp_path: Path,
) -> None:
    """Historical schema-v2 rows remain useful without invented v10 details.

    Args:
        tmp_path: Isolated source and destination directory.
    """
    results_jsonl = tmp_path / "legacy.jsonl"
    output_database = tmp_path / "dashboard.db"
    legacy_record = {
        "schema_version": 2,
        "datestamp": "2026-07-01_00-00-00",
        "date": "2026-07-01",
        "passed": True,
        "failures": 0,
        "full_elapsed_s": 100,
        "diff_elapsed_s": 5,
        "incr_elapsed_s": 5,
        "memory_mb": {"dar_backup": 12.5, "dar": 10.0, "par2": 20.0},
    }
    _write_jsonl(results_jsonl, [legacy_record])

    counts = build_dashboard_database(results_jsonl, output_database)

    assert counts["result_record_count"] == 1
    with sqlite3.connect(output_database) as database:
        row = database.execute(
            """SELECT schema_version, full_elapsed_s, dar_backup_peak_rss_mib,
                      source_bytes, completed
                 FROM runs"""
        ).fetchone()
        assert row == (2, 100, 12.5, None, None)
        assert database.execute("SELECT COUNT(*) FROM phases").fetchone() == (0,)
        assert database.execute(
            "SELECT value FROM dashboard_metadata WHERE key = 'engine_run_count'"
        ).fetchone() == ("0",)


def test_build_dashboard_invalid_json_does_not_replace_existing_output(
    tmp_path: Path,
) -> None:
    """Malformed history fails before replacing a previously generated database.

    Args:
        tmp_path: Isolated source and destination directory.
    """
    results_jsonl = tmp_path / "broken.jsonl"
    output_database = tmp_path / "dashboard.db"
    results_jsonl.write_text("{not-json}\n", encoding="utf-8")
    output_database.write_bytes(b"previous-dashboard")

    with pytest.raises(ValueError, match="invalid JSON"):
        build_dashboard_database(results_jsonl, output_database)

    assert output_database.read_bytes() == b"previous-dashboard"


def test_build_dashboard_incompatible_operational_schema_fails_closed(
    tmp_path: Path,
) -> None:
    """An explicitly supplied but incompatible metrics database is rejected.

    Args:
        tmp_path: Isolated source and destination directory.
    """
    results_jsonl = tmp_path / "results.jsonl"
    operational_database = tmp_path / "operational.db"
    output_database = tmp_path / "dashboard.db"
    _write_jsonl(results_jsonl, [_schema_v10_record()])
    with sqlite3.connect(operational_database) as database:
        database.execute("CREATE TABLE unrelated (id INTEGER PRIMARY KEY)")
    output_database.write_bytes(b"previous-dashboard")

    with pytest.raises(ValueError, match="missing table 'backup_runs'"):
        build_dashboard_database(
            results_jsonl, output_database, operational_database
        )

    assert output_database.read_bytes() == b"previous-dashboard"
