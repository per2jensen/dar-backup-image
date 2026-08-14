"""Tests for publication-option forwarding by the large-scale wrapper."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


WRAPPER_PATH = Path(__file__).parents[1] / "run_large_scale_test.sh"


def _isolated_wrapper(tmp_path: Path) -> Path:
    """Create a real wrapper checkout with a recording harness executable.

    Args:
        tmp_path: Isolated pytest temporary directory.

    Returns:
        Path to the copied wrapper.

    Raises:
        OSError: If the wrapper or recording harness cannot be created.
    """
    wrapper = tmp_path / "run_large_scale_test.sh"
    harness = tmp_path / "scripts" / "large_scale_test.sh"
    harness.parent.mkdir()
    shutil.copy2(WRAPPER_PATH, wrapper)
    harness.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "printf '%s\\n' \"$@\"\n",
        encoding="utf-8",
    )
    harness.chmod(0o755)
    return wrapper


def test_wrapper_advertise_options_are_forwarded_to_harness(tmp_path: Path) -> None:
    """Enabled publication and custom identity reach the internal harness.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    wrapper = _isolated_wrapper(tmp_path)
    environment = os.environ.copy()
    environment.update(
        {
            "BUILD_IMAGE": "false",
            "BITROT": "false",
            "ADVERTISE": "true",
            "TEST_NAME": "Cross-version restore",
            "ADVERTISE_CLASS": "2.7-to-2.8",
            "BASE_DIR": "/data/tmp/test",
            "SOURCE_GLOB": "source",
        }
    )

    result = subprocess.run(
        [str(wrapper)], env=environment, capture_output=True, text=True
    )

    assert result.returncode == 0, result.stderr
    arguments = result.stdout.splitlines()[1:]
    assert "--advertise" in arguments
    assert arguments[arguments.index("--test-name") + 1] == "Cross-version restore"
    assert arguments[arguments.index("--advertise-class") + 1] == "2.7-to-2.8"


def test_wrapper_invalid_advertise_value_fails_before_harness(tmp_path: Path) -> None:
    """An ambiguous publication request is rejected instead of treated as false.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    wrapper = _isolated_wrapper(tmp_path)
    environment = os.environ.copy()
    environment.update({"BUILD_IMAGE": "false", "ADVERTISE": "yes"})

    result = subprocess.run(
        [str(wrapper)], env=environment, capture_output=True, text=True
    )

    assert result.returncode != 0
    assert "ADVERTISE must be 'true' or 'false'" in result.stderr
