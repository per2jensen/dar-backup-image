# SPDX-FileCopyrightText: 2025-2026 Per Jensen
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This file is part of dar-backup-image:
# https://github.com/per2jensen/dar-backup-image
#
# License terms and warranty disclaimer:
# https://github.com/per2jensen/dar-backup-image/blob/main/LICENSE

"""End-to-end tests for manager numeric ownership restoration."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


BACKUP_SCRIPT = Path(__file__).parents[1] / "scripts" / "run-backup.sh"
DEFAULT_CONFIG = "/etc/dar-backup/dar-backup.conf"


def _run_container(
    image: str, docker_arguments: list[str], command_arguments: list[str]
) -> subprocess.CompletedProcess[str]:
    """Run a Docker command and capture its diagnostic output.

    Args:
        image: Docker image containing dar-backup and manager.
        docker_arguments: Docker runtime arguments placed before the image.
        command_arguments: Entrypoint arguments placed after the image.

    Returns:
        Completed Docker subprocess.
    """
    return subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            *docker_arguments,
            image,
            *command_arguments,
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def _alternate_gid() -> int:
    """Choose a valid numeric GID different from the invoking primary GID.

    Returns:
        Deterministic non-primary GID for the ownership fixture.
    """
    primary_gid = os.getgid()
    return 4 if primary_gid != 4 else 5


def _prepare_tiny_archive(
    test_env: dict[str, str], image: str
) -> tuple[Path, int]:
    """Create a one-file archive whose file has an alternate numeric GID.

    Args:
        test_env: Isolated backup-test directories and environment variables.
        image: Docker image containing dar-backup and manager.

    Returns:
        Source file path and its deliberately selected numeric GID.

    Raises:
        AssertionError: If fixture ownership, database creation, or backup fails.
    """
    source_file = Path(test_env["DAR_BACKUP_DATA_DIR"]) / "ownership.txt"
    source_file.write_text("numeric ownership smoke test\n", encoding="utf-8")
    expected_gid = _alternate_gid()

    chown_result = _run_container(
        image,
        [
            "--user",
            "0:0",
            "-v",
            f"{source_file.parent}:/data",
            "--entrypoint",
            "/bin/chown",
        ],
        [
            f"{os.getuid()}:{expected_gid}",
            "/data/ownership.txt",
        ],
    )
    assert chown_result.returncode == 0, chown_result.stderr
    assert source_file.stat().st_gid == expected_gid

    database_result = _run_container(
        image,
        [
            "--user",
            f"{os.getuid()}:{os.getgid()}",
            "-v",
            f"{test_env['DAR_BACKUP_DIR']}:/backups",
            "-v",
            f"{test_env['DAR_BACKUP_D_DIR']}:/backup.d",
            "--entrypoint",
            "/opt/venv/bin/manager",
        ],
        [
            "--create-db",
            "--config-file",
            DEFAULT_CONFIG,
            "--log-stdout",
        ],
    )
    assert database_result.returncode == 0, database_result.stderr

    environment = os.environ.copy()
    environment.update(test_env)
    environment["RUN_AS_GID"] = str(os.getgid())
    backup_result = subprocess.run(
        [str(BACKUP_SCRIPT), "-t", "FULL"],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert backup_result.returncode == 0, backup_result.stderr
    return source_file, expected_gid


def _restore_with_manager(
    test_env: dict[str, str], image: str, *, as_root: bool
) -> tuple[subprocess.CompletedProcess[str], Path]:
    """Restore the tiny archive through manager with ownership preservation.

    Args:
        test_env: Isolated backup-test directories and environment variables.
        image: Docker image containing dar-backup and manager.
        as_root: Whether manager and its DAR children run with UID/GID zero.

    Returns:
        Completed manager process and expected restored fixture path.
    """
    target = Path(test_env["WORKDIR"]) / (
        "restore-root" if as_root else "restore-unprivileged"
    )
    target.mkdir()
    if as_root:
        chown_result = _run_container(
            image,
            [
                "--user",
                "0:0",
                "-v",
                f"{target.parent}:/workdir",
                "--entrypoint",
                "/bin/chown",
            ],
            ["0:0", f"/workdir/{target.name}"],
        )
        if chown_result.returncode != 0:
            return chown_result, target / "ownership.txt"
    docker_arguments = [
        "--user",
        "0:0" if as_root else f"{os.getuid()}:{os.getgid()}",
        "-e",
        "HOME=/tmp",
        "-v",
        f"{test_env['DAR_BACKUP_DIR']}:/backups",
        "-v",
        f"{test_env['DAR_BACKUP_D_DIR']}:/backup.d",
        "-v",
        f"{target}:/restore",
        "--entrypoint",
        "/opt/venv/bin/manager",
    ]
    command_arguments = [
        "--config-file",
        DEFAULT_CONFIG,
        "--backup-def",
        "default",
        "--restore-path",
        "ownership.txt",
        "--when",
        "now",
        "--target",
        "/restore",
        "--preserve-ownership",
        "--log-stdout",
        "--verbose",
    ]
    result = _run_container(image, docker_arguments, command_arguments)
    return result, target / "ownership.txt"


def test_manager_root_restore_preserves_alternate_numeric_gid(
    test_env: dict[str, str], image: str
) -> None:
    """A root PITR extraction preserves the archived numeric UID and GID.

    Args:
        test_env: Isolated backup-test directories and environment variables.
        image: Docker image containing dar-backup and manager.
    """
    source_file, expected_gid = _prepare_tiny_archive(test_env, image)

    result, restored_file = _restore_with_manager(test_env, image, as_root=True)

    assert result.returncode == 0, result.stderr
    assert restored_file.read_bytes() == source_file.read_bytes()
    restored_stat = restored_file.stat()
    assert restored_stat.st_uid == source_file.stat().st_uid
    assert restored_stat.st_gid == expected_gid


def test_manager_unprivileged_restore_cannot_preserve_alternate_numeric_gid(
    test_env: dict[str, str], image: str
) -> None:
    """An unprivileged PITR extraction cannot satisfy exact ownership.

    Args:
        test_env: Isolated backup-test directories and environment variables.
        image: Docker image containing dar-backup and manager.
    """
    _, expected_gid = _prepare_tiny_archive(test_env, image)

    result, restored_file = _restore_with_manager(test_env, image, as_root=False)

    if result.returncode == 0:
        assert restored_file.stat().st_gid != expected_gid
        return
    assert "owner" in (result.stdout + result.stderr).lower()
