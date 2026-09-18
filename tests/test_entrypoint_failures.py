# SPDX-FileCopyrightText: 2025-2026 Per Jensen
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This file is part of dar-backup-image:
# https://github.com/per2jensen/dar-backup-image
#
# License terms and warranty disclaimer:
# https://github.com/per2jensen/dar-backup-image/blob/main/LICENSE

"""Subprocess tests for entrypoint permission preparation results."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).parents[1]
ENTRYPOINT = REPOSITORY_ROOT / "entrypoint.sh"


def _write_command(path: Path, content: str) -> None:
    """Write an executable command substitute.

    Args:
        path: Destination executable path.
        content: Complete shell script.

    Returns:
        None.
    """
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def _entrypoint_environment(
    tmp_path: Path,
    *,
    chown_exit_code: int,
) -> dict[str, str]:
    """Create a root-like environment with controlled ownership behavior.

    Args:
        tmp_path: Isolated pytest temporary directory.
        chown_exit_code: Status returned by fake ``chown``.

    Returns:
        Environment for invoking the real entrypoint.
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_command(
        bin_dir / "id",
        "#!/bin/bash\n"
        "case \"$1\" in -u|-g) printf '0\\n' ;; *) exit 2 ;; esac\n",
    )
    _write_command(
        bin_dir / "chown",
        "#!/bin/bash\n"
        f"exit {chown_exit_code}\n",
    )
    _write_command(bin_dir / "setpriv", "#!/bin/bash\nexit 0\n")

    config = tmp_path / "dar-backup.conf"
    config.write_text("# test config\n", encoding="utf-8")
    environment = os.environ.copy()
    environment.update(
        {
            "PATH": f"{bin_dir}:{environment['PATH']}",
            "DAR_BACKUP_CONFIG": str(config),
            "DAR_BACKUP_DIR": str(tmp_path / "backups"),
            "DAR_BACKUP_D_DIR": str(tmp_path / "backup.d"),
            "DAR_BACKUP_DATA_DIR": str(tmp_path / "data"),
            "DAR_BACKUP_RESTORE_DIR": str(tmp_path / "restore"),
            "DAR_BACKUP_FIX_PERMS": "1",
            "RUN_AS_UID": "1000",
            "RUN_AS_GID": "1000",
        }
    )
    return environment


def test_entrypoint_requested_ownership_change_succeeds(tmp_path: Path) -> None:
    """Requested ownership preparation reports completion before execution."""
    result = subprocess.run(
        ["bash", str(ENTRYPOINT), "--full-backup"],
        cwd=REPOSITORY_ROOT,
        env=_entrypoint_environment(tmp_path, chown_exit_code=0),
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "Directory permissions prepared for UID 1000 / GID 1000" in result.stdout


def test_entrypoint_requested_ownership_change_failure_is_fatal(
    tmp_path: Path,
) -> None:
    """A requested chown failure names the path and cannot be ignored."""
    environment = _entrypoint_environment(tmp_path, chown_exit_code=19)
    result = subprocess.run(
        ["bash", str(ENTRYPOINT), "--full-backup"],
        cwd=REPOSITORY_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "unable to set ownership" in result.stderr
    assert environment["DAR_BACKUP_DIR"] in result.stderr
    assert "UID 1000 / GID 1000" in result.stderr
