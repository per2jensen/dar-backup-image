# SPDX-FileCopyrightText: 2025-2026 Per Jensen
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This file is part of dar-backup-image:
# https://github.com/per2jensen/dar-backup-image
#
# License terms and warranty disclaimer:
# https://github.com/per2jensen/dar-backup-image/blob/main/LICENSE

"""Tests for the large-scale test harness command-line interface."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest


HARNESS_PATH = Path(__file__).parents[1] / "scripts" / "large_scale_test.sh"
VALID_DEFINITION = "-R /data\n-g tmp\n"
DEEP_BASE = "/data/tmp/image-large-scale-test"


def _run_harness(
    *args: str, extra_path: str | None = None
) -> subprocess.CompletedProcess[str]:
    """Run the harness with an optional PATH prefix for fake commands.

    Args:
        args: Command-line arguments to pass to the harness.
        extra_path: Optional directory to prepend to ``PATH``.

    Returns:
        Completed subprocess result.
    """
    environment = dict(os.environ)
    if extra_path is not None:
        environment["PATH"] = f"{extra_path}{os.pathsep}{environment['PATH']}"
    return subprocess.run(
        ["bash", str(HARNESS_PATH), *args],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )


def _combined(result: subprocess.CompletedProcess[str]) -> str:
    """Combine captured stdout and stderr for message assertions.

    Args:
        result: Completed subprocess result.

    Returns:
        Combined captured output.
    """
    return f"{result.stdout}\n{result.stderr}"


@pytest.fixture
def fake_docker_path(tmp_path: Path) -> str:
    """Provide a PATH prefix whose fake docker image inspect always fails.

    Args:
        tmp_path: Isolated pytest temporary directory.

    Returns:
        Directory containing the fake docker executable.
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker_path = bin_dir / "docker"
    docker_path.write_text("#!/usr/bin/env bash\nexit 1\n", encoding="utf-8")
    docker_path.chmod(0o755)
    return str(bin_dir)


def test_help_prints_concise_usage_and_exits_zero() -> None:
    """--help prints a short usage block instead of the script's comments."""
    result = _run_harness("--help")

    assert result.returncode == 0
    assert "Usage: large_scale_test.sh --definition <body> [options]" in result.stdout
    assert "SPDX-FileCopyrightText" not in result.stdout
    assert len(result.stdout.splitlines()) < 40


def test_unknown_option_exits_nonzero_with_error_on_stderr() -> None:
    """An unknown option fails with a non-zero status and a usage hint."""
    result = _run_harness("--bogus")

    assert result.returncode == 2
    assert "Unknown option: --bogus" in result.stderr
    assert "Usage: large_scale_test.sh" in result.stderr


def test_missing_definition_fails_with_clear_error() -> None:
    """An omitted definition fails before any external tool is invoked."""
    result = _run_harness()

    assert result.returncode == 1
    assert "ERROR: --definition is required" in _combined(result)


@pytest.mark.parametrize(
    ("option_args", "expected_message"),
    [
        (["--test-name", ""], "test-name must not be empty"),
        (["--par2-ratio", "0"], "par2-ratio must be an integer from 1 through 100"),
        (["--par2-ratio", "101"], "par2-ratio must be an integer from 1 through 100"),
        (["--par2-ratio", "abc"], "par2-ratio must be an integer from 1 through 100"),
        (["--timeout", "0"], "timeout must be a positive integer"),
        (["--timeout", "-1"], "timeout must be a positive integer"),
        (["--timeout", "abc"], "timeout must be a positive integer"),
        (["--incr-mutation-delay", "-1"], "incr-mutation-delay must be a non-negative integer"),
        (["--min-free-multiplier", "0"], "min-free-multiplier must be a positive integer"),
        (["--min-free-multiplier", "abc"], "min-free-multiplier must be a positive integer"),
        (["--dataset-id", "-bad"], "dataset-id must be 1-128 characters"),
        (["--dataset-id", "bad id"], "dataset-id must be 1-128 characters"),
        (["--dataset-id", "a" * 129], "dataset-id must be 1-128 characters"),
        (["--bitrot-seed", "123"], "bitrot-seed requires --bitrot"),
        (["--bitrot-mode", "fragmented"], "bitrot-mode requires --bitrot"),
        (["--bitrot", "--bitrot-mode", "bogus"], "bitrot-mode must be contiguous, fragmented, or edges"),
        (["--full-restore-mode", "bogus"], "full-restore-mode must be auto, forced, or disabled"),
        (["--full-restore-threshold-gib", "0"], "full-restore-threshold-gib must be a positive integer"),
        (["--full-restore-threshold-gib", "8589934592"], "full-restore-threshold-gib is too large"),
    ],
)
def test_option_validation_fails_before_preflight(
    option_args: list[str], expected_message: str
) -> None:
    """Invalid option values fail fast with a descriptive message.

    Args:
        option_args: Option arguments to append after a placeholder definition.
        expected_message: Message fragment expected in the combined output.
    """
    result = _run_harness("--definition", "x", *option_args)

    assert result.returncode == 1
    assert expected_message in _combined(result)


def test_base_requires_mountable_parent() -> None:
    """A one-level base directory is rejected before preflight."""
    result = _run_harness("--definition", VALID_DEFINITION, "--base", "/data")

    assert result.returncode == 1
    assert "must be at least two directories deep" in _combined(result)


def test_definition_root_must_match_mount_root() -> None:
    """The definition's -R path must equal the derived mount root."""
    result = _run_harness(
        "--definition",
        "-R /other\n-g tmp\n",
        "--base",
        DEEP_BASE,
    )

    assert result.returncode == 1
    assert "must match the mount root '/data'" in _combined(result)
    assert "got '/other'" in _combined(result)


def test_valid_configuration_reaches_preflight_without_docker_image(
    fake_docker_path: str,
) -> None:
    """A valid definition and base reach preflight, which rejects the missing image.

    Args:
        fake_docker_path: PATH prefix containing a failing fake docker.
    """
    result = _run_harness(
        "--definition",
        VALID_DEFINITION,
        "--base",
        DEEP_BASE,
        extra_path=fake_docker_path,
    )

    assert result.returncode == 1
    assert "image 'dar-backup:dev' not found locally" in _combined(result)


def test_zero_incr_mutation_delay_is_accepted(
    fake_docker_path: str,
) -> None:
    """--incr-mutation-delay 0 passes validation and reaches preflight.

    Args:
        fake_docker_path: PATH prefix containing a failing fake docker.
    """
    result = _run_harness(
        "--definition",
        VALID_DEFINITION,
        "--base",
        DEEP_BASE,
        "--incr-mutation-delay",
        "0",
        extra_path=fake_docker_path,
    )

    assert result.returncode == 1
    assert "image 'dar-backup:dev' not found locally" in _combined(result)
