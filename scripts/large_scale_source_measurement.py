#!/usr/bin/env python3
"""Measure files selected by the constrained large-scale DEFINITION contract."""

from __future__ import annotations

import argparse
import json
import logging
import os
import stat
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence

from large_scale_definition import DefinitionSelection, parse_selection_contract


LOGGER = logging.getLogger(__name__)
CACHE_TAG_NAME = "CACHEDIR.TAG"
CACHE_TAG_SIGNATURE = b"Signature: 8a477f597d28d172789f06886806bc55"


@dataclass(frozen=True)
class SourceMeasurement:
    """File-count and apparent-byte evidence for one source selection.

    Args:
        candidate_file_count: Unique regular files beneath effective inclusions.
        candidate_bytes: Apparent bytes before explicit pruning and cache tags.
        pruned_file_count: Candidate regular files excluded from the measurement.
        pruned_bytes: Apparent bytes excluded from the measurement.
        selected_file_count: Candidate regular files retained for backup evidence.
        selected_bytes: Apparent bytes retained for backup evidence.
        prune_path_count: Number of unique literal ``-P`` rules applied.
        cache_tagged_directory_count: Valid cache-tagged directories encountered.
    """

    candidate_file_count: int
    candidate_bytes: int
    pruned_file_count: int
    pruned_bytes: int
    selected_file_count: int
    selected_bytes: int
    prune_path_count: int
    cache_tagged_directory_count: int


def _absolute_under_root(root: Path, relative_path: str, label: str) -> Path:
    """Return a lexical absolute path contained by the source root.

    Args:
        root: Absolute source root.
        relative_path: Validated literal path relative to ``root``.
        label: Human-readable path role for diagnostics.

    Returns:
        Absolute, non-resolved path below ``root``.

    Raises:
        ValueError: If the path escapes the root or does not exist.
    """
    candidate = Path(os.path.abspath(root / relative_path))
    try:
        candidate.relative_to(root)
    except ValueError as error:
        raise ValueError(
            f"{label} path escapes source root {root}: {relative_path!r}"
        ) from error
    if not os.path.lexists(candidate):
        raise ValueError(f"{label} path does not exist: {candidate}")
    return candidate


def _contains(path: Path, ancestor: Path) -> bool:
    """Return whether a lexical path equals or descends from an ancestor.

    Args:
        path: Candidate absolute path.
        ancestor: Candidate absolute ancestor.

    Returns:
        ``True`` when ``path`` is within ``ancestor``.
    """
    return path == ancestor or ancestor in path.parents


def _minimal_scan_roots(paths: Sequence[Path]) -> tuple[Path, ...]:
    """Remove duplicate and nested scan roots without changing selection.

    Args:
        paths: Existing absolute inclusion paths.

    Returns:
        Unique roots where no returned root descends from another.
    """
    roots: list[Path] = []
    for path in sorted(set(paths), key=lambda item: (len(item.parts), str(item))):
        if any(_contains(path, existing) for existing in roots):
            continue
        roots.append(path)
    return tuple(roots)


def _valid_cache_tag(directory: Path) -> bool:
    """Return whether a directory contains the standard cache-tag signature.

    Args:
        directory: Existing directory being scanned.

    Returns:
        ``True`` only when ``CACHEDIR.TAG`` begins with the required signature.

    Raises:
        OSError: If an existing regular cache-tag file cannot be inspected.
    """
    tag_path = directory / CACHE_TAG_NAME
    try:
        tag_stat = tag_path.lstat()
    except FileNotFoundError:
        return False
    if not stat.S_ISREG(tag_stat.st_mode):
        return False
    with tag_path.open("rb") as tag_file:
        return tag_file.read(len(CACHE_TAG_SIGNATURE)) == CACHE_TAG_SIGNATURE


def _raise_walk_error(error: OSError) -> None:
    """Propagate an ``os.walk`` failure instead of omitting source data.

    Args:
        error: Filesystem traversal error.

    Raises:
        OSError: Always, preserving the original failure.
    """
    raise error


def _candidate_files(scan_root: Path) -> Sequence[Path]:
    """Collect lexical regular-file paths beneath one inclusion root.

    Args:
        scan_root: Existing literal inclusion file or directory.

    Returns:
        Regular files without following symlink targets.

    Raises:
        OSError: If an entry cannot be inspected or traversal fails.
    """
    root_stat = scan_root.lstat()
    if stat.S_ISREG(root_stat.st_mode):
        return (scan_root,)
    if not stat.S_ISDIR(root_stat.st_mode):
        return ()

    files: list[Path] = []
    for directory, _, filenames in os.walk(
        scan_root, followlinks=False, onerror=_raise_walk_error
    ):
        directory_path = Path(directory)
        for filename in filenames:
            candidate = directory_path / filename
            candidate_stat = candidate.lstat()
            if stat.S_ISREG(candidate_stat.st_mode):
                files.append(candidate)
    return tuple(files)


def _validate_prune_intersections(
    prune_paths: Sequence[Path], user_include_paths: Sequence[Path]
) -> None:
    """Require every literal prune to affect at least one user inclusion.

    Args:
        prune_paths: Existing absolute prune files or subtrees.
        user_include_paths: Existing user-supplied inclusion files or trees.

    Raises:
        ValueError: If a prune is irrelevant to every user inclusion.
    """
    for prune_path in prune_paths:
        if any(
            _contains(prune_path, include_path)
            or _contains(include_path, prune_path)
            for include_path in user_include_paths
        ):
            continue
        raise ValueError(
            f"literal -P path does not intersect any user -g path: {prune_path}"
        )


def measure_source(
    root: Path,
    selection: DefinitionSelection,
    required_include_path: str,
) -> SourceMeasurement:
    """Measure the constrained literal inclusion-minus-pruning selection.

    Args:
        root: Existing source root, which must match the definition's ``-R``.
        selection: Parsed large-scale definition selection contract.
        required_include_path: Harness primer path relative to ``root``.

    Returns:
        Deterministic selected, pruned, and candidate byte/count evidence.

    Raises:
        OSError: If filesystem entries cannot be traversed or inspected.
        ValueError: If roots differ or literal include/prune paths are invalid.
    """
    source_root = Path(os.path.abspath(root))
    if not source_root.is_dir():
        raise ValueError(f"source root must be an existing directory: {source_root}")
    definition_root = Path(os.path.abspath(selection.root))
    if definition_root != source_root:
        raise ValueError(
            f"definition -R {definition_root} does not match source root {source_root}"
        )

    user_includes = tuple(
        _absolute_under_root(source_root, path, "-g")
        for path in selection.include_paths
    )
    required_include = _absolute_under_root(
        source_root, required_include_path, "required primer"
    )
    prune_paths = tuple(
        _absolute_under_root(source_root, path, "-P")
        for path in selection.prune_paths
    )
    _validate_prune_intersections(prune_paths, user_includes)

    scan_roots = _minimal_scan_roots((*user_includes, required_include))
    candidate_paths: set[Path] = set()
    for scan_root in scan_roots:
        candidate_paths.update(_candidate_files(scan_root))

    cache_roots: set[Path] = set()
    if selection.cache_directory_tagging:
        candidate_directories = {
            parent
            for candidate in candidate_paths
            for parent in candidate.parents
            if parent == source_root or source_root in parent.parents
        }
        for directory in sorted(candidate_directories, key=str):
            if _valid_cache_tag(directory):
                cache_roots.add(directory)

    candidate_bytes = 0
    pruned_file_count = 0
    pruned_bytes = 0
    selected_file_count = 0
    selected_bytes = 0
    required_file_count = 0
    required_selected_count = 0
    for candidate in sorted(candidate_paths, key=str):
        file_size = candidate.lstat().st_size
        candidate_bytes += file_size
        required_candidate = _contains(candidate, required_include)
        if required_candidate:
            required_file_count += 1
        cache_excluded = any(_contains(candidate, cache) for cache in cache_roots)
        explicitly_pruned = any(_contains(candidate, prune) for prune in prune_paths)
        required_reincluded = selection.ordered_masks and required_candidate
        excluded = cache_excluded or (explicitly_pruned and not required_reincluded)
        if excluded:
            pruned_file_count += 1
            pruned_bytes += file_size
            continue
        selected_file_count += 1
        selected_bytes += file_size
        if required_candidate:
            required_selected_count += 1

    if required_file_count == 0:
        raise ValueError(
            f"required primer contains no regular files: {required_include}"
        )
    if required_selected_count != required_file_count:
        raise ValueError(
            "backup definition excludes one or more mandatory primer files; "
            "the large-scale restore contract requires the complete primer"
        )

    return SourceMeasurement(
        candidate_file_count=len(candidate_paths),
        candidate_bytes=candidate_bytes,
        pruned_file_count=pruned_file_count,
        pruned_bytes=pruned_bytes,
        selected_file_count=selected_file_count,
        selected_bytes=selected_bytes,
        prune_path_count=len(prune_paths),
        cache_tagged_directory_count=len(cache_roots),
    )


def _build_parser() -> argparse.ArgumentParser:
    """Build the source-measurement command-line parser.

    Returns:
        Configured argument parser.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--definition", required=True)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--required-include", required=True)
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    """Measure a definition and print one JSON evidence object.

    Args:
        arguments: Optional command-line arguments excluding the program name.

    Returns:
        Zero on success or two when definition/filesystem validation fails.
    """
    parsed = _build_parser().parse_args(arguments)
    try:
        selection = parse_selection_contract(parsed.definition)
        measurement = measure_source(
            parsed.root, selection, parsed.required_include
        )
    except (OSError, ValueError) as error:
        LOGGER.error("Unable to measure large-scale source selection: %s", error)
        return 2
    print(json.dumps(asdict(measurement), sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    raise SystemExit(main())
