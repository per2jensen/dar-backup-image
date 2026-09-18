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


def summarize(path: str) -> dict[str, Any]:
    """Summarize actual Grype severities from one SARIF report.

    Args:
        path: Filesystem path to a Grype SARIF report.

    Returns:
        Scan filename, result total, and severity counts.

    Raises:
        ValueError: If the report is missing, unreadable, or structurally invalid.
    """
    if not isinstance(path, str) or not path:
        raise ValueError("SARIF path must be a non-empty string")

    sarif_path = pathlib.Path(path)
    if not sarif_path.is_file():
        raise ValueError(f"Grype SARIF report is not a file: {sarif_path}")

    try:
        data = json.loads(sarif_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(
            f"Unable to read Grype SARIF report {sarif_path}: {error}"
        ) from error

    if not isinstance(data, dict):
        raise ValueError(f"Grype SARIF report root is not an object: {sarif_path}")

    runs = data.get("runs")
    if not isinstance(runs, list):
        raise ValueError(f"Grype SARIF report has no runs array: {sarif_path}")

    counts: collections.Counter[str] = collections.Counter()

    for run in runs:
        if not isinstance(run, dict):
            raise ValueError(
                f"Grype SARIF report contains an invalid run: {sarif_path}"
            )
        results = run.get("results")
        if not isinstance(results, list):
            raise ValueError(
                f"Grype SARIF run has no results array: {sarif_path}"
            )
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


def main() -> int:
    """Write a compact JSON summary for a requested SARIF report.

    Returns:
        Zero on success and two when the report is unavailable or invalid.
    """
    path = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        summary = summarize(path)
    except ValueError as error:
        LOGGER.error("Invalid Grype SARIF input: %s", error)
        return 2
    json.dump(summary, sys.stdout, separators=(",", ":"))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    raise SystemExit(main())
