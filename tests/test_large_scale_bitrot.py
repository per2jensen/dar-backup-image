"""Tests for reproducible large-scale bitrot selection and evidence."""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).parents[1] / "scripts" / "large_scale_bitrot.py"
MODULE_SPEC = importlib.util.spec_from_file_location("large_scale_bitrot", MODULE_PATH)
if MODULE_SPEC is None or MODULE_SPEC.loader is None:
    raise RuntimeError(f"Unable to load bitrot helper from {MODULE_PATH}")
BITROT_MODULE = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(BITROT_MODULE)


def _create_slices(tmp_path: Path, sizes: tuple[int, ...]) -> list[Path]:
    """Create numbered DAR-like slice files for selection tests.

    Args:
        tmp_path: Isolated pytest temporary directory.
        sizes: Exact byte size for every slice.

    Returns:
        Created paths in numeric slice order.
    """
    paths: list[Path] = []
    for number, size in enumerate(sizes, start=1):
        path = tmp_path / f"archive.{number}.dar"
        path.write_bytes(b"\0" * size)
        paths.append(path)
    return paths


def test_select_corruption_same_seed_reproduces_exact_range(tmp_path: Path) -> None:
    """The same run seed and phase reproduce byte-identical selection metadata.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    paths = _create_slices(tmp_path, (100_000, 100_000, 100_000))

    first = BITROT_MODULE.select_corruption(123456789, "full", paths)
    second = BITROT_MODULE.select_corruption(123456789, "full", reversed(paths))

    assert first == second
    assert first["seed"] == 123456789
    assert first["mode"] == "contiguous"
    assert first["region_count"] == 1
    assert first["length_bytes"] == 2_000


def test_select_corruption_fragmented_spreads_exact_budget_reproducibly(
    tmp_path: Path,
) -> None:
    """Fragmented mode creates separated regions with an exact 2% byte total.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    paths = _create_slices(tmp_path, (100_000, 100_000, 100_000))

    first = BITROT_MODULE.select_corruption(
        24680, "full", paths, mode="fragmented"
    )
    second = BITROT_MODULE.select_corruption(
        24680, "full", reversed(paths), mode="fragmented"
    )

    assert first == second
    assert first["mode"] == "fragmented"
    assert 2 <= first["region_count"] <= 10
    assert len(first["segments"]) == first["region_count"]
    assert sum(item["length_bytes"] for item in first["segments"]) == 2_000
    assert len({item["slice_number"] for item in first["segments"]}) == 1
    for previous, current in zip(first["segments"], first["segments"][1:]):
        assert (
            previous["offset_bytes"] + previous["length_bytes"]
            < current["offset_bytes"]
        )


def test_select_corruption_fragmented_tiny_slice_raises_value_error(
    tmp_path: Path,
) -> None:
    """Fragmented mode rejects input that cannot hold two safe regions.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    paths = _create_slices(tmp_path, (50,))

    with pytest.raises(ValueError, match="two separated corruption regions"):
        BITROT_MODULE.select_corruption(1, "full", paths, mode="fragmented")


def test_select_corruption_edges_targets_numeric_first_and_final_slices(
    tmp_path: Path,
) -> None:
    """Edges mode targets offset zero and EOF using numeric slice ordering.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    paths = []
    for number in (10, 2, 1):
        path = tmp_path / f"archive.{number}.dar"
        path.write_bytes(b"\0" * 200_000)
        paths.append(path)

    selection = BITROT_MODULE.select_corruption(5, "full", paths, mode="edges")

    first, final = selection["segments"]
    assert selection["mode"] == "edges"
    assert selection["region_count"] == 2
    assert first["slice_number"] == 1
    assert first["offset_bytes"] == 0
    assert final["slice_number"] == 10
    assert final["offset_bytes"] + final["length_bytes"] == final["slice_bytes"]
    assert first["length_bytes"] == 4_000
    assert final["length_bytes"] == 4_000


def test_select_corruption_edges_single_slice_uses_two_non_overlapping_regions(
    tmp_path: Path,
) -> None:
    """Edges mode safely places both windows in a one-slice archive.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    paths = _create_slices(tmp_path, (100_000,))

    selection = BITROT_MODULE.select_corruption(9, "diff", paths, mode="edges")

    first, final = selection["segments"]
    assert first["slice_number"] == final["slice_number"] == 1
    assert first["offset_bytes"] == 0
    assert final["offset_bytes"] + final["length_bytes"] == 100_000
    assert first["offset_bytes"] + first["length_bytes"] < final["offset_bytes"]
    assert first["length_bytes"] + final["length_bytes"] == 2_000


def test_select_corruption_edges_tiny_single_slice_raises_value_error(
    tmp_path: Path,
) -> None:
    """Edges mode rejects a slice that cannot hold two safe windows.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    paths = _create_slices(tmp_path, (50,))

    with pytest.raises(ValueError, match="too small for two edge regions"):
        BITROT_MODULE.select_corruption(1, "full", paths, mode="edges")


def test_select_corruption_unknown_mode_raises_value_error(tmp_path: Path) -> None:
    """Selection rejects unsupported bitrot modes at its public entry point.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    paths = _create_slices(tmp_path, (100_000,))

    with pytest.raises(ValueError, match="mode must be one of"):
        BITROT_MODULE.select_corruption(1, "full", paths, mode="unknown")


def test_select_corruption_edges_empty_phase_raises_value_error(
    tmp_path: Path,
) -> None:
    """Deterministic edges mode still requires a valid lifecycle phase.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    paths = _create_slices(tmp_path, (100_000,))

    with pytest.raises(ValueError, match="phase must be a non-empty string"):
        BITROT_MODULE.select_corruption(1, "", paths, mode="edges")


def test_helper_cli_emits_harness_segment_fields_for_fragmented_mode(
    tmp_path: Path,
) -> None:
    """The real helper CLI supplies every tab-delimited field Bash consumes.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    paths = _create_slices(tmp_path, (100_000,))
    selected = subprocess.run(
        [
            "python3",
            str(MODULE_PATH),
            "select",
            "--seed",
            "17",
            "--phase",
            "full",
            "--mode",
            "fragmented",
            str(paths[0]),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    decoded = json.loads(selected.stdout)

    segments = subprocess.run(
        [
            "python3",
            str(MODULE_PATH),
            "segments",
            "--selection",
            selected.stdout.strip(),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    lines = segments.stdout.splitlines()
    assert len(lines) == decoded["region_count"]
    assert all(len(line.split("\t")) == 7 for line in lines)


def test_select_corruption_boundary_start_crosses_two_slices_safely(
    tmp_path: Path,
) -> None:
    """A seed near a boundary produces two independently repairable segments.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    paths = _create_slices(tmp_path, (100_000, 100_000, 100_000))
    selection = None
    for seed in range(10_000):
        candidate = BITROT_MODULE.select_corruption(seed, "full", paths)
        if len(candidate["segments"]) == 2:
            selection = candidate
            break

    assert selection is not None
    assert len(selection["segments"]) == 2
    assert sum(item["length_bytes"] for item in selection["segments"]) == 2_000
    assert selection["segments"][0]["slice_number"] + 1 == selection["segments"][1][
        "slice_number"
    ]
    assert (
        selection["segments"][0]["offset_bytes"]
        + selection["segments"][0]["length_bytes"]
        == selection["segments"][0]["slice_bytes"]
    )
    assert selection["segments"][1]["offset_bytes"] == 0
    for segment in selection["segments"]:
        assert segment["length_bytes"] <= segment["slice_bytes"] * 2 // 100


def test_select_corruption_empty_slice_list_raises_value_error() -> None:
    """Selection rejects an archive with no DAR slices."""
    with pytest.raises(ValueError, match="at least one DAR slice"):
        BITROT_MODULE.select_corruption(1, "full", [])


def test_select_corruption_seed_above_uint64_raises_value_error(
    tmp_path: Path,
) -> None:
    """A replay seed outside the documented unsigned 64-bit range is rejected.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    paths = _create_slices(tmp_path, (100_000,))

    with pytest.raises(ValueError, match="seed must be between"):
        BITROT_MODULE.select_corruption(1 << 64, "full", paths)


def test_parse_par2_block_counts_extracts_found_total_and_damage() -> None:
    """Realistic PAR2 repair text yields auditable found and total counts."""
    output = "Target: archive.1.dar - damaged.\nFound 1959 of 2000 data blocks.\n"

    found, total = BITROT_MODULE.parse_par2_block_counts(output)

    assert found == 1959
    assert total == 2000
    assert total - found == 41


def test_parse_par2_block_counts_missing_line_raises_value_error() -> None:
    """Missing PAR2 block metrics are rejected instead of recorded as zero."""
    with pytest.raises(ValueError, match="does not contain data-block counts"):
        BITROT_MODULE.parse_par2_block_counts("Repair complete")


def test_evidence_updates_record_metrics_without_absolute_slice_path(
    tmp_path: Path,
) -> None:
    """Incremental evidence records timing and PAR2 metrics without host paths.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    slices = _create_slices(tmp_path, (100_000, 100_000))
    selection = BITROT_MODULE.select_corruption(7, "diff", slices)
    evidence_path = tmp_path / "evidence.json"

    BITROT_MODULE.initialize_phase_evidence(
        evidence_path, "diff", selection, buffer_bytes=1_048_576
    )
    BITROT_MODULE.update_phase_evidence(
        evidence_path,
        "diff",
        {
            "injection_elapsed_ms": 123,
            "repair_elapsed_ms": 456,
            "dar_detected_corruption": "passed",
            "dar_verify_after_repair": "passed",
            "status": "passed",
        },
    )
    BITROT_MODULE.update_segment_evidence(
        evidence_path,
        "diff",
        segment_index=0,
        found_blocks=1959,
        total_blocks=2000,
        repair_elapsed_ms=321,
        repair_status="passed",
    )

    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    phase = evidence["diff"]
    segment = phase["segments"][0]
    assert phase["buffer_bytes"] == 1_048_576
    assert phase["injection_elapsed_ms"] == 123
    assert phase["status"] == "passed"
    assert segment["par2_data_blocks_found"] == 1959
    assert segment["par2_data_blocks_total"] == 2000
    assert segment["par2_data_blocks_damaged"] == 41
    assert "path" not in segment


def test_update_slice_evidence_updates_every_region_in_repaired_slice(
    tmp_path: Path,
) -> None:
    """One PAR2 result is attached to all fragmented regions in its slice.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    slices = _create_slices(tmp_path, (100_000,))
    selection = BITROT_MODULE.select_corruption(
        37, "full", slices, mode="fragmented"
    )
    evidence_path = tmp_path / "evidence.json"
    BITROT_MODULE.initialize_phase_evidence(
        evidence_path, "full", selection, buffer_bytes=1_048_576
    )

    BITROT_MODULE.update_slice_evidence(
        evidence_path,
        "full",
        slice_number=1,
        found_blocks=1950,
        total_blocks=2000,
        repair_elapsed_ms=400,
        repair_status="passed",
    )

    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert evidence["full"]["mode"] == "fragmented"
    assert evidence["full"]["region_count"] == len(selection["segments"])
    for segment in evidence["full"]["segments"]:
        assert segment["par2_data_blocks_damaged"] == 50
        assert segment["repair_status"] == "passed"


def test_update_slice_evidence_unknown_slice_raises_value_error(
    tmp_path: Path,
) -> None:
    """A PAR2 result cannot be recorded against an unaffected slice.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    slices = _create_slices(tmp_path, (100_000,))
    selection = BITROT_MODULE.select_corruption(3, "full", slices)
    evidence_path = tmp_path / "evidence.json"
    BITROT_MODULE.initialize_phase_evidence(
        evidence_path, "full", selection, buffer_bytes=1_048_576
    )

    with pytest.raises(ValueError, match="No bitrot segments for slice 2"):
        BITROT_MODULE.update_slice_evidence(
            evidence_path,
            "full",
            slice_number=2,
            found_blocks=1950,
            total_blocks=2000,
            repair_elapsed_ms=400,
            repair_status="passed",
        )


def test_update_phase_evidence_uninitialized_phase_raises_value_error(
    tmp_path: Path,
) -> None:
    """Evidence updates fail clearly when selection was never initialized.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    with pytest.raises(ValueError, match="No initialized bitrot evidence"):
        BITROT_MODULE.update_phase_evidence(
            tmp_path / "evidence.json", "incr", {"status": "failed"}
        )
