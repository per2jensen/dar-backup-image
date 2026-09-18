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
Print Grype severity counts as shell-assignable KEY=VALUE lines.
Usage: python3 scripts/grype_summary_env.py <sarif-file>
"""
import sys
sys.path.insert(0, "scripts")
from grype_sarif_summary import summarize


def main() -> int:
    """Print validated Grype severity counts for shell consumers.

    Returns:
        Zero on success and two when the SARIF input is missing or invalid.
    """
    if len(sys.argv) != 2:
        print(f"ERROR: usage: {sys.argv[0]} <sarif-file>", file=sys.stderr)
        return 2

    try:
        summary = summarize(sys.argv[1])
    except ValueError as error:
        print(f"ERROR: unable to summarize Grype SARIF: {error}", file=sys.stderr)
        return 2

    counts = summary["counts"]
    for key in (
        "critical",
        "high",
        "medium",
        "low",
        "negligible",
        "warning",
        "note",
    ):
        print(f"{key.upper()}={counts.get(key, 0)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
