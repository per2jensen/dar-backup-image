# SPDX-FileCopyrightText: 2025-2026 Per Jensen
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This file is part of dar-backup-image:
# https://github.com/per2jensen/dar-backup-image
#
# License terms and warranty disclaimer:
# https://github.com/per2jensen/dar-backup-image/blob/main/LICENSE

"""Integration tests for atomic refresh housekeeping publication."""

from __future__ import annotations

import subprocess
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).parents[1]
HOUSEKEEPING = REPOSITORY_ROOT / "scripts" / "commit_refresh_housekeeping.sh"
DIGEST = "example.invalid/dar-backup@sha256:" + ("a" * 64)


def _run(
    command: list[str],
    cwd: Path,
    *,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run one subprocess for an integration test.

    Args:
        command: Command and arguments to execute.
        cwd: Working directory for the subprocess.
        check: Whether a nonzero exit should raise immediately.

    Returns:
        Completed subprocess with captured output.

    Raises:
        subprocess.CalledProcessError: If ``check`` is true and the command fails.
    """
    return subprocess.run(
        command,
        cwd=cwd,
        check=check,
        capture_output=True,
        text=True,
    )


def _git(repository: Path, *arguments: str) -> str:
    """Run Git and return stripped standard output.

    Args:
        repository: Git worktree or bare repository.
        *arguments: Git command arguments.

    Returns:
        Stripped standard output.

    Raises:
        subprocess.CalledProcessError: If Git exits unsuccessfully.
    """
    result = _run(["git", "-C", str(repository), *arguments], repository)
    return result.stdout.strip()


def _create_repository(tmp_path: Path) -> tuple[Path, Path, str]:
    """Create a worktree and bare origin with ignored evidence patterns.

    Args:
        tmp_path: Temporary directory owned by the test.

    Returns:
        Worktree, bare origin, and initial application SHA.

    Raises:
        subprocess.CalledProcessError: If repository setup fails.
    """
    origin = tmp_path / "origin.git"
    worktree = tmp_path / "worktree"
    _run(["git", "init", "--bare", "--initial-branch=main", str(origin)], tmp_path)
    _run(["git", "init", "--initial-branch=main", str(worktree)], tmp_path)
    _git(worktree, "config", "user.name", "Housekeeping Test")
    _git(worktree, "config", "user.email", "housekeeping@example.invalid")

    (worktree / ".gitignore").write_text(
        "*.sarif\n*.cyclonedx.json\n",
        encoding="utf-8",
    )
    (worktree / "doc").mkdir()
    (worktree / "doc" / "build-history.json").write_text("[]\n", encoding="utf-8")
    (worktree / "doc" / "cosign_badge.json").write_text("{}\n", encoding="utf-8")
    _git(worktree, "add", ".gitignore", "doc")
    _git(worktree, "commit", "-m", "initial source")
    application_sha = _git(worktree, "rev-parse", "HEAD")
    _git(worktree, "remote", "add", "origin", str(origin))
    _git(worktree, "push", "-u", "origin", "main")
    return worktree, origin, application_sha


def _write_housekeeping_files(worktree: Path) -> tuple[Path, Path, Path, Path]:
    """Create changed metadata and ignored evidence files.

    Args:
        worktree: Test checkout receiving generated housekeeping files.

    Returns:
        Relative history, SARIF, SBOM, and badge paths.
    """
    history = Path("doc/build-history.json")
    sarif = Path("doc/sarif/report.sarif")
    sbom = Path("doc/sbom/report.cyclonedx.json")
    badge = Path("doc/cosign_badge.json")
    (worktree / sarif).parent.mkdir()
    (worktree / sbom).parent.mkdir()
    (worktree / history).write_text('[{"tag":"1.2.3-4"}]\n', encoding="utf-8")
    (worktree / sarif).write_text('{"runs":[]}\n', encoding="utf-8")
    (worktree / sbom).write_text('{"bomFormat":"CycloneDX"}\n', encoding="utf-8")
    (worktree / badge).write_text('{"message":"ok"}\n', encoding="utf-8")
    return history, sarif, sbom, badge


def _run_housekeeping(
    worktree: Path,
    application_sha: str,
    paths: tuple[Path, Path, Path, Path],
) -> subprocess.CompletedProcess[str]:
    """Run the real housekeeping helper in a test checkout.

    Args:
        worktree: Test checkout to publish.
        application_sha: Source commit recorded in the tag annotation.
        paths: History, SARIF, SBOM, and badge paths.

    Returns:
        Completed helper subprocess.
    """
    history, sarif, sbom, badge = paths
    return _run(
        [
            "bash",
            str(HOUSEKEEPING),
            "1.2.3-4",
            application_sha,
            DIGEST,
            str(history),
            str(sarif),
            str(sbom),
            str(badge),
        ],
        worktree,
        check=False,
    )


def test_housekeeping_atomically_pushes_metadata_tag_and_ignored_evidence(
    tmp_path: Path,
) -> None:
    """Successful housekeeping publishes one tagged audit commit."""
    worktree, origin, application_sha = _create_repository(tmp_path)
    paths = _write_housekeeping_files(worktree)

    result = _run_housekeeping(worktree, application_sha, paths)

    assert result.returncode == 0, result.stderr
    remote_main = _git(origin, "rev-parse", "refs/heads/main")
    tag_target = _git(origin, "rev-parse", "refs/tags/v1.2.3-4^{commit}")
    tracked_files = _git(origin, "ls-tree", "-r", "--name-only", remote_main)
    tag_message = _git(origin, "for-each-ref", "--format=%(contents)", "refs/tags/v1.2.3-4")

    assert tag_target == remote_main
    assert "doc/sarif/report.sarif" in tracked_files
    assert "doc/sbom/report.cyclonedx.json" in tracked_files
    assert f"Application source: {application_sha}" in tag_message
    assert f"Image digest: {DIGEST}" in tag_message


def test_housekeeping_rejected_tag_leaves_remote_branch_unchanged(
    tmp_path: Path,
) -> None:
    """An atomic tag rejection cannot publish history without its tag."""
    worktree, origin, application_sha = _create_repository(tmp_path)
    original_main = _git(origin, "rev-parse", "refs/heads/main")
    paths = _write_housekeeping_files(worktree)
    hook = origin / "hooks" / "pre-receive"
    hook.write_text(
        "#!/bin/bash\n"
        "set -euo pipefail\n"
        "while read -r _old _new ref; do\n"
        "  if [[ \"${ref}\" == refs/tags/* ]]; then\n"
        "    exit 1\n"
        "  fi\n"
        "done\n",
        encoding="utf-8",
    )
    hook.chmod(0o755)

    result = _run_housekeeping(worktree, application_sha, paths)

    assert result.returncode != 0
    assert _git(origin, "rev-parse", "refs/heads/main") == original_main
    missing_tag = _run(
        ["git", "-C", str(origin), "rev-parse", "refs/tags/v1.2.3-4"],
        origin,
        check=False,
    )
    assert missing_tag.returncode != 0
