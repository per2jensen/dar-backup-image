"""Integration tests for existing GitHub Release finalization selection."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any


REPOSITORY_ROOT = Path(__file__).parents[1]
SELECTOR = REPOSITORY_ROOT / "scripts" / "select_release_finalization.py"
DIGEST = "sha256:" + ("a" * 64)
IMAGE_DIGEST = f"example/image@{DIGEST}"


def _run(
    command: list[str],
    cwd: Path,
    *,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run one subprocess with captured output.

    Args:
        command: Command and arguments to execute.
        cwd: Working directory for the subprocess.
        check: Whether to raise for a nonzero exit.

    Returns:
        Completed subprocess.

    Raises:
        subprocess.CalledProcessError: If ``check`` is true and execution fails.
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
        repository: Git worktree.
        *arguments: Git arguments.

    Returns:
        Stripped standard output.

    Raises:
        subprocess.CalledProcessError: If Git exits unsuccessfully.
    """
    return _run(["git", "-C", str(repository), *arguments], repository).stdout.strip()


def _record(source_sha: str) -> dict[str, Any]:
    """Build one valid release-history record.

    Args:
        source_sha: Immutable source commit.

    Returns:
        JSON-compatible release record.
    """
    return {
        "tag": "1.2.3-rc1",
        "git_revision": source_sha,
        "digest": DIGEST,
        "dar_backup_version": "1.4.5",
        "dar_version": "2.7.9",
        "cosign": {
            "signed": True,
            "image_digest": IMAGE_DIGEST,
            "rekor_log_entry": "https://search.sigstore.dev/?logIndex=123",
        },
        "sbom": {
            "file": "doc/sbom/release.cyclonedx.json",
            "release_asset_url": (
                "https://github.com/example/project/releases/download/"
                "v1.2.3-rc1/release.cyclonedx.json"
            ),
        },
        "grype_scan": {"file": "release.sarif"},
    }


def _create_release_repository(
    tmp_path: Path,
    *,
    tag_target_is_source: bool = True,
) -> tuple[Path, str, str]:
    """Create a source commit, housekeeping commit, and annotated release tag.

    Args:
        tmp_path: Temporary directory owned by the test.
        tag_target_is_source: Whether the tag should target the source commit.

    Returns:
        Repository path, source SHA, and housekeeping SHA.

    Raises:
        subprocess.CalledProcessError: If Git repository construction fails.
    """
    repository = tmp_path / "repository"
    _run(["git", "init", "--initial-branch=main", str(repository)], tmp_path)
    _git(repository, "config", "user.name", "Finalization Test")
    _git(repository, "config", "user.email", "finalize@example.invalid")
    (repository / "source.txt").write_text("immutable source\n", encoding="utf-8")
    _git(repository, "add", "source.txt")
    _git(repository, "commit", "-m", "release source")
    source_sha = _git(repository, "rev-parse", "HEAD")

    (repository / "doc" / "sbom").mkdir(parents=True)
    (repository / "doc" / "sarif").mkdir()
    (repository / "doc" / "sbom" / "release.cyclonedx.json").write_text(
        '{"bomFormat":"CycloneDX"}\n', encoding="utf-8"
    )
    (repository / "doc" / "sarif" / "release.sarif").write_text(
        '{"runs":[]}\n', encoding="utf-8"
    )
    (repository / "doc" / "build-history.json").write_text(
        json.dumps([_record(source_sha)], indent=2) + "\n",
        encoding="utf-8",
    )
    _git(repository, "add", "doc")
    _git(repository, "commit", "-m", "release housekeeping")
    housekeeping_sha = _git(repository, "rev-parse", "HEAD")
    tag_target = source_sha if tag_target_is_source else housekeeping_sha
    _git(
        repository,
        "tag",
        "-a",
        "v1.2.3-rc1",
        "-m",
        "Release version v1.2.3-rc1",
        "-m",
        f"Application source: {source_sha}",
        "-m",
        f"Housekeeping commit: {housekeeping_sha}",
        "-m",
        f"Image digest: {IMAGE_DIGEST}",
        tag_target,
    )
    return repository, source_sha, housekeeping_sha


def _run_selector(repository: Path) -> subprocess.CompletedProcess[str]:
    """Run the selector against one test repository.

    Args:
        repository: Test repository containing history and tags.

    Returns:
        Completed selector subprocess.
    """
    return _run(
        [
            "python3",
            str(SELECTOR),
            "--history",
            "doc/build-history.json",
            "--repository",
            ".",
            "--version",
            "1.2.3-rc1",
            "--dockerhub-repository",
            "example/image",
            "--github-repository",
            "example/project",
        ],
        repository,
        check=False,
    )


def test_selector_consistent_existing_release_returns_finalization_metadata(
    tmp_path: Path,
) -> None:
    """Consistent history, tag, digest, and evidence are accepted."""
    repository, source_sha, housekeeping_sha = _create_release_repository(tmp_path)

    result = _run_selector(repository)

    assert result.returncode == 0, result.stderr
    selection = json.loads(result.stdout)
    assert selection == {
        "dar_backup_version": "1.4.5",
        "dar_version": "2.7.9",
        "housekeeping_sha": housekeeping_sha,
        "image_digest": IMAGE_DIGEST,
        "rekor_url": "https://search.sigstore.dev/?logIndex=123",
        "sarif_file": "doc/sarif/release.sarif",
        "sbom_file": "doc/sbom/release.cyclonedx.json",
        "source_sha": source_sha,
        "version": "1.2.3-rc1",
    }


def test_selector_tag_not_pointing_to_source_rejects_finalization(
    tmp_path: Path,
) -> None:
    """A tag targeting housekeeping cannot authorize a GitHub Release."""
    repository, _, _ = _create_release_repository(
        tmp_path, tag_target_is_source=False
    )

    result = _run_selector(repository)

    assert result.returncode == 2
    assert "does not identify the recorded source commit" in result.stderr
    assert result.stdout == ""


def test_selector_missing_committed_evidence_rejects_finalization(
    tmp_path: Path,
) -> None:
    """A history record cannot substitute for a missing release asset."""
    repository, _, _ = _create_release_repository(tmp_path)
    (repository / "doc" / "sbom" / "release.cyclonedx.json").unlink()

    result = _run_selector(repository)

    assert result.returncode == 2
    assert "committed evidence file is missing or empty" in result.stderr
    assert result.stdout == ""


def test_selector_evidence_changed_after_housekeeping_rejects_finalization(
    tmp_path: Path,
) -> None:
    """Later modifications cannot replace evidence bound to the release tag."""
    repository, _, _ = _create_release_repository(tmp_path)
    (repository / "doc" / "sbom" / "release.cyclonedx.json").write_text(
        '{"bomFormat":"tampered"}\n', encoding="utf-8"
    )
    _git(repository, "add", "doc/sbom/release.cyclonedx.json")
    _git(repository, "commit", "-m", "replace evidence")

    result = _run_selector(repository)

    assert result.returncode == 2
    assert "current evidence differs from the housekeeping commit" in result.stderr
    assert result.stdout == ""
