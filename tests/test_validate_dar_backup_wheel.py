"""Tests for local dar-backup wheel validation."""

from __future__ import annotations

import hashlib
import importlib.util
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest


MODULE_PATH = (
    Path(__file__).parents[1] / "scripts" / "validate_dar_backup_wheel.py"
)
MODULE_SPEC = importlib.util.spec_from_file_location(
    "validate_dar_backup_wheel", MODULE_PATH
)
if MODULE_SPEC is None or MODULE_SPEC.loader is None:
    raise RuntimeError(f"Unable to load wheel validator from {MODULE_PATH}")
WHEEL_MODULE = importlib.util.module_from_spec(MODULE_SPEC)
sys.modules[MODULE_SPEC.name] = WHEEL_MODULE
MODULE_SPEC.loader.exec_module(WHEEL_MODULE)
validate_wheel = WHEEL_MODULE.validate_wheel
REPOSITORY_ROOT = Path(__file__).parents[1]


def _create_wheel(path: Path, project_name: str, version: str) -> Path:
    """Create a minimal synthetic wheel containing Core Metadata.

    Args:
        path: Wheel path to create.
        project_name: Project name written to Core Metadata.
        version: Version written to Core Metadata.

    Returns:
        Created wheel path.
    """
    metadata = (
        "Metadata-Version: 2.4\n"
        f"Name: {project_name}\n"
        f"Version: {version}\n"
        "\n"
    ).encode("utf-8")
    with zipfile.ZipFile(path, mode="w") as archive:
        archive.writestr(f"dar_backup-{version}.dist-info/METADATA", metadata)
    return path


def test_validate_wheel_matching_metadata_returns_identity_and_digest(
    tmp_path: Path,
) -> None:
    """A matching dar-backup wheel returns verified provenance.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    wheel_path = _create_wheel(
        tmp_path / "dar_backup-1.1.11.dev42-py3-none-any.whl",
        project_name="dar_backup",
        version="1.1.11.dev42",
    )

    details = validate_wheel(wheel_path, "1.1.11.dev42")

    assert details.path == wheel_path.resolve()
    assert details.project_name == "dar-backup"
    assert details.version == "1.1.11.dev42"
    assert details.sha256 == hashlib.sha256(wheel_path.read_bytes()).hexdigest()


def test_validate_wheel_version_mismatch_raises_value_error(
    tmp_path: Path,
) -> None:
    """A wheel whose metadata disagrees with the build pin is rejected.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    wheel_path = _create_wheel(
        tmp_path / "dar_backup-1.1.11.dev42-py3-none-any.whl",
        project_name="dar-backup",
        version="1.1.11.dev42",
    )

    with pytest.raises(ValueError, match="does not match DAR_BACKUP_VERSION"):
        validate_wheel(wheel_path, "1.1.11.dev41")


def test_make_validation_local_matching_wheel_succeeds(tmp_path: Path) -> None:
    """Make accepts local mode when the requested wheel metadata matches.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    version = "1.1.11.dev42"
    wheel_name = f"dar_backup-{version}-py3-none-any.whl"
    _create_wheel(
        tmp_path / wheel_name,
        project_name="dar-backup",
        version=version,
    )

    result = subprocess.run(
        [
            "make",
            "--no-print-directory",
            "validate-dar-backup-install",
            "DAR_BACKUP_INSTALL_SOURCE=local",
            f"DAR_BACKUP_LOCAL_DIST={tmp_path}",
            f"DAR_BACKUP_VERSION={version}",
            "UBUNTU_DIGEST=sha256:test",
        ],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def test_make_validation_unknown_install_source_fails() -> None:
    """Make rejects an unknown dar-backup installation source."""
    result = subprocess.run(
        [
            "make",
            "--no-print-directory",
            "validate-dar-backup-install",
            "DAR_BACKUP_INSTALL_SOURCE=unknown",
            "UBUNTU_DIGEST=sha256:test",
        ],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode != 0
    assert "must be 'pypi' or 'local'" in result.stderr
