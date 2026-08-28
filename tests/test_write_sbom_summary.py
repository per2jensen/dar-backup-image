# SPDX-FileCopyrightText: 2025-2026 Per Jensen
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This file is part of dar-backup-image:
# https://github.com/per2jensen/dar-backup-image
#
# License terms and warranty disclaimer:
# https://github.com/per2jensen/dar-backup-image/blob/main/LICENSE

"""Tests for resilient SBOM vulnerability summaries."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "scripts" / "write_sbom_summary.py"
MODULE_SPEC = importlib.util.spec_from_file_location("write_sbom_summary", MODULE_PATH)
if MODULE_SPEC is None or MODULE_SPEC.loader is None:
    raise RuntimeError(f"Unable to load SBOM summary helper from {MODULE_PATH}")
SBOM_SUMMARY = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(SBOM_SUMMARY)


def test_build_summary_valid_artifacts_counts_components_and_severities(
    tmp_path: Path,
) -> None:
    """Valid Syft and Grype JSON produce a complete severity summary.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    sbom = tmp_path / "sbom.json"
    grype = tmp_path / "grype.json"
    sbom.write_text(json.dumps({"components": [{}, {}]}), encoding="utf-8")
    grype.write_text(
        json.dumps(
            {
                "matches": [
                    {"vulnerability": {"severity": "High"}},
                    {"vulnerability": {"severity": "Low"}},
                ]
            }
        ),
        encoding="utf-8",
    )

    summary = SBOM_SUMMARY.build_summary("example/image:test", sbom, grype)

    scan = summary["sbom_vuln_scan"]
    assert scan["status"] == "complete"
    assert scan["components"] == 2
    assert scan["vulnerabilities"]["total"] == 2
    assert scan["vulnerabilities"]["by_severity"]["high"] == 1
    assert scan["vulnerabilities"]["by_severity"]["low"] == 1


def test_build_summary_missing_prerequisites_records_unavailable_status(
    tmp_path: Path,
) -> None:
    """Missing scan artifacts produce one explanatory summary, not an exception.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    summary = SBOM_SUMMARY.build_summary(
        "example/image:test",
        tmp_path / "missing-sbom.json",
        tmp_path / "missing-grype.json",
    )

    scan = summary["sbom_vuln_scan"]
    assert scan["status"] == "unavailable"
    assert "CycloneDX SBOM is missing" in scan["reason"]
    assert scan["components"] is None
    assert scan["vulnerabilities"] is None
