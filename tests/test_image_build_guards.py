# SPDX-FileCopyrightText: 2025-2026 Per Jensen
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This file is part of dar-backup-image:
# https://github.com/per2jensen/dar-backup-image
#
# License terms and warranty disclaimer:
# https://github.com/per2jensen/dar-backup-image/blob/main/LICENSE

"""Subprocess tests for immutable base and image metadata build guards."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).parents[1]
RESOLVE_DIGEST = REPOSITORY_ROOT / "scripts" / "resolve_ubuntu_digest.sh"
VERIFY_METADATA = REPOSITORY_ROOT / "scripts" / "verify_image_metadata.sh"
REVISION = "1" * 40
UBUNTU_DIGEST = "sha256:" + "2" * 64


def _write_executable(path: Path, content: str) -> None:
    """Write an executable test substitute.

    Args:
        path: Destination command path.
        content: Complete script text.

    Returns:
        None.
    """
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def test_resolve_ubuntu_digest_reports_canonical_pulled_digest(
    tmp_path: Path,
) -> None:
    """A successful pull and inspect returns the canonical Ubuntu digest."""
    fake_docker = tmp_path / "fake-docker"
    _write_executable(
        fake_docker,
        "#!/bin/bash\n"
        "set -euo pipefail\n"
        "if [[ \"$1\" == pull ]]; then exit 0; fi\n"
        "if [[ \"$1 $2\" == 'image inspect' ]]; then\n"
        f"  printf 'ubuntu@{UBUNTU_DIGEST}\\n'\n"
        "  exit 0\n"
        "fi\n"
        "echo \"unexpected arguments: $*\" >&2\n"
        "exit 3\n",
    )

    result = subprocess.run(
        [str(RESOLVE_DIGEST), str(fake_docker), "ubuntu:24.04", ""],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == UBUNTU_DIGEST
    assert f"Resolved ubuntu:24.04 to {UBUNTU_DIGEST}" in result.stderr


def test_resolve_ubuntu_digest_missing_repo_digest_fails(tmp_path: Path) -> None:
    """An inspect result without the canonical Ubuntu digest fails clearly."""
    fake_docker = tmp_path / "fake-docker"
    _write_executable(
        fake_docker,
        "#!/bin/bash\n"
        "set -euo pipefail\n"
        "if [[ \"$1\" == pull ]]; then exit 0; fi\n"
        "printf 'mirror.example/ubuntu@sha256:%064d\\n' 0\n",
    )

    result = subprocess.run(
        [str(RESOLVE_DIGEST), str(fake_docker), "ubuntu:24.04", ""],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "has no canonical ubuntu@sha256 repository digest" in result.stderr
    assert result.stdout == ""


def _metadata_environment(tmp_path: Path, version: str) -> dict[str, str]:
    """Create a label-serving Docker substitute and its environment.

    Args:
        tmp_path: Isolated pytest temporary directory.
        version: Image version returned by the substitute.

    Returns:
        Environment selecting the substitute through ``DOCKER``.
    """
    fake_docker = tmp_path / "fake-docker"
    labels = {
        "org.opencontainers.image.revision": REVISION,
        "org.opencontainers.image.version": version,
        "org.opencontainers.image.ref.name": "per2jensen/dar-backup:1.0.0",
        "org.opencontainers.image.base.digest": UBUNTU_DIGEST,
        "org.opencontainers.image.licenses": "GPL-3.0-or-later",
        "org.dar-backup.install-source": "pypi",
        "org.dar-backup.version": "1.1.11",
        "org.dar-backup.wheel.sha256": "not-applicable",
        "org.dar.version": "2.7.21",
    }
    cases = "\n".join(
        f'  {label!r}) printf \'%s\\n\' {value!r} ;;'
        for label, value in labels.items()
    )
    _write_executable(
        fake_docker,
        "#!/bin/bash\n"
        "set -euo pipefail\n"
        "format=\"$4\"\n"
        "label=\"${format#*\\\"}\"\n"
        "label=\"${label%%\\\"*}\"\n"
        "case \"${label}\" in\n"
        f"{cases}\n"
        "  *) echo \"unexpected label: ${label}\" >&2; exit 3 ;;\n"
        "esac\n",
    )
    environment = os.environ.copy()
    environment["DOCKER"] = str(fake_docker)
    return environment


def _run_metadata_verifier(
    tmp_path: Path,
    *,
    actual_version: str,
) -> subprocess.CompletedProcess[str]:
    """Run metadata verification against controlled image labels.

    Args:
        tmp_path: Isolated pytest temporary directory.
        actual_version: Version label emitted by fake Docker.

    Returns:
        Captured verifier process.
    """
    return subprocess.run(
        [
            str(VERIFY_METADATA),
            "dar-backup:1.0.0",
            REVISION,
            "1.0.0",
            "1.1.11",
            "2.7.21",
            UBUNTU_DIGEST,
            "pypi",
            "not-applicable",
        ],
        cwd=REPOSITORY_ROOT,
        env=_metadata_environment(tmp_path, actual_version),
        check=False,
        capture_output=True,
        text=True,
    )


def test_verify_image_metadata_exact_labels_succeed(tmp_path: Path) -> None:
    """A final image whose identity labels all match is accepted."""
    result = _run_metadata_verifier(tmp_path, actual_version="1.0.0")

    assert result.returncode == 0, result.stderr
    assert "Image metadata verified for dar-backup:1.0.0" in result.stdout


def test_verify_image_metadata_version_mismatch_fails(tmp_path: Path) -> None:
    """A stale image version label is rejected with expected and actual values."""
    result = _run_metadata_verifier(tmp_path, actual_version="0.9.1")

    assert result.returncode == 2
    assert "org.opencontainers.image.version mismatch" in result.stderr
    assert "expected: '1.0.0'" in result.stderr
    assert "actual:   '0.9.1'" in result.stderr
