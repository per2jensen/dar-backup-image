# SPDX-FileCopyrightText: 2025-2026 Per Jensen
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This file is part of dar-backup-image:
# https://github.com/per2jensen/dar-backup-image
#
# License terms and warranty disclaimer:
# https://github.com/per2jensen/dar-backup-image/blob/main/LICENSE

"""Tests for Grype SARIF vulnerability-severity summaries."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any


MODULE_PATH = Path(__file__).parents[1] / "scripts" / "grype_sarif_summary.py"
MODULE_SPEC = importlib.util.spec_from_file_location(
    "grype_sarif_summary",
    MODULE_PATH,
)
if MODULE_SPEC is None or MODULE_SPEC.loader is None:
    raise RuntimeError(f"Unable to load Grype SARIF summary helper from {MODULE_PATH}")
GRYPE_SUMMARY = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(GRYPE_SUMMARY)


def _write_sarif(path: Path, results: list[dict[str, Any]]) -> None:
    """Write a minimal Grype-compatible SARIF result document.

    Args:
        path: Destination SARIF file.
        results: SARIF result objects to include.
    """
    path.write_text(
        json.dumps({"runs": [{"results": results}]}),
        encoding="utf-8",
    )


def test_summarize_grype_messages_counts_vulnerability_severities(
    tmp_path: Path,
) -> None:
    """Grype message severities are counted independently of SARIF levels.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    sarif = tmp_path / "grype.sarif"
    _write_sarif(
        sarif,
        [
            {
                "level": "error",
                "message": {"text": "A critical vulnerability in deb package"},
            },
            {
                "level": "error",
                "message": {"text": "A high vulnerability in deb package"},
            },
            {
                "level": "warning",
                "message": {"text": "A medium vulnerability in deb package"},
            },
            {
                "level": "note",
                "message": {"text": "A low vulnerability in deb package"},
            },
        ],
    )

    summary = GRYPE_SUMMARY.summarize(str(sarif))

    assert summary is not None
    assert summary["total"] == 4
    assert summary["counts"] == {
        "critical": 1,
        "high": 1,
        "medium": 1,
        "low": 1,
        "negligible": 0,
        "warning": 0,
        "note": 0,
        "info": 0,
        "unknown": 0,
    }


def test_summarize_missing_grype_severity_counts_unknown(
    tmp_path: Path,
) -> None:
    """Presentation levels cannot substitute for missing Grype severities.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    sarif = tmp_path / "grype.sarif"
    _write_sarif(
        sarif,
        [
            {"level": "warning", "message": {"text": "Unexpected wording"}},
            {"level": "note", "message": {}},
        ],
    )

    summary = GRYPE_SUMMARY.summarize(str(sarif))

    assert summary is not None
    assert summary["total"] == 2
    assert summary["counts"]["unknown"] == 2
    assert summary["counts"]["warning"] == 0
    assert summary["counts"]["note"] == 0
