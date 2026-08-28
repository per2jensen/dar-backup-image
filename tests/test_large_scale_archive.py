# SPDX-FileCopyrightText: 2025-2026 Per Jensen
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This file is part of dar-backup-image:
# https://github.com/per2jensen/dar-backup-image
#
# License terms and warranty disclaimer:
# https://github.com/per2jensen/dar-backup-image/blob/main/LICENSE

"""Tests for large-scale archive discovery across backup phases."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "large_scale_archive.py"


def run_archive_discovery(
    backup_dir: Path,
    definition_name: str,
    backup_type: str,
) -> subprocess.CompletedProcess[str]:
    """Run archive discovery against an isolated real directory.

    Args:
        backup_dir: Directory containing test archive slices.
        definition_name: Expected archive filename prefix.
        backup_type: Backup phase to discover.

    Returns:
        Completed helper process with captured text output.
    """
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--backup-dir",
            str(backup_dir),
            "--definition-name",
            definition_name,
            "--backup-type",
            backup_type,
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def test_find_archive_base_midnight_rollover_returns_next_day_diff(
    tmp_path: Path,
) -> None:
    """A DIFF created after midnight is found independently of the FULL date.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    (tmp_path / "large-scale-test_FULL_2026-08-10.1.dar").touch()
    (tmp_path / "large-scale-test_DIFF_2026-08-11.1.dar").touch()
    (tmp_path / "large-scale-test_DIFF_2026-08-11.2.dar").touch()

    result = run_archive_discovery(tmp_path, "large-scale-test", "DIFF")

    assert result.returncode == 0
    assert result.stdout.strip() == "large-scale-test_DIFF_2026-08-11"
    assert result.stderr == ""


def test_find_archive_base_missing_phase_returns_failure(tmp_path: Path) -> None:
    """A missing phase archive fails with its expected filename pattern.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    (tmp_path / "large-scale-test_FULL_2026-08-10.1.dar").touch()

    result = run_archive_discovery(tmp_path, "large-scale-test", "DIFF")

    assert result.returncode == 1
    assert result.stdout == ""
    assert "No archive first slice matching" in result.stderr
    assert "large-scale-test_DIFF_YYYY-MM-DD.1.dar" in result.stderr


def test_find_archive_base_multiple_phase_archives_returns_failure(
    tmp_path: Path,
) -> None:
    """Multiple phase archive bases fail instead of choosing one silently.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    (tmp_path / "large-scale-test_DIFF_2026-08-10.1.dar").touch()
    (tmp_path / "large-scale-test_DIFF_2026-08-11.1.dar").touch()

    result = run_archive_discovery(tmp_path, "large-scale-test", "DIFF")

    assert result.returncode == 1
    assert result.stdout == ""
    assert "Multiple archive first slices match" in result.stderr
    assert "large-scale-test_DIFF_2026-08-10.1.dar" in result.stderr
    assert "large-scale-test_DIFF_2026-08-11.1.dar" in result.stderr
