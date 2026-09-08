# SPDX-FileCopyrightText: 2025-2026 Per Jensen
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This file is part of dar-backup-image:
# https://github.com/per2jensen/dar-backup-image
#
# License terms and warranty disclaimer:
# https://github.com/per2jensen/dar-backup-image/blob/main/LICENSE

"""Tests for portable cross-filesystem source manifests."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import struct
import sys

import pytest


MODULE_PATH = (
    Path(__file__).parents[1] / "scripts" / "cross_filesystem_manifest.py"
)
MODULE_SPEC = importlib.util.spec_from_file_location(
    "cross_filesystem_manifest", MODULE_PATH
)
if MODULE_SPEC is None or MODULE_SPEC.loader is None:
    raise RuntimeError(f"Unable to load manifest helper from {MODULE_PATH}")
MANIFEST_MODULE = importlib.util.module_from_spec(MODULE_SPEC)
sys.modules[MODULE_SPEC.name] = MANIFEST_MODULE
MODULE_SPEC.loader.exec_module(MANIFEST_MODULE)
ManifestError = MANIFEST_MODULE.ManifestError
capture_manifest = MANIFEST_MODULE.capture_manifest
validate_restorable_identity = MANIFEST_MODULE.validate_restorable_identity
verify_manifest = MANIFEST_MODULE.verify_manifest


def _acl_value(user_id: int) -> bytes:
    """Build a valid Linux POSIX access-ACL xattr value.

    Args:
        user_id: Numeric named-user ID.

    Returns:
        Binary ACL accepted by Linux filesystems.
    """
    undefined_id = 0xFFFFFFFF
    entries = (
        (0x01, 0o6, undefined_id),
        (0x02, 0o4, user_id),
        (0x04, 0o4, undefined_id),
        (0x10, 0o4, undefined_id),
        (0x20, 0o0, undefined_id),
    )
    return struct.pack("<I", 2) + b"".join(
        struct.pack("<HHI", tag, permissions, identifier)
        for tag, permissions, identifier in entries
    )


def _create_tree(root: Path) -> None:
    """Create a representative portable filesystem tree.

    Args:
        root: Empty root to populate.

    Returns:
        None.
    """
    selected = root / "selected"
    nested = selected / "with space" / "unicode-æøå"
    nested.mkdir(parents=True)
    data_file = nested / "payload.bin"
    data_file.write_bytes(b"portable\x00payload")
    os.chmod(data_file, 0o640)
    os.link(data_file, nested / "payload-hardlink.bin")
    (selected / "link").symlink_to("with space/unicode-æøå/payload.bin")
    os.setxattr(data_file, "user.cross-filesystem-test", b"metadata\x00value")
    os.setxattr(data_file, "system.posix_acl_access", _acl_value(os.getuid()))


def test_manifest_matching_tree_content_and_metadata_passes(tmp_path: Path) -> None:
    """Matching trees preserve portable content and metadata.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    source = tmp_path / "source"
    restored = tmp_path / "restored"
    source.mkdir()
    restored.mkdir()
    _create_tree(source)
    _create_tree(restored)
    manifest = capture_manifest(source, ["selected"])

    summary = verify_manifest(manifest, restored, strict_extra=True)

    assert summary["file_count"] == 2
    assert summary["hard_link_group_count"] == 1
    assert summary["xattr_count"] >= 2


def test_manifest_changed_file_raises_manifest_error(tmp_path: Path) -> None:
    """Changed restored bytes fail verification.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    source = tmp_path / "source"
    restored = tmp_path / "restored"
    source.mkdir()
    restored.mkdir()
    _create_tree(source)
    _create_tree(restored)
    manifest = capture_manifest(source, ["selected"])
    (restored / "selected/with space/unicode-æøå/payload.bin").write_bytes(
        b"changed"
    )

    with pytest.raises(ManifestError, match="portable metadata differs"):
        verify_manifest(manifest, restored, strict_extra=True)


def test_manifest_unexpected_restored_entry_raises_manifest_error(
    tmp_path: Path,
) -> None:
    """An extra restored path fails strict verification.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    source = tmp_path / "source"
    restored = tmp_path / "restored"
    source.mkdir()
    restored.mkdir()
    _create_tree(source)
    _create_tree(restored)
    manifest = capture_manifest(source, ["selected"])
    (restored / "unexpected.txt").write_text("unexpected", encoding="utf-8")

    with pytest.raises(ManifestError, match="unexpected restored entry"):
        verify_manifest(manifest, restored, strict_extra=True)


def test_manifest_source_drift_is_detected(tmp_path: Path) -> None:
    """A source change after capture fails the stability verification.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    source = tmp_path / "source"
    source.mkdir()
    _create_tree(source)
    manifest = capture_manifest(source, ["selected"])
    os.chmod(source / "selected/with space/unicode-æøå/payload.bin", 0o600)

    with pytest.raises(ManifestError, match="portable metadata differs"):
        verify_manifest(manifest, source, strict_extra=False)


def test_manifest_unsupported_fifo_raises_manifest_error(tmp_path: Path) -> None:
    """A FIFO is rejected rather than silently omitted.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    source = tmp_path / "source"
    source.mkdir()
    os.mkfifo(source / "pipe")

    with pytest.raises(ManifestError, match="unsupported filesystem entry"):
        capture_manifest(source, ["."])


def test_manifest_unsafe_selection_raises_value_error(tmp_path: Path) -> None:
    """Parent traversal cannot escape the source root.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    source = tmp_path / "source"
    source.mkdir()

    with pytest.raises(ValueError, match="safe relative path"):
        capture_manifest(source, ["../private"])


def test_validate_restorable_identity_matching_owner_passes(tmp_path: Path) -> None:
    """The current owner and group are legal for a non-root restore.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    source = tmp_path / "source"
    source.mkdir()
    (source / "file").write_text("content", encoding="utf-8")
    manifest = capture_manifest(source, ["file"])

    validate_restorable_identity(manifest, os.getuid(), [os.getgid()])


def test_validate_restorable_identity_wrong_owner_raises_manifest_error(
    tmp_path: Path,
) -> None:
    """An unavailable UID is rejected before non-root restoration.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    source = tmp_path / "source"
    source.mkdir()
    (source / "file").write_text("content", encoding="utf-8")
    manifest = capture_manifest(source, ["file"])

    with pytest.raises(ManifestError, match="cannot be recreated"):
        validate_restorable_identity(manifest, os.getuid() + 1, [os.getgid()])
