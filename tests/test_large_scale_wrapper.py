"""Tests for publication-option forwarding by the large-scale wrapper."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


WRAPPER_PATH = Path(__file__).parents[1] / "run_large_scale_test.sh"
DEFINITION_HELPER_PATH = (
    Path(__file__).parents[1] / "scripts" / "large_scale_definition.py"
)


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
    shutil.copy2(DEFINITION_HELPER_PATH, harness.parent / DEFINITION_HELPER_PATH.name)
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
            "FULL_RESTORE_MODE": "forced",
            "FULL_RESTORE_THRESHOLD_GIB": "40",
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
    assert arguments[arguments.index("--full-restore-mode") + 1] == "forced"
    assert arguments[arguments.index("--full-restore-threshold-gib") + 1] == "40"
    assert arguments[arguments.index("--slice") + 1] == "10G"


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


def test_wrapper_default_full_restore_is_auto_at_25_gib(tmp_path: Path) -> None:
    """The wrapper forwards the documented automatic complete-restore defaults.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    wrapper = _isolated_wrapper(tmp_path)
    environment = os.environ.copy()
    environment.update({"BUILD_IMAGE": "false", "BITROT": "false"})
    environment.pop("FULL_RESTORE_MODE", None)
    environment.pop("FULL_RESTORE_THRESHOLD_GIB", None)

    result = subprocess.run(
        [str(wrapper)], env=environment, capture_output=True, text=True
    )

    assert result.returncode == 0, result.stderr
    arguments = result.stdout.splitlines()[1:]
    assert arguments[arguments.index("--full-restore-mode") + 1] == "auto"
    assert arguments[arguments.index("--full-restore-threshold-gib") + 1] == "25"


def test_wrapper_invalid_full_restore_mode_fails_before_harness(
    tmp_path: Path,
) -> None:
    """An unknown full-restore mode is rejected instead of silently skipped.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    wrapper = _isolated_wrapper(tmp_path)
    environment = os.environ.copy()
    environment.update(
        {
            "BUILD_IMAGE": "false",
            "FULL_RESTORE_MODE": "sometimes",
        }
    )

    result = subprocess.run(
        [str(wrapper)], env=environment, capture_output=True, text=True
    )

    assert result.returncode != 0
    assert "FULL_RESTORE_MODE must be 'auto', 'forced', or 'disabled'" in result.stderr


def test_wrapper_invalid_full_restore_threshold_fails_before_harness(
    tmp_path: Path,
) -> None:
    """A non-positive automatic threshold is rejected before harness execution.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    wrapper = _isolated_wrapper(tmp_path)
    environment = os.environ.copy()
    environment.update(
        {
            "BUILD_IMAGE": "false",
            "FULL_RESTORE_THRESHOLD_GIB": "0",
        }
    )

    result = subprocess.run(
        [str(wrapper)], env=environment, capture_output=True, text=True
    )

    assert result.returncode != 0
    assert "FULL_RESTORE_THRESHOLD_GIB must be a positive integer" in result.stderr


def test_wrapper_unitless_cli_slice_fails_before_build_or_harness(
    tmp_path: Path,
) -> None:
    """A likely omitted unit is rejected before expensive external work.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    wrapper = _isolated_wrapper(tmp_path)
    environment = os.environ.copy()
    environment.update(
        {
            "BUILD_IMAGE": "true",
            "DEFINITION": "-R /data\n-g source",
        }
    )

    result = subprocess.run(
        [str(wrapper), "--slice", "10"],
        env=environment,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "slice size '10'" in result.stderr
    assert "explicit DAR unit" in result.stderr
    assert "Building" not in result.stdout


def test_wrapper_literal_prune_definition_reaches_harness(tmp_path: Path) -> None:
    """A quoted literal prune within an include satisfies the narrow contract.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    wrapper = _isolated_wrapper(tmp_path)
    environment = os.environ.copy()
    environment.update(
        {
            "BUILD_IMAGE": "false",
            "BITROT": "false",
            "BASE_DIR": "/data/tmp/test",
            "DEFINITION": (
                "-R /data\n-am\n-g SteamLibrary\n"
                "-P 'SteamLibrary/Metro Exodus'"
            ),
        }
    )

    result = subprocess.run(
        [str(wrapper)], env=environment, capture_output=True, text=True
    )

    assert result.returncode == 0, result.stderr
    assert "-P 'SteamLibrary/Metro Exodus'" in result.stdout


def test_wrapper_unsupported_wildcard_prune_fails_before_build(
    tmp_path: Path,
) -> None:
    """A wildcard prune is rejected before an expensive image build.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    wrapper = _isolated_wrapper(tmp_path)
    environment = os.environ.copy()
    environment.update(
        {
            "BUILD_IMAGE": "true",
            "BASE_DIR": "/data/tmp/test",
            "DEFINITION": "-R /data\n-g SteamLibrary\n-P 'SteamLibrary/*'",
        }
    )

    result = subprocess.run(
        [str(wrapper)], env=environment, capture_output=True, text=True
    )

    assert result.returncode != 0
    assert "wildcard" in result.stderr
    assert "Building" not in result.stdout
