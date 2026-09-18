# SPDX-FileCopyrightText: 2025-2026 Per Jensen
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This file is part of dar-backup-image:
# https://github.com/per2jensen/dar-backup-image
#
# License terms and warranty disclaimer:
# https://github.com/per2jensen/dar-backup-image/blob/main/LICENSE

"""Regression tests for repository-relative documentation links."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote, urlsplit


REPOSITORY_ROOT = Path(__file__).parents[1]
MARKDOWN_LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)")
HTML_LINK_RE = re.compile(r"href=[\"']([^\"']+)[\"']")


def _missing_local_targets(markdown_path: Path) -> list[str]:
    """Return repository-relative link targets that do not exist.

    Args:
        markdown_path: Markdown document whose local targets should be checked.

    Returns:
        Sorted display strings for missing targets, including their source file.

    Raises:
        ValueError: If the supplied path is not a Markdown file.
    """
    if markdown_path.suffix.lower() != ".md":
        raise ValueError(f"documentation path must be Markdown: {markdown_path}")

    content = markdown_path.read_text(encoding="utf-8")
    targets = MARKDOWN_LINK_RE.findall(content) + HTML_LINK_RE.findall(content)
    missing: list[str] = []
    for raw_target in targets:
        target = raw_target.strip("<>")
        parsed = urlsplit(target)
        if parsed.scheme or parsed.netloc or target.startswith(("#", "/")):
            continue
        relative_path = unquote(parsed.path)
        if not relative_path:
            continue
        candidate = (markdown_path.parent / relative_path).resolve()
        if not candidate.exists():
            missing.append(f"{markdown_path}: {target}")
    return sorted(missing)


def test_local_link_checker_accepts_existing_target(tmp_path: Path) -> None:
    """An existing relative Markdown target produces no missing-link result."""
    target = tmp_path / "target.md"
    target.write_text("# Target\n", encoding="utf-8")
    source = tmp_path / "source.md"
    source.write_text("[Target](target.md#target)\n", encoding="utf-8")

    assert _missing_local_targets(source) == []


def test_local_link_checker_reports_missing_target(tmp_path: Path) -> None:
    """A missing relative Markdown target is reported with source context."""
    source = tmp_path / "source.md"
    source.write_text("[Missing](missing.md)\n", encoding="utf-8")

    assert _missing_local_targets(source) == [f"{source}: missing.md"]


def test_repository_markdown_local_targets_exist() -> None:
    """Every repository-relative target in maintained Markdown exists."""
    missing = [
        failure
        for markdown_path in sorted(REPOSITORY_ROOT.rglob("*.md"))
        if ".git" not in markdown_path.parts
        for failure in _missing_local_targets(markdown_path)
    ]

    assert missing == []


def test_release_documentation_uses_current_rc2_qualification() -> None:
    """Release instructions require the clean RC2 qualification procedure."""
    readme = (REPOSITORY_ROOT / "README.md").read_text(encoding="utf-8")
    release_guide = (REPOSITORY_ROOT / "doc" / "Release.md").read_text(
        encoding="utf-8"
    )
    makefile = (REPOSITORY_ROOT / "Makefile").read_text(encoding="utf-8")

    for document in (readme, release_guide):
        assert "make dev-nuke" in document
        assert "make verify-dev-image" in document
        assert "make IMAGE=dar-backup:dev test-nobuild" in document
        assert "dry-run-release" not in document
    assert "`1.0.0-rc2` and verify:" in release_guide
    assert "dry-run-release:" not in makefile


def test_archive_documentation_describes_checksum_behavior() -> None:
    """Archive documentation reflects automatic checksum creation and checks."""
    readme = (REPOSITORY_ROOT / "README.md").read_text(encoding="utf-8")
    release_guide = (REPOSITORY_ROOT / "doc" / "Release.md").read_text(
        encoding="utf-8"
    )
    follow_ups = (
        REPOSITORY_ROOT / "doc" / "documentation-follow-ups.md"
    ).read_text(encoding="utf-8")

    assert "does create and subsequently validate a SHA-256 file" in readme
    assert "creates and validates a SHA-256 checksum" in release_guide
    assert "records a SHA-256\nchecksum" in follow_ups
    assert "checksum the saved archive" not in release_guide
