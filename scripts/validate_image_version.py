#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Validate release and refresh image-version policies."""

from __future__ import annotations

import argparse
import logging
import re
from pathlib import Path


logging.basicConfig(level=logging.INFO, format="%(message)s")
LOGGER = logging.getLogger(__name__)

RELEASE_VERSION_PATTERN = re.compile(
    r"^[0-9]+\.[0-9]+\.[0-9]+(?:\.[0-9]+)?"
    r"(?:-[0-9A-Za-z]+(?:[.-][0-9A-Za-z]+)*)?$"
)
STABLE_VERSION_PATTERN = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")


def read_image_version(path: Path) -> str:
    """Read and validate one canonical image-version file.

    Args:
        path: File containing exactly one supported image version.

    Returns:
        Validated version without trailing line endings.

    Raises:
        OSError: If the version file cannot be read.
        ValueError: If its content is empty, padded, multiline, or malformed.
    """
    raw_value = path.read_text(encoding="utf-8")
    version = raw_value.rstrip("\r\n")
    if not version:
        raise ValueError(f"image version file is empty: {path}")
    if version != version.strip() or "\n" in version or "\r" in version:
        raise ValueError(f"image version file must contain one unpadded value: {path}")
    if not RELEASE_VERSION_PATTERN.fullmatch(version):
        raise ValueError(f"unsupported IMAGE_VERSION value: {version!r}")
    return version


def validate_release_version(image_version: str, final_version: str) -> None:
    """Require a release output version to equal canonical IMAGE_VERSION.

    Args:
        image_version: Validated canonical version from the source revision.
        final_version: Requested final image version.

    Raises:
        ValueError: If either value is invalid or they differ.
    """
    if not RELEASE_VERSION_PATTERN.fullmatch(image_version):
        raise ValueError(f"invalid canonical image version: {image_version!r}")
    if not RELEASE_VERSION_PATTERN.fullmatch(final_version):
        raise ValueError(f"invalid final release version: {final_version!r}")
    if final_version != image_version:
        raise ValueError(
            f"FINAL_VERSION {final_version!r} must equal IMAGE_VERSION {image_version!r}"
        )


def validate_refresh_version(
    base_version: str,
    final_version: str,
) -> None:
    """Require a refresh output to be a numeric form of its stable base.

    Args:
        base_version: Stable release tag selected by refresh orchestration.
        final_version: Requested refresh image version.

    Raises:
        ValueError: If the base is unstable or the final version is not
            ``BASE_VERSION-N`` with a positive unpadded integer.
    """
    if not STABLE_VERSION_PATTERN.fullmatch(base_version):
        raise ValueError(f"invalid refresh BASE_VERSION: {base_version!r}")
    refresh_pattern = re.compile(rf"^{re.escape(base_version)}-[1-9][0-9]*$")
    if not refresh_pattern.fullmatch(final_version):
        raise ValueError(
            f"refresh FINAL_VERSION {final_version!r} must match "
            f"{base_version!r} followed by '-N' where N is positive"
        )


def parse_args() -> argparse.Namespace:
    """Parse version-policy command-line arguments.

    Returns:
        Parsed command and version values.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="policy", required=True)

    release = subparsers.add_parser("release")
    release.add_argument("--image-version-file", required=True, type=Path)
    release.add_argument("--final-version", required=True)

    refresh = subparsers.add_parser("refresh")
    refresh.add_argument("--base-version", required=True)
    refresh.add_argument("--final-version", required=True)
    return parser.parse_args()


def main() -> int:
    """Validate the requested policy and report a concise diagnostic.

    Returns:
        Zero when the policy is satisfied, otherwise two.
    """
    arguments = parse_args()
    try:
        if arguments.policy == "release":
            image_version = read_image_version(arguments.image_version_file)
            validate_release_version(image_version, arguments.final_version)
            LOGGER.info("✅ Release version verified: %s", image_version)
            return 0
        validate_refresh_version(
            arguments.base_version,
            arguments.final_version,
        )
    except (OSError, ValueError) as error:
        LOGGER.error("ERROR: %s", error)
        return 2

    LOGGER.info(
        "✅ Refresh version verified: %s from base %s",
        arguments.final_version,
        arguments.base_version,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
