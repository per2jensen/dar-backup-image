"""Subprocess tests for release and refresh image-version policy."""

from __future__ import annotations

import subprocess
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).parents[1]
VALIDATOR = REPOSITORY_ROOT / "scripts" / "validate_image_version.py"


def _run_validator(
    version_file: Path | None,
    policy: str,
    *,
    final_version: str,
    base_version: str = "",
) -> subprocess.CompletedProcess[str]:
    """Run the real version validator as a subprocess.

    Args:
        version_file: Canonical image-version file required by release policy.
        policy: Either ``release`` or ``refresh``.
        final_version: Requested final image version.
        base_version: Stable base required by refresh policy.

    Returns:
        Completed subprocess with captured output.
    """
    if policy == "release" and version_file is None:
        raise ValueError("release policy requires a version file")

    command = ["python3", str(VALIDATOR), policy]
    if policy == "release":
        command.extend(["--image-version-file", str(version_file)])
    if policy == "refresh":
        command.extend(["--base-version", base_version])
    command.extend(["--final-version", final_version])
    return subprocess.run(command, check=False, capture_output=True, text=True)


def _write_version(tmp_path: Path, version: str) -> Path:
    """Write a canonical version file for one test.

    Args:
        tmp_path: Temporary directory owned by the test.
        version: Exact content to write.

    Returns:
        Path to the created version file.
    """
    version_file = tmp_path / "IMAGE_VERSION"
    version_file.write_text(version, encoding="utf-8")
    return version_file


def _run_make_guard(
    target: str,
    version_file: Path,
    *,
    final_version: str | None,
    base_version: str = "",
) -> subprocess.CompletedProcess[str]:
    """Invoke a real Makefile version-policy target without Docker access.

    Args:
        target: Make target to execute.
        version_file: Canonical image-version file.
        final_version: Requested final image version, or ``None`` to exercise
            the Makefile's development default.
        base_version: Stable base supplied to a refresh target.

    Returns:
        Completed Make subprocess with captured output.
    """
    command = [
        "make",
        "--no-print-directory",
        "DOCKER=true",
        "DAR_BACKUP_VERSION=test-component",
        "DAR_VERSION=test-dar",
        f"IMAGE_VERSION_FILE={version_file}",
    ]
    if final_version is not None:
        command.append(f"FINAL_VERSION={final_version}")
    if base_version:
        command.append(f"BASE_VERSION={base_version}")
    command.append(target)
    return subprocess.run(
        command,
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_release_version_exact_rc_match_succeeds(tmp_path: Path) -> None:
    """An RC final version exactly matching IMAGE_VERSION is accepted."""
    version_file = _write_version(tmp_path, "1.0.0-rc1\n")

    result = _run_validator(
        version_file,
        "release",
        final_version="1.0.0-rc1",
    )

    assert result.returncode == 0
    assert "Release version verified: 1.0.0-rc1" in result.stderr


def test_release_version_default_dev_fails(tmp_path: Path) -> None:
    """The convenient development default cannot pass a release guard."""
    version_file = _write_version(tmp_path, "1.0.0-rc1")

    result = _run_validator(version_file, "release", final_version="dev")

    assert result.returncode == 2
    assert "invalid final release version: 'dev'" in result.stderr


def test_release_version_different_valid_version_fails(tmp_path: Path) -> None:
    """A valid but noncanonical release version is rejected."""
    version_file = _write_version(tmp_path, "1.0.0-rc1")

    result = _run_validator(
        version_file,
        "release",
        final_version="1.0.0-rc2",
    )

    assert result.returncode == 2
    assert "must equal IMAGE_VERSION" in result.stderr


def test_refresh_version_matching_stable_base_and_suffix_succeeds() -> None:
    """A positive numeric refresh suffix on the selected base is accepted."""

    result = _run_validator(
        None,
        "refresh",
        base_version="1.0.0",
        final_version="1.0.0-12",
    )

    assert result.returncode == 0
    assert "Refresh version verified: 1.0.0-12" in result.stderr


def test_refresh_version_unstable_base_fails() -> None:
    """Refresh orchestration must select a stable release as its base."""

    result = _run_validator(
        None,
        "refresh",
        base_version="1.0.1-rc1",
        final_version="1.0.1-rc1-1",
    )

    assert result.returncode == 2
    assert "invalid refresh BASE_VERSION" in result.stderr


def test_refresh_version_zero_or_padded_suffix_fails() -> None:
    """Refresh counters must be positive canonical integers."""
    zero = _run_validator(
        None,
        "refresh",
        base_version="1.0.0",
        final_version="1.0.0-0",
    )
    padded = _run_validator(
        None,
        "refresh",
        base_version="1.0.0",
        final_version="1.0.0-01",
    )

    assert zero.returncode == 2
    assert padded.returncode == 2
    assert "must match" in zero.stderr
    assert "must match" in padded.stderr


def test_make_release_guard_exact_match_succeeds(tmp_path: Path) -> None:
    """The Make release guard accepts the exact committed version."""
    version_file = _write_version(tmp_path, "2.0.0-rc1")

    result = _run_make_guard(
        "check-release-image-version",
        version_file,
        final_version="2.0.0-rc1",
    )

    assert result.returncode == 0
    assert "Release version verified" in result.stderr


def test_make_final_target_dev_default_fails_before_docker(tmp_path: Path) -> None:
    """The Make release guard rejects the otherwise convenient dev version."""
    version_file = _write_version(tmp_path, "2.0.0-rc1")

    result = _run_make_guard(
        "final",
        version_file,
        final_version=None,
    )

    assert result.returncode == 2
    assert "invalid final release version" in result.stderr
    assert "Ensuring dar-backup:dev exists" not in result.stdout


def test_make_refresh_guard_derived_version_succeeds(tmp_path: Path) -> None:
    """The refresh guard ignores IMAGE_VERSION and accepts its derived output."""
    version_file = _write_version(tmp_path, "9.9.9-rc1")

    result = _run_make_guard(
        "check-refresh-image-version",
        version_file,
        base_version="2.0.0",
        final_version="2.0.0-4",
    )

    assert result.returncode == 0
    assert "Refresh version verified" in result.stderr
