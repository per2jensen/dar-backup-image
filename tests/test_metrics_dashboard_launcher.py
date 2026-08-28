"""Tests for the one-command Datasette dashboard launcher."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
from pathlib import Path


SCRIPT_PATH = Path(__file__).parents[1] / "run_metrics_dashboard.sh"


def _write_minimal_history(path: Path) -> None:
    """Write one historical record accepted by the dashboard builder.

    Args:
        path: JSONL fixture path.

    Returns:
        None.

    Raises:
        OSError: If the fixture cannot be written.
    """
    record = {
        "schema_version": 2,
        "datestamp": "2026-07-01_00-00-00",
        "date": "2026-07-01",
        "passed": True,
        "failures": 0,
    }
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")


def _write_fake_docker(directory: Path, calls_file: Path) -> None:
    """Create a subprocess-compatible Docker recorder for launcher tests.

    Args:
        directory: Directory placed first in ``PATH``.
        calls_file: File receiving one argument record per Docker call.

    Returns:
        None.

    Raises:
        OSError: If the executable cannot be created.
    """
    docker_path = directory / "docker"
    docker_path.write_text(
        """#!/bin/bash
set -euo pipefail
printf '%q ' "$@" >> "${FAKE_DOCKER_CALLS_FILE:?}"
printf '\n' >> "${FAKE_DOCKER_CALLS_FILE:?}"
""",
        encoding="utf-8",
    )
    docker_path.chmod(0o755)
    if calls_file.exists():
        raise OSError(f"calls file unexpectedly exists: {calls_file}")


def test_dashboard_launcher_builds_database_and_runs_local_read_only_container(
    tmp_path: Path,
) -> None:
    """One launcher invocation builds evidence and starts hardened Datasette.

    Args:
        tmp_path: Isolated inputs, output, and fake Docker executable.
    """
    results_jsonl = tmp_path / "results.jsonl"
    dashboard_database = tmp_path / "output" / "dashboard.db"
    calls_file = tmp_path / "docker-calls"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _write_minimal_history(results_jsonl)
    _write_fake_docker(fake_bin, calls_file)
    environment = os.environ.copy()
    environment.update(
        {
            "PATH": f"{fake_bin}:{environment['PATH']}",
            "RESULTS_JSONL": str(results_jsonl),
            "BACKUP_METRICS_DB": "",
            "DASHBOARD_OUTPUT": str(dashboard_database),
            "DASHBOARD_PORT": "8123",
            "FAKE_DOCKER_CALLS_FILE": str(calls_file),
        }
    )

    result = subprocess.run(
        [str(SCRIPT_PATH)],
        check=False,
        capture_output=True,
        env=environment,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert dashboard_database.is_file()
    with sqlite3.connect(dashboard_database) as database:
        assert database.execute("SELECT COUNT(*) FROM runs").fetchone() == (1,)
        assert database.execute(
            "SELECT COUNT(*) FROM engine_backup_runs"
        ).fetchone() == (0,)
    docker_calls = calls_file.read_text(encoding="utf-8").splitlines()
    assert len(docker_calls) == 2
    assert docker_calls[0].startswith("build ")
    assert docker_calls[1].startswith("run ")
    assert "127.0.0.1:8123:8001" in docker_calls[1]
    assert "--read-only" in docker_calls[1]
    assert "--immutable" in docker_calls[1]
    assert "http://127.0.0.1:8123/-/dashboards/large-scale" in result.stderr


def test_dashboard_launcher_invalid_port_fails_before_creating_output(
    tmp_path: Path,
) -> None:
    """An unsafe listener port is rejected before database or Docker work.

    Args:
        tmp_path: Isolated unused output directory.
    """
    dashboard_database = tmp_path / "dashboard.db"
    environment = os.environ.copy()
    environment.update(
        {
            "DASHBOARD_OUTPUT": str(dashboard_database),
            "DASHBOARD_PORT": "70000",
        }
    )

    result = subprocess.run(
        [str(SCRIPT_PATH)],
        check=False,
        capture_output=True,
        env=environment,
        text=True,
    )

    assert result.returncode == 2
    assert "DASHBOARD_PORT must be an integer between 1 and 65535" in result.stderr
    assert not dashboard_database.exists()
