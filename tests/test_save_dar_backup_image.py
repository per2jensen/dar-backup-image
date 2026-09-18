# SPDX-FileCopyrightText: 2025-2026 Per Jensen
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This file is part of dar-backup-image:
# https://github.com/per2jensen/dar-backup-image
#
# License terms and warranty disclaimer:
# https://github.com/per2jensen/dar-backup-image/blob/main/LICENSE

"""Contract tests for atomic Docker image archive creation."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).parents[1]
SCRIPT = REPOSITORY_ROOT / "scripts" / "save-dar-backup-image.sh"
VERSION = "1.0.0"


def _write_fake_commands(bin_dir: Path, save_exit_code: int) -> None:
    """Create deterministic curl and Docker substitutes.

    Args:
        bin_dir: Directory prepended to ``PATH``.
        save_exit_code: Status returned after Docker emits archive bytes.

    Returns:
        None.
    """
    bin_dir.mkdir()
    curl = bin_dir / "curl"
    curl.write_text(
        "#!/bin/bash\n"
        f"printf '[{{\"build_number\":1,\"tag\":\"{VERSION}\","
        "\"created\":\"2026-09-18T00:00:00Z\"}]\\n'\n",
        encoding="utf-8",
    )
    curl.chmod(0o755)

    docker = bin_dir / "docker"
    docker.write_text(
        "#!/bin/bash\n"
        "set -euo pipefail\n"
        "case \"$1\" in\n"
        "  pull) exit 0 ;;\n"
        f"  save) printf 'docker image archive bytes'; exit {save_exit_code} ;;\n"
        "  *) echo \"unexpected docker arguments: $*\" >&2; exit 3 ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    docker.chmod(0o755)


def _run_archive_script(
    tmp_path: Path,
    save_exit_code: int,
) -> tuple[subprocess.CompletedProcess[str], Path]:
    """Run the archive helper with controlled external commands.

    Args:
        tmp_path: Isolated pytest temporary directory.
        save_exit_code: Status returned by the fake Docker save.

    Returns:
        Captured process and archive directory.
    """
    bin_dir = tmp_path / "bin"
    archive_dir = tmp_path / "archives"
    _write_fake_commands(bin_dir, save_exit_code)
    environment = os.environ.copy()
    environment["PATH"] = f"{bin_dir}:{environment['PATH']}"
    environment["DOCKER_ARCHIVE_DIR"] = str(archive_dir)
    result = subprocess.run(
        [str(SCRIPT)],
        cwd=REPOSITORY_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    return result, archive_dir


def test_save_image_publishes_valid_archive_and_checksum(tmp_path: Path) -> None:
    """A complete Docker save is atomically published with valid checksum."""
    result, archive_dir = _run_archive_script(tmp_path, save_exit_code=0)
    archive = archive_dir / f"dar-backup-{VERSION}-docker-image.tar.gz"
    checksum = archive_dir / f"{archive.name}.sha256"

    assert result.returncode == 0, result.stdout + result.stderr
    assert archive.is_file()
    assert checksum.is_file()
    assert "Saved and verified" in result.stdout
    verification = subprocess.run(
        ["sha256sum", "-c", checksum.name],
        cwd=archive_dir,
        check=False,
        capture_output=True,
        text=True,
    )
    assert verification.returncode == 0, verification.stderr


def test_save_image_failure_leaves_no_published_archive(tmp_path: Path) -> None:
    """A partial Docker save fails and cannot masquerade as a valid archive."""
    result, archive_dir = _run_archive_script(tmp_path, save_exit_code=9)
    archive = archive_dir / f"dar-backup-{VERSION}-docker-image.tar.gz"

    assert result.returncode != 0
    assert "no archive was published" in result.stdout
    assert not archive.exists()
    assert not Path(f"{archive}.sha256").exists()
    assert list(archive_dir.glob(".dar-backup-*")) == []
