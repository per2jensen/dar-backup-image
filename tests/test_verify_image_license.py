"""Integration tests for the embedded image LICENSE checksum gate."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).parents[1]
VERIFIER = REPOSITORY_ROOT / "scripts" / "verify_image_license.sh"
EXPECTED_SHA256 = "3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986"


def _write_fake_docker(bin_dir: Path, license_sha256: str) -> None:
    """Create a Docker substitute that hashes a controlled image LICENSE.

    Args:
        bin_dir: Directory that will be prepended to ``PATH``.
        license_sha256: Digest the substitute should report for ``/LICENSE``.

    Returns:
        None.
    """
    bin_dir.mkdir()
    docker = bin_dir / "docker"
    docker.write_text(
        "#!/bin/bash\n"
        "set -euo pipefail\n"
        "if [[ \"$*\" != \"run --rm --entrypoint sha256sum test-image:1 /LICENSE\" ]]; then\n"
        "    >&2 echo \"unexpected docker arguments: $*\"\n"
        "    exit 3\n"
        "fi\n"
        f"printf '%s  /LICENSE\\n' '{license_sha256}'\n",
        encoding="utf-8",
    )
    docker.chmod(0o755)


def _run_verifier(tmp_path: Path, actual_sha256: str) -> subprocess.CompletedProcess[str]:
    """Run the real verifier with a controlled Docker checksum result.

    Args:
        tmp_path: Temporary directory owned by the test.
        actual_sha256: Digest the Docker substitute should return.

    Returns:
        Completed subprocess with captured output.
    """
    bin_dir = tmp_path / "bin"
    _write_fake_docker(bin_dir, actual_sha256)
    environment = os.environ.copy()
    environment["PATH"] = f"{bin_dir}:{environment['PATH']}"
    return subprocess.run(
        ["bash", str(VERIFIER), "test-image:1", EXPECTED_SHA256],
        cwd=REPOSITORY_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )


def test_verify_image_license_matching_sha256_succeeds(tmp_path: Path) -> None:
    """An image containing the expected LICENSE passes the checksum gate."""
    result = _run_verifier(tmp_path, EXPECTED_SHA256)

    assert result.returncode == 0, result.stderr
    assert "Embedded /LICENSE SHA-256 verified" in result.stdout
    assert EXPECTED_SHA256 in result.stdout


def test_verify_image_license_mismatched_sha256_fails(tmp_path: Path) -> None:
    """An image containing different LICENSE bytes fails before publication."""
    actual_sha256 = "0" * 64

    result = _run_verifier(tmp_path, actual_sha256)

    assert result.returncode == 2
    assert "/LICENSE SHA-256 mismatch" in result.stderr
    assert f"expected: '{EXPECTED_SHA256}'" in result.stderr
    assert f"actual:   '{actual_sha256}'" in result.stderr
