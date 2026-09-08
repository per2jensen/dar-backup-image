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

"""Capture and verify portable filesystem manifests for restore tests."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import logging
import os
from pathlib import Path, PurePosixPath
import stat
import sys
from typing import Any, Sequence


LOGGER = logging.getLogger(__name__)
BUFFER_BYTES = 1024 * 1024
MANIFEST_VERSION = 1
PORTABLE_XATTR_PREFIX = "user."
POSIX_ACL_NAMES = frozenset(
    {"system.posix_acl_access", "system.posix_acl_default"}
)
SUPPORTED_KINDS = frozenset({"directory", "file", "symlink"})


class ManifestError(RuntimeError):
    """Indicate that a source or restored tree violates the manifest contract."""


def _validate_root(path: Path, label: str) -> Path:
    """Validate and resolve a directory root.

    Args:
        path: Candidate directory.
        label: Human-readable argument name.

    Returns:
        Resolved directory path.

    Raises:
        ValueError: If the candidate is missing or is not a directory.
    """
    if path is None:
        raise ValueError(f"{label} must not be None")
    resolved = path.resolve()
    if not resolved.is_dir():
        raise ValueError(f"{label} must be an existing directory: {path}")
    return resolved


def _validate_selection(value: str) -> PurePosixPath:
    """Validate one selection relative to a source root.

    Args:
        value: User-supplied POSIX relative path.

    Returns:
        Validated relative path.

    Raises:
        ValueError: If the selection is empty, absolute, or traverses upward.
    """
    if not value:
        raise ValueError("selection must not be empty")
    selection = PurePosixPath(value)
    if selection.is_absolute() or ".." in selection.parts:
        raise ValueError(f"selection must be a safe relative path: {value!r}")
    if value == ".":
        return PurePosixPath(".")
    normalized_parts = tuple(part for part in selection.parts if part not in {"", "."})
    if not normalized_parts:
        raise ValueError(f"selection must identify a path: {value!r}")
    return PurePosixPath(*normalized_parts)


def _entry_kind(mode: int) -> str:
    """Return the supported kind name for a stat mode.

    Args:
        mode: Mode returned by ``lstat``.

    Returns:
        Stable entry-kind name.

    Raises:
        ManifestError: If the entry type is not portable for this harness.
    """
    if stat.S_ISDIR(mode):
        return "directory"
    if stat.S_ISREG(mode):
        return "file"
    if stat.S_ISLNK(mode):
        return "symlink"
    raise ManifestError(f"unsupported filesystem entry mode: {mode:#o}")


def _sha256(path: Path) -> str:
    """Calculate one regular file's SHA-256 digest.

    Args:
        path: File to read.

    Returns:
        Lowercase hexadecimal digest.

    Raises:
        OSError: If the file cannot be read.
    """
    digest = hashlib.sha256()
    with path.open("rb") as input_file:
        while chunk := input_file.read(BUFFER_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def _portable_attributes(path: Path) -> dict[str, str]:
    """Read POSIX ACL and portable user extended attributes.

    Args:
        path: Entry to inspect without following symbolic links.

    Returns:
        Attribute names mapped to base64-encoded binary values.

    Raises:
        OSError: If attributes cannot be listed or read.
    """
    attributes: dict[str, str] = {}
    for name in sorted(os.listxattr(path, follow_symlinks=False)):
        if name not in POSIX_ACL_NAMES and not name.startswith(
            PORTABLE_XATTR_PREFIX
        ):
            continue
        value = os.getxattr(path, name, follow_symlinks=False)
        attributes[name] = base64.b64encode(value).decode("ascii")
    return attributes


def _relative_children(root: Path, relative_directory: PurePosixPath) -> list[PurePosixPath]:
    """Walk one directory without following symbolic links.

    Args:
        root: Source root.
        relative_directory: Directory relative to the root.

    Returns:
        The directory's full descendant set in bytewise lexical order.

    Raises:
        OSError: If an entry cannot be scanned.
    """
    entries: list[PurePosixPath] = []
    pending = [relative_directory]
    while pending:
        current = pending.pop()
        children = sorted(
            os.scandir(root / Path(str(current))),
            key=lambda item: os.fsencode(item.name),
            reverse=True,
        )
        for child in children:
            relative_path = current / child.name
            entries.append(relative_path)
            if child.is_dir(follow_symlinks=False):
                pending.append(relative_path)
    return sorted(entries, key=lambda item: os.fsencode(str(item)))


def _selection_entries(root: Path, selections: Sequence[PurePosixPath]) -> list[PurePosixPath]:
    """Resolve selections into an exact relative entry set.

    Args:
        root: Existing source root.
        selections: Validated paths relative to the root.

    Returns:
        Deduplicated selected entries plus structural ancestor directories.

    Raises:
        FileNotFoundError: If a selected entry is absent.
        ManifestError: If a selection crosses the root filesystem device.
        OSError: If filesystem metadata cannot be read.
    """
    root_device = root.stat().st_dev
    entries: set[PurePosixPath] = set()
    for selection in selections:
        if selection == PurePosixPath("."):
            candidates = _relative_children(root, PurePosixPath("."))
        else:
            selected_path = root / Path(str(selection))
            selected_stat = selected_path.lstat()
            candidates = [selection]
            if stat.S_ISDIR(selected_stat.st_mode):
                candidates.extend(_relative_children(root, selection))
            parent = selection.parent
            while parent != PurePosixPath("."):
                entries.add(parent)
                parent = parent.parent
        for relative_path in candidates:
            entry_stat = (root / Path(str(relative_path))).lstat()
            if entry_stat.st_dev != root_device:
                raise ManifestError(
                    "selection crosses a filesystem boundary at "
                    f"{relative_path}: root st_dev={root_device}, "
                    f"entry st_dev={entry_stat.st_dev}"
                )
            entries.add(relative_path)
    return sorted(entries, key=lambda item: os.fsencode(str(item)))


def _build_entries(root: Path, paths: Sequence[PurePosixPath]) -> list[dict[str, Any]]:
    """Build manifest entries and portable hard-link identities.

    Args:
        root: Existing source root.
        paths: Relative paths included in the selection.

    Returns:
        JSON-serializable manifest entry objects.

    Raises:
        ManifestError: If an unsupported entry is encountered.
        OSError: If content or metadata cannot be read.
    """
    entries: list[dict[str, Any]] = []
    regular_paths_by_inode: dict[tuple[int, int], list[str]] = {}
    for relative_path in paths:
        absolute_path = root / Path(str(relative_path))
        entry_stat = absolute_path.lstat()
        kind = _entry_kind(entry_stat.st_mode)
        record: dict[str, Any] = {
            "path": str(relative_path),
            "kind": kind,
            "mode": stat.S_IMODE(entry_stat.st_mode),
            "uid": entry_stat.st_uid,
            "gid": entry_stat.st_gid,
            "xattrs": _portable_attributes(absolute_path),
        }
        if kind == "file":
            record["size"] = entry_stat.st_size
            record["sha256"] = _sha256(absolute_path)
            regular_paths_by_inode.setdefault(
                (entry_stat.st_dev, entry_stat.st_ino), []
            ).append(str(relative_path))
        elif kind == "symlink":
            record.pop("mode")
            record["target"] = os.readlink(absolute_path)
        entries.append(record)

    link_groups = sorted(
        (sorted(group, key=os.fsencode) for group in regular_paths_by_inode.values() if len(group) > 1),
        key=lambda group: [os.fsencode(item) for item in group],
    )
    group_by_path = {
        path: group_index
        for group_index, group in enumerate(link_groups, start=1)
        for path in group
    }
    for record in entries:
        if record["path"] in group_by_path:
            record["hard_link_group"] = group_by_path[record["path"]]
    return entries


def capture_manifest(source_root: Path, selection_values: Sequence[str]) -> dict[str, Any]:
    """Capture one selected source tree as portable JSON data.

    Args:
        source_root: Root against which selections are resolved.
        selection_values: Relative path selections; empty means the complete root.

    Returns:
        Complete manifest object.

    Raises:
        ManifestError: If the selection contains unsupported content.
        OSError: If source content cannot be read.
        ValueError: If a path argument is invalid.
    """
    root = _validate_root(source_root, "source_root")
    raw_selections = list(selection_values) or ["."]
    selections = [_validate_selection(value) for value in raw_selections]
    paths = _selection_entries(root, selections)
    entries = _build_entries(root, paths)
    return {
        "manifest_version": MANIFEST_VERSION,
        "selections": [str(selection) for selection in selections],
        "source_device": root.stat().st_dev,
        "entries": entries,
    }


def validate_restorable_identity(
    manifest: dict[str, Any], required_uid: int, allowed_gids: Sequence[int]
) -> None:
    """Require manifest ownership that a non-root user can recreate.

    Args:
        manifest: Captured manifest to validate.
        required_uid: UID required for every selected entry.
        allowed_gids: GIDs available to the restore process.

    Returns:
        None.

    Raises:
        ManifestError: If an entry has incompatible ownership.
        ValueError: If identity arguments are invalid.
    """
    if required_uid < 0:
        raise ValueError("required_uid must not be negative")
    group_set = set(allowed_gids)
    if not group_set or any(group_id < 0 for group_id in group_set):
        raise ValueError("allowed_gids must contain non-negative group IDs")
    incompatible: list[str] = []
    for entry in manifest["entries"]:
        if entry.get("uid") == required_uid and entry.get("gid") in group_set:
            continue
        incompatible.append(str(entry.get("path", "<unknown>")))
    if incompatible:
        paths = ", ".join(incompatible[:20])
        raise ManifestError(
            "selected ownership cannot be recreated by the non-root identity: "
            f"{paths}"
        )


def _validate_manifest(value: Any) -> dict[str, Any]:
    """Validate the minimum manifest structure.

    Args:
        value: Decoded JSON value.

    Returns:
        Validated manifest mapping.

    Raises:
        ValueError: If the value is malformed or unsupported.
    """
    if not isinstance(value, dict):
        raise ValueError("manifest must be a JSON object")
    if value.get("manifest_version") != MANIFEST_VERSION:
        raise ValueError("manifest_version is missing or unsupported")
    selections = value.get("selections")
    entries = value.get("entries")
    if not isinstance(selections, list) or not all(
        isinstance(item, str) for item in selections
    ):
        raise ValueError("manifest selections must be an array of strings")
    if not isinstance(entries, list) or not all(isinstance(item, dict) for item in entries):
        raise ValueError("manifest entries must be an array of objects")
    return value


def load_manifest(path: Path) -> dict[str, Any]:
    """Read and validate a manifest file.

    Args:
        path: Existing JSON manifest path.

    Returns:
        Validated manifest object.

    Raises:
        OSError: If the file cannot be read.
        ValueError: If the JSON or schema is invalid.
    """
    if path is None:
        raise ValueError("manifest path must not be None")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"invalid manifest JSON in {path}: {error}") from error
    return _validate_manifest(value)


def _summary(manifest: dict[str, Any]) -> dict[str, int]:
    """Summarize a validated manifest.

    Args:
        manifest: Validated manifest object.

    Returns:
        Entry, file, byte, metadata, and hard-link counts.
    """
    entries = manifest["entries"]
    files = [entry for entry in entries if entry.get("kind") == "file"]
    return {
        "entry_count": len(entries),
        "file_count": len(files),
        "bytes": sum(int(entry.get("size", 0)) for entry in files),
        "xattr_count": sum(len(entry.get("xattrs", {})) for entry in entries),
        "hard_link_group_count": len(
            {entry["hard_link_group"] for entry in entries if "hard_link_group" in entry}
        ),
    }


def verify_manifest(
    manifest: dict[str, Any], root: Path, strict_extra: bool
) -> dict[str, int]:
    """Verify a source or restored tree against a captured manifest.

    Args:
        manifest: Expected validated manifest.
        root: Directory containing the current tree.
        strict_extra: Whether entries outside the expected set are forbidden.

    Returns:
        Successful comparison summary.

    Raises:
        ManifestError: If any content or metadata differs.
        OSError: If current content cannot be read.
        ValueError: If arguments are invalid.
    """
    current = capture_manifest(root, manifest["selections"])
    mismatches: list[str] = []
    expected_by_path = {entry["path"]: entry for entry in manifest["entries"]}
    current_by_path = {entry["path"]: entry for entry in current["entries"]}
    for path in sorted(set(expected_by_path) - set(current_by_path), key=os.fsencode):
        mismatches.append(f"missing entry: {path}")
    for path in sorted(set(current_by_path) - set(expected_by_path), key=os.fsencode):
        mismatches.append(f"unexpected selected entry: {path}")
    for path in sorted(set(expected_by_path) & set(current_by_path), key=os.fsencode):
        if expected_by_path[path] != current_by_path[path]:
            mismatches.append(f"content or portable metadata differs: {path}")

    if strict_extra:
        all_current_paths = {
            str(item) for item in _relative_children(_validate_root(root, "root"), PurePosixPath("."))
        }
        for path in sorted(all_current_paths - set(expected_by_path), key=os.fsencode):
            mismatches.append(f"unexpected restored entry: {path}")
    if mismatches:
        details = "\n".join(f"- {message}" for message in mismatches[:100])
        raise ManifestError(f"manifest verification failed:\n{details}")
    return _summary(manifest)


def _parser() -> argparse.ArgumentParser:
    """Build the command-line parser.

    Returns:
        Configured argument parser.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    capture = subparsers.add_parser("capture", help="capture a source manifest")
    capture.add_argument("--source-root", type=Path, required=True)
    capture.add_argument("--selection", action="append", default=[])
    capture.add_argument("--output", type=Path, required=True)
    capture.add_argument("--required-uid", type=int)
    capture.add_argument("--allowed-gid", action="append", type=int, default=[])
    verify = subparsers.add_parser("verify", help="verify a tree against a manifest")
    verify.add_argument("--manifest", type=Path, required=True)
    verify.add_argument("--root", type=Path, required=True)
    verify.add_argument("--strict-extra", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Capture or verify one portable filesystem manifest.

    Args:
        argv: Optional argument vector excluding the executable name.

    Returns:
        Zero on success and one on operational or comparison failure.
    """
    args = _parser().parse_args(argv)
    try:
        if args.command == "capture":
            manifest = capture_manifest(args.source_root, args.selection)
            if args.required_uid is not None:
                validate_restorable_identity(
                    manifest, args.required_uid, args.allowed_gid
                )
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(manifest, separators=(",", ":"), ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            print(json.dumps(_summary(manifest), separators=(",", ":")))
            return 0
        manifest = load_manifest(args.manifest)
        summary = verify_manifest(manifest, args.root, args.strict_extra)
        print(json.dumps(summary, separators=(",", ":")))
        return 0
    except (ManifestError, OSError, ValueError) as error:
        LOGGER.error("Manifest operation failed: %s", error)
        return 1


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    raise SystemExit(main())
