#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2025-2026 Per Jensen
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This file is part of dar-backup-image:
# https://github.com/per2jensen/dar-backup-image
#
# License terms and warranty disclaimer:
# https://github.com/per2jensen/dar-backup-image/blob/main/LICENSE

"""
Summarize a Grype SARIF report into severity counts for build metadata.
"""

from __future__ import annotations

import collections
import json
import logging
import pathlib
import re
import sys
from typing import Any


LOGGER = logging.getLogger(__name__)
GRYPE_SEVERITY_PATTERN = re.compile(
    r"^A (?P<severity>critical|high|medium|low) vulnerability\b",
    re.IGNORECASE,
)
SUMMARY_ORDER = (
    "critical",
    "high",
    "medium",
    "low",
    "negligible",
    "warning",
    "note",
    "info",
    "unknown",
)


def _result_severity(result: object) -> str:
    """Extract Grype's vulnerability severity from one SARIF result.

    Grype encodes its vulnerability severity in the result message. SARIF's
    ``level`` is a presentation level which merges critical/high into ``error``,
    uses ``warning`` for medium, and merges all remaining severities into
    ``note``. It therefore cannot provide an auditable severity count.

    Args:
        result: Candidate SARIF result object.

    Returns:
        Lowercase Grype severity, or ``unknown`` when it cannot be established.
    """
    if not isinstance(result, dict):
        return "unknown"

    message = result.get("message")
    if not isinstance(message, dict):
        return "unknown"

    text = message.get("text")
    if not isinstance(text, str):
        return "unknown"

    match = GRYPE_SEVERITY_PATTERN.match(text)
    if match is None:
        return "unknown"
    return match.group("severity").lower()


def summarize(path: str) -> dict[str, Any] | None:
    """Summarize actual Grype severities from one SARIF report.

    Args:
        path: Filesystem path to a Grype SARIF report.

    Returns:
        Scan filename, result total, and severity counts, or ``None`` when the
        report is missing or cannot be decoded.
    """
    if not isinstance(path, str) or not path:
        raise ValueError("SARIF path must be a non-empty string")

    sarif_path = pathlib.Path(path)
    if not sarif_path.is_file():
        return None

    try:
        data = json.loads(sarif_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        LOGGER.warning("Unable to read Grype SARIF report %s: %s", sarif_path, error)
        return None

    if not isinstance(data, dict):
        LOGGER.warning("Grype SARIF report root is not an object: %s", sarif_path)
        return None

    runs = data.get("runs")
    if not isinstance(runs, list):
        LOGGER.warning("Grype SARIF report has no runs array: %s", sarif_path)
        return None

    counts: collections.Counter[str] = collections.Counter()

    for run in runs:
        if not isinstance(run, dict):
            LOGGER.warning("Grype SARIF report contains an invalid run: %s", sarif_path)
            return None
        results = run.get("results")
        if not isinstance(results, list):
            LOGGER.warning(
                "Grype SARIF run has no results array: %s",
                sarif_path,
            )
            return None
        for result in results:
            counts[_result_severity(result)] += 1

    summary_counts = {key: counts.get(key, 0) for key in SUMMARY_ORDER}
    for key, value in counts.items():
        if key not in summary_counts:
            summary_counts[key] = value

    return {
        "file": sarif_path.name,
        "total": sum(counts.values()),
        "counts": summary_counts,
    }


def main() -> None:
    """Write a compact JSON summary for a requested SARIF report."""
    path = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        summary = summarize(path)
    except ValueError as error:
        LOGGER.error("Invalid Grype SARIF input: %s", error)
        summary = None
    json.dump(summary, sys.stdout, separators=(",", ":"))


if __name__ == "__main__":
    main()
