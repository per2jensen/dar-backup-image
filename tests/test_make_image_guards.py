# SPDX-FileCopyrightText: 2025-2026 Per Jensen
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This file is part of dar-backup-image:
# https://github.com/per2jensen/dar-backup-image
#
# License terms and warranty disclaimer:
# https://github.com/per2jensen/dar-backup-image/blob/main/LICENSE

"""Behavioral tests for Make image verification and publication boundaries."""

from __future__ import annotations

import subprocess
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).parents[1]


def _write_fake_docker(path: Path, output: str, exit_code: int) -> None:
    """Create a Docker substitute for the CLI-version Make target.

    Args:
        path: Destination executable.
        output: Text written by the substitute.
        exit_code: Status returned by the substitute.

    Returns:
        None.
    """
    path.write_text(
        "#!/bin/bash\n"
        f"printf '%s\\n' {output!r}\n"
        f"exit {exit_code}\n",
        encoding="utf-8",
    )
    path.chmod(0o755)


def _run_cli_verification(
    tmp_path: Path,
    *,
    output: str,
    exit_code: int,
) -> subprocess.CompletedProcess[str]:
    """Run the real Make verification recipe with a Docker substitute.

    Args:
        tmp_path: Isolated pytest temporary directory.
        output: Simulated CLI output.
        exit_code: Simulated Docker status.

    Returns:
        Captured Make process.
    """
    fake_docker = tmp_path / "fake-docker"
    _write_fake_docker(fake_docker, output, exit_code)
    return subprocess.run(
        [
            "make",
            "--silent",
            f"DOCKER={fake_docker}",
            "FINAL_VERSION=1.0.0",
            "DAR_BACKUP_VERSION=1.1.11",
            "verify-cli-version",
        ],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_verify_cli_version_matching_output_succeeds(tmp_path: Path) -> None:
    """The Make verifier explicitly confirms a matching embedded CLI."""
    result = _run_cli_verification(
        tmp_path,
        output="dar-backup 1.1.11",
        exit_code=0,
    )

    assert result.returncode == 0, result.stderr
    assert "dar-backup --version is correct: 1.1.11" in result.stdout


def test_verify_cli_version_docker_failure_is_not_a_version_mismatch(
    tmp_path: Path,
) -> None:
    """A Docker execution error retains its context and fails verification."""
    result = _run_cli_verification(
        tmp_path,
        output="daemon unavailable",
        exit_code=17,
    )

    assert result.returncode != 0
    assert "unable to run dar-backup --version" in result.stderr
    assert "daemon unavailable" in result.stderr


def test_test_nobuild_uses_selected_image_in_pytest_environment() -> None:
    """The no-build test recipe passes its exact image to the test suite."""
    result = subprocess.run(
        ["make", "--dry-run", "IMAGE=example.invalid/dar-backup:test", "test-nobuild"],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert 'image inspect "example.invalid/dar-backup:test"' in result.stdout
    assert 'IMAGE="example.invalid/dar-backup:test" pytest' in result.stdout
    assert "pytest-json-report is not installed" in result.stdout


def test_release_target_fails_without_remote_side_effects() -> None:
    """The legacy local release entry point stops with workflow guidance."""
    result = subprocess.run(
        ["make", "--silent", "release"],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "Manual Docker Release workflow" in result.stderr
    assert "make final" in result.stderr


def test_obsolete_dry_run_release_target_is_unavailable() -> None:
    """The removed local release simulation cannot be invoked accidentally."""
    result = subprocess.run(
        ["make", "--silent", "dry-run-release"],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "No rule to make target 'dry-run-release'" in result.stderr


def test_dev_nuke_does_not_ignore_prune_failures() -> None:
    """Release qualification cannot continue after an incomplete Docker prune."""
    makefile = (REPOSITORY_ROOT / "Makefile").read_text(encoding="utf-8")
    target = makefile[makefile.index("dev-nuke:"):makefile.index("dev-rebuild:")]

    assert "if ! $(DOCKER) builder prune -a -f" in target
    assert "if ! $(DOCKER) image prune -a -f" in target
    assert "refusing to claim a clean build" in target
    assert "|| true" not in target
