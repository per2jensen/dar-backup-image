# SPDX-FileCopyrightText: 2025-2026 Per Jensen
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This file is part of dar-backup-image:
# https://github.com/per2jensen/dar-backup-image
#
# License terms and warranty disclaimer:
# https://github.com/per2jensen/dar-backup-image/blob/main/LICENSE

"""Validate percentage and slice restore-test evidence for one backup."""

from __future__ import annotations

import argparse
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path


SAMPLING_PATTERN = re.compile(
    r"Restore-test sampling: eligible=(\d+) configured=([0-9.]+)% "
    r"calculated=(\d+) capped=(\d+)"
)
COVERAGE_PATTERN = re.compile(
    r"Restore-test slice coverage: data-bearing=(\d+) covered=(\d+) "
    r"additional-files=(\d+)"
)
EVIDENCE_PATTERN = re.compile(
    r"Restore-test slice evidence: data-bearing=(\d+) predicted=(\d+) "
    r"extracted=(\d+) verified=(\d+)"
)


@dataclass(frozen=True)
class RestoreTestEvidence:
    """Store validated evidence emitted by one backup verification.

    Args:
        eligible_files: Files eligible for percentage sampling.
        calculated_files: Rounded percentage target before the cap.
        selected_files: Percentage target after the cap.
        verified_files: Total files verified by the engine.
        data_slices: Data-bearing archive slices.
        covered_slices: Data-bearing slices selected for restore.
        predicted_slices: Slices predicted by DAR catalogue evidence.
        extracted_slices: Slices represented by extracted files.
        verified_slices: Slices represented by verified files.
    """

    eligible_files: int
    calculated_files: int
    selected_files: int
    verified_files: int
    data_slices: int
    covered_slices: int
    predicted_slices: int
    extracted_slices: int
    verified_slices: int

    def as_tsv(self) -> str:
        """Return stable shell-readable evidence fields.

        Returns:
            Tab-separated integer fields.
        """
        values = (
            self.eligible_files,
            self.calculated_files,
            self.selected_files,
            self.verified_files,
            self.data_slices,
            self.covered_slices,
            self.predicted_slices,
            self.extracted_slices,
            self.verified_slices,
        )
        return "\t".join(str(value) for value in values)


def _last_match(pattern: re.Pattern[str], text: str, label: str) -> re.Match[str]:
    """Return the final matching log record.

    Args:
        pattern: Compiled evidence pattern.
        text: Complete current log text.
        label: Human-readable evidence label.

    Returns:
        Final regular-expression match.

    Raises:
        ValueError: If the evidence record is absent.
    """
    matches = list(pattern.finditer(text))
    if not matches:
        raise ValueError(f"missing {label} evidence in backup log")
    return matches[-1]


def validate_evidence(
    log_file: Path,
    metrics_db: Path,
    definition: str,
    backup_type: str,
    archive_name: str,
    expected_percentage: float,
) -> RestoreTestEvidence:
    """Validate engine metrics and restore-test log evidence.

    Args:
        log_file: dar-backup log produced by the harness.
        metrics_db: dar-backup operational metrics database.
        definition: Backup definition name.
        backup_type: FULL, DIFF, or INCR.
        archive_name: Exact archive base name.
        expected_percentage: Configured restore-test percentage.

    Returns:
        Validated evidence counts.

    Raises:
        ValueError: If inputs or evidence are missing or inconsistent.
        OSError: If the log cannot be read.
        sqlite3.Error: If metrics evidence cannot be queried.
    """
    if not definition.strip() or not archive_name.strip():
        raise ValueError("definition and archive_name must not be empty")
    if backup_type not in {"FULL", "DIFF", "INCR"}:
        raise ValueError(f"invalid backup_type: {backup_type!r}")
    if not 0 < expected_percentage <= 100:
        raise ValueError("expected_percentage must be greater than 0 and at most 100")
    if not log_file.is_file() or not metrics_db.is_file():
        raise ValueError("log_file and metrics_db must be existing files")

    log_text = log_file.read_text(encoding="utf-8", errors="replace")
    sampling = _last_match(SAMPLING_PATTERN, log_text, "percentage sampling")
    coverage = _last_match(COVERAGE_PATTERN, log_text, "slice coverage")
    slice_evidence = _last_match(EVIDENCE_PATTERN, log_text, "slice verification")

    eligible, configured, calculated, selected = sampling.groups()
    data_slices, covered_slices, _additional_files = coverage.groups()
    evidence_data, predicted, extracted, verified = slice_evidence.groups()
    if float(configured) != expected_percentage:
        raise ValueError(
            f"restore-test percentage mismatch: expected {expected_percentage}, got {configured}"
        )

    with sqlite3.connect(metrics_db) as database:
        row = database.execute(
            """
            SELECT status, restore_test_passed, files_verified
            FROM backup_runs
            WHERE backup_definition = ? AND backup_type = ? AND archive_name = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (definition, backup_type, archive_name),
        ).fetchone()
    if row is None:
        raise ValueError(f"missing metrics row for archive {archive_name!r}")
    status, restore_test_passed, files_verified = row
    if status != "SUCCESS" or restore_test_passed != 1:
        raise ValueError(
            "restore test did not pass: "
            f"status={status!r}, restore_test_passed={restore_test_passed!r}"
        )
    if not isinstance(files_verified, int) or files_verified < 1:
        raise ValueError("restore test did not verify any files")

    integer_values = [
        int(eligible),
        int(calculated),
        int(selected),
        files_verified,
        int(data_slices),
        int(covered_slices),
        int(predicted),
        int(extracted),
        int(verified),
    ]
    if any(value < 1 for value in integer_values):
        raise ValueError(f"restore-test evidence contains a zero count: {integer_values!r}")
    if integer_values[2] > integer_values[3]:
        raise ValueError("verified file count is below the percentage-selected count")
    if int(evidence_data) != integer_values[4]:
        raise ValueError("slice coverage and verification disagree on data-bearing slices")
    if len(set(integer_values[4:])) != 1:
        raise ValueError(
            "not every data-bearing slice was selected, extracted, and verified: "
            f"{integer_values[4:]!r}"
        )
    return RestoreTestEvidence(*integer_values)


def main() -> int:
    """Run the restore-test evidence validator.

    Returns:
        Process exit status.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--log-file", required=True, type=Path)
    parser.add_argument("--metrics-db", required=True, type=Path)
    parser.add_argument("--definition", required=True)
    parser.add_argument("--backup-type", required=True)
    parser.add_argument("--archive-name", required=True)
    parser.add_argument("--percentage", required=True, type=float)
    arguments = parser.parse_args()
    try:
        evidence = validate_evidence(
            arguments.log_file,
            arguments.metrics_db,
            arguments.definition,
            arguments.backup_type,
            arguments.archive_name,
            arguments.percentage,
        )
    except (OSError, sqlite3.Error, ValueError) as error:
        parser.error(str(error))
    print(evidence.as_tsv())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
