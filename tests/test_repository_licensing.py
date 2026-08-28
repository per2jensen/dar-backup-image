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
