"""Tests for complete large-scale restore content comparison."""

from __future__ import annotations

import importlib.util
import shutil
import sys
from pathlib import Path

import pytest


MODULE_PATH = (
    Path(__file__).parents[1] / "scripts" / "large_scale_restore_compare.py"
)
MODULE_SPEC = importlib.util.spec_from_file_location(
    "large_scale_restore_compare", MODULE_PATH
)
if MODULE_SPEC is None or MODULE_SPEC.loader is None:
    raise RuntimeError(f"Unable to load restore comparator from {MODULE_PATH}")
RESTORE_MODULE = importlib.util.module_from_spec(MODULE_SPEC)
sys.modules[MODULE_SPEC.name] = RESTORE_MODULE
MODULE_SPEC.loader.exec_module(RESTORE_MODULE)
ComparisonError = RESTORE_MODULE.ComparisonError
compare_restore = RESTORE_MODULE.compare_restore


def _build_matching_trees(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Create source and restored trees with a complete required fixture.

    Args:
        tmp_path: Isolated pytest temporary directory.

    Returns:
        Source root, restored root, and required relative fixture path.
    """
    source_root = tmp_path / "source"
    restored_root = tmp_path / "restored"
    required_relative = Path("work/diff-primer")
    source_fixture = source_root / required_relative
    source_fixture.mkdir(parents=True)
    (source_fixture / "primer.bin").write_bytes(b"primer-content")
    (source_fixture / "target.txt").write_text("target\n", encoding="utf-8")
    (source_fixture / "link.txt").symlink_to("target.txt")
    source_selected = source_root / "photos"
    source_selected.mkdir()
    (source_selected / "photo.raw").write_bytes(b"raw-photo-content")
    (source_root / "intentionally-excluded.tmp").write_text(
        "excluded\n", encoding="utf-8"
    )

    restored_root.mkdir()
    shutil.copytree(source_fixture, restored_root / required_relative, symlinks=True)
    shutil.copytree(source_selected, restored_root / "photos", symlinks=True)
    return source_root, restored_root, required_relative


def test_compare_restore_matching_selected_content_returns_counts(
    tmp_path: Path,
) -> None:
    """Matching restored content passes without requiring excluded source paths.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    source_root, restored_root, required_relative = _build_matching_trees(tmp_path)

    summary = compare_restore(source_root, restored_root, required_relative)

    assert summary.restored_file_count == 3
    assert summary.restored_bytes == len(b"primer-contenttarget\nraw-photo-content")
    assert summary.required_entry_count == 3


def test_compare_restore_changed_file_raises_comparison_error(tmp_path: Path) -> None:
    """A restored file with different bytes fails checksum comparison.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    source_root, restored_root, required_relative = _build_matching_trees(tmp_path)
    (restored_root / "photos" / "photo.raw").write_bytes(b"corrupt")

    with pytest.raises(ComparisonError, match="file size differs"):
        compare_restore(source_root, restored_root, required_relative)


def test_compare_restore_missing_required_entry_raises_comparison_error(
    tmp_path: Path,
) -> None:
    """A missing harness fixture file cannot be hidden by restored-only traversal.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    source_root, restored_root, required_relative = _build_matching_trees(tmp_path)
    (restored_root / required_relative / "primer.bin").unlink()

    with pytest.raises(ComparisonError, match="required restored entry is missing"):
        compare_restore(source_root, restored_root, required_relative)
