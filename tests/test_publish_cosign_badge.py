"""Integration tests for publishing the release cosign badge."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest


REPOSITORY_ROOT = Path(__file__).parents[1]
PUBLISH_SCRIPT = REPOSITORY_ROOT / "scripts" / "publish_cosign_badge.sh"
BADGE_WRITER = REPOSITORY_ROOT / "scripts" / "write_cosign_badge.py"
COMMIT_HELPER = REPOSITORY_ROOT / "scripts" / "git_commit_if_changed.sh"


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


def _create_repository(tmp_path: Path, initial_status: str) -> tuple[Path, Path]:
    """Create a working repository and bare origin containing badge helpers.

    Args:
        tmp_path: Temporary directory owned by the test.
        initial_status: Initial badge message, either ``ok`` or ``failed``.

    Returns:
        Pair containing the working repository and bare remote paths.

    Raises:
        ValueError: If ``initial_status`` is unsupported.
    """
    if initial_status not in {"ok", "failed"}:
        raise ValueError(f"unsupported initial badge status: {initial_status}")

    remote = tmp_path / "origin.git"
    worktree = tmp_path / "worktree"
    _run(["git", "init", "--bare", "--initial-branch=main", str(remote)], tmp_path)
    _run(["git", "init", "--initial-branch=main", str(worktree)], tmp_path)
    _run(["git", "remote", "add", "origin", str(remote)], worktree)

    scripts = worktree / "scripts"
    scripts.mkdir()
    for source in (PUBLISH_SCRIPT, BADGE_WRITER, COMMIT_HELPER):
        shutil.copy2(source, scripts / source.name)

    badge = {
        "schemaVersion": 1,
        "label": "cosign",
        "message": initial_status,
        "color": "f77f00" if initial_status == "ok" else "9e9e9e",
    }
    badge_path = worktree / "doc" / "cosign_badge.json"
    badge_path.parent.mkdir()
    badge_path.write_text(json.dumps(badge, indent=2) + "\n", encoding="utf-8")

    _run(["git", "config", "user.name", "test-user"], worktree)
    _run(["git", "config", "user.email", "test@example.invalid"], worktree)
    _run(["git", "add", "."], worktree)
    _run(["git", "commit", "-m", "initial badge"], worktree)
    _run(["git", "push", "--set-upstream", "origin", "main"], worktree)
    return worktree, remote


@pytest.mark.parametrize(
    ("initial_status", "published_status"),
    [("ok", "failed"), ("failed", "ok")],
)
def test_publish_cosign_badge_valid_status_updates_remote_main(
    tmp_path: Path, initial_status: str, published_status: str
) -> None:
    """A valid status is committed and pushed to the remote main branch."""
    worktree, remote = _create_repository(tmp_path, initial_status)

    result = _run(
        [
            "bash",
            "scripts/publish_cosign_badge.sh",
            published_status,
            f"publish {published_status} badge",
        ],
        worktree,
    )

    remote_badge = _run(
        ["git", f"--git-dir={remote}", "show", "main:doc/cosign_badge.json"],
        tmp_path,
    )
    remote_payload = json.loads(remote_badge.stdout)
    assert remote_payload["message"] == published_status
    assert f"Published cosign badge '{published_status}'" in result.stdout


def test_publish_cosign_badge_invalid_status_rejects_without_remote_change(
    tmp_path: Path,
) -> None:
    """An invalid status fails before creating or pushing a commit."""
    worktree, remote = _create_repository(tmp_path, "ok")
    original_remote_sha = _run(
        ["git", f"--git-dir={remote}", "rev-parse", "main"], tmp_path
    ).stdout.strip()

    result = _run(
        [
            "bash",
            "scripts/publish_cosign_badge.sh",
            "unknown",
            "invalid badge",
        ],
        worktree,
        check=False,
    )

    current_remote_sha = _run(
        ["git", f"--git-dir={remote}", "rev-parse", "main"], tmp_path
    ).stdout.strip()
    assert result.returncode == 2
    assert "badge status must be 'ok' or 'failed'" in result.stderr
    assert current_remote_sha == original_remote_sha


def test_publish_cosign_badge_concurrent_main_update_is_retried(
    tmp_path: Path,
) -> None:
    """A real non-fast-forward race is fetched, regenerated, and retried."""
    worktree, remote = _create_repository(tmp_path, "ok")
    racer = tmp_path / "racer"
    marker = tmp_path / "race-triggered"
    _run(["git", "clone", str(remote), str(racer)], tmp_path)
    _run(["git", "config", "user.name", "racing-user"], racer)
    _run(["git", "config", "user.email", "racer@example.invalid"], racer)

    hook = worktree / ".git" / "hooks" / "pre-push"
    hook.write_text(
        "#!/bin/bash\n"
        "set -euo pipefail\n"
        f'if [[ ! -f "{marker}" ]]; then\n'
        f'  touch "{marker}"\n'
        f'  printf "%s\\n" "concurrent update" > "{racer / "race.txt"}"\n'
        f'  git -C "{racer}" add race.txt\n'
        f'  git -C "{racer}" commit -m "concurrent main update"\n'
        f'  git -C "{racer}" push origin main\n'
        "fi\n",
        encoding="utf-8",
    )
    hook.chmod(0o755)

    result = _run(
        [
            "bash",
            "scripts/publish_cosign_badge.sh",
            "failed",
            "publish failed badge after race",
        ],
        worktree,
    )

    remote_badge = _run(
        ["git", f"--git-dir={remote}", "show", "main:doc/cosign_badge.json"],
        tmp_path,
    )
    remote_race = _run(
        ["git", f"--git-dir={remote}", "show", "main:race.txt"], tmp_path
    )
    assert json.loads(remote_badge.stdout)["message"] == "failed"
    assert remote_race.stdout == "concurrent update\n"
    assert "badge push raced with another update" in result.stderr
