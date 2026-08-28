# SPDX-FileCopyrightText: 2025-2026 Per Jensen
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This file is part of dar-backup-image:
# https://github.com/per2jensen/dar-backup-image
#
# License terms and warranty disclaimer:
# https://github.com/per2jensen/dar-backup-image/blob/main/LICENSE

"""Integration tests for guarded and legacy refresh source layouts."""

from __future__ import annotations

import subprocess
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).parents[1]
FINALIZER = REPOSITORY_ROOT / "scripts" / "finalize_refresh_image.sh"


def _create_source_layout(
    tmp_path: Path,
    *,
    image_version: str | None,
    guarded: bool,
) -> Path:
    """Create a minimal application checkout with a real Make target.

    Args:
        tmp_path: Temporary directory owned by the test.
        image_version: IMAGE_VERSION content, or ``None`` to omit the file.
        guarded: Whether the checkout exposes the new refresh target.

    Returns:
        Path to the isolated application source tree.
    """
    source = tmp_path / "source"
    source.mkdir()
    if image_version is not None:
        (source / "IMAGE_VERSION").write_text(image_version, encoding="utf-8")
    target = "refresh-final-noscan" if guarded else "final-noscan"
    (source / "Makefile").write_text(
        f"{target}:\n"
        "\t@printf '%s\\n' "
        f"'{target} FINAL=$(FINAL_VERSION) BASE=$(BASE_VERSION) "
        "DAR_BACKUP=$(DAR_BACKUP_VERSION) DAR=$(DAR_VERSION)'\n",
        encoding="utf-8",
    )
    return source


def _run_finalizer(
    source: Path,
    *,
    base_version: str,
    final_version: str,
) -> subprocess.CompletedProcess[str]:
    """Run the real refresh finalizer against an isolated source checkout.

    Args:
        source: Application source directory.
        base_version: Stable release selected by orchestration.
        final_version: Derived refresh image version.

    Returns:
        Completed subprocess with captured output.
    """
    return subprocess.run(
        [
            "bash",
            str(FINALIZER),
            str(source),
            base_version,
            final_version,
            "component-1.2.3",
            "dar-2.7.21",
        ],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_finalize_refresh_guarded_source_uses_dedicated_target(
    tmp_path: Path,
) -> None:
    """A current tagged checkout uses its own guarded refresh target."""
    source = _create_source_layout(tmp_path, image_version="9.9.9-rc1", guarded=True)

    result = _run_finalizer(
        source,
        base_version="1.2.3",
        final_version="1.2.3-4",
    )

    assert result.returncode == 0, result.stderr
    assert "refresh-final-noscan FINAL=1.2.3-4 BASE=1.2.3" in result.stdout
    assert "final-noscan FINAL=" not in result.stdout.replace(
        "refresh-final-noscan FINAL=", ""
    )


def test_finalize_refresh_legacy_source_validates_then_uses_legacy_target(
    tmp_path: Path,
) -> None:
    """An old tagged checkout is validated externally without an overlay."""
    source = _create_source_layout(tmp_path, image_version="9.9.9", guarded=False)

    result = _run_finalizer(
        source,
        base_version="1.2.3",
        final_version="1.2.3-4",
    )

    assert result.returncode == 0, result.stderr
    assert "final-noscan FINAL=1.2.3-4" in result.stdout
    assert "Refresh version verified" in result.stderr


def test_finalize_refresh_legacy_source_rejects_invalid_version_before_make(
    tmp_path: Path,
) -> None:
    """The compatibility path cannot invoke Make with a mismatched final."""
    source = _create_source_layout(tmp_path, image_version=None, guarded=False)

    result = _run_finalizer(
        source,
        base_version="1.2.4",
        final_version="1.2.3-1",
    )

    assert result.returncode == 2
    assert "must match" in result.stderr
    assert "final-noscan FINAL=" not in result.stdout
