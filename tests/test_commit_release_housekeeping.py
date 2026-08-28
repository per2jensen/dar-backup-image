# SPDX-FileCopyrightText: 2025-2026 Per Jensen
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This file is part of dar-backup-image:
# https://github.com/per2jensen/dar-backup-image
#
# License terms and warranty disclaimer:
# https://github.com/per2jensen/dar-backup-image/blob/main/LICENSE

"""Integration tests for atomic release housekeeping publication."""

from __future__ import annotations

import subprocess
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).parents[1]
HOUSEKEEPING = REPOSITORY_ROOT / "scripts" / "commit_release_housekeeping.sh"
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
        Worktree, bare origin, and immutable release-source SHA.

    Raises:
        subprocess.CalledProcessError: If repository setup fails.
    """
    origin = tmp_path / "origin.git"
    worktree = tmp_path / "worktree"
    _run(["git", "init", "--bare", "--initial-branch=main", str(origin)], tmp_path)
    _run(["git", "init", "--initial-branch=main", str(worktree)], tmp_path)
    _git(worktree, "config", "user.name", "Release Test")
    _git(worktree, "config", "user.email", "release@example.invalid")

    (worktree / ".gitignore").write_text(
        "*.sarif\n*.cyclonedx.json\n",
        encoding="utf-8",
    )
    for directory in ("doc", "docs", "clonepulse"):
        (worktree / directory).mkdir()
    files = {
        "doc/build-history.json": "[]\n",
        "doc/cosign_badge.json": "{}\n",
        "README.md": "old readme\n",
        "docs/index.html": "old page\n",
        "clonepulse/fetch_clones.json": "[]\n",
    }
    for name, content in files.items():
        (worktree / name).write_text(content, encoding="utf-8")
    _git(worktree, "add", ".")
    _git(worktree, "commit", "-m", "immutable release source")
    source_sha = _git(worktree, "rev-parse", "HEAD")
    _git(worktree, "remote", "add", "origin", str(origin))
    _git(worktree, "push", "-u", "origin", "main")
    return worktree, origin, source_sha


def _write_housekeeping_files(worktree: Path) -> tuple[Path, ...]:
    """Create the complete set of generated release files.

    Args:
        worktree: Test checkout receiving generated housekeeping files.

    Returns:
        Relative paths in the helper's required argument order.
    """
    paths = (
        Path("doc/build-history.json"),
        Path("doc/sarif/report.sarif"),
        Path("doc/sbom/report.cyclonedx.json"),
        Path("README.md"),
        Path("doc/cosign_badge.json"),
        Path("docs/index.html"),
        Path("clonepulse/fetch_clones.json"),
    )
    (worktree / paths[1]).parent.mkdir()
    (worktree / paths[2]).parent.mkdir()
    contents = (
        '[{"tag":"1.2.3-rc1"}]\n',
        '{"runs":[]}\n',
        '{"bomFormat":"CycloneDX"}\n',
        "new readme\n",
        '{"message":"ok"}\n',
        "new page\n",
        '[{"version":"1.2.3-rc1"}]\n',
    )
    for path, content in zip(paths, contents, strict=True):
        (worktree / path).write_text(content, encoding="utf-8")
    return paths


def _run_housekeeping(
    worktree: Path,
    source_sha: str,
    paths: tuple[Path, ...],
) -> subprocess.CompletedProcess[str]:
    """Run the real release-housekeeping helper.

    Args:
        worktree: Test checkout to publish.
        source_sha: Immutable release-source commit.
        paths: Generated housekeeping paths.

    Returns:
        Completed helper subprocess.
    """
    return _run(
        [
            "bash",
            str(HOUSEKEEPING),
            "1.2.3-rc1",
            source_sha,
            DIGEST,
            *(str(path) for path in paths),
        ],
        worktree,
        check=False,
    )


def test_housekeeping_atomically_pushes_source_tag_and_ignored_evidence(
    tmp_path: Path,
) -> None:
    """A release publishes one audit commit and a source-pointing tag."""
    worktree, origin, source_sha = _create_repository(tmp_path)
    paths = _write_housekeeping_files(worktree)

    result = _run_housekeeping(worktree, source_sha, paths)

    assert result.returncode == 0, result.stderr
    remote_main = _git(origin, "rev-parse", "refs/heads/main")
    tag_target = _git(origin, "rev-parse", "refs/tags/v1.2.3-rc1^{commit}")
    tracked_files = _git(origin, "ls-tree", "-r", "--name-only", remote_main)
    tag_message = _git(
        origin,
        "for-each-ref",
        "--format=%(contents)",
        "refs/tags/v1.2.3-rc1",
    )

    assert remote_main != source_sha
    assert tag_target == source_sha
    assert "doc/sarif/report.sarif" in tracked_files
    assert "doc/sbom/report.cyclonedx.json" in tracked_files
    assert f"Application source: {source_sha}" in tag_message
    assert f"Housekeeping commit: {remote_main}" in tag_message
    assert f"Image digest: {DIGEST}" in tag_message


def test_housekeeping_rejected_tag_leaves_remote_branch_unchanged(
    tmp_path: Path,
) -> None:
    """An atomic tag rejection cannot publish release housekeeping alone."""
    worktree, origin, source_sha = _create_repository(tmp_path)
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

    result = _run_housekeeping(worktree, source_sha, paths)

    assert result.returncode != 0
    assert _git(origin, "rev-parse", "refs/heads/main") == original_main
    missing_tag = _run(
        ["git", "-C", str(origin), "rev-parse", "refs/tags/v1.2.3-rc1"],
        origin,
        check=False,
    )
    assert missing_tag.returncode != 0


def test_housekeeping_wrong_starting_source_rejects_without_remote_change(
    tmp_path: Path,
) -> None:
    """A checkout not rooted at the selected source cannot publish metadata."""
    worktree, origin, source_sha = _create_repository(tmp_path)
    original_main = _git(origin, "rev-parse", "refs/heads/main")
    paths = _write_housekeeping_files(worktree)
    wrong_source = "b" * 40

    result = _run_housekeeping(worktree, wrong_source, paths)

    assert result.returncode != 0
    assert source_sha in result.stderr
    assert _git(origin, "rev-parse", "refs/heads/main") == original_main


def test_housekeeping_unexpected_staged_file_rejects_without_remote_change(
    tmp_path: Path,
) -> None:
    """An unrelated staged change cannot enter the release audit commit."""
    worktree, origin, source_sha = _create_repository(tmp_path)
    original_main = _git(origin, "rev-parse", "refs/heads/main")
    paths = _write_housekeeping_files(worktree)
    (worktree / "source.txt").write_text("unexpected change\n", encoding="utf-8")
    _git(worktree, "add", "source.txt")

    result = _run_housekeeping(worktree, source_sha, paths)

    assert result.returncode != 0
    assert "unexpected staged housekeeping path: source.txt" in result.stderr
    assert _git(origin, "rev-parse", "refs/heads/main") == original_main


def test_housekeeping_empty_evidence_rejects_without_remote_change(
    tmp_path: Path,
) -> None:
    """An empty SBOM cannot enter the release audit transaction."""
    worktree, origin, source_sha = _create_repository(tmp_path)
    original_main = _git(origin, "rev-parse", "refs/heads/main")
    paths = _write_housekeeping_files(worktree)
    (worktree / paths[2]).write_text("", encoding="utf-8")

    result = _run_housekeeping(worktree, source_sha, paths)

    assert result.returncode != 0
    assert "does not exist or is empty" in result.stderr
    assert _git(origin, "rev-parse", "refs/heads/main") == original_main
