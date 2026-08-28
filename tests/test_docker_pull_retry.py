# SPDX-FileCopyrightText: 2025-2026 Per Jensen
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This file is part of dar-backup-image:
# https://github.com/per2jensen/dar-backup-image
#
# License terms and warranty disclaimer:
# https://github.com/per2jensen/dar-backup-image/blob/main/LICENSE

"""Tests for the Docker image pull retry wrapper."""

import os
import subprocess
from pathlib import Path


SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "docker-pull-retry.sh"


def write_fake_docker(directory: Path) -> Path:
    """Create a deterministic Docker executable for transport-failure tests.

    A real registry connection reset cannot be triggered reliably in a unit
    test, so this executable preserves the subprocess boundary while emulating
    Docker's exit status across successive pull attempts.

    Args:
        directory: Directory in which to create the executable.

    Returns:
        Path to the fake Docker executable.

    Raises:
        OSError: If the executable cannot be written or made executable.
    """
    docker_path = directory / "docker"
    docker_path.write_text(
        """#!/bin/bash
set -euo pipefail

if [[ "${1:-}" != "pull" || "${2:-}" != "${FAKE_DOCKER_EXPECTED_IMAGE:?}" ]]; then
  >&2 echo "unexpected docker arguments: $*"
  exit 9
fi

state_file="${FAKE_DOCKER_STATE_FILE:?}"
success_on_attempt="${FAKE_DOCKER_SUCCESS_ON_ATTEMPT:?}"
attempt=0
if [[ -f "$state_file" ]]; then
  read -r attempt < "$state_file"
fi
attempt=$((attempt + 1))
printf '%s\n' "$attempt" > "$state_file"

if (( attempt >= success_on_attempt )); then
  echo "pull complete"
  exit 0
fi

>&2 echo "read: connection reset by peer"
exit 1
"""
    )
    docker_path.chmod(0o755)
    return docker_path


def run_retry_script(
    tmp_path: Path,
    *,
    max_attempts: int,
    success_on_attempt: int,
) -> tuple[subprocess.CompletedProcess[str], Path]:
    """Run the retry wrapper against an isolated fake Docker executable.

    Args:
        tmp_path: Temporary directory for the executable and attempt counter.
        max_attempts: Maximum pull attempts passed to the wrapper.
        success_on_attempt: Attempt on which fake Docker starts succeeding.

    Returns:
        Completed wrapper process and path to its attempt counter.

    Raises:
        ValueError: If either attempt value is less than one.
        OSError: If the fake executable cannot be created.
    """
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least one")
    if success_on_attempt < 1:
        raise ValueError("success_on_attempt must be at least one")

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    write_fake_docker(fake_bin)
    state_file = tmp_path / "attempt-count"
    image = "ghcr.io/example/project:ci-test"
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:{env['PATH']}",
            "FAKE_DOCKER_EXPECTED_IMAGE": image,
            "FAKE_DOCKER_STATE_FILE": str(state_file),
            "FAKE_DOCKER_SUCCESS_ON_ATTEMPT": str(success_on_attempt),
        }
    )

    result = subprocess.run(
        [str(SCRIPT_PATH), image, str(max_attempts), "0"],
        check=False,
        capture_output=True,
        env=env,
        text=True,
    )
    return result, state_file


def test_docker_pull_retry_transient_failure_eventually_succeeds(tmp_path: Path) -> None:
    """A later successful pull returns success after retrying."""
    result, state_file = run_retry_script(
        tmp_path,
        max_attempts=3,
        success_on_attempt=2,
    )

    assert result.returncode == 0, result.stderr
    assert state_file.read_text().strip() == "2"
    assert "attempt 2/3" in result.stderr
    assert "Successfully pulled" in result.stderr


def test_docker_pull_retry_permanent_failure_exhausts_attempts(tmp_path: Path) -> None:
    """A permanent pull failure exits nonzero after the configured limit."""
    result, state_file = run_retry_script(
        tmp_path,
        max_attempts=3,
        success_on_attempt=4,
    )

    assert result.returncode != 0
    assert state_file.read_text().strip() == "3"
    assert "Failed to pull" in result.stderr
    assert "after 3 attempts" in result.stderr


def test_docker_pull_retry_zero_attempt_limit_rejected() -> None:
    """An invalid zero-attempt limit fails before invoking Docker."""
    result = subprocess.run(
        [str(SCRIPT_PATH), "ghcr.io/example/project:ci-test", "0", "0"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "MAX_ATTEMPTS must be an integer between 1 and 20" in result.stderr
