"""Tests for the Docker layer size report."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "size-report.sh"


def test_size_report_converts_docker_units_as_decimal_si(tmp_path: Path) -> None:
    """Docker GB, MB, and kB values are normalized to decimal MB.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    executable_dir = tmp_path / "bin"
    executable_dir.mkdir()
    docker_path = executable_dir / "docker"
    docker_path.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "printf '%s\\n' "
        "'{\"Size\":\"500MB\",\"CreatedBy\":\"medium layer\"}' "
        "'{\"Size\":\"1GB\",\"CreatedBy\":\"large layer\"}' "
        "'{\"Size\":\"100kB\",\"CreatedBy\":\"small layer\"}' "
        "'{\"Size\":\"1B\",\"CreatedBy\":\"filtered layer\"}'\n",
        encoding="utf-8",
    )
    docker_path.chmod(0o755)
    environment = dict(os.environ)
    environment["PATH"] = f"{executable_dir}:{environment['PATH']}"

    result = subprocess.run(
        [str(SCRIPT_PATH), "example:test"],
        check=True,
        capture_output=True,
        env=environment,
        text=True,
    )

    assert "1000 MB" in result.stdout
    assert "500 MB" in result.stdout
    assert "0.1 MB" in result.stdout
    assert "filtered layer" not in result.stdout
    assert result.stdout.index("large layer") < result.stdout.index("medium layer")


def test_size_report_missing_image_fails_with_clear_error() -> None:
    """An omitted image reference fails before invoking Docker."""
    result = subprocess.run(
        [str(SCRIPT_PATH)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert result.stderr == "ERROR: exactly one non-empty image reference is required\n"
