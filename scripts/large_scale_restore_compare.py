#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2025-2026 Per Jensen
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This file is part of dar-backup-image:
# https://github.com/per2jensen/dar-backup-image
#
# License terms and warranty disclaimer:
# https://github.com/per2jensen/dar-backup-image/blob/main/LICENSE

"""Compare a complete large-scale PITR restore with its live source."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import stat
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence


LOGGER = logging.getLogger(__name__)
HASH_BUFFER_BYTES = 1024 * 1024
MAX_REPORTED_MISMATCHES = 100
METADATA_PROFILE = "portable-posix-v1"
POSIX_ACL_XATTR_NAMES = frozenset(
    {"system.posix_acl_access", "system.posix_acl_default"}
)
PORTABLE_XATTR_PREFIX = "user."


class ComparisonError(RuntimeError):
    """Indicate that restored content differs from its live source."""


@dataclass(frozen=True)
class ComparisonSummary:
    """Describe the content and portable metadata checked in one restored tree.

    Attributes:
        restored_entry_count: Number of restored filesystem entries checked.
        restored_file_count: Number of restored regular-file paths checked.
        restored_bytes: Total apparent bytes across restored regular-file paths.
        required_entry_count: Number of required fixture entries checked.
        ownership_entry_count: Number of numeric UID/GID pairs checked.
        permission_entry_count: Number of non-symlink permission modes checked.
        posix_acl_count: Number of POSIX ACL attributes checked.
        portable_xattr_count: Number of ``user.*`` attributes checked.
        hard_link_group_count: Number of multi-path hard-link groups checked.
        metadata_profile: Stable name of the metadata comparison contract.
        filesystem_device: Shared source and restore filesystem device number.
    """

    restored_entry_count: int
    restored_file_count: int
    restored_bytes: int
    required_entry_count: int
    ownership_entry_count: int
    permission_entry_count: int
    posix_acl_count: int
    portable_xattr_count: int
    hard_link_group_count: int
    metadata_profile: str
    filesystem_device: int


@dataclass(frozen=True)
class EntryComparisonCounts:
    """Describe the successful comparisons attempted for one filesystem entry.

    Attributes:
        regular_files: Number of regular-file paths checked.
        restored_bytes: Apparent restored bytes checked.
        ownership_entries: Number of numeric UID/GID pairs checked.
        permission_entries: Number of non-symlink permission modes checked.
        posix_acls: Number of POSIX ACL attributes checked.
        portable_xattrs: Number of portable ``user.*`` attributes checked.
    """

    regular_files: int = 0
    restored_bytes: int = 0
    ownership_entries: int = 0
    permission_entries: int = 0
    posix_acls: int = 0
    portable_xattrs: int = 0


def _validate_directory(path: Path, label: str) -> Path:
    """Validate and resolve one directory argument.

    Args:
        path: Directory supplied by the caller.
        label: Human-readable argument label for errors.

    Returns:
        The resolved directory path.

    Raises:
        ValueError: If the path is missing or is not a directory.
    """
    if path is None:
        raise ValueError(f"{label} must not be None")
    resolved = path.resolve()
    if not resolved.is_dir():
        raise ValueError(f"{label} must be an existing directory: {path}")
    return resolved


def _relative_entries(root: Path) -> list[Path]:
    """Return every entry below a directory without following symlinks.

    Args:
        root: Existing directory to walk.

    Returns:
        Relative entry paths in deterministic lexical order.

    Raises:
        OSError: If an entry cannot be scanned.
    """
    entries: list[Path] = []
    pending = [Path(".")]
    while pending:
        relative_directory = pending.pop()
        directory = root / relative_directory
        children = sorted(os.scandir(directory), key=lambda item: item.name)
        for child in children:
            relative_path = relative_directory / child.name
            entries.append(relative_path)
            if child.is_dir(follow_symlinks=False):
                pending.append(relative_path)
    return sorted(entries, key=lambda path: os.fsencode(str(path)))


def _sha256(path: Path) -> str:
    """Calculate the SHA-256 digest of one regular file.

    Args:
        path: Regular file to read.

    Returns:
        Lowercase hexadecimal SHA-256 digest.

    Raises:
        OSError: If the file cannot be read.
    """
    digest = hashlib.sha256()
    with path.open("rb") as input_file:
        while chunk := input_file.read(HASH_BUFFER_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def _entry_kind(mode: int) -> str:
    """Return a stable name for a filesystem mode's entry type.

    Args:
        mode: ``st_mode`` value returned by ``lstat``.

    Returns:
        Stable filesystem entry type name.
    """
    if stat.S_ISREG(mode):
        return "file"
    if stat.S_ISDIR(mode):
        return "directory"
    if stat.S_ISLNK(mode):
        return "symlink"
    if stat.S_ISFIFO(mode):
        return "fifo"
    if stat.S_ISCHR(mode):
        return "character-device"
    if stat.S_ISBLK(mode):
        return "block-device"
    if stat.S_ISSOCK(mode):
        return "socket"
    return "unknown"


def _append_mismatch(mismatches: list[str], message: str) -> None:
    """Append a mismatch while bounding retained diagnostic output.

    Args:
        mismatches: Per-operation mismatch collection.
        message: Human-readable mismatch description.

    Returns:
        None.
    """
    if len(mismatches) < MAX_REPORTED_MISMATCHES:
        mismatches.append(message)


def _validate_same_filesystem_devices(
    source_device: int, restored_device: int
) -> None:
    """Require source and restore roots to identify the same filesystem.

    Args:
        source_device: Source root ``st_dev`` value.
        restored_device: Restore root ``st_dev`` value.

    Returns:
        None.

    Raises:
        ValueError: If either device is invalid or the devices differ.
    """
    if source_device < 0 or restored_device < 0:
        raise ValueError("filesystem device numbers must not be negative")
    if source_device == restored_device:
        return
    raise ValueError(
        "source_root and restored_root must be on the same filesystem: "
        f"source st_dev={source_device}, restored st_dev={restored_device}"
    )


def _compare_ownership(
    source_uid: int,
    source_gid: int,
    restored_uid: int,
    restored_gid: int,
    relative_path: Path,
    mismatches: list[str],
) -> None:
    """Compare numeric POSIX ownership for one filesystem entry.

    Args:
        source_uid: Numeric source owner ID.
        source_gid: Numeric source group ID.
        restored_uid: Numeric restored owner ID.
        restored_gid: Numeric restored group ID.
        relative_path: Relative path used in diagnostics.
        mismatches: Per-operation mismatch collection to update.

    Returns:
        None.
    """
    if source_uid == restored_uid and source_gid == restored_gid:
        return
    _append_mismatch(
        mismatches,
        f"numeric ownership differs for {relative_path}: "
        f"source={source_uid}:{source_gid}, restored={restored_uid}:{restored_gid}",
    )


def _compare_filesystem_device(
    entry_device: int,
    expected_device: int,
    relative_path: Path,
    tree_label: str,
    mismatches: list[str],
) -> None:
    """Require an entry to remain within its root filesystem device.

    Args:
        entry_device: Entry ``st_dev`` value.
        expected_device: Root ``st_dev`` value required by the contract.
        relative_path: Relative path used in diagnostics.
        tree_label: Human-readable source or restore tree name.
        mismatches: Per-operation mismatch collection to update.

    Returns:
        None.
    """
    if entry_device == expected_device:
        return
    _append_mismatch(
        mismatches,
        f"{tree_label} entry crosses the same-filesystem boundary for "
        f"{relative_path}: root st_dev={expected_device}, "
        f"entry st_dev={entry_device}",
    )


def _read_portable_attributes(path: Path) -> tuple[dict[str, bytes], dict[str, bytes]]:
    """Read POSIX ACLs and portable user extended attributes from one entry.

    Attribute operations do not follow symlinks. ACLs are represented by their
    canonical kernel xattr values; this is valid because the comparison contract
    requires source and restore entries to live on the same filesystem.

    Args:
        path: Filesystem entry whose attributes are read.

    Returns:
        POSIX ACL attributes followed by portable ``user.*`` attributes.

    Raises:
        OSError: If the attribute names or values cannot be read.
    """
    names = os.listxattr(path, follow_symlinks=False)
    acl_attributes: dict[str, bytes] = {}
    portable_attributes: dict[str, bytes] = {}
    for name in names:
        if name not in POSIX_ACL_XATTR_NAMES and not name.startswith(
            PORTABLE_XATTR_PREFIX
        ):
            continue
        value = os.getxattr(path, name, follow_symlinks=False)
        if name in POSIX_ACL_XATTR_NAMES:
            acl_attributes[name] = value
        else:
            portable_attributes[name] = value
    return acl_attributes, portable_attributes


def _compare_attribute_group(
    source_attributes: dict[str, bytes],
    restored_attributes: dict[str, bytes],
    relative_path: Path,
    label: str,
    mismatches: list[str],
) -> int:
    """Compare one named group of byte-valued filesystem attributes.

    Args:
        source_attributes: Expected attribute names and binary values.
        restored_attributes: Restored attribute names and binary values.
        relative_path: Relative path used in diagnostics.
        label: Human-readable attribute class name.
        mismatches: Per-operation mismatch collection to update.

    Returns:
        Number of distinct attributes checked.
    """
    source_names = set(source_attributes)
    restored_names = set(restored_attributes)
    for name in sorted(source_names - restored_names):
        _append_mismatch(
            mismatches,
            f"{label} is missing for {relative_path}: {name}",
        )
    for name in sorted(restored_names - source_names):
        _append_mismatch(
            mismatches,
            f"unexpected {label} for {relative_path}: {name}",
        )
    for name in sorted(source_names & restored_names):
        if source_attributes[name] == restored_attributes[name]:
            continue
        _append_mismatch(
            mismatches,
            f"{label} value differs for {relative_path}: {name}",
        )
    return len(source_names | restored_names)


def _compare_portable_attributes(
    source_path: Path,
    restored_path: Path,
    relative_path: Path,
    mismatches: list[str],
) -> tuple[int, int]:
    """Compare POSIX ACL and portable xattr values for one entry.

    Args:
        source_path: Expected live source entry.
        restored_path: Restored entry to verify.
        relative_path: Relative path used in diagnostics.
        mismatches: Per-operation mismatch collection to update.

    Returns:
        POSIX ACL count followed by portable xattr count.

    Raises:
        OSError: If attributes cannot be read.
    """
    source_acls, source_xattrs = _read_portable_attributes(source_path)
    restored_acls, restored_xattrs = _read_portable_attributes(restored_path)
    acl_count = _compare_attribute_group(
        source_acls,
        restored_acls,
        relative_path,
        "POSIX ACL",
        mismatches,
    )
    xattr_count = _compare_attribute_group(
        source_xattrs,
        restored_xattrs,
        relative_path,
        "portable extended attribute",
        mismatches,
    )
    return acl_count, xattr_count


def _compare_permission_mode(
    source_mode: int,
    restored_mode: int,
    relative_path: Path,
    mismatches: list[str],
) -> None:
    """Compare POSIX permission bits for one non-symlink entry.

    Args:
        source_mode: Source ``st_mode`` value returned by ``lstat``.
        restored_mode: Restored ``st_mode`` value returned by ``lstat``.
        relative_path: Relative path used in diagnostics.
        mismatches: Per-operation mismatch collection to update.

    Returns:
        None.
    """
    source_permissions = stat.S_IMODE(source_mode)
    restored_permissions = stat.S_IMODE(restored_mode)
    if source_permissions == restored_permissions:
        return
    _append_mismatch(
        mismatches,
        f"permission mode differs for {relative_path}: "
        f"source={source_permissions:04o}, restored={restored_permissions:04o}",
    )


def _compare_entry(
    source_path: Path,
    restored_path: Path,
    relative_path: Path,
    mismatches: list[str],
) -> EntryComparisonCounts:
    """Compare one restored entry with the corresponding live source entry.

    Args:
        source_path: Expected live source entry.
        restored_path: Restored entry to verify.
        relative_path: Relative path used in diagnostics.
        mismatches: Per-operation mismatch collection to update.

    Returns:
        Counts for the content and metadata comparisons attempted.

    Raises:
        OSError: If entry metadata or content cannot be read.
    """
    try:
        source_stat = source_path.lstat()
    except FileNotFoundError:
        _append_mismatch(mismatches, f"source entry is missing: {relative_path}")
        return EntryComparisonCounts()

    restored_stat = restored_path.lstat()
    source_kind = _entry_kind(source_stat.st_mode)
    restored_kind = _entry_kind(restored_stat.st_mode)
    if source_kind != restored_kind:
        _append_mismatch(
            mismatches,
            f"entry type differs for {relative_path}: "
            f"source={source_kind}, restored={restored_kind}",
        )
        return EntryComparisonCounts()

    _compare_ownership(
        source_stat.st_uid,
        source_stat.st_gid,
        restored_stat.st_uid,
        restored_stat.st_gid,
        relative_path,
        mismatches,
    )
    acl_count, xattr_count = _compare_portable_attributes(
        source_path,
        restored_path,
        relative_path,
        mismatches,
    )

    if restored_kind == "symlink":
        source_target = os.readlink(source_path)
        restored_target = os.readlink(restored_path)
        if source_target != restored_target:
            _append_mismatch(
                mismatches,
                f"symlink target differs for {relative_path}: "
                f"source={source_target!r}, restored={restored_target!r}",
            )
        return EntryComparisonCounts(
            ownership_entries=1,
            posix_acls=acl_count,
            portable_xattrs=xattr_count,
        )

    _compare_permission_mode(
        source_stat.st_mode,
        restored_stat.st_mode,
        relative_path,
        mismatches,
    )

    if restored_kind != "file":
        return EntryComparisonCounts(
            ownership_entries=1,
            permission_entries=1,
            posix_acls=acl_count,
            portable_xattrs=xattr_count,
        )

    if source_stat.st_size != restored_stat.st_size:
        _append_mismatch(
            mismatches,
            f"file size differs for {relative_path}: "
            f"source={source_stat.st_size}, restored={restored_stat.st_size}",
        )
        return EntryComparisonCounts(
            regular_files=1,
            restored_bytes=restored_stat.st_size,
            ownership_entries=1,
            permission_entries=1,
            posix_acls=acl_count,
            portable_xattrs=xattr_count,
        )

    if _sha256(source_path) != _sha256(restored_path):
        _append_mismatch(mismatches, f"SHA-256 differs for {relative_path}")
    return EntryComparisonCounts(
        regular_files=1,
        restored_bytes=restored_stat.st_size,
        ownership_entries=1,
        permission_entries=1,
        posix_acls=acl_count,
        portable_xattrs=xattr_count,
    )


def _hard_link_groups(
    root: Path, relative_paths: Sequence[Path]
) -> set[tuple[Path, ...]]:
    """Return multi-path regular-file hard-link groups within one selection.

    Args:
        root: Root containing every supplied relative path.
        relative_paths: Existing regular-file paths included in the comparison.

    Returns:
        Sets of relative paths grouped by filesystem device and inode identity.

    Raises:
        OSError: If filesystem metadata cannot be read.
    """
    paths_by_inode: dict[tuple[int, int], list[Path]] = {}
    for relative_path in relative_paths:
        entry_stat = (root / relative_path).lstat()
        if not stat.S_ISREG(entry_stat.st_mode):
            continue
        identity = (entry_stat.st_dev, entry_stat.st_ino)
        paths_by_inode.setdefault(identity, []).append(relative_path)
    return {
        tuple(sorted(paths, key=lambda path: os.fsencode(str(path))))
        for paths in paths_by_inode.values()
        if len(paths) > 1
    }


def _compare_hard_link_groups(
    source_root: Path,
    restored_root: Path,
    relative_paths: Sequence[Path],
    mismatches: list[str],
) -> int:
    """Compare hard-link relationships without comparing inode numbers.

    Args:
        source_root: Root of the expected live entries.
        restored_root: Root of the restored entries.
        relative_paths: Common selection whose link topology is compared.
        mismatches: Per-operation mismatch collection to update.

    Returns:
        Number of expected multi-path hard-link groups checked.

    Raises:
        OSError: If filesystem metadata cannot be read.
    """
    source_groups = _hard_link_groups(source_root, relative_paths)
    restored_groups = _hard_link_groups(restored_root, relative_paths)
    for group in sorted(source_groups - restored_groups, key=str):
        paths = ", ".join(str(path) for path in group)
        _append_mismatch(mismatches, f"restored hard-link group is split: {paths}")
    for group in sorted(restored_groups - source_groups, key=str):
        paths = ", ".join(str(path) for path in group)
        _append_mismatch(mismatches, f"unexpected restored hard-link group: {paths}")
    return len(source_groups)


def compare_restore(
    source_root: Path, restored_root: Path, required_relative_path: Path
) -> ComparisonSummary:
    """Compare every restored entry and require complete fixture restoration.

    The restored archive tree is the comparison selection boundary. This avoids
    treating files intentionally omitted by arbitrary DAR exclusion expressions
    as missing. Every restored entry must match its live counterpart. The
    harness-owned primer tree has no intentional omissions, so it is also
    compared in the source-to-restore direction to detect missing extraction.

    Args:
        source_root: Filesystem root used by the backup definition's ``-R``.
        restored_root: Target containing the complete PITR extraction.
        required_relative_path: Harness primer directory relative to both roots.

    Returns:
        Counts and byte totals for the successfully compared restore.

    Raises:
        ComparisonError: If content, types, links, or required entries differ.
        OSError: If filesystem content cannot be read.
        ValueError: If paths are invalid or unsafe.
    """
    source = _validate_directory(source_root, "source_root")
    restored = _validate_directory(restored_root, "restored_root")
    if source == restored:
        raise ValueError("source_root and restored_root must be different directories")
    source_device = source.stat().st_dev
    restored_device = restored.stat().st_dev
    _validate_same_filesystem_devices(source_device, restored_device)
    if required_relative_path is None:
        raise ValueError("required_relative_path must not be None")
    if required_relative_path.is_absolute() or ".." in required_relative_path.parts:
        raise ValueError("required_relative_path must be a safe relative path")

    required_source = source / required_relative_path
    required_restored = restored / required_relative_path
    if not required_source.is_dir():
        raise ValueError(
            f"required source fixture must be an existing directory: {required_source}"
        )

    restored_entries = _relative_entries(restored)
    required_entries = _relative_entries(required_source)
    mismatches: list[str] = []
    restored_file_count = 0
    restored_bytes = 0
    ownership_entry_count = 0
    permission_entry_count = 0
    posix_acl_count = 0
    portable_xattr_count = 0

    if not restored_entries:
        _append_mismatch(mismatches, "complete restore target is empty")

    for relative_path in restored_entries:
        try:
            source_entry_stat = (source / relative_path).lstat()
        except FileNotFoundError:
            source_entry_stat = None
        if source_entry_stat is not None:
            _compare_filesystem_device(
                source_entry_stat.st_dev,
                source_device,
                relative_path,
                "source",
                mismatches,
            )
        restored_entry_stat = (restored / relative_path).lstat()
        _compare_filesystem_device(
            restored_entry_stat.st_dev,
            restored_device,
            relative_path,
            "restore",
            mismatches,
        )
        counts = _compare_entry(
            source / relative_path,
            restored / relative_path,
            relative_path,
            mismatches,
        )
        restored_file_count += counts.regular_files
        restored_bytes += counts.restored_bytes
        ownership_entry_count += counts.ownership_entries
        permission_entry_count += counts.permission_entries
        posix_acl_count += counts.posix_acls
        portable_xattr_count += counts.portable_xattrs

    common_paths: list[Path] = []
    for relative_path in restored_entries:
        try:
            source_stat = (source / relative_path).lstat()
            restored_stat = (restored / relative_path).lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISREG(source_stat.st_mode) and stat.S_ISREG(restored_stat.st_mode):
            common_paths.append(relative_path)
    hard_link_group_count = _compare_hard_link_groups(
        source,
        restored,
        common_paths,
        mismatches,
    )

    if not required_restored.is_dir():
        _append_mismatch(
            mismatches,
            f"required restored fixture is missing: {required_relative_path}",
        )
    else:
        restored_required_entries = set(_relative_entries(required_restored))
        for relative_path in required_entries:
            if relative_path not in restored_required_entries:
                _append_mismatch(
                    mismatches,
                    f"required restored entry is missing: "
                    f"{required_relative_path / relative_path}",
                )

    if mismatches:
        details = "\n".join(f"- {message}" for message in mismatches)
        raise ComparisonError(f"full restore comparison failed:\n{details}")

    return ComparisonSummary(
        restored_entry_count=len(restored_entries),
        restored_file_count=restored_file_count,
        restored_bytes=restored_bytes,
        required_entry_count=len(required_entries),
        ownership_entry_count=ownership_entry_count,
        permission_entry_count=permission_entry_count,
        posix_acl_count=posix_acl_count,
        portable_xattr_count=portable_xattr_count,
        hard_link_group_count=hard_link_group_count,
        metadata_profile=METADATA_PROFILE,
        filesystem_device=source_device,
    )


def compare_permission_modes(source_root: Path, restored_root: Path) -> int:
    """Compare POSIX permission bits across two complete directory trees.

    Symlink mode bits are intentionally ignored because Linux does not provide
    portable, meaningful symlink permission restoration semantics.

    Args:
        source_root: Source tree whose permission modes are expected.
        restored_root: Restored tree whose permission modes are verified.

    Returns:
        Number of matching non-symlink entries checked.

    Raises:
        ComparisonError: If entries, types, or permission modes differ.
        OSError: If filesystem metadata cannot be read.
        ValueError: If paths are invalid or refer to the same directory.
    """
    source = _validate_directory(source_root, "source_root")
    restored = _validate_directory(restored_root, "restored_root")
    if source == restored:
        raise ValueError("source_root and restored_root must be different directories")
    _validate_same_filesystem_devices(source.stat().st_dev, restored.stat().st_dev)

    source_entries = set(_relative_entries(source))
    restored_entries = set(_relative_entries(restored))
    mismatches: list[str] = []
    checked = 0

    for relative_path in sorted(
        source_entries | restored_entries,
        key=lambda path: os.fsencode(str(path)),
    ):
        if relative_path not in source_entries:
            _append_mismatch(
                mismatches, f"unexpected restored entry: {relative_path}"
            )
            continue
        if relative_path not in restored_entries:
            _append_mismatch(
                mismatches, f"required restored entry is missing: {relative_path}"
            )
            continue

        source_stat = (source / relative_path).lstat()
        restored_stat = (restored / relative_path).lstat()
        source_kind = _entry_kind(source_stat.st_mode)
        restored_kind = _entry_kind(restored_stat.st_mode)
        if source_kind != restored_kind:
            _append_mismatch(
                mismatches,
                f"entry type differs for {relative_path}: "
                f"source={source_kind}, restored={restored_kind}",
            )
            continue
        if source_kind == "symlink":
            continue
        checked += 1
        _compare_permission_mode(
            source_stat.st_mode,
            restored_stat.st_mode,
            relative_path,
            mismatches,
        )

    if mismatches:
        details = "\n".join(f"- {message}" for message in mismatches)
        raise ComparisonError(f"permission comparison failed:\n{details}")
    return checked


def _parse_args(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments.

    Args:
        arguments: Optional arguments excluding the executable name.

    Returns:
        Parsed command-line namespace.
    """
    parser = argparse.ArgumentParser(
        description="Compare a complete PITR restore with its live source."
    )
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--restored-root", required=True, type=Path)
    parser.add_argument("--required-relative-path", required=True, type=Path)
    parser.add_argument(
        "--permissions-only",
        action="store_true",
        help="compare only tree membership, entry types, and POSIX permission bits",
    )
    return parser.parse_args(arguments)


def main(arguments: Sequence[str] | None = None) -> int:
    """Run the full-restore comparison command.

    Args:
        arguments: Optional arguments excluding the executable name.

    Returns:
        Zero when the restore matches, otherwise one.
    """
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parsed = _parse_args(arguments)
    try:
        if parsed.permissions_only:
            checked = compare_permission_modes(
                parsed.source_root,
                parsed.restored_root,
            )
            json.dump(
                {"permission_entry_count": checked},
                fp=sys.stdout,
                separators=(",", ":"),
            )
            sys.stdout.write("\n")
            return 0
        summary = compare_restore(
            parsed.source_root,
            parsed.restored_root,
            parsed.required_relative_path,
        )
    except (ComparisonError, OSError, ValueError) as error:
        LOGGER.error("%s", error)
        return 1
    json.dump(asdict(summary), fp=sys.stdout, separators=(",", ":"))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
