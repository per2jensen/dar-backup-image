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
    environment.pop("DAR_BACKUP_LOCK_DIR", None)
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


def test_entrypoint_default_lock_directory_is_private_and_exported(
    tmp_path: Path,
) -> None:
    """Create and export a private directory when no override is set.

    Args:
        tmp_path: Isolated pytest temporary directory.

    Returns:
        None.
    """
    environment = _entrypoint_environment(tmp_path, chown_exit_code=0)
    capture_path = tmp_path / "captured-lock-directory"
    setpriv_path = tmp_path / "bin" / "setpriv"
    _write_command(
        setpriv_path,
        "#!/bin/bash\n"
        f"printf '%s' \"$DAR_BACKUP_LOCK_DIR\" > {capture_path!s}\n"
        "exit 0\n",
    )

    result = subprocess.run(
        ["bash", str(ENTRYPOINT), "--full-backup"],
        cwd=REPOSITORY_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    expected_lock_directory = Path(environment["DAR_BACKUP_DIR"]) / ".dar-backup-locks"
    assert result.returncode == 0, result.stderr
    assert expected_lock_directory.is_dir()
    assert expected_lock_directory.stat().st_mode & 0o777 == 0o700
    assert capture_path.read_text(encoding="utf-8") == str(expected_lock_directory)


def test_entrypoint_default_lock_path_regular_file_is_fatal(tmp_path: Path) -> None:
    """Stop with context when the default lock path is not a directory.

    Args:
        tmp_path: Isolated pytest temporary directory.

    Returns:
        None.
    """
    environment = _entrypoint_environment(tmp_path, chown_exit_code=0)
    backup_directory = Path(environment["DAR_BACKUP_DIR"])
    backup_directory.mkdir()
    invalid_lock_path = backup_directory / ".dar-backup-locks"
    invalid_lock_path.write_text("not a directory\n", encoding="utf-8")

    result = subprocess.run(
        ["bash", str(ENTRYPOINT), "--full-backup"],
        cwd=REPOSITORY_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "default lock path is not a real directory" in result.stderr
    assert str(invalid_lock_path) in result.stderr


def test_entrypoint_explicit_lock_directory_is_preserved(tmp_path: Path) -> None:
    """Preserve an operator-provided lock directory unchanged.

    Args:
        tmp_path: Isolated pytest temporary directory.

    Returns:
        None.
    """
    environment = _entrypoint_environment(tmp_path, chown_exit_code=0)
    explicit_lock_directory = tmp_path / "operator-locks"
    explicit_lock_directory.mkdir()
    environment["DAR_BACKUP_LOCK_DIR"] = str(explicit_lock_directory)
    capture_path = tmp_path / "captured-lock-directory"
    setpriv_path = tmp_path / "bin" / "setpriv"
    _write_command(
        setpriv_path,
        "#!/bin/bash\n"
        f"printf '%s' \"$DAR_BACKUP_LOCK_DIR\" > {capture_path!s}\n"
        "exit 0\n",
    )

    result = subprocess.run(
        ["bash", str(ENTRYPOINT), "--full-backup"],
        cwd=REPOSITORY_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert capture_path.read_text(encoding="utf-8") == str(explicit_lock_directory)


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
    explicit_lock_directory = tmp_path / "operator-locks"
    explicit_lock_directory.mkdir()
    environment["DAR_BACKUP_LOCK_DIR"] = str(explicit_lock_directory)
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
