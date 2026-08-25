"""Integration tests for refresh tag and image revision publication guards."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest


REPOSITORY_ROOT = Path(__file__).parents[1]
TAG_VERIFIER = REPOSITORY_ROOT / "scripts" / "verify_docker_tag_available.sh"
REVISION_VERIFIER = REPOSITORY_ROOT / "scripts" / "verify_image_revision.sh"
APPLICATION_SHA = "1234567890abcdef1234567890abcdef12345678"


def _write_fake_docker(bin_dir: Path) -> None:
    """Create a Docker substitute controlled through per-test environment data.

    Args:
        bin_dir: Directory that will be prepended to ``PATH``.

    Returns:
        None.
    """
    bin_dir.mkdir()
    docker = bin_dir / "docker"
    docker.write_text(
        "#!/bin/bash\n"
        "set -euo pipefail\n"
        "if [[ \"$*\" != \"${FAKE_DOCKER_EXPECTED_ARGS:?}\" ]]; then\n"
        "    >&2 echo \"unexpected docker arguments: $*\"\n"
        "    exit 3\n"
        "fi\n"
        "printf '%s\\n' \"${FAKE_DOCKER_OUTPUT-}\"\n"
        "exit \"${FAKE_DOCKER_EXIT_CODE:?}\"\n",
        encoding="utf-8",
    )
    docker.chmod(0o755)


def _run_with_fake_docker(
    tmp_path: Path,
    script: Path,
    arguments: list[str],
    *,
    expected_docker_arguments: str,
    docker_output: str,
    docker_exit_code: int,
) -> subprocess.CompletedProcess[str]:
    """Run a real guard script with a deterministic Docker substitute.

    Args:
        tmp_path: Temporary directory owned by the test.
        script: Guard script to execute.
        arguments: Arguments passed to the guard script.
        expected_docker_arguments: Exact Docker arguments required by the fake.
        docker_output: Output returned by the Docker substitute.
        docker_exit_code: Exit status returned by the Docker substitute.

    Returns:
        Completed subprocess with captured output.
    """
    bin_dir = tmp_path / "bin"
    _write_fake_docker(bin_dir)
    environment = os.environ.copy()
    environment["PATH"] = f"{bin_dir}:{environment['PATH']}"
    environment["FAKE_DOCKER_EXPECTED_ARGS"] = expected_docker_arguments
    environment["FAKE_DOCKER_OUTPUT"] = docker_output
    environment["FAKE_DOCKER_EXIT_CODE"] = str(docker_exit_code)
    return subprocess.run(
        ["bash", str(script), *arguments],
        cwd=REPOSITORY_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )


def test_verify_docker_tag_available_missing_manifest_succeeds(
    tmp_path: Path,
) -> None:
    """A registry response proving the refresh tag is absent permits a build."""
    result = _run_with_fake_docker(
        tmp_path,
        TAG_VERIFIER,
        ["per2jensen/dar-backup", "1.2.3-4"],
        expected_docker_arguments=(
            "manifest inspect per2jensen/dar-backup:1.2.3-4"
        ),
        docker_output="manifest unknown",
        docker_exit_code=1,
    )

    assert result.returncode == 0, result.stderr
    assert "Docker tag is available" in result.stdout


def test_verify_docker_tag_available_existing_manifest_fails(tmp_path: Path) -> None:
    """An existing immutable refresh tag is never accepted for overwrite."""
    result = _run_with_fake_docker(
        tmp_path,
        TAG_VERIFIER,
        ["per2jensen/dar-backup", "1.2.3-4"],
        expected_docker_arguments=(
            "manifest inspect per2jensen/dar-backup:1.2.3-4"
        ),
        docker_output='{"schemaVersion": 2}',
        docker_exit_code=0,
    )

    assert result.returncode == 2
    assert "already exists and will not be overwritten" in result.stderr


@pytest.mark.parametrize(
    "diagnostic",
    ["TLS handshake timeout", "docker: command not found"],
)
def test_verify_docker_tag_available_unexpected_error_fails_closed(
    tmp_path: Path,
    diagnostic: str,
) -> None:
    """An unexpected registry failure cannot be mistaken for an unused tag."""
    result = _run_with_fake_docker(
        tmp_path,
        TAG_VERIFIER,
        ["per2jensen/dar-backup", "1.2.3-4"],
        expected_docker_arguments=(
            "manifest inspect per2jensen/dar-backup:1.2.3-4"
        ),
        docker_output=diagnostic,
        docker_exit_code=1,
    )

    assert result.returncode == 2
    assert "could not prove Docker tag" in result.stderr
    assert diagnostic in result.stderr


def test_verify_image_revision_matching_application_sha_succeeds(
    tmp_path: Path,
) -> None:
    """An image labeled with its exact application commit passes."""
    result = _run_with_fake_docker(
        tmp_path,
        REVISION_VERIFIER,
        ["dar-backup:1.2.3-4", APPLICATION_SHA],
        expected_docker_arguments=(
            "inspect --format {{ index .Config.Labels "
            '"org.opencontainers.image.revision" }} dar-backup:1.2.3-4'
        ),
        docker_output=APPLICATION_SHA,
        docker_exit_code=0,
    )

    assert result.returncode == 0, result.stderr
    assert "Image revision verified" in result.stdout
    assert APPLICATION_SHA in result.stdout


def test_verify_image_revision_mismatched_application_sha_fails(
    tmp_path: Path,
) -> None:
    """An image labeled with another valid commit is rejected."""
    actual_revision = "0" * 40
    result = _run_with_fake_docker(
        tmp_path,
        REVISION_VERIFIER,
        ["dar-backup:1.2.3-4", APPLICATION_SHA],
        expected_docker_arguments=(
            "inspect --format {{ index .Config.Labels "
            '"org.opencontainers.image.revision" }} dar-backup:1.2.3-4'
        ),
        docker_output=actual_revision,
        docker_exit_code=0,
    )

    assert result.returncode == 2
    assert "image revision mismatch" in result.stderr
    assert f"expected: '{APPLICATION_SHA}'" in result.stderr
    assert f"actual:   '{actual_revision}'" in result.stderr


def test_verify_image_revision_abbreviated_expected_sha_fails_before_docker(
    tmp_path: Path,
) -> None:
    """An abbreviated expected application revision is invalid input."""
    result = subprocess.run(
        [
            "bash",
            str(REVISION_VERIFIER),
            "dar-backup:1.2.3-4",
            APPLICATION_SHA[:7],
        ],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "must be 40 lowercase hexadecimal characters" in result.stderr


@pytest.mark.parametrize("actual_revision", ["", "1234567"])
def test_verify_image_revision_missing_or_malformed_label_fails(
    tmp_path: Path,
    actual_revision: str,
) -> None:
    """A missing or abbreviated image revision label is rejected."""
    result = _run_with_fake_docker(
        tmp_path,
        REVISION_VERIFIER,
        ["dar-backup:1.2.3-4", APPLICATION_SHA],
        expected_docker_arguments=(
            "inspect --format {{ index .Config.Labels "
            '"org.opencontainers.image.revision" }} dar-backup:1.2.3-4'
        ),
        docker_output=actual_revision,
        docker_exit_code=0,
    )

    assert result.returncode == 2
    assert "has an invalid revision label" in result.stderr
