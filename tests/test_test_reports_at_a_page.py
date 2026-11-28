# SPDX-FileCopyrightText: 2025-2026 Per Jensen
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This file is part of dar-backup-image:
# https://github.com/per2jensen/dar-backup-image
#
# License terms and warranty disclaimer:
# https://github.com/per2jensen/dar-backup-image/blob/main/LICENSE

"""Tests for the one-page large-scale test report generator."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).parents[1] / "scripts" / "test_reports_at_a_page.py"
MODULE_SPEC = importlib.util.spec_from_file_location(
    "test_reports_at_a_page", MODULE_PATH
)
if MODULE_SPEC is None or MODULE_SPEC.loader is None:
    raise RuntimeError(f"Unable to load report generator from {MODULE_PATH}")
REPORT_MODULE = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(REPORT_MODULE)
build_report = REPORT_MODULE.build_report
format_axis_bytes = REPORT_MODULE._format_axis_bytes
daily_worst_status = REPORT_MODULE._daily_worst_status
image_series = REPORT_MODULE._image_series
render_chart_table = REPORT_MODULE._render_chart_table
series_breakdown = REPORT_MODULE._series_breakdown


def _fixture_record(
    date: str,
    passed: bool,
    *,
    completed: bool | None = None,
    datestamp: str | None = None,
) -> dict:
    """Build one minimal valid result record.

    Args:
        date: Run date in ISO format.
        passed: Whether the run passed.
        completed: Whether the run completed, or ``None`` when unspecified.
        datestamp: Unique run timestamp for chronological ordering.

    Returns:
        Minimal record accepted by the report generator.
    """
    record: dict = {
        "date": date,
        "passed": passed,
        "datestamp": datestamp or f"{date}_10-00-00",
    }
    if completed is not None:
        record["completed"] = completed
    return record


def test_build_report_writes_summary_and_run_table_for_valid_records(
    tmp_path: Path,
) -> None:
    """A valid JSONL fixture produces Markdown with summary and run sections.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    input_path = tmp_path / "results.jsonl"
    input_path.write_text(
        "\n".join(
            [
                '{"date": "2026-08-01", "passed": true, "datestamp": "2026-08-01_10-00-00"}',
                '{"date": "2026-08-02", "passed": false, "completed": true, "exit_code": 1, "failures": 2, "datestamp": "2026-08-02_10-00-00"}',
                '{"date": "2026-08-03", "passed": false, "completed": false, "exit_code": 130, "aborted_phase": "full_backup:interrupted", "datestamp": "2026-08-03_10-00-00"}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    output_path = tmp_path / "report.md"

    result = build_report(
        input_path=input_path,
        output_path=output_path,
        chart_dir=None,
        with_graphs=False,
    )

    markdown = output_path.read_text(encoding="utf-8")
    assert result["records"] == 3
    assert result["charts"] == []
    assert "## Summary" in markdown
    assert "| Runs | 3 |" in markdown
    assert "1 pass" in markdown
    assert "1 fail" in markdown
    assert "1 incomplete" in markdown
    assert "| Dev runs | 3 (1 pass, 1 fail, 1 incomplete) |" in markdown
    assert "Published runs" not in markdown
    assert "## Latest run" in markdown
    assert "## Runs" in markdown
    assert "| Date | Test | Image | dar-backup | Result |" in markdown
    assert "✅ Pass" in markdown
    assert "❌ Fail" in markdown
    assert "⚠️ Incomplete" in markdown


def test_build_report_missing_input_fails_with_clear_error(tmp_path: Path) -> None:
    """A missing results file raises a clear ValueError.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    with pytest.raises(ValueError, match="is not a file"):
        build_report(
            input_path=tmp_path / "missing.jsonl",
            output_path=tmp_path / "report.md",
            chart_dir=None,
            with_graphs=False,
        )


def test_build_report_emits_license_header(tmp_path: Path) -> None:
    """Generated Markdown carries the repository license header.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    input_path = tmp_path / "results.jsonl"
    input_path.write_text(
        '{"date": "2026-08-01", "passed": true}\n', encoding="utf-8"
    )
    output_path = tmp_path / "report.md"

    build_report(
        input_path=input_path,
        output_path=output_path,
        chart_dir=None,
        with_graphs=False,
    )

    markdown = output_path.read_text(encoding="utf-8")
    # REUSE-IgnoreStart
    # The assertions below name the required header tags; they are test data,
    # not this file's own licensing declarations.
    assert "SPDX-FileCopyrightText:" in markdown
    assert "SPDX-License-Identifier: GPL-3.0-or-later" in markdown
    assert "https://github.com/per2jensen/dar-backup-image" in markdown
    assert (
        "https://github.com/per2jensen/dar-backup-image/blob/main/LICENSE"
        in markdown
    )
    # REUSE-IgnoreEnd


def test_build_report_renders_bitrot_method_and_extent_columns(
    tmp_path: Path,
) -> None:
    """Bitrot methodology and extent are rendered as table columns.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    input_path = tmp_path / "results.jsonl"
    input_path.write_text(
        '{"date": "2026-08-01", "passed": true, '
        '"configuration": {"bitrot": {"mode": "fragmented", "corruption_percent": 2}}, '
        '"bitrot_evidence": {'
        '"full": {"length_bytes": 21474836, "region_count": 5}, '
        '"diff": {"length_bytes": 6238714, "region_count": 10}, '
        '"incr": {"length_bytes": 6280661, "region_count": 8}'
        '}}\n',
        encoding="utf-8",
    )
    output_path = tmp_path / "report.md"

    build_report(
        input_path=input_path,
        output_path=output_path,
        chart_dir=None,
        with_graphs=False,
    )

    markdown = output_path.read_text(encoding="utf-8")
    assert "| Bitrot method | Bitrot extent |" in markdown
    assert "fragmented @ 2%" in markdown
    assert "32.4 MiB / 23 regions" in markdown


def test_build_report_malformed_line_fails_with_line_number(tmp_path: Path) -> None:
    """A malformed JSON line raises with the offending line number.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    input_path = tmp_path / "results.jsonl"
    input_path.write_text(
        '{"date": "2026-08-01", "passed": true}\nnot json\n',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Invalid JSON on line 2"):
        build_report(
            input_path=input_path,
            output_path=tmp_path / "report.md",
            chart_dir=None,
            with_graphs=False,
        )


def test_format_axis_bytes_gib_range_returns_gib_label() -> None:
    """Byte ticks at and above one GiB render as binary gigabyte labels."""
    assert format_axis_bytes(2**30, 0) == "1.0 GiB"
    assert format_axis_bytes(10**11, 0) == "93.1 GiB"
    assert format_axis_bytes(2**41, 0) == "2.0 TiB"


def test_format_axis_bytes_sub_gib_returns_lower_unit_label() -> None:
    """Byte ticks below one GiB render with the next smaller binary unit."""
    assert format_axis_bytes(2**20, 0) == "1.0 MiB"
    assert format_axis_bytes(2**10, 0) == "1.0 KiB"
    assert format_axis_bytes(1, 0) == "1 B"


def test_render_charts_sizes_chart_written_with_axis_formatter(tmp_path: Path) -> None:
    """Rendering charts produces a per-series sizes chart without formatter errors.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    pytest.importorskip("matplotlib")
    records = [
        {
            "date": "2026-08-01",
            "passed": True,
            "source_bytes": 10_000_000_000,
            "full_size_bytes": 6_000_000_000,
        }
    ]
    chart_dir = tmp_path / "charts"

    chart_paths, note = REPORT_MODULE._render_charts(records, chart_dir)

    assert note is None
    assert (chart_dir / "sizes-dev.png") in chart_paths
    assert (chart_dir / "sizes-dev.png").is_file()


def test_daily_worst_status_mixed_day_returns_worst_outcome() -> None:
    """A date with passing and failing runs reports the failing outcome."""
    records = [
        {"date": "2026-08-11", "passed": True},
        {"date": "2026-08-11", "passed": False, "completed": True},
    ]
    assert daily_worst_status(records) == {"2026-08-11": "fail"}


def test_daily_worst_status_all_pass_day_returns_pass() -> None:
    """A date with only passing runs stays green instead of overstating."""
    records = [
        {"date": "2026-08-11", "passed": True},
        {"date": "2026-08-11", "passed": True},
    ]
    assert daily_worst_status(records) == {"2026-08-11": "pass"}


def test_image_series_repo_qualified_reference_is_published() -> None:
    """A repo-qualified image reference classifies as published."""
    record = {"image_reference": "per2jensen/dar-backup:1.0.0"}
    assert image_series(record) == "published"


def test_image_series_local_or_missing_reference_is_dev() -> None:
    """Local tags and missing references classify as dev images."""
    assert image_series({"image_reference": "dar-backup:dev"}) == "dev"
    assert image_series({"image_reference": None}) == "dev"
    assert image_series({}) == "dev"


def test_render_charts_split_all_charts_by_image_series(
    tmp_path: Path,
) -> None:
    """Mixed image references render every chart per series.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    pytest.importorskip("matplotlib")
    records = [
        {
            "date": "2026-08-01",
            "passed": True,
            "image_reference": "dar-backup:dev",
        },
        {
            "date": "2026-08-02",
            "passed": False,
            "completed": True,
            "image_reference": "per2jensen/dar-backup:1.0.0",
        },
    ]
    chart_dir = tmp_path / "charts"

    chart_paths, note = REPORT_MODULE._render_charts(records, chart_dir)

    assert note is None
    for series in ("dev", "published"):
        for chart_type in ("status-timeline", "durations", "sizes", "memory"):
            chart_path = chart_dir / f"{chart_type}-{series}.png"
            assert chart_path in chart_paths
            assert chart_path.is_file()


def test_render_chart_table_pairs_dev_and_published_columns() -> None:
    """Chart references render as paired Dev and Published table columns."""
    refs = [
        "charts/status-timeline-dev.png",
        "charts/status-timeline-published.png",
        "charts/sizes-dev.png",
        "charts/sizes-published.png",
    ]

    markdown = "\n".join(render_chart_table(refs))

    assert "<th>Dev</th>" in markdown
    assert "<th>Published</th>" in markdown
    assert (
        '<img src="charts/status-timeline-dev.png" alt="Status timeline (dev)" '
        'width="100%">'
        in markdown
    )
    assert (
        '<img src="charts/status-timeline-published.png" '
        'alt="Status timeline (published)" width="100%">'
        in markdown
    )


def test_render_chart_table_missing_series_uses_placeholder() -> None:
    """A chart missing one series shows a placeholder instead of a broken image."""
    refs = ["charts/sizes-dev.png"]

    markdown = "\n".join(render_chart_table(refs))

    assert '<img src="charts/sizes-dev.png" alt="Sizes (dev)" width="100%">' in markdown
    assert "\u2014" in markdown
    assert "sizes-published.png" not in markdown


def test_series_breakdown_counts_outcomes_per_series() -> None:
    """Outcome counters are separated per image series."""
    records = [
        {"passed": True, "image_reference": "dar-backup:dev"},
        {"passed": False, "completed": True, "image_reference": "dar-backup:dev"},
        {"passed": True, "image_reference": "per2jensen/dar-backup:1.0.0"},
    ]

    assert series_breakdown(records) == {
        "dev": {"pass": 1, "fail": 1, "incomplete": 0},
        "published": {"pass": 1, "fail": 0, "incomplete": 0},
    }


def test_series_breakdown_only_includes_series_with_runs() -> None:
    """A missing published series is omitted instead of shown as zero runs."""
    records = [{"passed": True, "image_reference": "dar-backup:dev"}]

    assert series_breakdown(records) == {
        "dev": {"pass": 1, "fail": 0, "incomplete": 0}
    }
