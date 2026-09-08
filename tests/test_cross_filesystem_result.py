# SPDX-FileCopyrightText: 2025-2026 Per Jensen
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This file is part of dar-backup-image:
# https://github.com/per2jensen/dar-backup-image
#
# License terms and warranty disclaimer:
# https://github.com/per2jensen/dar-backup-image/blob/main/LICENSE

"""Tests for cross-filesystem JSONL result records."""

from __future__ import annotations

import importlib.util
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys

import pytest


MODULE_PATH = Path(__file__).parents[1] / "scripts" / "cross_filesystem_result.py"
MODULE_SPEC = importlib.util.spec_from_file_location(
    "cross_filesystem_result", MODULE_PATH
)
if MODULE_SPEC is None or MODULE_SPEC.loader is None:
    raise RuntimeError(f"Unable to load result writer from {MODULE_PATH}")
RESULT_MODULE = importlib.util.module_from_spec(MODULE_SPEC)
sys.modules[MODULE_SPEC.name] = RESULT_MODULE
MODULE_SPEC.loader.exec_module(RESULT_MODULE)
append_record = RESULT_MODULE.append_record
build_record = RESULT_MODULE.build_record


def _environment() -> dict[str, str]:
    """Build a complete successful result environment.

    Returns:
        Valid result variables for both scenario slots.
    """
    environment = {
        "CFT_RUN_ID": "20260908T120000Z-123",
        "CFT_STARTED_AT": "2026-09-08T12:00:00Z",
        "CFT_FINISHED_AT": "2026-09-08T12:00:05Z",
        "CFT_COMPLETED": "1",
        "CFT_ABORTED_PHASE": "",
        "CFT_EXIT_CODE": "0",
        "CFT_PASSED": "1",
        "CFT_REQUESTED_SCENARIO": "home-to-data",
        "CFT_BACKUP_USER": "pj",
        "CFT_BACKUP_UID": "1000",
        "CFT_BACKUP_GID": "1000",
        "CFT_DATASET_ID": "documents-v1",
        "CFT_IMAGE_REFERENCE": "dar-backup:dev",
        "CFT_IMAGE_ID": "sha256:image",
        "CFT_IMAGE_REPO_DIGEST": "",
        "CFT_IMAGE_REVISION": "abc123",
        "CFT_IMAGE_VERSION": "dev",
        "CFT_SLICE_SIZE": "1G",
        "CFT_PAR2_RATIO": "5",
        "CFT_TIMEOUT": "86400",
        "CFT_KEEP": "0",
        "CFT_ELAPSED_SECONDS": "5",
        "CFT_SCRIPT_VERSION": "1",
        "CFT_GIT_COMMIT": "abcdef",
        "CFT_GIT_DIRTY": "0",
    }
    for prefix, status, expected, observed in (
        ("ETC", "skipped", "permission_denied", "not_run"),
        ("HOME", "passed", "success", "success"),
    ):
        environment.update(
            {
                f"CFT_{prefix}_STATUS": status,
                f"CFT_{prefix}_EXPECTED_OUTCOME": expected,
                f"CFT_{prefix}_OBSERVED_OUTCOME": observed,
                f"CFT_{prefix}_FAILURE_REASON": "",
                f"CFT_{prefix}_SELECTION_COUNT": "0" if prefix == "ETC" else "2",
                f"CFT_{prefix}_DEFINITION_SHA256": "definition-hash",
            }
        )
        check_status = "skipped" if status == "skipped" else "passed"
        for check in RESULT_MODULE.CHECK_NAMES:
            environment[f"CFT_{prefix}_CHECK_{check.upper()}"] = check_status
    environment.update(
        {
            "CFT_HOME_SOURCE_ENTRIES": "5",
            "CFT_HOME_SOURCE_FILES": "2",
            "CFT_HOME_SOURCE_BYTES": "4096",
            "CFT_HOME_SOURCE_FSTYPE": "btrfs",
            "CFT_HOME_SOURCE_DEVICE": "44",
            "CFT_HOME_ARCHIVE_BYTES": "2048",
            "CFT_HOME_ARCHIVE_SLICES": "1",
            "CFT_HOME_ARCHIVE_FSTYPE": "zfs",
            "CFT_HOME_ARCHIVE_DEVICE": "45",
            "CFT_HOME_RESTORE_FSTYPE": "zfs",
            "CFT_HOME_RESTORE_DEVICE": "45",
            "CFT_HOME_RESTORE_ENTRIES": "5",
            "CFT_HOME_RESTORE_FILES": "2",
            "CFT_HOME_RESTORE_BYTES": "4096",
            "CFT_HOME_RESTORE_XATTRS": "1",
            "CFT_HOME_RESTORE_HARD_LINK_GROUPS": "1",
            "CFT_HOME_BACKUP_SECONDS": "1",
            "CFT_HOME_VERIFY_SECONDS": "2",
            "CFT_HOME_RESTORE_SECONDS": "1",
            "CFT_HOME_TOTAL_SECONDS": "5",
        }
    )
    return environment


def test_build_record_success_contains_nested_scenario_evidence() -> None:
    """A completed run produces schema-v1 nested evidence."""
    record = build_record(_environment())

    assert record["schema_version"] == 1
    assert record["passed"] is True
    assert record["scenarios"]["etc_to_home"]["status"] == "skipped"
    home = record["scenarios"]["home_to_data"]
    assert home["source"]["filesystem"] == {"type": "btrfs", "device": 44}
    assert home["restore"]["filesystem"] == {"type": "zfs", "device": 45}


def test_build_record_expected_permission_denial_can_pass() -> None:
    """The deliberate non-root `/etc` denial is a successful test outcome."""
    environment = _environment()
    environment["CFT_REQUESTED_SCENARIO"] = "etc-to-home"
    environment["CFT_ETC_STATUS"] = "passed"
    environment["CFT_ETC_OBSERVED_OUTCOME"] = "permission_denied"
    environment["CFT_HOME_STATUS"] = "skipped"
    for check in RESULT_MODULE.CHECK_NAMES:
        environment[f"CFT_ETC_CHECK_{check.upper()}"] = "skipped"
    environment["CFT_ETC_CHECK_BACKUP"] = "passed"
    environment["CFT_ETC_CHECK_OVERALL"] = "passed"

    record = build_record(environment)

    assert record["passed"] is True
    assert record["scenarios"]["etc_to_home"]["observed_backup_outcome"] == (
        "permission_denied"
    )


def test_build_record_aborted_run_cannot_claim_passed() -> None:
    """An incomplete run cannot be serialized as passing."""
    environment = _environment()
    environment["CFT_COMPLETED"] = "0"
    environment["CFT_ABORTED_PHASE"] = "home-to-data_backup"

    with pytest.raises(ValueError, match="must be completed"):
        build_record(environment)


def test_append_record_preserves_one_compact_json_object_per_line(
    tmp_path: Path,
) -> None:
    """Repeated durable appends produce valid independent JSON lines.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    result_path = tmp_path / "results" / "cross-filesystem-results.jsonl"
    record = build_record(_environment())

    append_record(result_path, record)
    append_record(result_path, record)

    lines = result_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert all(json.loads(line)["run_id"] == record["run_id"] for line in lines)


def test_append_record_concurrent_writers_do_not_interleave(tmp_path: Path) -> None:
    """File locking preserves every concurrent JSONL record.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    result_path = tmp_path / "cross-filesystem-results.jsonl"
    records = []
    for index in range(20):
        environment = _environment()
        environment["CFT_RUN_ID"] = f"run-{index}"
        records.append(build_record(environment))

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(lambda record: append_record(result_path, record), records))

    stored = [
        json.loads(line)
        for line in result_path.read_text(encoding="utf-8").splitlines()
    ]
    assert {record["run_id"] for record in stored} == {
        record["run_id"] for record in records
    }


def test_record_does_not_contain_home_source_paths() -> None:
    """Structured history includes only opaque selection identity."""
    encoded = json.dumps(build_record(_environment()))

    assert "/home/pj" not in encoded
    assert "Documents" not in encoded
    assert "documents-v1" in encoded
