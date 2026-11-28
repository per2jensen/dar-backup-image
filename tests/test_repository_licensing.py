# SPDX-FileCopyrightText: 2025-2026 Per Jensen
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This file is part of dar-backup-image:
# https://github.com/per2jensen/dar-backup-image
#
# License terms and warranty disclaimer:
# https://github.com/per2jensen/dar-backup-image/blob/main/LICENSE

"""Tests for repository copyright and licence-header policy."""

from __future__ import annotations

import subprocess
from pathlib import Path


SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "validate_license_headers.py"
REPOSITORY_ROOT = Path(__file__).parents[1]


def _run_validator(repository_root: Path) -> subprocess.CompletedProcess[str]:
    """Run the real licence-header validator against a Git working tree.

    Args:
        repository_root: Git working tree to validate.

    Returns:
        Completed validator process.

    Raises:
        ValueError: If ``repository_root`` is not a directory.
    """
    if not isinstance(repository_root, Path):
        raise ValueError("repository_root must be a pathlib.Path")
    if not repository_root.is_dir():
        raise ValueError(f"repository root is not a directory: {repository_root}")
    return subprocess.run(
        ["python3", str(SCRIPT_PATH), "--root", str(repository_root)],
        capture_output=True,
        check=False,
        text=True,
    )


def test_license_header_validator_repository_files_pass() -> None:
    """All current commentable repository files satisfy the header policy."""
    result = _run_validator(REPOSITORY_ROOT)

    assert result.returncode == 0, result.stderr
    assert "Validated license headers" in result.stderr


def test_license_header_validator_missing_header_fails(tmp_path: Path) -> None:
    """A newly tracked Python file without a header is rejected.

    Args:
        tmp_path: Isolated real Git working tree.
    """
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    invalid_file = tmp_path / "missing_header.py"
    invalid_file.write_text("value = 1\n", encoding="utf-8")
    subprocess.run(
        ["git", "-C", str(tmp_path), "add", "missing_header.py"],
        check=True,
    )

    result = _run_validator(tmp_path)

    assert result.returncode == 2
    assert "missing_header.py has an incomplete GPL-3.0-or-later header" in result.stderr
    assert "SPDX-FileCopyrightText:" in result.stderr


# REUSE-IgnoreStart
# The tag below is fixture data for the helper; it is not this file's header.
_SPDX_LICENSE_IDENTIFIER = "SPDX-License-Identifier:"
# REUSE-IgnoreEnd


def _unignored_spdx_license_lines(text: str) -> list[tuple[int, str]]:
    """Return literal SPDX license tag lines REUSE would parse as declarations.

    Args:
        text: Python source text to inspect line by line.

    Returns:
        ``(line number, stripped text)`` pairs for tag occurrences that are
        neither header comments nor wrapped in a REUSE-Ignore block.
    """
    offenders: list[tuple[int, str]] = []
    ignoring = False
    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if "REUSE-IgnoreStart" in stripped:
            ignoring = True
            continue
        if "REUSE-IgnoreEnd" in stripped:
            ignoring = False
            continue
        if _SPDX_LICENSE_IDENTIFIER in line and not line.lstrip().startswith("#"):
            if not ignoring:
                offenders.append((number, stripped))
    return offenders


def _tracked_python_paths() -> list[Path]:
    """Return tracked and non-ignored Python files under the repository root."""
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z", "*.py"],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
    )
    return sorted(
        REPOSITORY_ROOT / raw.decode("utf-8")
        for raw in result.stdout.split(b"\0")
        if raw
    )


def test_unignored_spdx_license_literal_is_detected() -> None:
    """A literal SPDX license tag outside a REUSE-Ignore block is flagged."""
    line_text = f'message = "{_SPDX_LICENSE_IDENTIFIER} GPL-3.0-or-later"'
    text = f"{line_text}\n"

    assert _unignored_spdx_license_lines(text) == [(1, line_text)]


def test_reuse_ignored_spdx_license_literal_is_not_detected() -> None:
    """A literal SPDX license tag inside a REUSE-Ignore block is accepted."""
    text = (
        "# REUSE-IgnoreStart\n"
        f'message = "{_SPDX_LICENSE_IDENTIFIER} GPL-3.0-or-later"\n'
        "# REUSE-IgnoreEnd\n"
    )

    assert _unignored_spdx_license_lines(text) == []


def test_repository_python_literal_spdx_lines_are_reuse_ignored() -> None:
    """Every literal SPDX license tag in tracked Python sits in a REUSE-Ignore block."""
    offenders: list[str] = []
    for path in _tracked_python_paths():
        text = path.read_text(encoding="utf-8")
        for number, content in _unignored_spdx_license_lines(text):
            offenders.append(f"{path}:{number}: {content}")

    assert offenders == []
