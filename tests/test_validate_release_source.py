"""Integration tests for immutable release-source validation."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).parents[1]
VALIDATION_SCRIPT = REPOSITORY_ROOT / "scripts" / "validate_release_source.sh"


def _run(
    arguments: list[str], cwd: Path, *, check: bool = True
) -> subprocess.CompletedProcess[str]:
    """Run a subprocess with captured text output.

    Args:
        arguments: Command and arguments to execute.
        cwd: Working directory for the command.
        check: Whether to raise when the command exits unsuccessfully.

    Returns:
        Completed subprocess result.

    Raises:
        subprocess.CalledProcessError: If ``check`` is true and the command fails.
    """
    return subprocess.run(
        arguments,
        cwd=cwd,
        check=check,
        capture_output=True,
        text=True,
    )


def _create_source_checkout(tmp_path: Path) -> tuple[Path, Path, str]:
    """Create a detached source checkout matching a bare remote main tip.

    Args:
        tmp_path: Temporary directory owned by the test.

    Returns:
        Source checkout, publishing checkout, and selected source SHA.
    """
    remote = tmp_path / "origin.git"
    publisher = tmp_path / "publisher"
    source = tmp_path / "source"

    _run(["git", "init", "--bare", "--initial-branch=main", str(remote)], tmp_path)
    _run(["git", "init", "--initial-branch=main", str(publisher)], tmp_path)
    _run(["git", "remote", "add", "origin", str(remote)], publisher)
    _run(["git", "config", "user.name", "test-user"], publisher)
    _run(["git", "config", "user.email", "test@example.invalid"], publisher)
    (publisher / "release-source.txt").write_text("release source\n", encoding="utf-8")
    _run(["git", "add", "release-source.txt"], publisher)
    _run(["git", "commit", "-m", "release source"], publisher)
    _run(["git", "push", "--set-upstream", "origin", "main"], publisher)
    source_sha = _run(["git", "rev-parse", "HEAD"], publisher).stdout.strip()

    _run(["git", "clone", str(remote), str(source)], tmp_path)
    _run(["git", "checkout", "--detach", source_sha], source)
    scripts = source / "scripts"
    scripts.mkdir()
    shutil.copy2(VALIDATION_SCRIPT, scripts / VALIDATION_SCRIPT.name)
    return source, publisher, source_sha


def test_validate_release_source_matching_main_tip_succeeds(tmp_path: Path) -> None:
    """The selected detached commit is accepted when it equals remote main."""
    source, _, source_sha = _create_source_checkout(tmp_path)

    result = _run(
        [
            "bash",
            "scripts/validate_release_source.sh",
            source_sha,
            "refs/heads/main",
        ],
        source,
    )

    assert f"Immutable release source verified: {source_sha}" in result.stdout


def test_validate_release_source_advanced_main_fails(tmp_path: Path) -> None:
    """The selected commit is rejected when remote main advances."""
    source, publisher, source_sha = _create_source_checkout(tmp_path)
    (publisher / "later-change.txt").write_text("later\n", encoding="utf-8")
    _run(["git", "add", "later-change.txt"], publisher)
    _run(["git", "commit", "-m", "advance main"], publisher)
    _run(["git", "push", "origin", "main"], publisher)

    result = _run(
        [
            "bash",
            "scripts/validate_release_source.sh",
            source_sha,
            "refs/heads/main",
        ],
        source,
        check=False,
    )

    assert result.returncode == 2
    assert "main advanced after this release was dispatched" in result.stderr


def test_validate_release_source_non_main_dispatch_fails(tmp_path: Path) -> None:
    """A release dispatch from a non-main ref is rejected immediately."""
    source, _, source_sha = _create_source_checkout(tmp_path)

    result = _run(
        [
            "bash",
            "scripts/validate_release_source.sh",
            source_sha,
            "refs/heads/feature",
        ],
        source,
        check=False,
    )

    assert result.returncode == 2
    assert "releases must be dispatched from main" in result.stderr
