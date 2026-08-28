# SPDX-FileCopyrightText: 2025-2026 Per Jensen
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This file is part of dar-backup-image:
# https://github.com/per2jensen/dar-backup-image
#
# License terms and warranty disclaimer:
# https://github.com/per2jensen/dar-backup-image/blob/main/LICENSE

"""Regression tests for scripts/backup-restore-compare.sh helpers."""

import os
import subprocess
from pathlib import Path


SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "backup-restore-compare.sh"


def run_bash_function(function_name: str, *args: str) -> subprocess.CompletedProcess[str]:
    """Source the E2E script and invoke one named helper function.

    Args:
        function_name: Bash function to invoke.
        *args: Positional arguments passed to the Bash function.

    Returns:
        The completed Bash subprocess with captured text output.

    Raises:
        ValueError: If function_name is empty.
    """
    if not function_name:
        raise ValueError("function_name must not be empty")

    command = """
source "$1"
function_name="$2"
shift 2
"${function_name}" "$@"
"""
    return subprocess.run(
        ["bash", "-c", command, "bash", str(SCRIPT_PATH), function_name, *args],
        check=False,
        capture_output=True,
        text=True,
    )


def test_validate_pitr_report_present_path_success_accepted() -> None:
    """A successful report containing the requested path is accepted."""
    path = "data/hello.txt"
    output = f"PITR chain report selected archive #1 for '{path}'."

    result = run_bash_function("validate_pitr_report", path, "0", "0", output)

    assert result.returncode == 0, result.stderr


def test_validate_pitr_report_deleted_path_tombstone_accepted() -> None:
    """The manager's expected tombstone status and diagnostic are accepted."""
    path = "data/sub/inner/note.md"
    output = f"Cannot restore '{path}': archive #2 recorded the path as removed at 2026-08-16."

    result = run_bash_function("validate_pitr_report", path, "1", "1", output)

    assert result.returncode == 0, result.stderr


def test_validate_pitr_report_deleted_path_unrelated_failure_rejected() -> None:
    """A generic report failure cannot masquerade as an expected deletion."""
    path = "data/sub/inner/note.md"
    output = f"Cannot restore '{path}': archive slice is missing."

    result = run_bash_function("validate_pitr_report", path, "1", "1", output)

    assert result.returncode != 0
    assert "did not confirm the expected deletion" in result.stderr


def test_validate_pitr_report_present_path_nonzero_status_rejected() -> None:
    """A report for a present path must not accept a nonzero exit status."""
    path = "data/hello.txt"
    output = f"PITR chain report failed for '{path}'."

    result = run_bash_function("validate_pitr_report", path, "0", "1", output)

    assert result.returncode != 0
    assert "failed for present path" in result.stderr


def test_assert_different_inode_independent_files_accepted(tmp_path: Path) -> None:
    """Two independently created files satisfy the different-inode assertion."""
    first = tmp_path / "first.bin"
    second = tmp_path / "second.bin"
    first.write_bytes(b"same content")
    second.write_bytes(b"same content")

    result = run_bash_function("assert_different_inode", str(first), str(second))

    assert result.returncode == 0, result.stderr


def test_assert_different_inode_hardlinks_rejected(tmp_path: Path) -> None:
    """Two hard links to one inode fail the different-inode assertion."""
    first = tmp_path / "first.bin"
    second = tmp_path / "second.bin"
    first.write_bytes(b"shared inode")
    os.link(first, second)

    result = run_bash_function("assert_different_inode", str(first), str(second))

    assert result.returncode != 0
    assert "hardlink incorrectly preserved" in result.stdout
