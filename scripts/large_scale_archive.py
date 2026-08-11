#!/usr/bin/env python3
"""Discover archives created by the large-scale test harness."""

from __future__ import annotations

import argparse
import logging
import re
from pathlib import Path
from typing import Sequence


LOGGER = logging.getLogger(__name__)
VALID_BACKUP_TYPES = {"FULL", "DIFF", "INCR"}


def find_archive_base(
    backup_dir: Path,
    definition_name: str,
    backup_type: str,
) -> str:
    """Return the unique archive base created for one backup phase.

    Args:
        backup_dir: Private backup directory for the current harness run.
        definition_name: Backup definition and archive filename prefix.
        backup_type: Backup phase type: ``FULL``, ``DIFF``, or ``INCR``.

    Returns:
        Archive basename without the ``.<slice>.dar`` suffix.

    Raises:
        ValueError: If an input is empty, invalid, or not a directory.
        FileNotFoundError: If no first archive slice matches the phase.
        RuntimeError: If multiple archive bases match the phase.
    """
    if not isinstance(backup_dir, Path):
        raise ValueError("backup_dir must be a pathlib.Path")
    if not backup_dir.is_dir():
        raise ValueError(f"backup_dir is not a directory: {backup_dir}")
    if not isinstance(definition_name, str) or not definition_name:
        raise ValueError("definition_name must be a non-empty string")
    if not isinstance(backup_type, str):
        raise ValueError("backup_type must be a string")
    if backup_type not in VALID_BACKUP_TYPES:
        valid_types = ", ".join(sorted(VALID_BACKUP_TYPES))
        raise ValueError(f"backup_type must be one of {valid_types}, got {backup_type!r}")

    filename_pattern = re.compile(
        rf"^{re.escape(definition_name)}_{backup_type}_"
        rf"\d{{4}}-\d{{2}}-\d{{2}}\.1\.dar$"
    )
    candidates = sorted(
        path
        for path in backup_dir.iterdir()
        if path.is_file() and filename_pattern.fullmatch(path.name)
    )

    expected_pattern = f"{definition_name}_{backup_type}_YYYY-MM-DD.1.dar"
    if not candidates:
        raise FileNotFoundError(
            f"No archive first slice matching {expected_pattern!r} in {backup_dir}"
        )
    if len(candidates) > 1:
        candidate_names = ", ".join(path.name for path in candidates)
        raise RuntimeError(
            f"Multiple archive first slices match {expected_pattern!r} in "
            f"{backup_dir}: {candidate_names}"
        )

    return candidates[0].name.removesuffix(".1.dar")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse archive-discovery command-line arguments.

    Args:
        argv: Optional argument sequence. Defaults to ``sys.argv``.

    Returns:
        Parsed command-line arguments.
    """
    parser = argparse.ArgumentParser(
        description="Find the unique archive base for a large-scale backup phase."
    )
    parser.add_argument("--backup-dir", required=True, type=Path)
    parser.add_argument("--definition-name", required=True)
    parser.add_argument("--backup-type", required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Run archive discovery and write the unique basename to stdout.

    Args:
        argv: Optional argument sequence. Defaults to ``sys.argv``.

    Returns:
        Zero on success and one when archive discovery fails.
    """
    args = parse_args(argv)
    try:
        archive_base = find_archive_base(
            args.backup_dir,
            args.definition_name,
            args.backup_type,
        )
    except (FileNotFoundError, RuntimeError, ValueError) as error:
        LOGGER.error("Archive discovery failed: %s", error)
        return 1

    print(archive_base)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    raise SystemExit(main())
