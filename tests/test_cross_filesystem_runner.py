# SPDX-FileCopyrightText: 2025-2026 Per Jensen
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This file is part of dar-backup-image:
# https://github.com/per2jensen/dar-backup-image
#
# License terms and warranty disclaimer:
# https://github.com/per2jensen/dar-backup-image/blob/main/LICENSE

"""Non-Docker tests for the cross-filesystem Bash runner."""

from __future__ import annotations

import subprocess
from pathlib import Path


RUNNER_PATH = Path(__file__).parents[1] / "run_cross_filesystem_test.sh"


def _run(*arguments: str) -> subprocess.CompletedProcess[str]:
    """Run the harness until argument validation completes or fails.

    Args:
        *arguments: Runner command-line arguments.

    Returns:
        Captured subprocess result.
    """
    return subprocess.run(
        [str(RUNNER_PATH), *arguments],
        check=False,
        capture_output=True,
        text=True,
    )


def _run_function(
    function_name: str, *arguments: str
) -> subprocess.CompletedProcess[str]:
    """Source the runner and invoke one public test helper.

    Args:
        function_name: Bash function to call.
        *arguments: Function arguments.

    Returns:
        Captured Bash subprocess result.
    """
    command = """
source "$1"
function_name="$2"
shift 2
"${function_name}" "$@"
"""
    return subprocess.run(
        ["bash", "-c", command, "bash", str(RUNNER_PATH), function_name, *arguments],
        check=False,
        capture_output=True,
        text=True,
    )


def test_runner_help_lists_cross_filesystem_scenarios() -> None:
    """Help documents both supported filesystem directions."""
    result = _run("--help")

    assert result.returncode == 0
    assert "etc-to-home|home-to-data|both" in result.stdout
    assert "--backup-user pj|root" in result.stdout


def test_runner_home_scenario_without_source_fails_before_docker() -> None:
    """A home backup cannot accidentally select the entire home directory."""
    result = _run("--scenario", "home-to-data")

    assert result.returncode != 0
    assert "requires at least one --home-source" in result.stderr


def test_runner_invalid_backup_user_fails_before_docker() -> None:
    """Only the agreed root and pj identities are accepted."""
    result = _run("--backup-user", "daemon")

    assert result.returncode != 0
    assert "--backup-user must be pj or root" in result.stderr


def test_runner_home_source_outside_home_root_fails_before_docker() -> None:
    """A source outside `/home/pj` is rejected without invoking Docker."""
    result = _run("--scenario", "home-to-data", "--home-source", "/etc")

    assert result.returncode != 0
    assert "must be below /home/pj" in result.stderr


def test_runner_whole_home_source_fails_before_docker() -> None:
    """The complete home directory is never accepted implicitly."""
    result = _run(
        "--scenario", "home-to-data", "--home-source", "/home/pj"
    )

    assert result.returncode != 0
    assert "not the whole home directory" in result.stderr


def test_runner_home_source_overlapping_restore_fails_before_docker() -> None:
    """A source cannot contain the changing Btrfs restore destination."""
    result = _run(
        "--scenario", "home-to-data", "--home-source", "/home/pj/tmp"
    )

    assert result.returncode != 0
    assert "overlaps the home restore base" in result.stderr


def test_runner_invalid_dataset_id_fails_before_docker() -> None:
    """Personal paths cannot be placed in the opaque dataset identifier."""
    result = _run("--dataset-id", "/home/pj/Documents")

    assert result.returncode != 0
    assert "--dataset-id must be" in result.stderr


def test_expected_permission_failure_access_denial_is_accepted(
    tmp_path: Path,
) -> None:
    """A nonzero access-denied backup without an archive is expected.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    output = tmp_path / "backup.log"
    output.write_text("Cannot open /source/shadow: Permission denied\n", encoding="utf-8")

    result = _run_function(
        "classify_expected_permission_failure", "7", str(output), "0"
    )

    assert result.returncode == 0, result.stderr


def test_expected_permission_failure_unexpected_success_is_rejected(
    tmp_path: Path,
) -> None:
    """A successful non-root `/etc` backup violates the negative test.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    output = tmp_path / "backup.log"
    output.write_text("Backup complete\n", encoding="utf-8")

    result = _run_function(
        "classify_expected_permission_failure", "0", str(output), "0"
    )

    assert result.returncode != 0
    assert "unexpectedly succeeded" in result.stderr


def test_expected_permission_failure_unrelated_failure_is_rejected(
    tmp_path: Path,
) -> None:
    """An image or configuration error cannot pass as a permission denial.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    output = tmp_path / "backup.log"
    output.write_text("Configuration syntax error\n", encoding="utf-8")

    result = _run_function(
        "classify_expected_permission_failure", "2", str(output), "0"
    )

    assert result.returncode != 0
    assert "unrelated to access permissions" in result.stderr


def test_expected_permission_failure_usable_archive_is_rejected(
    tmp_path: Path,
) -> None:
    """A usable archive cannot accompany the expected denial outcome.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    output = tmp_path / "backup.log"
    output.write_text("Permission denied\n", encoding="utf-8")

    result = _run_function(
        "classify_expected_permission_failure", "7", str(output), "1"
    )

    assert result.returncode != 0
    assert "usable FULL archive" in result.stderr


def test_cleanup_validation_accepts_only_matching_marked_child(
    tmp_path: Path,
) -> None:
    """Cleanup accepts a generated child with the current run marker.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    parent = tmp_path / "runs"
    target = parent / "generated"
    target.mkdir(parents=True)
    (target / ".cross-filesystem-test-run").write_text(
        "test-run\n", encoding="utf-8"
    )
    result = subprocess.run(
        [
            "bash",
            "-c",
            'source "$1"; RUN_ID=test-run; validate_cleanup_target "$2" "$3"',
            "bash",
            str(RUNNER_PATH),
            str(target),
            str(parent),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def test_cleanup_validation_rejects_unmarked_directory(tmp_path: Path) -> None:
    """Cleanup refuses an ordinary user directory without its marker.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    parent = tmp_path / "runs"
    target = parent / "ordinary"
    target.mkdir(parents=True)

    result = _run_function("validate_cleanup_target", str(target), str(parent))

    assert result.returncode != 0


def test_require_filesystem_type_rejects_wrong_type(tmp_path: Path) -> None:
    """Filesystem validation fails closed on an unexpected type.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    result = _run_function(
        "require_filesystem_type", str(tmp_path), "not-a-filesystem", "test target"
    )

    assert result.returncode != 0
    assert "must be on not-a-filesystem" in result.stderr
