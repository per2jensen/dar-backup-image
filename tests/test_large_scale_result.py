"""Tests for schema-v4 large-scale test result records."""

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
write_result = RESULT_MODULE.write_result


def _base_environment() -> dict[str, str]:
    """Build complete valid result-writer input for one successful run.

    Returns:
        Environment values accepted by ``build_record``.
    """
    environment = {
        "LST_DATESTAMP": "2026-08-09_12-00-00",
        "LST_DATE": "2026-08-09",
        "LST_GIT_COMMIT": "1234567",
        "LST_DAR_BACKUP_VER": "1.2.3",
        "LST_DAR_VER": "2.7.21",
        "LST_PAR2_VER": "par2cmdline version 0.8.1",
        "LST_PYTHON_VER": "Python 3.12.3",
        "LST_OS_DESC": "Ubuntu 24.04.4 LTS",
        "LST_KERNEL": "6.17.0-test",
        "LST_FULL_ELAPSED": "4000",
        "LST_FULL_GB": "116.23",
        "LST_DIFF_ELAPSED": "8",
        "LST_DIFF_GB": "0.58",
        "LST_INCR_ELAPSED": "7",
        "LST_INCR_GB": "0.59",
        "LST_DB_MB": "33.2",
        "LST_DAR_MB": "32.1",
        "LST_PAR2_MB": "146.9",
        "LST_MGR_MB": "40.6",
        "LST_FAILURES": "0",
        "LST_SCRIPT_VERSION": "11",
        "LST_HARNESS_GIT_COMMIT": "1234567890abcdef1234567890abcdef12345678",
        "LST_HARNESS_GIT_DIRTY": "0",
        "LST_IMAGE_REFERENCE": "per2jensen/dar-backup:0.8.0-rc1",
        "LST_IMAGE_ID": "sha256:image-config-digest",
        "LST_IMAGE_REPO_DIGEST": "per2jensen/dar-backup@sha256:manifest-digest",
        "LST_IMAGE_REVISION": "1234567",
        "LST_IMAGE_VERSION": "0.8.0-rc1",
        "LST_SOURCE_FILE_COUNT": "42137",
        "LST_SOURCE_BYTES": "124802341776",
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
        "LST_PITR_OVERALL_STATUS": "passed",
        "LST_BITROT_SEED": "987654321",
        "LST_BITROT_EVIDENCE_FILE": "",
    }
    return environment


def test_write_result_completed_run_appends_schema_v4_to_both_histories(
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
    assert local_record["schema_version"] == 4
    assert local_record["passed"] is True
    assert local_record["completed"] is True
    assert local_record["aborted_phase"] is None
    assert local_record["git_commit"] == "1234567"
    assert local_record["image_id"] == "sha256:image-config-digest"
    assert local_record["source_file_count"] == 42137
    assert local_record["full_size_bytes"] == 124801234567
    assert local_record["checks"]["pitr_restore"]["overall"] == "passed"
    assert local_record["bitrot_seed"] == 987654321
    assert local_record["bitrot_evidence"] is None


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
            "LST_FULL_GB": "",
            "LST_DIFF_ELAPSED": "0",
            "LST_DIFF_GB": "",
            "LST_INCR_ELAPSED": "0",
            "LST_INCR_GB": "",
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
            "LST_PITR_OVERALL_STATUS": "not_run",
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
    assert stored_record["completed"] is False
    assert stored_record["aborted_phase"] == "full_backup"
    assert stored_record["exit_code"] == 17
    assert stored_record["full_size_gb"] is None
    assert stored_record["source_bytes"] is None
    assert stored_record["checks"]["backup"]["full"] == "failed"
    assert stored_record["checks"]["backup"]["diff"] == "not_run"
    assert stored_record["checks"]["bitrot_repair"]["full"] == "skipped"


def test_write_result_existing_schema_v2_history_remains_readable(
    tmp_path: Path,
) -> None:
    """Appending schema v4 preserves an existing schema-v2 JSONL record.

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
    assert records[1]["schema_version"] == 4


def test_build_record_includes_incremental_bitrot_evidence(tmp_path: Path) -> None:
    """Schema v4 embeds per-phase bitrot and PAR2 block evidence.

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

    assert record["schema_version"] == 4
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
