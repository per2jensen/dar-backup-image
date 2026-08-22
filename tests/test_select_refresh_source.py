"""Integration tests for build-history-driven refresh source selection."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).parents[1]
SELECTOR = REPOSITORY_ROOT / "scripts" / "select_refresh_source.py"


def _run_git(repository: Path, *arguments: str) -> str:
    """Run Git in an isolated test repository.

    Args:
        repository: Git worktree used by the command.
        *arguments: Git command arguments.

    Returns:
        Stripped standard output.

    Raises:
        subprocess.CalledProcessError: If Git exits unsuccessfully.
    """
    result = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _create_repository(tmp_path: Path) -> tuple[Path, str, str]:
    """Create source and housekeeping commits with a tag on housekeeping.

    Args:
        tmp_path: Temporary directory owned by the test.

    Returns:
        Repository path, source SHA, and housekeeping SHA.

    Raises:
        subprocess.CalledProcessError: If repository setup fails.
    """
    repository = tmp_path / "repository"
    repository.mkdir()
    _run_git(repository, "init", "--initial-branch=main")
    _run_git(repository, "config", "user.name", "Refresh Test")
    _run_git(repository, "config", "user.email", "refresh@example.invalid")

    source_file = repository / "application.txt"
    source_file.write_text("released source\n", encoding="utf-8")
    _run_git(repository, "add", "application.txt")
    _run_git(repository, "commit", "-m", "application source")
    source_sha = _run_git(repository, "rev-parse", "HEAD")

    history_file = repository / "housekeeping.txt"
    history_file.write_text("release metadata\n", encoding="utf-8")
    _run_git(repository, "add", "housekeeping.txt")
    _run_git(repository, "commit", "-m", "release housekeeping")
    housekeeping_sha = _run_git(repository, "rev-parse", "HEAD")
    _run_git(repository, "tag", "-a", "v1.2.3", "-m", "release 1.2.3")
    return repository, source_sha, housekeeping_sha


def _write_history(tmp_path: Path, record: dict[str, Any]) -> Path:
    """Write one latest build-history record.

    Args:
        tmp_path: Temporary directory owned by the test.
        record: Record to serialize as the only history entry.

    Returns:
        Path to the created JSON file.
    """
    path = tmp_path / "build-history.json"
    path.write_text(json.dumps([record]), encoding="utf-8")
    return path


def _run_selector(
    history: Path, repository: Path
) -> subprocess.CompletedProcess[str]:
    """Run the real refresh-source selector.

    Args:
        history: Build-history JSON file.
        repository: Git repository used to resolve revisions.

    Returns:
        Completed selector subprocess with captured output.
    """
    return subprocess.run(
        [
            "python3",
            str(SELECTOR),
            "--history",
            str(history),
            "--repository",
            str(repository),
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def test_selector_tag_mismatch_uses_recorded_source_commit(tmp_path: Path) -> None:
    """Historical housekeeping tags do not replace the recorded build source."""
    repository, source_sha, housekeeping_sha = _create_repository(tmp_path)
    history = _write_history(
        tmp_path,
        {"tag": "1.2.3", "git_revision": source_sha[:7]},
    )

    result = _run_selector(history, repository)

    assert result.returncode == 0, result.stderr
    selection = json.loads(result.stdout)
    assert selection == {
        "application_sha": source_sha,
        "base_version": "1.2.3",
        "raw_tag": "1.2.3",
        "recorded_revision": source_sha[:7],
        "release_tag_sha": housekeeping_sha,
        "tag_matches_source": False,
    }


def test_selector_unresolvable_recorded_revision_fails(tmp_path: Path) -> None:
    """An unknown recorded source cannot silently fall back to the release tag."""
    repository, _, _ = _create_repository(tmp_path)
    history = _write_history(
        tmp_path,
        {"tag": "1.2.3-4", "git_revision": "deadbee"},
    )

    result = _run_selector(history, repository)

    assert result.returncode == 2
    assert "cannot resolve Git revision 'deadbee'" in result.stderr
    assert result.stdout == ""


def test_selector_invalid_latest_tag_fails(tmp_path: Path) -> None:
    """A prerelease cannot be treated as a stable refresh base."""
    repository, source_sha, _ = _create_repository(tmp_path)
    history = _write_history(
        tmp_path,
        {"tag": "1.2.3-rc1", "git_revision": source_sha},
    )

    result = _run_selector(history, repository)

    assert result.returncode == 2
    assert "must be x.y.z or x.y.z-N" in result.stderr
