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

"""Validate repository-specific copyright and license header policy."""

from __future__ import annotations

import argparse
import logging
import subprocess
from collections.abc import Sequence
from pathlib import Path


LOGGER = logging.getLogger(__name__)
REPOSITORY_URL = "https://github.com/per2jensen/dar-backup-image"
LICENSE_URLS = {
    "GPL-3.0-or-later": f"{REPOSITORY_URL}/blob/main/LICENSE",
    "MIT": f"{REPOSITORY_URL}/blob/main/LICENSES/MIT.txt",
}
COMMENTABLE_SUFFIXES = frozenset({".md", ".py", ".sh", ".yaml", ".yml"})
COMMENTABLE_NAMES = frozenset(
    {
        ".dockerignore",
        ".gitignore",
        "Dockerfile",
        "Makefile",
        "anchore-tool-versions.env",
        "dar-backup.conf",
        "default",
        "index.template.html",
        "requirements.txt",
    }
)


def _is_commentable_file(relative_path: Path, size_bytes: int) -> bool:
    """Return whether a tracked file must contain an embedded header.

    Args:
        relative_path: File path relative to the repository root.
        size_bytes: Current file size in bytes.

    Returns:
        True when the repository policy requires an embedded header.

    Raises:
        ValueError: If the path is absolute or the size is negative.
    """
    if relative_path.is_absolute():
        raise ValueError("relative_path must not be absolute")
    if size_bytes < 0:
        raise ValueError("size_bytes must not be negative")
    if size_bytes == 0:
        return False
    if relative_path.parts[0] in {".reuse", "LICENSES", "src"}:
        return relative_path.parts[:2] == ("src", "clonepulse")
    if relative_path.suffix in COMMENTABLE_SUFFIXES:
        return True
    return relative_path.name in COMMENTABLE_NAMES


def _expected_license(relative_path: Path) -> str:
    """Return the expected SPDX licence for a commentable file.

    Args:
        relative_path: File path relative to the repository root.

    Returns:
        ``MIT`` for Clonepulse files and ``GPL-3.0-or-later`` otherwise.

    Raises:
        ValueError: If the path is absolute.
    """
    if relative_path.is_absolute():
        raise ValueError("relative_path must not be absolute")
    if relative_path.parts[0] == "clonepulse":
        return "MIT"
    if relative_path.parts[:2] == ("src", "clonepulse"):
        return "MIT"
    return "GPL-3.0-or-later"


def _list_repository_files(repository_root: Path) -> list[Path]:
    """List tracked and untracked non-ignored repository files.

    Args:
        repository_root: Existing Git working tree root.

    Returns:
        Sorted paths relative to ``repository_root``.

    Raises:
        ValueError: If ``repository_root`` is not a directory.
        subprocess.CalledProcessError: If Git cannot enumerate the files.
    """
    if not isinstance(repository_root, Path):
        raise ValueError("repository_root must be a pathlib.Path")
    if not repository_root.is_dir():
        raise ValueError(f"repository root is not a directory: {repository_root}")
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=repository_root,
        check=True,
        capture_output=True,
    )
    paths = [
        Path(raw_path.decode("utf-8"))
        for raw_path in result.stdout.split(b"\0")
        if raw_path
    ]
    return sorted(paths)


def validate_license_header(
    file_path: Path, relative_path: Path, expected_license: str
) -> None:
    """Validate one embedded repository license header.

    Args:
        file_path: Existing UTF-8 text file to validate.
        relative_path: File path used in diagnostics.
        expected_license: Required SPDX licence identifier.

    Returns:
        None.

    Raises:
        OSError: If the file cannot be read.
        ValueError: If inputs or the header are invalid.
    """
    if not isinstance(file_path, Path):
        raise ValueError("file_path must be a pathlib.Path")
    if not isinstance(relative_path, Path) or relative_path.is_absolute():
        raise ValueError("relative_path must be a relative pathlib.Path")
    if expected_license not in LICENSE_URLS:
        raise ValueError(f"unsupported expected license: {expected_license!r}")
    if not file_path.is_file():
        raise ValueError(f"license-header target is not a file: {file_path}")

    header = "\n".join(file_path.read_text(encoding="utf-8").splitlines()[:30])
    # REUSE scans literal tag examples as declarations unless they are explicitly
    # excluded; these strings are validator inputs, not this file's licensing data.
    # REUSE-IgnoreStart
    required_fragments = (
        "SPDX-FileCopyrightText:",
        f"SPDX-License-Identifier: {expected_license}",
        REPOSITORY_URL,
        LICENSE_URLS[expected_license],
    )
    # REUSE-IgnoreEnd
    missing = [fragment for fragment in required_fragments if fragment not in header]
    if missing:
        raise ValueError(
            f"{relative_path} has an incomplete {expected_license} header; "
            f"missing: {', '.join(missing)}"
        )


def validate_repository(repository_root: Path) -> int:
    """Validate every commentable file selected by repository policy.

    Args:
        repository_root: Existing Git working tree root.

    Returns:
        Number of validated commentable files.

    Raises:
        OSError: If a selected file cannot be inspected.
        ValueError: If a selected file has invalid licensing information.
        subprocess.CalledProcessError: If Git cannot enumerate repository files.
    """
    if not isinstance(repository_root, Path):
        raise ValueError("repository_root must be a pathlib.Path")

    validated_count = 0
    errors: list[str] = []
    for relative_path in _list_repository_files(repository_root):
        file_path = repository_root / relative_path
        try:
            size_bytes = file_path.stat().st_size
            if not _is_commentable_file(relative_path, size_bytes):
                continue
            validate_license_header(
                file_path,
                relative_path,
                _expected_license(relative_path),
            )
        except (OSError, ValueError) as error:
            errors.append(str(error))
            continue
        validated_count += 1

    if errors:
        raise ValueError("license header validation failed:\n" + "\n".join(errors))
    if validated_count == 0:
        raise ValueError("repository contains no commentable files to validate")
    return validated_count


def parse_args(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse license-header validator arguments.

    Args:
        arguments: Optional arguments excluding the executable name.

    Returns:
        Parsed command-line namespace.

    Raises:
        SystemExit: If argparse rejects the command line.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    return parser.parse_args(arguments)


def main(arguments: Sequence[str] | None = None) -> int:
    """Validate repository headers from command-line arguments.

    Args:
        arguments: Optional arguments excluding the executable name.

    Returns:
        Zero on success and two when validation fails.

    Raises:
        SystemExit: Only when argparse rejects the command line.
    """
    args = parse_args(arguments)
    try:
        validated_count = validate_repository(args.root.resolve())
    except (OSError, UnicodeError, ValueError, subprocess.CalledProcessError) as error:
        LOGGER.error("Unable to validate repository license headers: %s", error)
        return 2
    LOGGER.info("Validated license headers in %d files", validated_count)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    raise SystemExit(main())
