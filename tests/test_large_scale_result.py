# SPDX-FileCopyrightText: 2025-2026 Per Jensen
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This file is part of dar-backup-image:
# https://github.com/per2jensen/dar-backup-image
#
# License terms and warranty disclaimer:
# https://github.com/per2jensen/dar-backup-image/blob/main/LICENSE

"""Tests for schema-v10 large-scale test result records."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).parents[1] / "scripts" / "large_scale_result.py"
MODULE_SPEC = importlib.util.spec_from_file_location("large_scale_result", MODULE_PATH)
if MODULE_SPEC is None or MODULE_SPEC.loader is None:
    raise RuntimeError(f"Unable to load result writer from {MODULE_PATH}")
RESULT_MODULE = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(RESULT_MODULE)
build_record = RESULT_MODULE.build_record
regression_warnings = RESULT_MODULE.regression_warnings
write_result = RESULT_MODULE.write_result


def _base_environment() -> dict[str, str]:
    """Build complete valid result-writer input for one successful run.

    Returns:
        Environment values accepted by ``build_record``.
    """
    environment = {
        "LST_DATESTAMP": "2026-08-09_12-00-00",
        "LST_DATE": "2026-08-09",
        "LST_ADVERTISE_REQUESTED": "1",
        "LST_TEST_NAME": "Large scale torture test",
        "LST_ADVERTISE_CLASS": "v0.8.0-rc1",
        "LST_GIT_COMMIT": "1234567",
        "LST_DAR_BACKUP_VER": "1.2.3",
        "LST_DAR_VER": "2.7.21",
        "LST_PAR2_VER": "par2cmdline version 0.8.1",
        "LST_PYTHON_VER": "Python 3.12.3",
        "LST_OS_DESC": "Ubuntu 24.04.4 LTS",
        "LST_KERNEL": "6.17.0-test",
        "LST_FULL_ELAPSED": "4000",
        "LST_FULL_GIB": "116.23",
        "LST_DIFF_ELAPSED": "8",
        "LST_DIFF_GIB": "0.58",
        "LST_INCR_ELAPSED": "7",
        "LST_INCR_GIB": "0.59",
        "LST_DB_MIB": "33.2",
        "LST_DAR_MIB": "32.1",
        "LST_PAR2_MIB": "146.9",
        "LST_MGR_MIB": "40.6",
        "LST_FAILURES": "0",
        "LST_SCRIPT_VERSION": "11",
        "LST_HARNESS_GIT_COMMIT": "1234567890abcdef1234567890abcdef12345678",
        "LST_HARNESS_GIT_DIRTY": "0",
        "LST_IMAGE_REFERENCE": "per2jensen/dar-backup:0.8.0-rc1",
        "LST_IMAGE_ID": "sha256:image-config-digest",
        "LST_IMAGE_REPO_DIGEST": "per2jensen/dar-backup@sha256:manifest-digest",
        "LST_IMAGE_REVISION": "1234567",
        "LST_IMAGE_VERSION": "0.8.0-rc1",
        "LST_DATASET_ID": "photos-2026-fixed",
        "LST_SLICE_SIZE": "10G",
        "LST_SLICE_SIZE_BYTES": str(10 * 1024**3),
        "LST_SLICE_SIZE_SOURCE": "definition",
        "LST_PAR2_RATIO": "5",
        "LST_COMMAND_TIMEOUT_SECONDS": "86400",
        "LST_MIN_FREE_MULTIPLIER": "2",
        "LST_BITROT_ENABLED": "1",
        "LST_BITROT_MODE": "contiguous",
        "LST_BITROT_PERCENT": "2",
        "LST_SOURCE_FILE_COUNT": "42137",
        "LST_SOURCE_BYTES": "124802341776",
        "LST_SOURCE_ALLOCATED_BYTES": "124900000000",
        "LST_SOURCE_DIRECTORY_COUNT": "1500",
        "LST_SOURCE_SYMLINK_COUNT": "12",
        "LST_SOURCE_OTHER_ENTRY_COUNT": "0",
        "LST_SOURCE_HARD_LINK_GROUP_COUNT": "4",
        "LST_SOURCE_ZERO_FILE_COUNT": "3",
        "LST_SOURCE_SMALL_FILE_COUNT": "12000",
        "LST_SOURCE_MEDIUM_FILE_COUNT": "29000",
        "LST_SOURCE_LARGE_FILE_COUNT": "1134",
        "LST_SOURCE_MAX_FILE_BYTES": str(4 * 1024**3),
        "LST_DIFF_MODIFIED_FILE_COUNT": "116",
        "LST_DIFF_MODIFIED_APPARENT_BYTES": "310000000",
        "LST_DIFF_CREATED_FILE_COUNT": "2",
        "LST_DIFF_CREATED_BYTES": "2097250",
        "LST_DIFF_DELETED_FILE_COUNT": "1",
        "LST_INCR_MODIFIED_FILE_COUNT": "116",
        "LST_INCR_MODIFIED_APPARENT_BYTES": "310000000",
        "LST_INCR_CREATED_FILE_COUNT": "2",
        "LST_INCR_CREATED_BYTES": "2097250",
        "LST_INCR_DELETED_FILE_COUNT": "1",
        "LST_HOST_LOGICAL_CPU_COUNT": "16",
        "LST_HOST_MEMORY_BYTES": str(64 * 1024**3),
        "LST_DISK_FREE_BYTES_START": str(2 * 1024**4),
        "LST_DISK_FREE_BYTES_END": str(1500 * 1024**3),
        "LST_BACKUP_DEFINITION_SHA256": "definition-digest",
        "LST_FULL_BYTES": "124801234567",
        "LST_DIFF_BYTES": "622770258",
        "LST_INCR_BYTES": "633507676",
        "LST_OVERALL_ELAPSED": "4512",
        "LST_COMPLETED": "1",
        "LST_CURRENT_PHASE": "completed",
        "LST_EXIT_CODE": "0",
        "LST_MANAGER_DB_STATUS": "passed",
        "LST_FULL_BACKUP_STATUS": "passed",
        "LST_DIFF_BACKUP_STATUS": "passed",
        "LST_INCR_BACKUP_STATUS": "passed",
        "LST_FULL_ARCHIVE_STATUS": "passed",
        "LST_DIFF_ARCHIVE_STATUS": "passed",
        "LST_INCR_ARCHIVE_STATUS": "passed",
        "LST_FULL_PAR2_FILES_STATUS": "passed",
        "LST_DIFF_PAR2_FILES_STATUS": "passed",
        "LST_INCR_PAR2_FILES_STATUS": "passed",
        "LST_FULL_PAR2_VERIFY_STATUS": "passed",
        "LST_DIFF_PAR2_VERIFY_STATUS": "passed",
        "LST_INCR_PAR2_VERIFY_STATUS": "passed",
        "LST_FULL_BITROT_STATUS": "passed",
        "LST_DIFF_BITROT_STATUS": "passed",
        "LST_INCR_BITROT_STATUS": "passed",
        "LST_DIFF_CONTENTS_STATUS": "passed",
        "LST_INCR_CONTENTS_STATUS": "passed",
        "LST_PITR_EXECUTION_STATUS": "passed",
        "LST_PITR_STRUCTURE_STATUS": "passed",
        "LST_PITR_CHECKSUM_STATUS": "passed",
        "LST_PITR_PERMISSION_STATUS": "passed",
        "LST_PITR_OVERALL_STATUS": "passed",
        "LST_FULL_RESTORE_MODE": "forced",
        "LST_FULL_RESTORE_THRESHOLD_BYTES": str(25 * 1024**3),
        "LST_FULL_RESTORE_PERFORMED": "1",
        "LST_FULL_RESTORE_DECISION_REASON": "forced_by_user",
        "LST_FULL_RESTORE_EXECUTION_STATUS": "passed",
        "LST_FULL_RESTORE_CONTENT_STATUS": "passed",
        "LST_FULL_RESTORE_METADATA_STATUS": "passed",
        "LST_FULL_RESTORE_OVERALL_STATUS": "passed",
        "LST_FULL_RESTORE_FILE_COUNT": "42137",
        "LST_FULL_RESTORE_BYTES": "124802341776",
        "LST_FULL_RESTORE_ENTRY_COUNT": "42140",
        "LST_FULL_RESTORE_OWNERSHIP_COUNT": "42140",
        "LST_FULL_RESTORE_PERMISSION_COUNT": "42139",
        "LST_FULL_RESTORE_POSIX_ACL_COUNT": "2",
        "LST_FULL_RESTORE_XATTR_COUNT": "3",
        "LST_FULL_RESTORE_HARD_LINK_GROUP_COUNT": "1",
        "LST_RESTORE_METADATA_PROFILE": "portable-posix-v1",
        "LST_SOURCE_FILESYSTEM_TYPE": "btrfs",
        "LST_RESTORE_FILESYSTEM_TYPE": "btrfs",
        "LST_SOURCE_FILESYSTEM_DEVICE": "44",
        "LST_RESTORE_FILESYSTEM_DEVICE": "44",
        "LST_BITROT_SEED": "987654321",
        "LST_BITROT_EVIDENCE_FILE": "",
        "LST_EFFECTIVE_DEFINITION_FILE": "",
        "LST_BACKUP_DIR": "",
        "LST_PAR2_DIR": "",
        "LST_DEFINITION_NAME": "large-scale-test",
        "LST_PHASE_JOURNAL_FILE": "",
        "LST_RESOURCE_LOG_FILE": "",
        "LST_METRICS_SAMPLE_INTERVAL_SECONDS": "5",
    }
    return environment


def test_write_result_completed_run_appends_schema_v10_to_both_histories(
    tmp_path: Path,
) -> None:
    """A completed lifecycle writes compatible local and repository evidence.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    results_dir = tmp_path / "results"
    repo_dir = tmp_path / "repo"
    (repo_dir / "doc" / "test-report").mkdir(parents=True)
    record = build_record(_base_environment())

    warnings = write_result(record, results_dir, repo_dir)

    local_record = json.loads(
        (results_dir / "large-scale-results.jsonl").read_text(encoding="utf-8")
    )
    mirrored_record = json.loads(
        (repo_dir / "doc" / "test-report" / "large-scale-results.jsonl").read_text(
            encoding="utf-8"
        )
    )
    assert warnings == []
    assert local_record == mirrored_record
    assert local_record["schema_version"] == 10
    assert local_record["advertise"] is True
    assert local_record["test_name"] == "Large scale torture test"
    assert local_record["advertise_class"] == "v0.8.0-rc1"
    assert local_record["passed"] is True
    assert local_record["completed"] is True
    assert local_record["aborted_phase"] is None
    assert local_record["git_commit"] == "1234567"
    assert local_record["image_id"] == "sha256:image-config-digest"
    assert local_record["source_file_count"] == 42137
    assert local_record["full_size_bytes"] == 124801234567
    assert local_record["checks"]["pitr_restore"]["overall"] == "passed"
    assert local_record["checks"]["pitr_restore"]["permission_modes"] == "passed"
    assert local_record["checks"]["full_restore"] == {
        "mode": "forced",
        "threshold_bytes": 25 * 1024**3,
        "source_bytes": 124802341776,
        "performed": True,
        "decision_reason": "forced_by_user",
        "execution": "passed",
        "content_comparison": "passed",
        "portable_metadata": "passed",
        "overall": "passed",
        "restored_file_count": 42137,
        "restored_bytes": 124802341776,
        "restored_entry_count": 42140,
        "ownership_entry_count": 42140,
        "permission_entry_count": 42139,
        "posix_acl_count": 2,
        "portable_xattr_count": 3,
        "hard_link_group_count": 1,
        "metadata_profile": "portable-posix-v1",
        "source_filesystem": "btrfs",
        "restore_filesystem": "btrfs",
        "source_filesystem_device": 44,
        "restore_filesystem_device": 44,
        "same_filesystem": True,
    }
    assert local_record["bitrot_seed"] == 987654321
    assert local_record["bitrot_evidence"] is None
    assert {
        "configuration",
        "workload",
        "environment",
        "phases",
        "artifacts",
        "checks",
        "telemetry",
    }.issubset(local_record)
    assert local_record["configuration"]["slice_size"] == {
        "display": "10G",
        "bytes": 10 * 1024**3,
        "source": "definition",
    }
    assert local_record["workload"]["dataset_id"] == "photos-2026-fixed"
    assert local_record["workload"]["source"]["entry_count"] == 43649
    assert local_record["environment"]["logical_cpu_count"] == 16
    assert local_record["phases"]["full_backup"]["duration_s"] == 4000.0
    assert local_record["artifacts"]["full"]["archive_bytes"] == 124801234567
    assert local_record["telemetry"]["sampling_interval_s"] == 5


def test_build_record_summarizes_coarse_phase_and_artifact_evidence(
    tmp_path: Path,
) -> None:
    """Major phases receive coarse RSS aggregates and artifact summaries.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    backup_dir = tmp_path / "backups"
    par2_dir = tmp_path / "par2"
    backup_dir.mkdir()
    par2_dir.mkdir()
    (backup_dir / "large-scale-test_FULL_2026-08-09.1.dar").write_bytes(b"a" * 5)
    (backup_dir / "large-scale-test_FULL_2026-08-09.2.dar").write_bytes(b"b" * 3)
    (par2_dir / "large-scale-test_FULL_2026-08-09.1.dar.par2").write_bytes(
        b"p" * 2
    )
    definition = tmp_path / "definition"
    definition.write_text("-R /data\n-s 10G\n-z6\n-g photos\n", encoding="utf-8")
    journal = tmp_path / "phase-journal.tsv"
    journal.write_text(
        "start\tfull_backup\t1000000000\nend\tfull_backup\t2500000000\n",
        encoding="utf-8",
    )
    resource_log = tmp_path / "rss.log"
    resource_log.write_text(
        "12:00:00 pid=10 rss=2048 kB vsz=4096 kB cmd=par2 "
        "phase=full_backup epoch_ms=1000\n"
        "12:00:00 sample=resource phase=full_backup epoch_ms=1000 "
        "process_count=1 named_process_rss_kib=2048\n",
        encoding="utf-8",
    )
    environment = _base_environment()
    environment.update(
        {
            "LST_BACKUP_DIR": str(backup_dir),
            "LST_PAR2_DIR": str(par2_dir),
            "LST_EFFECTIVE_DEFINITION_FILE": str(definition),
            "LST_PHASE_JOURNAL_FILE": str(journal),
            "LST_RESOURCE_LOG_FILE": str(resource_log),
            "LST_FULL_BYTES": "8",
        }
    )

    record = build_record(environment)

    assert record["configuration"]["performance_options"]["compression"] == [
        "-z6"
    ]
    assert record["phases"]["full_backup"] == {
        "status": "passed",
        "duration_s": 1.5,
        "resources": {
            "sample_count": 1,
            "peak_named_process_rss_mib": 2.0,
            "peak_process_rss_mib": {"par2": 2.0},
        },
    }
    assert record["artifacts"]["full"]["slice_count"] == 2
    assert record["artifacts"]["full"]["smallest_slice_bytes"] == 3
    assert record["artifacts"]["full"]["largest_slice_bytes"] == 5
    assert record["artifacts"]["full"]["par2_file_count"] == 1
    assert record["telemetry"]["resource_monitor_status"] == "collected"
    assert record["telemetry"]["sample_count"] == 1


def test_build_record_malformed_phase_journal_raises_value_error(
    tmp_path: Path,
) -> None:
    """Incomplete phase timing evidence is rejected instead of guessed.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    journal = tmp_path / "phase-journal.tsv"
    journal.write_text("start\tfull_backup\t1000000000\n", encoding="utf-8")
    environment = _base_environment()
    environment["LST_PHASE_JOURNAL_FILE"] = str(journal)

    with pytest.raises(ValueError, match="unfinished phase"):
        build_record(environment)


def test_build_record_inconsistent_file_size_buckets_raise_value_error() -> None:
    """Workload shape cannot disagree with the selected regular-file count."""
    environment = _base_environment()
    environment["LST_SOURCE_SMALL_FILE_COUNT"] = "11999"

    with pytest.raises(ValueError, match="file-size buckets"):
        build_record(environment)


def test_build_record_high_frequency_sampling_interval_raises_value_error() -> None:
    """Schema telemetry rejects a profiler-like one-second sampling interval."""
    environment = _base_environment()
    environment["LST_METRICS_SAMPLE_INTERVAL_SECONDS"] = "1"

    with pytest.raises(ValueError, match="coarse 5-second"):
        build_record(environment)


def test_build_record_binary_units_use_iec_field_names() -> None:
    """Binary size and memory values are published under IEC unit names."""
    record = build_record(_base_environment())

    assert record["full_size_gib"] == 116.23
    assert record["diff_size_gib"] == 0.58
    assert record["incr_size_gib"] == 0.59
    assert record["memory_mib"] == {
        "dar_backup": 33.2,
        "dar": 32.1,
        "par2": 146.9,
        "manager": 40.6,
    }


def test_build_record_misleading_si_field_names_are_absent() -> None:
    """Schema v10 does not duplicate binary measurements under SI unit names."""
    record = build_record(_base_environment())

    for misleading_key in (
        "full_size_gb",
        "diff_size_gb",
        "incr_size_gb",
        "memory_mb",
    ):
        assert misleading_key not in record


def test_regression_warnings_compare_legacy_memory_history() -> None:
    """Schema-v9 memory values remain comparable with legacy history."""
    environment = _base_environment()
    environment["LST_DAR_MIB"] = "64.0"
    record = build_record(environment)
    legacy_history = [
        {
            "schema_version": 8,
            "passed": True,
            "full_elapsed_s": 4000,
            "memory_mb": {
                "dar_backup": 33.2,
                "dar": 32.0,
                "par2": 146.9,
                "manager": 40.6,
            },
        }
    ]

    warnings = regression_warnings(record, legacy_history)

    assert len(warnings) == 1
    assert warnings[0].startswith("Peak dar memory (MiB) (64.0) is 2.0x")


def test_write_result_aborted_run_records_phase_and_unreached_checks(
    tmp_path: Path,
) -> None:
    """An aborted lifecycle remains failed and distinguishes skipped/not-run checks.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    environment = _base_environment()
    environment.update(
        {
            "LST_FULL_ELAPSED": "19",
            "LST_FULL_GIB": "",
            "LST_DIFF_ELAPSED": "0",
            "LST_DIFF_GIB": "",
            "LST_INCR_ELAPSED": "0",
            "LST_INCR_GIB": "",
            "LST_FAILURES": "0",
            "LST_SOURCE_FILE_COUNT": "",
            "LST_SOURCE_BYTES": "",
            "LST_BACKUP_DEFINITION_SHA256": "",
            "LST_FULL_BYTES": "",
            "LST_DIFF_BYTES": "",
            "LST_INCR_BYTES": "",
            "LST_COMPLETED": "0",
            "LST_CURRENT_PHASE": "full_backup",
            "LST_EXIT_CODE": "17",
            "LST_MANAGER_DB_STATUS": "passed",
            "LST_FULL_BACKUP_STATUS": "failed",
            "LST_DIFF_BACKUP_STATUS": "not_run",
            "LST_INCR_BACKUP_STATUS": "not_run",
            "LST_FULL_ARCHIVE_STATUS": "not_run",
            "LST_DIFF_ARCHIVE_STATUS": "not_run",
            "LST_INCR_ARCHIVE_STATUS": "not_run",
            "LST_FULL_PAR2_FILES_STATUS": "not_run",
            "LST_DIFF_PAR2_FILES_STATUS": "not_run",
            "LST_INCR_PAR2_FILES_STATUS": "not_run",
            "LST_FULL_PAR2_VERIFY_STATUS": "not_run",
            "LST_DIFF_PAR2_VERIFY_STATUS": "not_run",
            "LST_INCR_PAR2_VERIFY_STATUS": "not_run",
            "LST_FULL_BITROT_STATUS": "skipped",
            "LST_DIFF_BITROT_STATUS": "skipped",
            "LST_INCR_BITROT_STATUS": "skipped",
            "LST_DIFF_CONTENTS_STATUS": "not_run",
            "LST_INCR_CONTENTS_STATUS": "not_run",
            "LST_PITR_EXECUTION_STATUS": "not_run",
            "LST_PITR_STRUCTURE_STATUS": "not_run",
            "LST_PITR_CHECKSUM_STATUS": "not_run",
            "LST_PITR_PERMISSION_STATUS": "not_run",
            "LST_PITR_OVERALL_STATUS": "not_run",
            "LST_FULL_RESTORE_PERFORMED": "0",
            "LST_FULL_RESTORE_DECISION_REASON": "not_evaluated",
            "LST_FULL_RESTORE_EXECUTION_STATUS": "not_run",
            "LST_FULL_RESTORE_CONTENT_STATUS": "not_run",
            "LST_FULL_RESTORE_METADATA_STATUS": "not_run",
            "LST_FULL_RESTORE_OVERALL_STATUS": "not_run",
            "LST_FULL_RESTORE_FILE_COUNT": "",
            "LST_FULL_RESTORE_BYTES": "",
            "LST_FULL_RESTORE_ENTRY_COUNT": "",
            "LST_FULL_RESTORE_OWNERSHIP_COUNT": "",
            "LST_FULL_RESTORE_PERMISSION_COUNT": "",
            "LST_FULL_RESTORE_POSIX_ACL_COUNT": "",
            "LST_FULL_RESTORE_XATTR_COUNT": "",
            "LST_FULL_RESTORE_HARD_LINK_GROUP_COUNT": "",
        }
    )
    record = build_record(environment)

    write_result(record, tmp_path / "results", None)

    stored_record = json.loads(
        (tmp_path / "results" / "large-scale-results.jsonl").read_text(
            encoding="utf-8"
        )
    )
    assert stored_record["passed"] is False
    assert stored_record["advertise"] is False
    assert stored_record["completed"] is False
    assert stored_record["aborted_phase"] == "full_backup"
    assert stored_record["exit_code"] == 17
    assert stored_record["full_size_gib"] is None
    assert stored_record["source_bytes"] is None
    assert stored_record["checks"]["backup"]["full"] == "failed"
    assert stored_record["checks"]["backup"]["diff"] == "not_run"
    assert stored_record["checks"]["bitrot_repair"]["full"] == "skipped"


def test_write_result_existing_schema_v2_history_remains_readable(
    tmp_path: Path,
) -> None:
    """Appending schema v10 preserves an existing schema-v2 JSONL record.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    history_path = results_dir / "large-scale-results.jsonl"
    schema_v2_record = {
        "schema_version": 2,
        "full_elapsed_s": 4000,
        "memory_mb": {"dar_backup": 30.0, "dar": 32.0, "par2": 146.0, "manager": 40.0},
        "passed": True,
    }
    history_path.write_text(json.dumps(schema_v2_record) + "\n", encoding="utf-8")

    write_result(build_record(_base_environment()), results_dir, None)

    records = [json.loads(line) for line in history_path.read_text(encoding="utf-8").splitlines()]
    assert len(records) == 2
    assert records[0] == schema_v2_record
    assert records[1]["schema_version"] == 10


def test_build_record_includes_incremental_bitrot_evidence(tmp_path: Path) -> None:
    """Schema v10 retains per-phase bitrot and PAR2 block evidence.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    evidence = {
        "full": {
            "seed": 987654321,
            "status": "passed",
            "segments": [
                {
                    "slice": "archive.7.dar",
                    "par2_data_blocks_found": 1959,
                    "par2_data_blocks_total": 2000,
                    "par2_data_blocks_damaged": 41,
                }
            ],
        }
    }
    evidence_path = tmp_path / "bitrot-evidence.json"
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
    environment = _base_environment()
    environment["LST_BITROT_EVIDENCE_FILE"] = str(evidence_path)

    record = build_record(environment)

    assert record["schema_version"] == 10
    assert record["bitrot_evidence"] == evidence


def test_build_record_malformed_bitrot_evidence_raises_value_error(
    tmp_path: Path,
) -> None:
    """Malformed evidence cannot silently enter the release history.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    evidence_path = tmp_path / "bitrot-evidence.json"
    evidence_path.write_text("{not-json", encoding="utf-8")
    environment = _base_environment()
    environment["LST_BITROT_EVIDENCE_FILE"] = str(evidence_path)

    with pytest.raises(ValueError, match="Malformed JSON evidence"):
        build_record(environment)


def test_build_record_passed_pitr_with_failed_permissions_raises_value_error() -> None:
    """A successful PITR claim requires successful permission verification."""
    environment = _base_environment()
    environment["LST_PITR_PERMISSION_STATUS"] = "failed"

    with pytest.raises(ValueError, match="requires passed execution.*permission modes"):
        build_record(environment)


def test_build_record_passed_full_restore_with_failed_metadata_raises_value_error() -> None:
    """A successful full-restore claim requires portable metadata verification."""
    environment = _base_environment()
    environment["LST_FULL_RESTORE_METADATA_STATUS"] = "failed"

    with pytest.raises(ValueError, match="requires passed execution.*metadata"):
        build_record(environment)


def test_build_record_different_restore_filesystem_device_raises_value_error() -> None:
    """Cross-filesystem evidence violates the explicit schema-v8 contract."""
    environment = _base_environment()
    environment["LST_RESTORE_FILESYSTEM_DEVICE"] = "45"

    with pytest.raises(ValueError, match="must be on the same filesystem device"):
        build_record(environment)


def test_build_record_unsupported_filesystem_type_raises_value_error() -> None:
    """Filesystems outside the documented portable profile are rejected."""
    environment = _base_environment()
    environment["LST_SOURCE_FILESYSTEM_TYPE"] = "xfs"
    environment["LST_RESTORE_FILESYSTEM_TYPE"] = "xfs"

    with pytest.raises(ValueError, match="LST_SOURCE_FILESYSTEM_TYPE"):
        build_record(environment)


def test_build_record_missing_acl_fixture_evidence_raises_value_error() -> None:
    """A passed portable profile must prove both access and default ACLs."""
    environment = _base_environment()
    environment["LST_FULL_RESTORE_POSIX_ACL_COUNT"] = "1"

    with pytest.raises(ValueError, match="access and default POSIX ACL fixtures"):
        build_record(environment)


def test_build_record_advertise_requested_success_above_100_gib_is_eligible() -> None:
    """An opted-in successful run above the inclusive threshold is advertisable."""
    environment = _base_environment()
    environment["LST_SOURCE_BYTES"] = str(100 * 1024**3 + 1)

    record = build_record(environment)

    assert record["advertise"] is True


def test_build_record_advertise_not_requested_is_not_eligible() -> None:
    """A qualifying run remains private unless publication was requested."""
    environment = _base_environment()
    environment["LST_ADVERTISE_REQUESTED"] = "0"

    record = build_record(environment)

    assert record["advertise"] is False


def test_build_record_source_exactly_100_gib_is_eligible() -> None:
    """The advertised source-size rule includes exactly 100 GiB."""
    environment = _base_environment()
    environment["LST_SOURCE_BYTES"] = str(100 * 1024**3)

    record = build_record(environment)

    assert record["advertise"] is True


def test_build_record_source_one_byte_below_100_gib_is_not_eligible() -> None:
    """The inclusive publication boundary still rejects smaller sources."""
    environment = _base_environment()
    environment["LST_SOURCE_BYTES"] = str(100 * 1024**3 - 1)

    record = build_record(environment)

    assert record["advertise"] is False


def test_build_record_missing_source_size_is_not_eligible() -> None:
    """A run without measured source bytes cannot be advertised."""
    environment = _base_environment()
    environment["LST_SOURCE_BYTES"] = ""

    record = build_record(environment)

    assert record["advertise"] is False


def test_build_record_failed_run_is_not_eligible() -> None:
    """An opted-in run with a recorded failure cannot be advertised."""
    environment = _base_environment()
    environment["LST_FAILURES"] = "1"
    environment["LST_EXIT_CODE"] = "1"

    record = build_record(environment)

    assert record["passed"] is False
    assert record["advertise"] is False


def test_build_record_custom_publication_identity_is_preserved() -> None:
    """Specialized tests retain their explicit public name and class."""
    environment = _base_environment()
    environment["LST_TEST_NAME"] = "DAR 2.7 restore using DAR 2.8"
    environment["LST_ADVERTISE_CLASS"] = "2.7-to-2.8-restore"

    record = build_record(environment)

    assert record["test_name"] == "DAR 2.7 restore using DAR 2.8"
    assert record["advertise_class"] == "2.7-to-2.8-restore"


def test_build_record_empty_publication_name_raises_value_error() -> None:
    """An empty stable publication-envelope name is rejected."""
    environment = _base_environment()
    environment["LST_TEST_NAME"] = ""

    with pytest.raises(ValueError, match="LST_TEST_NAME"):
        build_record(environment)


def test_build_record_auto_restore_above_threshold_is_explicitly_skipped() -> None:
    """Auto mode records an unambiguous size-based skip decision."""
    environment = _base_environment()
    environment.update(
        {
            "LST_FULL_RESTORE_MODE": "auto",
            "LST_FULL_RESTORE_PERFORMED": "0",
            "LST_FULL_RESTORE_DECISION_REASON": "source_exceeds_threshold",
            "LST_FULL_RESTORE_EXECUTION_STATUS": "skipped",
            "LST_FULL_RESTORE_CONTENT_STATUS": "skipped",
            "LST_FULL_RESTORE_METADATA_STATUS": "skipped",
            "LST_FULL_RESTORE_OVERALL_STATUS": "skipped",
            "LST_FULL_RESTORE_FILE_COUNT": "",
            "LST_FULL_RESTORE_BYTES": "",
            "LST_FULL_RESTORE_ENTRY_COUNT": "",
            "LST_FULL_RESTORE_OWNERSHIP_COUNT": "",
            "LST_FULL_RESTORE_PERMISSION_COUNT": "",
            "LST_FULL_RESTORE_POSIX_ACL_COUNT": "",
            "LST_FULL_RESTORE_XATTR_COUNT": "",
            "LST_FULL_RESTORE_HARD_LINK_GROUP_COUNT": "",
        }
    )

    record = build_record(environment)

    assert record["checks"]["full_restore"]["performed"] is False
    assert record["checks"]["full_restore"]["decision_reason"] == (
        "source_exceeds_threshold"
    )
    assert record["checks"]["full_restore"]["overall"] == "skipped"


def test_build_record_auto_restore_within_threshold_is_explicitly_passed() -> None:
    """Auto mode records successful execution for a source below 25 GiB."""
    environment = _base_environment()
    source_bytes = 7 * 1024**3
    environment.update(
        {
            "LST_SOURCE_BYTES": str(source_bytes),
            "LST_FULL_RESTORE_MODE": "auto",
            "LST_FULL_RESTORE_DECISION_REASON": "source_within_threshold",
            "LST_FULL_RESTORE_BYTES": str(source_bytes),
        }
    )

    record = build_record(environment)

    full_restore = record["checks"]["full_restore"]
    assert full_restore["source_bytes"] == source_bytes
    assert full_restore["performed"] is True
    assert full_restore["decision_reason"] == "source_within_threshold"
    assert full_restore["overall"] == "passed"


def test_build_record_disabled_restore_is_explicitly_skipped() -> None:
    """Disabled mode records user intent separately from an automatic skip."""
    environment = _base_environment()
    environment.update(
        {
            "LST_FULL_RESTORE_MODE": "disabled",
            "LST_FULL_RESTORE_PERFORMED": "0",
            "LST_FULL_RESTORE_DECISION_REASON": "disabled_by_user",
            "LST_FULL_RESTORE_EXECUTION_STATUS": "skipped",
            "LST_FULL_RESTORE_CONTENT_STATUS": "skipped",
            "LST_FULL_RESTORE_METADATA_STATUS": "skipped",
            "LST_FULL_RESTORE_OVERALL_STATUS": "skipped",
            "LST_FULL_RESTORE_FILE_COUNT": "",
            "LST_FULL_RESTORE_BYTES": "",
            "LST_FULL_RESTORE_ENTRY_COUNT": "",
            "LST_FULL_RESTORE_OWNERSHIP_COUNT": "",
            "LST_FULL_RESTORE_PERMISSION_COUNT": "",
            "LST_FULL_RESTORE_POSIX_ACL_COUNT": "",
            "LST_FULL_RESTORE_XATTR_COUNT": "",
            "LST_FULL_RESTORE_HARD_LINK_GROUP_COUNT": "",
        }
    )

    record = build_record(environment)

    full_restore = record["checks"]["full_restore"]
    assert full_restore["performed"] is False
    assert full_restore["decision_reason"] == "disabled_by_user"
    assert full_restore["overall"] == "skipped"


def test_build_record_forced_restore_accepts_source_above_threshold() -> None:
    """Forced mode can record a successful 400 GiB complete restore."""
    environment = _base_environment()
    source_bytes = 400 * 1024**3
    environment.update(
        {
            "LST_SOURCE_BYTES": str(source_bytes),
            "LST_FULL_RESTORE_MODE": "forced",
            "LST_FULL_RESTORE_PERFORMED": "1",
            "LST_FULL_RESTORE_DECISION_REASON": "forced_by_user",
            "LST_FULL_RESTORE_FILE_COUNT": "220487",
            "LST_FULL_RESTORE_BYTES": str(source_bytes),
            "LST_FULL_RESTORE_ENTRY_COUNT": "220500",
            "LST_FULL_RESTORE_OWNERSHIP_COUNT": "220500",
            "LST_FULL_RESTORE_PERMISSION_COUNT": "220499",
        }
    )

    record = build_record(environment)

    full_restore = record["checks"]["full_restore"]
    assert full_restore["source_bytes"] == source_bytes
    assert full_restore["threshold_bytes"] == 25 * 1024**3
    assert full_restore["performed"] is True
    assert full_restore["overall"] == "passed"


def test_build_record_unperformed_restore_cannot_pass() -> None:
    """Contradictory full-restore evidence is rejected instead of published."""
    environment = _base_environment()
    environment["LST_FULL_RESTORE_PERFORMED"] = "0"

    with pytest.raises(ValueError, match="cannot pass when it was not performed"):
        build_record(environment)
