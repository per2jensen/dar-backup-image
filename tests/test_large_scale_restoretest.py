# SPDX-FileCopyrightText: 2025-2026 Per Jensen
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This file is part of dar-backup-image:
# https://github.com/per2jensen/dar-backup-image
#
# License terms and warranty disclaimer:
# https://github.com/per2jensen/dar-backup-image/blob/main/LICENSE

"""Tests for large-scale restore-test evidence validation."""

from __future__ import annotations

import configparser
import importlib.util
import sqlite3
import sys
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).parents[1] / "scripts" / "large_scale_restoretest.py"
MODULE_SPEC = importlib.util.spec_from_file_location("large_scale_restoretest", MODULE_PATH)
if MODULE_SPEC is None or MODULE_SPEC.loader is None:
    raise RuntimeError(f"Unable to load restore-test helper from {MODULE_PATH}")
MODULE = importlib.util.module_from_spec(MODULE_SPEC)
sys.modules[MODULE_SPEC.name] = MODULE
MODULE_SPEC.loader.exec_module(MODULE)
validate_evidence = MODULE.validate_evidence
HARNESS_PATH = Path(__file__).parents[1] / "scripts" / "large_scale_test.sh"


def _write_evidence(tmp_path: Path, *, verified_slices: int = 4) -> tuple[Path, Path]:
    """Create representative log and metrics evidence.

    Args:
        tmp_path: Isolated pytest temporary directory.
        verified_slices: Verified slice count written to the log.

    Returns:
        Log and SQLite database paths.
    """
    log_path = tmp_path / "dar-backup.log"
    log_path.write_text(
        "Restore-test sampling: eligible=200 configured=3% calculated=6 capped=6\n"
        "Restore-test slice coverage: data-bearing=4 covered=4 additional-files=2\n"
        "Restore-test slice evidence: data-bearing=4 predicted=4 extracted=4 "
        f"verified={verified_slices}\n",
        encoding="utf-8",
    )
    database_path = tmp_path / "metrics.db"
    with sqlite3.connect(database_path) as database:
        database.execute(
            """CREATE TABLE backup_runs (
                id INTEGER PRIMARY KEY,
                backup_definition TEXT,
                backup_type TEXT,
                archive_name TEXT,
                status TEXT,
                restore_test_passed INTEGER,
                files_verified INTEGER
            )"""
        )
        database.execute(
            "INSERT INTO backup_runs VALUES (1, ?, ?, ?, ?, ?, ?)",
            ("large-scale-test", "FULL", "archive_FULL_2026-11-21", "SUCCESS", 1, 8),
        )
    return log_path, database_path


def test_generated_config_enables_percentage_and_slice_restore_tests() -> None:
    """Require the harness config to enable both advanced restore modes.

    Returns:
        None.
    """
    lines = HARNESS_PATH.read_text(encoding="utf-8").splitlines()
    function_index = lines.index("write_config() {")
    config_start = lines.index('    cat > "$CONFIG_FILE" << EOF', function_index) + 1
    config_end = lines.index("EOF", config_start)
    rendered = "\n".join(lines[config_start:config_end])
    rendered = rendered.replace("${RESTORETEST_PERCENT}", "3")
    rendered = rendered.replace("${RESTORETEST_MAX_FILES}", "1000")
    rendered = rendered.replace("${RESTORETEST_COVER_SLICES}", "true")
    parser = configparser.ConfigParser(interpolation=None)
    parser.read_string(rendered)

    assert parser.getfloat("MISC", "RESTORETEST_PERCENT") == 3.0
    assert parser.getint("MISC", "RESTORETEST_MAX_FILES") == 1000
    assert parser.getboolean("MISC", "RESTORETEST_COVER_SLICES") is True


def test_validate_evidence_complete_percentage_and_slice_restore_passes(
    tmp_path: Path,
) -> None:
    """Accept complete percentage and all-slice restore evidence.

    Args:
        tmp_path: Isolated pytest temporary directory.

    Returns:
        None.
    """
    log_path, database_path = _write_evidence(tmp_path)

    evidence = validate_evidence(
        log_path,
        database_path,
        "large-scale-test",
        "FULL",
        "archive_FULL_2026-11-21",
        3.0,
    )

    assert evidence.selected_files == 6
    assert evidence.verified_files == 8
    assert evidence.verified_slices == 4


def test_validate_evidence_incomplete_slice_restore_raises(tmp_path: Path) -> None:
    """Reject evidence that leaves a data-bearing slice unverified.

    Args:
        tmp_path: Isolated pytest temporary directory.

    Returns:
        None.
    """
    log_path, database_path = _write_evidence(tmp_path, verified_slices=3)

    with pytest.raises(ValueError, match="not every data-bearing slice"):
        validate_evidence(
            log_path,
            database_path,
            "large-scale-test",
            "FULL",
            "archive_FULL_2026-11-21",
            3.0,
        )


def test_validate_evidence_missing_percentage_sampling_raises(tmp_path: Path) -> None:
    """Reject a run without percentage-selection evidence.

    Args:
        tmp_path: Isolated pytest temporary directory.

    Returns:
        None.
    """
    log_path, database_path = _write_evidence(tmp_path)
    log_path.write_text("no sampling evidence\n", encoding="utf-8")

    with pytest.raises(ValueError, match="missing percentage sampling"):
        validate_evidence(
            log_path,
            database_path,
            "large-scale-test",
            "FULL",
            "archive_FULL_2026-11-21",
            3.0,
        )
