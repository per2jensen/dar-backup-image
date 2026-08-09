"""Tests for reproducible large-scale bitrot selection and evidence."""

from __future__ import annotations

import importlib.util
import json
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
    assert first["length_bytes"] == 2_000


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
