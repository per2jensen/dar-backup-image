"""Tests for constrained large-scale source selection measurement."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest


SCRIPTS_DIR = Path(__file__).parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from large_scale_definition import parse_selection_contract  # noqa: E402
from large_scale_source_measurement import (  # noqa: E402
    CACHE_TAG_NAME,
    CACHE_TAG_SIGNATURE,
    measure_source,
)


def _write_bytes(path: Path, size: int) -> None:
    """Create a deterministic regular file of an exact apparent size.

    Args:
        path: Destination beneath the isolated pytest directory.
        size: Positive number of bytes to write.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)


def test_measure_source_literal_prunes_select_expected_files_and_bytes(
    tmp_path: Path,
) -> None:
    """Two quoted subtree prunes are removed from candidate evidence.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    root = tmp_path / "source"
    _write_bytes(root / "SteamLibrary" / "Keep Game" / "keep.bin", 11)
    _write_bytes(
        root
        / "SteamLibrary"
        / "steamapps"
        / "common"
        / "Metro Exodus"
        / "metro.bin",
        13,
    )
    _write_bytes(
        root
        / "SteamLibrary"
        / "steamapps"
        / "common"
        / "The Witcher 3"
        / "witcher.bin",
        17,
    )
    _write_bytes(root / "diff-primer" / "primer.bin", 5)
    definition = f"""\
-R {root}
-am
-g SteamLibrary
-P 'SteamLibrary/steamapps/common/Metro Exodus'
-P 'SteamLibrary/steamapps/common/The Witcher 3'
"""

    measurement = measure_source(
        root, parse_selection_contract(definition), "diff-primer"
    )

    assert measurement.candidate_file_count == 4
    assert measurement.candidate_bytes == 46
    assert measurement.pruned_file_count == 2
    assert measurement.pruned_bytes == 30
    assert measurement.selected_file_count == 2
    assert measurement.selected_bytes == 16
    assert measurement.prune_path_count == 2
    assert measurement.cache_tagged_directory_count == 0


def test_measure_source_overlapping_includes_count_each_file_once(
    tmp_path: Path,
) -> None:
    """A nested repeated inclusion cannot inflate source evidence.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    root = tmp_path / "source"
    _write_bytes(root / "photos" / "nested" / "photo.raw", 19)
    _write_bytes(root / "diff-primer" / "primer.bin", 5)
    definition = f"-R {root}\n-g photos\n-g photos/nested"

    measurement = measure_source(
        root, parse_selection_contract(definition), "diff-primer"
    )

    assert measurement.candidate_file_count == 2
    assert measurement.selected_file_count == 2
    assert measurement.selected_bytes == 24


def test_measure_source_records_high_level_workload_shape(tmp_path: Path) -> None:
    """Selected entries, allocation, links, and size bands are summarized.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    root = tmp_path / "source"
    data = root / "data"
    data.mkdir(parents=True)
    (data / "empty.bin").touch()
    _write_bytes(data / "small.bin", 1)
    (data / "medium.bin").touch()
    os.truncate(data / "medium.bin", 2 * 1024**2)
    (data / "large.bin").touch()
    os.truncate(data / "large.bin", 101 * 1024**2)
    _write_bytes(data / "linked-a.bin", 4)
    os.link(data / "linked-a.bin", data / "linked-b.bin")
    os.symlink("small.bin", data / "small-link")
    _write_bytes(root / "diff-primer" / "primer.bin", 5)
    definition = f"-R {root}\n-g data"

    measurement = measure_source(
        root, parse_selection_contract(definition), "diff-primer"
    )

    assert measurement.selected_file_count == 7
    assert measurement.selected_directory_count == 2
    assert measurement.selected_symlink_count == 1
    assert measurement.selected_other_entry_count == 0
    assert measurement.selected_hard_link_group_count == 1
    assert measurement.selected_zero_file_count == 1
    assert measurement.selected_small_file_count == 4
    assert measurement.selected_medium_file_count == 1
    assert measurement.selected_large_file_count == 1
    assert measurement.selected_max_file_bytes == 101 * 1024**2
    assert measurement.selected_allocated_bytes >= 0


def test_measure_source_pruned_entries_do_not_inflate_workload_shape(
    tmp_path: Path,
) -> None:
    """Directories and links under a literal prune are excluded from shape metrics.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    root = tmp_path / "source"
    _write_bytes(root / "data" / "keep.bin", 7)
    _write_bytes(root / "data" / "private" / "hidden.bin", 9)
    os.symlink("hidden.bin", root / "data" / "private" / "hidden-link")
    _write_bytes(root / "diff-primer" / "primer.bin", 5)
    definition = f"-R {root}\n-g data\n-P data/private"

    measurement = measure_source(
        root, parse_selection_contract(definition), "diff-primer"
    )

    assert measurement.selected_file_count == 2
    assert measurement.selected_directory_count == 2
    assert measurement.selected_symlink_count == 0


def test_measure_source_cache_tagging_excludes_tagged_directory_contents(
    tmp_path: Path,
) -> None:
    """The supported cache-tag option excludes a valid tagged subtree.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    root = tmp_path / "source"
    _write_bytes(root / "SteamLibrary" / "keep.bin", 7)
    cache_directory = root / "SteamLibrary" / "shader-cache"
    _write_bytes(cache_directory / "cached.bin", 23)
    tag_payload = CACHE_TAG_SIGNATURE + b"\n"
    cache_directory.joinpath(CACHE_TAG_NAME).write_bytes(tag_payload)
    _write_bytes(root / "diff-primer" / "primer.bin", 5)
    definition = f"""\
-R {root}
--cache-directory-tagging
-g SteamLibrary
"""

    measurement = measure_source(
        root, parse_selection_contract(definition), "diff-primer"
    )

    assert measurement.candidate_file_count == 4
    assert measurement.candidate_bytes == 35 + len(tag_payload)
    assert measurement.pruned_file_count == 2
    assert measurement.pruned_bytes == 23 + len(tag_payload)
    assert measurement.selected_file_count == 2
    assert measurement.selected_bytes == 12
    assert measurement.cache_tagged_directory_count == 1


def test_measure_source_nonexistent_literal_prune_raises_value_error(
    tmp_path: Path,
) -> None:
    """A mistyped literal prune fails instead of silently inflating evidence.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    root = tmp_path / "source"
    _write_bytes(root / "SteamLibrary" / "keep.bin", 7)
    _write_bytes(root / "diff-primer" / "primer.bin", 5)
    definition = f"-R {root}\n-g SteamLibrary\n-P SteamLibrary/Missing"

    with pytest.raises(ValueError, match="-P path does not exist"):
        measure_source(root, parse_selection_contract(definition), "diff-primer")


def test_measure_source_irrelevant_literal_prune_raises_value_error(
    tmp_path: Path,
) -> None:
    """An existing prune outside every user inclusion fails as likely misuse.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    root = tmp_path / "source"
    _write_bytes(root / "SteamLibrary" / "keep.bin", 7)
    _write_bytes(root / "other" / "private.bin", 9)
    _write_bytes(root / "diff-primer" / "primer.bin", 5)
    definition = f"-R {root}\n-g SteamLibrary\n-P other"

    with pytest.raises(ValueError, match="does not intersect"):
        measure_source(root, parse_selection_contract(definition), "diff-primer")


def test_measure_source_normal_mode_prune_cannot_remove_required_primer(
    tmp_path: Path,
) -> None:
    """A non-ordered prune covering the primer fails before backup.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    root = tmp_path / "source"
    _write_bytes(root / "selected" / "keep.bin", 7)
    _write_bytes(root / "diff-primer" / "primer.bin", 5)
    definition = f"-R {root}\n-g .\n-P diff-primer"

    with pytest.raises(ValueError, match="mandatory primer"):
        measure_source(root, parse_selection_contract(definition), "diff-primer")


def test_measure_source_ordered_injected_include_restores_required_primer(
    tmp_path: Path,
) -> None:
    """The harness's final primer -g overrides an earlier -P under simple -am.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    root = tmp_path / "source"
    _write_bytes(root / "selected" / "keep.bin", 7)
    _write_bytes(root / "diff-primer" / "primer.bin", 5)
    definition = f"-R {root}\n-am\n-g .\n-P diff-primer"

    measurement = measure_source(
        root, parse_selection_contract(definition), "diff-primer"
    )

    assert measurement.selected_file_count == 2
    assert measurement.selected_bytes == 12


def test_measure_source_matches_real_dar_literal_selection(
    tmp_path: Path, image: str
) -> None:
    """A tiny real DAR archive selects the same files and apparent bytes.

    Args:
        tmp_path: Isolated pytest temporary directory bind-mounted into Docker.
        image: Docker image containing the DAR binary under test.
    """
    root = tmp_path / "source"
    _write_bytes(root / "SteamLibrary" / "Keep Game" / "keep.bin", 11)
    _write_bytes(
        root / "SteamLibrary" / "Metro Exodus" / "metro.bin", 13
    )
    cache_directory = root / "SteamLibrary" / "shader-cache"
    _write_bytes(cache_directory / "cached.bin", 23)
    cache_directory.joinpath(CACHE_TAG_NAME).write_bytes(
        CACHE_TAG_SIGNATURE + b"\n"
    )
    _write_bytes(root / "diff-primer" / "primer.bin", 5)
    user_definition = f"""\
-R {root}
-am
--cache-directory-tagging
-g SteamLibrary
-P 'SteamLibrary/Metro Exodus'
"""
    measurement = measure_source(
        root, parse_selection_contract(user_definition), "diff-primer"
    )
    effective_definition = tmp_path / "effective-definition"
    effective_definition.write_text(
        f"{user_definition}-g diff-primer\n", encoding="utf-8"
    )
    archive = tmp_path / "selection-archive"
    restore = tmp_path / "restore"
    restore.mkdir()
    common_docker_arguments = [
        "docker",
        "run",
        "--rm",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "-e",
        "HOME=/tmp",
        "-v",
        f"{tmp_path}:{tmp_path}",
        "--entrypoint",
        "/usr/local/bin/dar",
        image,
    ]
    create_result = subprocess.run(
        [
            *common_docker_arguments,
            "-c",
            str(archive),
            "--noconf",
            "-B",
            str(effective_definition),
            "-Q",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert create_result.returncode == 0, create_result.stderr
    restore_result = subprocess.run(
        [
            *common_docker_arguments,
            "-x",
            str(archive),
            "-R",
            str(restore),
            "--noconf",
            "-Q",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert restore_result.returncode == 0, restore_result.stderr

    restored_files = [path for path in restore.rglob("*") if path.is_file()]
    restored_bytes = sum(path.stat().st_size for path in restored_files)
    restored_relative_paths = {
        path.relative_to(restore).as_posix() for path in restored_files
    }

    assert restored_relative_paths == {
        "SteamLibrary/Keep Game/keep.bin",
        "diff-primer/primer.bin",
    }
    assert len(restored_files) == measurement.selected_file_count
    assert restored_bytes == measurement.selected_bytes
