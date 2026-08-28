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

"""Select reproducible bitrot ranges and persist per-slice repair evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence


MAX_SEED = (1 << 64) - 1
EDGE_PERCENT = 1
VALID_MODES = {"contiguous", "fragmented", "edges"}
VALID_STATUSES = {"passed", "failed", "skipped", "not_run", "in_progress"}
SLICE_PATTERN = re.compile(r"\.(\d+)\.dar$")
PAR2_BLOCK_PATTERN = re.compile(
    r"Found\s+(\d+)\s+of\s+(\d+)\s+data blocks", re.IGNORECASE
)


def _slice_number(path: Path) -> int:
    """Extract the numeric DAR slice number from a path.

    Args:
        path: DAR slice path ending in ``.<number>.dar``.

    Returns:
        The numeric slice number.

    Raises:
        ValueError: If the filename is not a numbered DAR slice.
    """
    match = SLICE_PATTERN.search(path.name)
    if match is None:
        raise ValueError(f"Not a numbered DAR slice: {path}")
    return int(match.group(1))


def _validate_seed(seed: int) -> None:
    """Validate a 64-bit unsigned random seed.

    Args:
        seed: Seed supplied by the harness or operator.

    Raises:
        ValueError: If the seed is outside the supported range.
    """
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise ValueError("seed must be an integer")
    if seed < 0 or seed > MAX_SEED:
        raise ValueError(f"seed must be between 0 and {MAX_SEED}")


def _phase_random(seed: int, phase: str) -> random.Random:
    """Create a deterministic random generator for one lifecycle phase.

    Args:
        seed: Run-level 64-bit seed.
        phase: Stable phase label such as ``full`` or ``diff``.

    Returns:
        A phase-specific deterministic random generator.

    Raises:
        ValueError: If the seed or phase is invalid.
    """
    _validate_seed(seed)
    if not isinstance(phase, str) or not phase.strip():
        raise ValueError("phase must be a non-empty string")
    digest = hashlib.sha256(f"{seed}:{phase.lower()}".encode("utf-8")).digest()
    return random.Random(int.from_bytes(digest, byteorder="big", signed=False))


def _build_segments(
    slice_paths: Sequence[Path],
    slice_sizes: Sequence[int],
    start_index: int,
    start_offset: int,
    length_bytes: int,
    region_index: int = 0,
) -> list[dict[str, Any]] | None:
    """Map a logical corruption interval onto one or more physical slices.

    Args:
        slice_paths: Naturally ordered DAR slice paths.
        slice_sizes: Size of each corresponding slice in bytes.
        start_index: Zero-based slice containing the interval start.
        start_offset: Byte offset within the starting slice.
        length_bytes: Total bytes to corrupt across slices.
        region_index: Zero-based corruption-region identifier.

    Returns:
        Segment dictionaries, or ``None`` if the archive ends before the range.

    Raises:
        ValueError: If the supplied range or slice metadata is invalid.
    """
    if len(slice_paths) != len(slice_sizes) or not slice_paths:
        raise ValueError(
            "slice paths and sizes must be non-empty and have equal length"
        )
    if start_index < 0 or start_index >= len(slice_paths):
        raise ValueError("start_index is outside the slice list")
    if start_offset < 0 or start_offset >= slice_sizes[start_index]:
        raise ValueError("start_offset is outside the starting slice")
    if length_bytes <= 0:
        raise ValueError("length_bytes must be positive")
    if region_index < 0:
        raise ValueError("region_index must be non-negative")

    segments: list[dict[str, Any]] = []
    remaining = length_bytes
    current_offset = start_offset
    for index in range(start_index, len(slice_paths)):
        available = slice_sizes[index] - current_offset
        segment_length = min(remaining, available)
        if segment_length > 0:
            segments.append(
                {
                    "segment_index": len(segments),
                    "region_index": region_index,
                    "slice": slice_paths[index].name,
                    "path": str(slice_paths[index]),
                    "slice_number": _slice_number(slice_paths[index]),
                    "slice_bytes": slice_sizes[index],
                    "offset_bytes": current_offset,
                    "length_bytes": segment_length,
                }
            )
            remaining -= segment_length
        if remaining == 0:
            return segments
        current_offset = 0
    return None


def _inspect_slices(
    slice_paths: Sequence[Path],
) -> tuple[list[Path], list[int]]:
    """Validate, naturally order, and measure DAR slices.

    Args:
        slice_paths: DAR slice paths belonging to one archive.

    Returns:
        Numerically ordered paths and their sizes in bytes.

    Raises:
        OSError: If slice metadata cannot be read.
        ValueError: If paths are missing, duplicated, empty, or malformed.
    """
    if not slice_paths:
        raise ValueError("at least one DAR slice is required")

    ordered_paths = sorted((Path(path) for path in slice_paths), key=_slice_number)
    if len(set(ordered_paths)) != len(ordered_paths):
        raise ValueError("DAR slice paths must be unique")

    slice_sizes: list[int] = []
    for path in ordered_paths:
        if not path.is_file():
            raise ValueError(f"DAR slice does not exist or is not a file: {path}")
        size = path.stat().st_size
        if size <= 0:
            raise ValueError(f"DAR slice is empty: {path}")
        slice_sizes.append(size)
    return ordered_paths, slice_sizes


def _positive_composition(
    total: int, parts: int, generator: random.Random
) -> list[int]:
    """Split an integer into reproducible positive parts.

    Args:
        total: Positive total to distribute.
        parts: Number of positive result values.
        generator: Deterministic random source.

    Returns:
        Positive integers whose sum equals ``total``.

    Raises:
        ValueError: If the total cannot supply every requested part.
    """
    if total <= 0:
        raise ValueError("composition total must be positive")
    if parts <= 0 or parts > total:
        raise ValueError("composition parts must be between 1 and total")
    if parts == 1:
        return [total]
    cuts = sorted(generator.sample(range(1, total), parts - 1))
    boundaries = [0, *cuts, total]
    return [
        boundaries[index + 1] - boundaries[index]
        for index in range(parts)
    ]


def _weak_composition(
    total: int, parts: int, generator: random.Random
) -> list[int]:
    """Split a non-negative integer into reproducible non-negative parts.

    Args:
        total: Non-negative total to distribute.
        parts: Number of result values.
        generator: Deterministic random source.

    Returns:
        Non-negative integers whose sum equals ``total``.

    Raises:
        ValueError: If the total or part count is invalid.
    """
    if total < 0:
        raise ValueError("composition total must be non-negative")
    if parts <= 0:
        raise ValueError("composition parts must be positive")
    if parts == 1:
        return [total]
    bars = sorted(generator.sample(range(total + parts - 1), parts - 1))
    values: list[int] = []
    previous = -1
    for bar in bars:
        values.append(bar - previous - 1)
        previous = bar
    values.append(total + parts - 2 - previous)
    return values


def _select_contiguous(
    seed: int,
    phase: str,
    ordered_paths: Sequence[Path],
    slice_sizes: Sequence[int],
    corruption_percent: int,
) -> dict[str, Any]:
    """Select one reproducible interval that may cross slice boundaries.

    Args:
        seed: Run-level unsigned 64-bit seed.
        phase: Lifecycle phase label.
        ordered_paths: Numerically ordered DAR slices.
        slice_sizes: Corresponding slice sizes.
        corruption_percent: Safe byte budget relative to the starting slice.

    Returns:
        JSON-serializable contiguous selection.

    Raises:
        ValueError: If a safe interval cannot be constructed.
    """
    phase_random = _phase_random(seed, phase)
    archive_bytes = sum(slice_sizes)

    # Random offsets normally remain inside one slice, but offsets near an end
    # naturally spill into following slices. Reject only selections that exceed
    # the same safe percentage budget on any affected slice.
    for _ in range(4096):
        logical_offset = phase_random.randrange(archive_bytes)
        bytes_before_slice = 0
        start_index = 0
        for index, size in enumerate(slice_sizes):
            if logical_offset < bytes_before_slice + size:
                start_index = index
                break
            bytes_before_slice += size
        start_size = slice_sizes[start_index]
        start_offset = logical_offset - bytes_before_slice
        length_bytes = max(1, start_size * corruption_percent // 100)
        segments = _build_segments(
            ordered_paths,
            slice_sizes,
            start_index,
            start_offset,
            length_bytes,
        )
        if segments is None:
            continue
        safe = all(
            segment["length_bytes"]
            <= max(1, segment["slice_bytes"] * corruption_percent // 100)
            for segment in segments
        )
        if not safe:
            continue
        return {
            "seed": seed,
            "phase": phase.lower(),
            "mode": "contiguous",
            "corruption_percent": corruption_percent,
            "logical_offset_bytes": logical_offset,
            "length_bytes": length_bytes,
            "region_count": 1,
            "segments": segments,
        }

    # A non-crossing fallback is always safe and prevents pathological mixes of
    # tiny and large slices from making a deterministic seed unusable.
    start_index = phase_random.randrange(len(ordered_paths))
    start_size = slice_sizes[start_index]
    length_bytes = max(1, start_size * corruption_percent // 100)
    start_offset = phase_random.randrange(start_size - length_bytes + 1)
    segments = _build_segments(
        ordered_paths,
        slice_sizes,
        start_index,
        start_offset,
        length_bytes,
    )
    if segments is None:
        raise ValueError("unable to construct a safe corruption interval")
    return {
        "seed": seed,
        "phase": phase.lower(),
        "mode": "contiguous",
        "corruption_percent": corruption_percent,
        "logical_offset_bytes": sum(slice_sizes[:start_index]) + start_offset,
        "length_bytes": length_bytes,
        "region_count": 1,
        "segments": segments,
    }


def _select_fragmented(
    seed: int,
    phase: str,
    ordered_paths: Sequence[Path],
    slice_sizes: Sequence[int],
    corruption_percent: int,
) -> dict[str, Any]:
    """Spread one slice's corruption budget across 2-10 separated regions.

    Args:
        seed: Run-level unsigned 64-bit seed.
        phase: Lifecycle phase label.
        ordered_paths: Numerically ordered DAR slices.
        slice_sizes: Corresponding slice sizes.
        corruption_percent: Exact byte budget relative to the selected slice.

    Returns:
        JSON-serializable fragmented selection.

    Raises:
        ValueError: If no slice can hold at least two separated regions.
    """
    generator = _phase_random(seed, phase)
    viable: list[tuple[int, int]] = []
    for index, size in enumerate(slice_sizes):
        budget = max(1, size * corruption_percent // 100)
        maximum_regions = min(10, budget, size - budget + 1)
        if maximum_regions >= 2:
            viable.append((index, maximum_regions))
    if not viable:
        raise ValueError("no DAR slice can hold two separated corruption regions")

    start_index, maximum_regions = generator.choice(viable)
    region_count = generator.randint(2, maximum_regions)
    slice_size = slice_sizes[start_index]
    length_bytes = max(1, slice_size * corruption_percent // 100)
    region_lengths = _positive_composition(length_bytes, region_count, generator)

    # Reserve one byte between adjacent regions, then distribute all remaining
    # clean bytes across the leading, internal, and trailing gaps.
    free_bytes = slice_size - length_bytes - (region_count - 1)
    gaps = _weak_composition(free_bytes, region_count + 1, generator)
    for gap_index in range(1, region_count):
        gaps[gap_index] += 1

    segments: list[dict[str, Any]] = []
    offset = gaps[0]
    for region_index, region_length in enumerate(region_lengths):
        segments.append(
            {
                "segment_index": region_index,
                "region_index": region_index,
                "slice": ordered_paths[start_index].name,
                "path": str(ordered_paths[start_index]),
                "slice_number": _slice_number(ordered_paths[start_index]),
                "slice_bytes": slice_size,
                "offset_bytes": offset,
                "length_bytes": region_length,
            }
        )
        offset += region_length + gaps[region_index + 1]

    return {
        "seed": seed,
        "phase": phase.lower(),
        "mode": "fragmented",
        "corruption_percent": corruption_percent,
        "logical_offset_bytes": None,
        "length_bytes": length_bytes,
        "region_count": region_count,
        "segments": segments,
    }


def _select_edges(
    seed: int,
    phase: str,
    ordered_paths: Sequence[Path],
    slice_sizes: Sequence[int],
) -> dict[str, Any]:
    """Select one-percent windows at the archive's first and final edges.

    Args:
        seed: Run-level seed recorded with the deterministic selection.
        phase: Lifecycle phase label.
        ordered_paths: Numerically ordered DAR slices.
        slice_sizes: Corresponding slice sizes.

    Returns:
        JSON-serializable edge selection.

    Raises:
        ValueError: If a boundary slice is too small for one-percent windows.
    """
    first_path = ordered_paths[0]
    final_path = ordered_paths[-1]
    first_size = slice_sizes[0]
    final_size = slice_sizes[-1]
    segments: list[dict[str, Any]] = []

    first_length = first_size * EDGE_PERCENT // 100
    final_length = final_size * EDGE_PERCENT // 100
    if first_length <= 0 or final_length <= 0:
        raise ValueError(
            "boundary DAR slices must be at least 100 bytes for edge corruption"
        )
    if first_path == final_path and first_length + final_length >= first_size:
        raise ValueError("single DAR slice is too small for two edge regions")

    edge_values = (
        (first_path, first_size, 0, first_length),
        (final_path, final_size, final_size - final_length, final_length),
    )
    for region_index, (path, size, offset, length) in enumerate(edge_values):
        segments.append(
            {
                "segment_index": region_index,
                "region_index": region_index,
                "slice": path.name,
                "path": str(path),
                "slice_number": _slice_number(path),
                "slice_bytes": size,
                "offset_bytes": offset,
                "length_bytes": length,
            }
        )

    return {
        "seed": seed,
        "phase": phase.lower(),
        "mode": "edges",
        "corruption_percent": EDGE_PERCENT * 2,
        "edge_percent": EDGE_PERCENT,
        "logical_offset_bytes": None,
        "length_bytes": first_length + final_length,
        "region_count": 2,
        "segments": segments,
    }


def select_corruption(
    seed: int,
    phase: str,
    slice_paths: Sequence[Path],
    corruption_percent: int = 2,
    mode: str = "contiguous",
) -> dict[str, Any]:
    """Select reproducible corruption regions for one supported test mode.

    Args:
        seed: Run-level unsigned 64-bit random seed.
        phase: Stable phase label used to derive independent random choices.
        slice_paths: DAR slice paths belonging to one archive.
        corruption_percent: Maximum corruption percentage for every affected slice.
        mode: ``contiguous``, ``fragmented``, or ``edges``.

    Returns:
        JSON-serializable selection metadata and physical slice segments.

    Raises:
        OSError: If a slice cannot be inspected.
        ValueError: If inputs are invalid or no safe interval can be selected.
    """
    _validate_seed(seed)
    if not isinstance(phase, str) or not phase.strip():
        raise ValueError("phase must be a non-empty string")
    if not isinstance(corruption_percent, int) or isinstance(corruption_percent, bool):
        raise ValueError("corruption_percent must be an integer")
    if corruption_percent <= 0 or corruption_percent >= 100:
        raise ValueError("corruption_percent must be between 1 and 99")
    if not isinstance(mode, str) or mode not in VALID_MODES:
        raise ValueError(f"mode must be one of: {', '.join(sorted(VALID_MODES))}")
    if mode == "edges" and corruption_percent != EDGE_PERCENT * 2:
        raise ValueError("edges mode requires 2% corruption: 1% at each end")

    ordered_paths, slice_sizes = _inspect_slices(slice_paths)
    if mode == "contiguous":
        return _select_contiguous(
            seed, phase, ordered_paths, slice_sizes, corruption_percent
        )
    if mode == "fragmented":
        return _select_fragmented(
            seed, phase, ordered_paths, slice_sizes, corruption_percent
        )
    return _select_edges(
        seed,
        phase,
        ordered_paths,
        slice_sizes,
    )


def parse_par2_block_counts(output: str) -> tuple[int, int]:
    """Extract found and total PAR2 data-block counts from repair output.

    Args:
        output: Text emitted by ``par2 repair`` for one damaged slice.

    Returns:
        A ``(found, total)`` tuple.

    Raises:
        ValueError: If the expected block-count line is absent or invalid.
    """
    if not isinstance(output, str) or not output:
        raise ValueError("PAR2 output must be a non-empty string")
    match = PAR2_BLOCK_PATTERN.search(output)
    if match is None:
        raise ValueError("PAR2 output does not contain data-block counts")
    found = int(match.group(1))
    total = int(match.group(2))
    if total <= 0 or found < 0 or found > total:
        raise ValueError(
            f"Invalid PAR2 data-block counts: found={found}, total={total}"
        )
    return found, total


def _load_evidence(path: Path) -> dict[str, Any]:
    """Load an existing evidence object or return a new empty object.

    Args:
        path: Evidence JSON file.

    Returns:
        The decoded evidence mapping.

    Raises:
        OSError: If an existing file cannot be read.
        ValueError: If existing JSON is malformed or not an object.
    """
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(
            f"Malformed bitrot evidence JSON in {path}: {error}"
        ) from error
    if not isinstance(value, dict):
        raise ValueError(f"Bitrot evidence in {path} must be a JSON object")
    return value


def _save_evidence(path: Path, evidence: Mapping[str, Any]) -> None:
    """Atomically write the current evidence object.

    Args:
        path: Evidence JSON destination.
        evidence: JSON-serializable evidence mapping.

    Raises:
        OSError: If the destination cannot be written or replaced.
        TypeError: If evidence is not JSON serializable.
        ValueError: If an argument is invalid.
    """
    if path is None:
        raise ValueError("path must not be None")
    if evidence is None:
        raise ValueError("evidence must not be None")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            json.dump(evidence, temporary_file, separators=(",", ":"))
            temporary_file.write("\n")
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def initialize_phase_evidence(
    path: Path, phase: str, selection: Mapping[str, Any], buffer_bytes: int
) -> None:
    """Persist initial evidence immediately after selecting a corruption range.

    Args:
        path: Per-run evidence JSON file.
        phase: Lifecycle phase key.
        selection: Selection returned by ``select_corruption``.
        buffer_bytes: Injection I/O buffer size.

    Raises:
        OSError: If evidence cannot be read or written.
        TypeError: If evidence is not JSON serializable.
        ValueError: If inputs are invalid.
    """
    if not phase:
        raise ValueError("phase must be non-empty")
    if not isinstance(buffer_bytes, int) or buffer_bytes <= 0:
        raise ValueError("buffer_bytes must be a positive integer")
    segments = selection.get("segments")
    if not isinstance(segments, list) or not segments:
        raise ValueError("selection must contain at least one segment")

    public_segments: list[dict[str, Any]] = []
    for segment in segments:
        if not isinstance(segment, dict):
            raise ValueError("selection segments must be objects")
        public_segments.append(
            {
                key: value
                for key, value in segment.items()
                if key != "path"
            }
            | {
                "par2_data_blocks_found": None,
                "par2_data_blocks_total": None,
                "par2_data_blocks_damaged": None,
                "repair_elapsed_ms": None,
                "repair_status": "not_run",
            }
        )

    evidence = _load_evidence(path)
    evidence[phase.lower()] = {
        "seed": selection.get("seed"),
        "mode": selection.get("mode", "contiguous"),
        "corruption_percent": selection.get("corruption_percent"),
        "edge_percent": selection.get("edge_percent"),
        "logical_offset_bytes": selection.get("logical_offset_bytes"),
        "length_bytes": selection.get("length_bytes"),
        "region_count": selection.get("region_count", 1),
        "buffer_bytes": buffer_bytes,
        "injection_elapsed_ms": None,
        "repair_elapsed_ms": None,
        "dar_detected_corruption": "not_run",
        "dar_verify_after_repair": "not_run",
        "status": "in_progress",
        "segments": public_segments,
    }
    _save_evidence(path, evidence)


def update_phase_evidence(path: Path, phase: str, updates: Mapping[str, Any]) -> None:
    """Update top-level evidence fields for one phase.

    Args:
        path: Per-run evidence JSON file.
        phase: Lifecycle phase key.
        updates: Field values to merge into the phase evidence.

    Raises:
        OSError: If evidence cannot be read or written.
        TypeError: If evidence is not JSON serializable.
        ValueError: If the phase or updates are invalid.
    """
    if not updates:
        raise ValueError("at least one phase update is required")
    evidence = _load_evidence(path)
    phase_key = phase.lower()
    phase_evidence = evidence.get(phase_key)
    if not isinstance(phase_evidence, dict):
        raise ValueError(f"No initialized bitrot evidence for phase {phase!r}")
    for key, value in updates.items():
        if key in {"status", "dar_detected_corruption", "dar_verify_after_repair"}:
            if value not in VALID_STATUSES:
                raise ValueError(f"Invalid evidence status for {key}: {value!r}")
        phase_evidence[key] = value
    _save_evidence(path, evidence)


def update_segment_evidence(
    path: Path,
    phase: str,
    segment_index: int,
    found_blocks: int,
    total_blocks: int,
    repair_elapsed_ms: int,
    repair_status: str,
) -> None:
    """Record PAR2 metrics and repair outcome for one affected slice.

    Args:
        path: Per-run evidence JSON file.
        phase: Lifecycle phase key.
        segment_index: Zero-based segment index from the selection.
        found_blocks: PAR2 data blocks found before repair.
        total_blocks: Total PAR2 data blocks protecting the slice.
        repair_elapsed_ms: Repair-command duration in milliseconds.
        repair_status: Repair status string.

    Raises:
        OSError: If evidence cannot be read or written.
        TypeError: If evidence is not JSON serializable.
        ValueError: If inputs or existing evidence are invalid.
    """
    if segment_index < 0:
        raise ValueError("segment_index must be non-negative")
    if total_blocks <= 0 or found_blocks < 0 or found_blocks > total_blocks:
        raise ValueError("PAR2 block counts are invalid")
    if repair_elapsed_ms < 0:
        raise ValueError("repair_elapsed_ms must be non-negative")
    if repair_status not in VALID_STATUSES:
        raise ValueError(f"Invalid repair status: {repair_status!r}")

    evidence = _load_evidence(path)
    phase_evidence = evidence.get(phase.lower())
    if not isinstance(phase_evidence, dict):
        raise ValueError(f"No initialized bitrot evidence for phase {phase!r}")
    segments = phase_evidence.get("segments")
    if not isinstance(segments, list) or segment_index >= len(segments):
        raise ValueError(f"No bitrot segment {segment_index} for phase {phase!r}")
    segment = segments[segment_index]
    if not isinstance(segment, dict):
        raise ValueError("Stored bitrot segment must be an object")
    segment.update(
        {
            "par2_data_blocks_found": found_blocks,
            "par2_data_blocks_total": total_blocks,
            "par2_data_blocks_damaged": total_blocks - found_blocks,
            "repair_elapsed_ms": repair_elapsed_ms,
            "repair_status": repair_status,
        }
    )
    _save_evidence(path, evidence)


def update_slice_evidence(
    path: Path,
    phase: str,
    slice_number: int,
    found_blocks: int,
    total_blocks: int,
    repair_elapsed_ms: int,
    repair_status: str,
) -> None:
    """Record one PAR2 repair result on every region in an affected slice.

    Args:
        path: Per-run evidence JSON file.
        phase: Lifecycle phase key.
        slice_number: Numeric DAR slice repaired once by PAR2.
        found_blocks: PAR2 data blocks found before repair.
        total_blocks: Total PAR2 data blocks protecting the slice.
        repair_elapsed_ms: Repair-command duration in milliseconds.
        repair_status: Repair status string.

    Raises:
        OSError: If evidence cannot be read or written.
        TypeError: If evidence is not JSON serializable.
        ValueError: If inputs or existing evidence are invalid.
    """
    if not isinstance(slice_number, int) or isinstance(slice_number, bool):
        raise ValueError("slice_number must be an integer")
    if slice_number <= 0:
        raise ValueError("slice_number must be positive")
    if total_blocks <= 0 or found_blocks < 0 or found_blocks > total_blocks:
        raise ValueError("PAR2 block counts are invalid")
    if repair_elapsed_ms < 0:
        raise ValueError("repair_elapsed_ms must be non-negative")
    if repair_status not in VALID_STATUSES:
        raise ValueError(f"Invalid repair status: {repair_status!r}")

    evidence = _load_evidence(path)
    phase_evidence = evidence.get(phase.lower())
    if not isinstance(phase_evidence, dict):
        raise ValueError(f"No initialized bitrot evidence for phase {phase!r}")
    segments = phase_evidence.get("segments")
    if not isinstance(segments, list):
        raise ValueError(f"No bitrot segments for phase {phase!r}")

    matching_segments = [
        segment
        for segment in segments
        if isinstance(segment, dict) and segment.get("slice_number") == slice_number
    ]
    if not matching_segments:
        raise ValueError(
            f"No bitrot segments for slice {slice_number} in phase {phase!r}"
        )
    updates = {
        "par2_data_blocks_found": found_blocks,
        "par2_data_blocks_total": total_blocks,
        "par2_data_blocks_damaged": total_blocks - found_blocks,
        "repair_elapsed_ms": repair_elapsed_ms,
        "repair_status": repair_status,
    }
    for segment in matching_segments:
        segment.update(updates)
    _save_evidence(path, evidence)


def _parse_selection(value: str) -> dict[str, Any]:
    """Decode a selection passed between helper CLI commands.

    Args:
        value: JSON-encoded selection object.

    Returns:
        Decoded selection mapping.

    Raises:
        ValueError: If JSON is malformed or not an object.
    """
    try:
        selection = json.loads(value)
    except json.JSONDecodeError as error:
        raise ValueError(f"Malformed selection JSON: {error}") from error
    if not isinstance(selection, dict):
        raise ValueError("selection JSON must contain an object")
    return selection


def _build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser used by the Bash harness.

    Returns:
        Configured argument parser.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    seed_parser = subparsers.add_parser("validate-seed")
    seed_parser.add_argument("--seed", type=int, required=True)

    select_parser = subparsers.add_parser("select")
    select_parser.add_argument("--seed", type=int, required=True)
    select_parser.add_argument("--phase", required=True)
    select_parser.add_argument("--percent", type=int, default=2)
    select_parser.add_argument(
        "--mode", choices=sorted(VALID_MODES), default="contiguous"
    )
    select_parser.add_argument("slices", nargs="+")

    segments_parser = subparsers.add_parser("segments")
    segments_parser.add_argument("--selection", required=True)

    subparsers.add_parser("parse-blocks")

    init_parser = subparsers.add_parser("init")
    init_parser.add_argument("--file", type=Path, required=True)
    init_parser.add_argument("--phase", required=True)
    init_parser.add_argument("--selection", required=True)
    init_parser.add_argument("--buffer-bytes", type=int, required=True)

    phase_parser = subparsers.add_parser("update-phase")
    phase_parser.add_argument("--file", type=Path, required=True)
    phase_parser.add_argument("--phase", required=True)
    phase_parser.add_argument("--status")
    phase_parser.add_argument("--injection-elapsed-ms", type=int)
    phase_parser.add_argument("--repair-elapsed-ms", type=int)
    phase_parser.add_argument("--dar-detected-corruption")
    phase_parser.add_argument("--dar-verify-after-repair")

    segment_parser = subparsers.add_parser("update-segment")
    segment_parser.add_argument("--file", type=Path, required=True)
    segment_parser.add_argument("--phase", required=True)
    segment_parser.add_argument("--index", type=int, required=True)
    segment_parser.add_argument("--found", type=int, required=True)
    segment_parser.add_argument("--total", type=int, required=True)
    segment_parser.add_argument("--repair-elapsed-ms", type=int, required=True)
    segment_parser.add_argument("--repair-status", required=True)

    slice_parser = subparsers.add_parser("update-slice")
    slice_parser.add_argument("--file", type=Path, required=True)
    slice_parser.add_argument("--phase", required=True)
    slice_parser.add_argument("--slice-number", type=int, required=True)
    slice_parser.add_argument("--found", type=int, required=True)
    slice_parser.add_argument("--total", type=int, required=True)
    slice_parser.add_argument("--repair-elapsed-ms", type=int, required=True)
    slice_parser.add_argument("--repair-status", required=True)
    return parser


def main() -> int:
    """Run the selected helper operation for the Bash harness.

    Returns:
        Zero after producing or persisting valid evidence.

    Raises:
        OSError: If slice metadata or evidence files cannot be accessed.
        TypeError: If evidence cannot be serialized.
        ValueError: If command inputs or PAR2 output are invalid.
    """
    arguments = _build_parser().parse_args()
    if arguments.command == "validate-seed":
        _validate_seed(arguments.seed)
        print(arguments.seed)
        return 0
    if arguments.command == "select":
        selection = select_corruption(
            arguments.seed,
            arguments.phase,
            [Path(value) for value in arguments.slices],
            arguments.percent,
            arguments.mode,
        )
        print(json.dumps(selection, separators=(",", ":")))
        return 0
    if arguments.command == "segments":
        selection = _parse_selection(arguments.selection)
        segments = selection.get("segments")
        if not isinstance(segments, list) or not segments:
            raise ValueError("selection contains no segments")
        for segment in segments:
            if not isinstance(segment, dict):
                raise ValueError("selection segment must be an object")
            print(
                "\t".join(
                    str(segment[key])
                    for key in (
                        "segment_index",
                        "region_index",
                        "path",
                        "slice_number",
                        "slice_bytes",
                        "offset_bytes",
                        "length_bytes",
                    )
                )
            )
        return 0
    if arguments.command == "parse-blocks":
        found, total = parse_par2_block_counts(sys.stdin.read())
        print(f"{found}\t{total}")
        return 0
    if arguments.command == "init":
        initialize_phase_evidence(
            arguments.file,
            arguments.phase,
            _parse_selection(arguments.selection),
            arguments.buffer_bytes,
        )
        return 0
    if arguments.command == "update-phase":
        updates = {
            key: value
            for key, value in {
                "status": arguments.status,
                "injection_elapsed_ms": arguments.injection_elapsed_ms,
                "repair_elapsed_ms": arguments.repair_elapsed_ms,
                "dar_detected_corruption": arguments.dar_detected_corruption,
                "dar_verify_after_repair": arguments.dar_verify_after_repair,
            }.items()
            if value is not None
        }
        update_phase_evidence(arguments.file, arguments.phase, updates)
        return 0
    if arguments.command == "update-segment":
        update_segment_evidence(
            arguments.file,
            arguments.phase,
            arguments.index,
            arguments.found,
            arguments.total,
            arguments.repair_elapsed_ms,
            arguments.repair_status,
        )
        return 0
    if arguments.command == "update-slice":
        update_slice_evidence(
            arguments.file,
            arguments.phase,
            arguments.slice_number,
            arguments.found,
            arguments.total,
            arguments.repair_elapsed_ms,
            arguments.repair_status,
        )
        return 0
    raise ValueError(f"Unsupported command: {arguments.command}")


if __name__ == "__main__":
    raise SystemExit(main())
