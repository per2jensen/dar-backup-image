#!/usr/bin/env python3
"""Validate a local dar-backup wheel before a Docker build."""

from __future__ import annotations

import argparse
import hashlib
import logging
import re
import sys
import zipfile
from dataclasses import dataclass
from email import policy
from email.parser import BytesParser
from pathlib import Path, PurePosixPath
from typing import Sequence


LOGGER = logging.getLogger("validate-dar-backup-wheel")
EXPECTED_PROJECT_NAME = "dar-backup"


@dataclass(frozen=True)
class WheelDetails:
    """Validated identity and digest of a wheel.

    Attributes:
        path: Resolved path to the wheel.
        project_name: Normalized project name from Core Metadata.
        version: Version from Core Metadata.
        sha256: Lowercase hexadecimal SHA-256 digest.
    """

    path: Path
    project_name: str
    version: str
    sha256: str


def _canonical_project_name(name: str) -> str:
    """Normalize a Python distribution name for comparison.

    Args:
        name: Distribution name from Core Metadata.

    Returns:
        PEP 503-style normalized project name.
    """
    return re.sub(r"[-_.]+", "-", name).lower()


def _sha256_file(path: Path) -> str:
    """Calculate the SHA-256 digest of a regular file.

    Args:
        path: File to hash.

    Returns:
        Lowercase hexadecimal SHA-256 digest.

    Raises:
        OSError: If the file cannot be read.
    """
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _find_metadata_member(archive: zipfile.ZipFile) -> str:
    """Find the wheel's single safe dist-info METADATA member.

    Args:
        archive: Open wheel ZIP archive.

    Returns:
        Path of the unique METADATA member inside the archive.

    Raises:
        ValueError: If METADATA is missing, duplicated, or has an unsafe path.
    """
    metadata_members: list[str] = []
    for member_name in archive.namelist():
        member_path = PurePosixPath(member_name)
        if member_path.is_absolute() or ".." in member_path.parts:
            raise ValueError(f"Wheel contains an unsafe path: {member_name!r}")
        if (
            len(member_path.parts) == 2
            and member_path.parts[0].endswith(".dist-info")
            and member_path.parts[1] == "METADATA"
        ):
            metadata_members.append(member_name)

    if len(metadata_members) != 1:
        raise ValueError(
            "Wheel must contain exactly one top-level .dist-info/METADATA file; "
            f"found {len(metadata_members)}"
        )
    return metadata_members[0]


def validate_wheel(wheel_path: Path, expected_version: str) -> WheelDetails:
    """Validate a local dar-backup wheel and return its provenance.

    Args:
        wheel_path: Path to the candidate wheel.
        expected_version: Required dar-backup version.

    Returns:
        Validated wheel identity and digest.

    Raises:
        OSError: If the wheel cannot be read.
        ValueError: If an input or wheel metadata is invalid.
        zipfile.BadZipFile: If the wheel is not a valid ZIP archive.
    """
    if not isinstance(wheel_path, Path):
        raise ValueError("wheel_path must be a pathlib.Path")
    if not isinstance(expected_version, str) or not expected_version.strip():
        raise ValueError("expected_version must be a non-empty string")
    if wheel_path.suffix != ".whl":
        raise ValueError(f"Local package must be a .whl file: {wheel_path}")
    if not wheel_path.is_file():
        raise ValueError(f"Local wheel is not a regular file: {wheel_path}")

    resolved_path = wheel_path.resolve(strict=True)
    with zipfile.ZipFile(resolved_path, mode="r") as archive:
        metadata_member = _find_metadata_member(archive)
        metadata = BytesParser(policy=policy.default).parsebytes(
            archive.read(metadata_member)
        )

    project_name = str(metadata.get("Name", "")).strip()
    version = str(metadata.get("Version", "")).strip()
    if _canonical_project_name(project_name) != EXPECTED_PROJECT_NAME:
        raise ValueError(
            f"Wheel project is {project_name!r}, expected {EXPECTED_PROJECT_NAME!r}"
        )
    if version != expected_version:
        raise ValueError(
            f"Wheel version {version!r} does not match DAR_BACKUP_VERSION "
            f"{expected_version!r}"
        )

    return WheelDetails(
        path=resolved_path,
        project_name=EXPECTED_PROJECT_NAME,
        version=version,
        sha256=_sha256_file(resolved_path),
    )


def _build_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser.

    Returns:
        Configured argument parser.
    """
    parser = argparse.ArgumentParser(
        description="Validate a local dar-backup wheel and print its SHA-256"
    )
    parser.add_argument("--wheel", required=True, type=Path)
    parser.add_argument("--expected-version", required=True)
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    """Validate command-line inputs and print the wheel SHA-256.

    Args:
        arguments: Optional command-line arguments excluding the program name.

    Returns:
        Zero on success and two for an invalid wheel.
    """
    parser = _build_parser()
    parsed = parser.parse_args(arguments)
    try:
        details = validate_wheel(parsed.wheel, parsed.expected_version)
    except (OSError, ValueError, zipfile.BadZipFile) as error:
        LOGGER.error("Local dar-backup wheel validation failed: %s", error)
        return 2

    sys.stdout.write(f"{details.sha256}\n")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    raise SystemExit(main())
