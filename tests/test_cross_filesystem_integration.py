# SPDX-FileCopyrightText: 2025-2026 Per Jensen
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This file is part of dar-backup-image:
# https://github.com/per2jensen/dar-backup-image
#
# License terms and warranty disclaimer:
# https://github.com/per2jensen/dar-backup-image/blob/main/LICENSE

"""Opt-in Docker tests for the host Btrfs/ZFS integration harness."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile

import pytest


RUNNER_PATH = Path(__file__).parents[1] / "run_cross_filesystem_test.sh"
INTEGRATION_ENABLED = os.environ.get("RUN_CROSS_FILESYSTEM_INTEGRATION") == "1"
pytestmark = pytest.mark.skipif(
    not INTEGRATION_ENABLED,
    reason="set RUN_CROSS_FILESYSTEM_INTEGRATION=1 on the Btrfs/ZFS host",
)


def _run(*arguments: str) -> subprocess.CompletedProcess[str]:
    """Run one real cross-filesystem integration scenario.

    Args:
        *arguments: Runner command-line arguments.

    Returns:
        Completed harness process.
    """
    image = os.environ.get("IMAGE", "dar-backup:dev")
    return subprocess.run(
        [str(RUNNER_PATH), "--image", image, "--slice", "100M", *arguments],
        check=False,
        capture_output=True,
        text=True,
        timeout=86_400,
    )


def _acl_value(user_id: int) -> bytes:
    """Build a valid Linux POSIX access ACL for an integration fixture.

    Args:
        user_id: Numeric named-user ID.

    Returns:
        Binary ACL xattr accepted by Linux Btrfs and ZFS.
    """
    undefined_id = 0xFFFFFFFF
    entries = (
        (0x01, 0o6, undefined_id),
        (0x02, 0o4, user_id),
        (0x04, 0o4, undefined_id),
        (0x10, 0o4, undefined_id),
        (0x20, 0o0, undefined_id),
    )
    return struct.pack("<I", 2) + b"".join(
        struct.pack("<HHI", tag, permissions, identifier)
        for tag, permissions, identifier in entries
    )


def test_cross_filesystem_integration_pj_etc_denial_passes() -> None:
    """The real non-root `/etc` result is classified without ambiguity."""
    result = _run("--scenario", "etc-to-home", "--backup-user", "pj")

    results_path = Path(
        "/data/tmp/dar-backup-cross-filesystem-test/results/"
        "cross-filesystem-results.jsonl"
    )
    record = json.loads(
        results_path.read_text(encoding="utf-8").splitlines()[-1]
    )
    etc_result = record["scenarios"]["etc_to_home"]
    assert etc_result["observed_backup_outcome"] in {
        "permission_denied",
        "failure",
    }
    if result.returncode == 0:
        assert etc_result["status"] == "passed"
    else:
        assert etc_result["failure_reason"] == "usable_archive_from_denied_source"


def test_cross_filesystem_integration_root_etc_round_trip_passes() -> None:
    """A root `/etc` archive survives ZFS storage and Btrfs restoration."""
    result = _run("--scenario", "etc-to-home", "--backup-user", "root")

    assert result.returncode == 0, result.stdout + result.stderr


def test_cross_filesystem_integration_pj_home_round_trip_passes() -> None:
    """Selected Btrfs home data restores with metadata onto ZFS."""
    source = Path(
        tempfile.mkdtemp(prefix="cross-filesystem-source-", dir="/home/pj/tmp")
    )
    try:
        payload = source / "payload.txt"
        payload.write_text("cross-filesystem\n", encoding="utf-8")
        os.chmod(payload, 0o640)
        os.link(payload, source / "payload-hardlink.txt")
        (source / "payload-link.txt").symlink_to("payload.txt")
        os.setxattr(payload, "user.cross-filesystem-test", b"portable\x00metadata")
        os.setxattr(payload, "system.posix_acl_access", _acl_value(os.getuid()))
        result = _run(
            "--scenario",
            "home-to-data",
            "--backup-user",
            "pj",
            "--home-source",
            str(source),
            "--dataset-id",
            "pytest-fixture",
        )
    finally:
        shutil.rmtree(source)

    assert result.returncode == 0, result.stdout + result.stderr
