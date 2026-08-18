"""Tests for complete large-scale restore content comparison."""

from __future__ import annotations

import importlib.util
import os
import shutil
import struct
import subprocess
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
compare_permission_modes = RESTORE_MODULE.compare_permission_modes
compare_attribute_group = RESTORE_MODULE._compare_attribute_group
compare_filesystem_device = RESTORE_MODULE._compare_filesystem_device
compare_ownership = RESTORE_MODULE._compare_ownership
validate_same_filesystem_devices = RESTORE_MODULE._validate_same_filesystem_devices


def _posix_access_acl_value(user_id: int, named_user_permissions: int) -> bytes:
    """Build one valid Linux POSIX access-ACL xattr value.

    Args:
        user_id: Numeric ID for the named-user ACL entry.
        named_user_permissions: Three-bit permission value for that entry.

    Returns:
        Binary ``system.posix_acl_access`` value accepted by Linux filesystems.
    """
    undefined_id = 0xFFFFFFFF
    entries = (
        (0x01, 0o6, undefined_id),
        (0x02, named_user_permissions, user_id),
        (0x04, 0o4, undefined_id),
        (0x10, 0o4, undefined_id),
        (0x20, 0o0, undefined_id),
    )
    return struct.pack("<I", 2) + b"".join(
        struct.pack("<HHI", tag, permissions, identifier)
        for tag, permissions, identifier in entries
    )


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
    assert summary.ownership_entry_count == summary.restored_entry_count
    assert summary.permission_entry_count == summary.restored_entry_count - 1
    assert summary.metadata_profile == "portable-posix-v1"
    assert summary.filesystem_device == source_root.stat().st_dev


def test_validate_same_filesystem_devices_matching_values_pass() -> None:
    """Equal filesystem device numbers satisfy the restore contract."""
    validate_same_filesystem_devices(42, 42)


def test_validate_same_filesystem_devices_different_values_raise_value_error() -> None:
    """A cross-filesystem restore target is rejected explicitly."""
    with pytest.raises(ValueError, match="must be on the same filesystem"):
        validate_same_filesystem_devices(42, 84)


def test_compare_ownership_different_numeric_ids_records_mismatch() -> None:
    """Numeric UID/GID differences are reported without resolving names."""
    mismatches: list[str] = []

    compare_ownership(1000, 1000, 1001, 1002, Path("private.txt"), mismatches)

    assert mismatches == [
        "numeric ownership differs for private.txt: "
        "source=1000:1000, restored=1001:1002"
    ]


def test_compare_filesystem_device_nested_mount_records_mismatch() -> None:
    """An entry from a nested filesystem violates the same-filesystem contract."""
    mismatches: list[str] = []

    compare_filesystem_device(84, 42, Path("nested/photo.raw"), "source", mismatches)

    assert mismatches == [
        "source entry crosses the same-filesystem boundary for nested/photo.raw: "
        "root st_dev=42, entry st_dev=84"
    ]


def test_compare_restore_matching_portable_xattr_passes(tmp_path: Path) -> None:
    """A byte-identical user extended attribute is counted and accepted.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    source_root, restored_root, required_relative = _build_matching_trees(tmp_path)
    source_file = source_root / "photos" / "photo.raw"
    restored_file = restored_root / "photos" / "photo.raw"
    value = b"portable\x00metadata\xff"
    os.setxattr(source_file, "user.dar-backup.profile", value)
    os.setxattr(restored_file, "user.dar-backup.profile", value)

    summary = compare_restore(source_root, restored_root, required_relative)

    assert summary.portable_xattr_count == 1


def test_compare_restore_missing_portable_xattr_raises_comparison_error(
    tmp_path: Path,
) -> None:
    """A missing restored user extended attribute fails comparison.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    source_root, restored_root, required_relative = _build_matching_trees(tmp_path)
    os.setxattr(
        source_root / "photos" / "photo.raw",
        "user.dar-backup.profile",
        b"portable-posix-v1",
    )

    with pytest.raises(
        ComparisonError,
        match=r"portable extended attribute is missing for photos/photo.raw",
    ):
        compare_restore(source_root, restored_root, required_relative)


def test_compare_restore_matching_posix_acl_passes(tmp_path: Path) -> None:
    """A byte-identical POSIX access ACL is counted and accepted.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    source_root, restored_root, required_relative = _build_matching_trees(tmp_path)
    source_file = source_root / "photos" / "photo.raw"
    restored_file = restored_root / "photos" / "photo.raw"
    acl_value = _posix_access_acl_value(os.getuid(), 0o4)
    os.setxattr(source_file, "system.posix_acl_access", acl_value)
    os.setxattr(restored_file, "system.posix_acl_access", acl_value)

    summary = compare_restore(source_root, restored_root, required_relative)

    assert summary.posix_acl_count == 1


def test_compare_attribute_group_different_acl_value_records_mismatch() -> None:
    """Different canonical ACL values are rejected deterministically."""
    attribute_name = "system.posix_acl_access"
    mismatches: list[str] = []

    checked = compare_attribute_group(
        {attribute_name: b"source-acl"},
        {attribute_name: b"restored-acl"},
        Path("restricted"),
        "POSIX ACL",
        mismatches,
    )

    assert checked == 1
    assert mismatches == [
        "POSIX ACL value differs for restricted: system.posix_acl_access"
    ]


def test_compare_restore_matching_hard_link_group_passes(tmp_path: Path) -> None:
    """Equivalent multi-path hard-link topology is counted and accepted.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    source_root, restored_root, required_relative = _build_matching_trees(tmp_path)
    source_first = source_root / "photos" / "linked-a.raw"
    source_first.write_bytes(b"linked-content")
    os.link(source_first, source_root / "photos" / "linked-b.raw")
    restored_first = restored_root / "photos" / "linked-a.raw"
    restored_first.write_bytes(b"linked-content")
    os.link(restored_first, restored_root / "photos" / "linked-b.raw")

    summary = compare_restore(source_root, restored_root, required_relative)

    assert summary.hard_link_group_count == 1


def test_compare_restore_split_hard_link_group_raises_comparison_error(
    tmp_path: Path,
) -> None:
    """Restoring hard-linked names as separate inodes fails comparison.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    source_root, restored_root, required_relative = _build_matching_trees(tmp_path)
    source_first = source_root / "photos" / "linked-a.raw"
    source_first.write_bytes(b"linked-content")
    os.link(source_first, source_root / "photos" / "linked-b.raw")
    (restored_root / "photos" / "linked-a.raw").write_bytes(b"linked-content")
    (restored_root / "photos" / "linked-b.raw").write_bytes(b"linked-content")

    with pytest.raises(ComparisonError, match="restored hard-link group is split"):
        compare_restore(source_root, restored_root, required_relative)


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


def test_compare_restore_matching_file_and_directory_modes_pass(
    tmp_path: Path,
) -> None:
    """Matching explicit file and directory permission modes are accepted.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    source_root, restored_root, required_relative = _build_matching_trees(tmp_path)
    source_directory = source_root / "photos"
    restored_directory = restored_root / "photos"
    source_file = source_directory / "photo.raw"
    restored_file = restored_directory / "photo.raw"
    source_directory.chmod(0o750)
    restored_directory.chmod(0o750)
    source_file.chmod(0o640)
    restored_file.chmod(0o640)

    compare_restore(source_root, restored_root, required_relative)


def test_compare_restore_file_mode_mismatch_raises_comparison_error(
    tmp_path: Path,
) -> None:
    """A restored regular file with broader permissions fails comparison.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    source_root, restored_root, required_relative = _build_matching_trees(tmp_path)
    (source_root / "photos" / "photo.raw").chmod(0o600)
    (restored_root / "photos" / "photo.raw").chmod(0o644)

    with pytest.raises(
        ComparisonError,
        match=r"permission mode differs for photos/photo.raw: source=0600, restored=0644",
    ):
        compare_restore(source_root, restored_root, required_relative)


def test_compare_restore_directory_mode_mismatch_raises_comparison_error(
    tmp_path: Path,
) -> None:
    """A restored directory with different permissions fails comparison.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    source_root, restored_root, required_relative = _build_matching_trees(tmp_path)
    (source_root / "photos").chmod(0o750)
    (restored_root / "photos").chmod(0o755)

    with pytest.raises(
        ComparisonError,
        match=r"permission mode differs for photos: source=0750, restored=0755",
    ):
        compare_restore(source_root, restored_root, required_relative)


def test_compare_permission_modes_matching_tree_returns_checked_count(
    tmp_path: Path,
) -> None:
    """The mandatory PITR permission comparison accepts a matching tree.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    source_root, restored_root, required_relative = _build_matching_trees(tmp_path)
    source_fixture = source_root / required_relative
    restored_fixture = restored_root / required_relative
    source_fixture.chmod(0o750)
    restored_fixture.chmod(0o750)

    checked = compare_permission_modes(source_fixture, restored_fixture)

    assert checked == 2


def test_compare_permission_modes_file_mismatch_raises_comparison_error(
    tmp_path: Path,
) -> None:
    """The mandatory PITR permission check rejects a changed file mode.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    source_root, restored_root, required_relative = _build_matching_trees(tmp_path)
    source_fixture = source_root / required_relative
    restored_fixture = restored_root / required_relative
    (source_fixture / "primer.bin").chmod(0o440)
    (restored_fixture / "primer.bin").chmod(0o640)

    with pytest.raises(
        ComparisonError,
        match=r"permission mode differs for primer.bin: source=0440, restored=0640",
    ):
        compare_permission_modes(source_fixture, restored_fixture)


def test_permissions_only_cli_reports_matching_entry_count(tmp_path: Path) -> None:
    """The real CLI exposes permission-only verification to the Bash harness.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    source_root, restored_root, required_relative = _build_matching_trees(tmp_path)
    source_fixture = source_root / required_relative
    restored_fixture = restored_root / required_relative

    result = subprocess.run(
        [
            sys.executable,
            str(MODULE_PATH),
            "--source-root",
            str(source_fixture),
            "--restored-root",
            str(restored_fixture),
            "--required-relative-path",
            ".",
            "--permissions-only",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == '{"permission_entry_count":2}\n'
