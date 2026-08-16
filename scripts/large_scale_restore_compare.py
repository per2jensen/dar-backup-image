#!/usr/bin/env python3
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


class ComparisonError(RuntimeError):
    """Indicate that restored content differs from its live source."""


@dataclass(frozen=True)
class ComparisonSummary:
    """Describe the content successfully checked in one restored tree.

    Attributes:
        restored_entry_count: Number of restored filesystem entries checked.
        restored_file_count: Number of restored regular-file paths checked.
        restored_bytes: Total apparent bytes across restored regular-file paths.
        required_entry_count: Number of required fixture entries checked.
    """

    restored_entry_count: int
    restored_file_count: int
    restored_bytes: int
    required_entry_count: int


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


def _compare_entry(
    source_path: Path,
    restored_path: Path,
    relative_path: Path,
    mismatches: list[str],
) -> tuple[int, int]:
    """Compare one restored entry with the corresponding live source entry.

    Args:
        source_path: Expected live source entry.
        restored_path: Restored entry to verify.
        relative_path: Relative path used in diagnostics.
        mismatches: Per-operation mismatch collection to update.

    Returns:
        A tuple containing regular-file count and apparent bytes checked.

    Raises:
        OSError: If entry metadata or content cannot be read.
    """
    try:
        source_stat = source_path.lstat()
    except FileNotFoundError:
        _append_mismatch(mismatches, f"source entry is missing: {relative_path}")
        return 0, 0

    restored_stat = restored_path.lstat()
    source_kind = _entry_kind(source_stat.st_mode)
    restored_kind = _entry_kind(restored_stat.st_mode)
    if source_kind != restored_kind:
        _append_mismatch(
            mismatches,
            f"entry type differs for {relative_path}: "
            f"source={source_kind}, restored={restored_kind}",
        )
        return 0, 0

    if restored_kind == "symlink":
        source_target = os.readlink(source_path)
        restored_target = os.readlink(restored_path)
        if source_target != restored_target:
            _append_mismatch(
                mismatches,
                f"symlink target differs for {relative_path}: "
                f"source={source_target!r}, restored={restored_target!r}",
            )
        return 0, 0

    if restored_kind != "file":
        return 0, 0

    if source_stat.st_size != restored_stat.st_size:
        _append_mismatch(
            mismatches,
            f"file size differs for {relative_path}: "
            f"source={source_stat.st_size}, restored={restored_stat.st_size}",
        )
        return 1, restored_stat.st_size

    if _sha256(source_path) != _sha256(restored_path):
        _append_mismatch(mismatches, f"SHA-256 differs for {relative_path}")
    return 1, restored_stat.st_size


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

    if not restored_entries:
        _append_mismatch(mismatches, "complete restore target is empty")

    for relative_path in restored_entries:
        file_count, file_bytes = _compare_entry(
            source / relative_path,
            restored / relative_path,
            relative_path,
            mismatches,
        )
        restored_file_count += file_count
        restored_bytes += file_bytes

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
    )


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
