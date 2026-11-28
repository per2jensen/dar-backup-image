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

"""Render a one-page Markdown overview of the large-scale test results."""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import tempfile
from datetime import date, datetime
from pathlib import Path
from typing import Any, Sequence


LOGGER = logging.getLogger(__name__)

# REUSE-IgnoreStart
# The generated Markdown embeds the repository license header verbatim. These
# literal tag strings are template data, not this file's own declarations.
GENERATED_FILE_LICENSE_HEADER = (
    "<!--\n"
    "SPDX-FileCopyrightText: 2025-2026 Per Jensen\n"
    "\n"
    "SPDX-License-Identifier: GPL-3.0-or-later\n"
    "\n"
    "This file is part of dar-backup-image:\n"
    "https://github.com/per2jensen/dar-backup-image\n"
    "\n"
    "License terms and warranty disclaimer:\n"
    "https://github.com/per2jensen/dar-backup-image/blob/main/LICENSE\n"
    "-->"
)
# REUSE-IgnoreEnd

STATUS_LABELS = {
    "pass": "Pass",
    "fail": "Fail",
    "incomplete": "Incomplete",
}
STATUS_EMOJI = {
    "pass": "\u2705",
    "fail": "\u274c",
    "incomplete": "\u26a0\ufe0f",
}
STATUS_COLORS = {
    "pass": "#2e7d32",
    "fail": "#c62828",
    "incomplete": "#ef6c00",
}
STATUS_RANK = {
    "pass": 0,
    "incomplete": 1,
    "fail": 2,
}
CHART_TYPES = ("status-timeline", "durations", "sizes", "memory")
IMAGE_SERIES_ORDER = ("dev", "published")
PROCESS_ORDER = ("dar_backup", "dar", "par2", "manager")
PROCESS_COLORS = {
    "dar_backup": "#1f77b4",
    "dar": "#ff7f0e",
    "par2": "#2ca02c",
    "manager": "#d62728",
}
MIB_TO_MB_FACTOR = 2**20 / 1_000_000


def _parse_records(input_path: Path) -> list[dict[str, Any]]:
    """Read and validate the JSONL test results file.

    Args:
        input_path: Path to a newline-delimited JSON file.

    Returns:
        Chronologically ordered result records.

    Raises:
        ValueError: If the file is unreadable, empty, or contains malformed records.
        OSError: If the file cannot be read for environmental reasons.
    """
    if not input_path.is_file():
        raise ValueError(f"Test results file is not a file: {input_path}")

    try:
        text = input_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise ValueError(f"Unable to read test results file {input_path}: {error}") from error

    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(
                f"Invalid JSON on line {line_number} of {input_path}: {error}"
            ) from error
        if not isinstance(record, dict):
            raise ValueError(
                f"Result on line {line_number} of {input_path} must be an object"
            )
        if not isinstance(record.get("date"), str) or not record["date"]:
            raise ValueError(
                f"Result on line {line_number} of {input_path} has no valid date"
            )
        try:
            date.fromisoformat(record["date"])
        except ValueError as error:
            raise ValueError(
                f"Result on line {line_number} of {input_path} has an invalid date "
                f"{record['date']!r}"
            ) from error
        if not isinstance(record.get("passed"), bool):
            raise ValueError(
                f"Result on line {line_number} of {input_path} has no boolean 'passed'"
            )
        records.append(record)

    if not records:
        raise ValueError(f"Test results file contains no records: {input_path}")

    return sorted(records, key=lambda item: (item["date"], item.get("datestamp", "")))


def _result_status(record: dict[str, Any]) -> str:
    """Classify one result record into a stable three-way outcome.

    Args:
        record: One validated result record.

    Returns:
        ``pass``, ``fail``, or ``incomplete``.
    """
    if record.get("passed") is True:
        return "pass"
    if record.get("completed") is False:
        return "incomplete"
    return "fail"


def _daily_worst_status(records: Sequence[dict[str, Any]]) -> dict[str, str]:
    """Map each run date to the worst outcome recorded that day.

    Args:
        records: Chronologically ordered result records.

    Returns:
        Date strings mapped to the worst outcome for that date.
    """
    daily_worst: dict[str, str] = {}
    for record in records:
        record_date = record["date"]
        candidate = _result_status(record)
        current = daily_worst.get(record_date)
        if current is None or STATUS_RANK[candidate] > STATUS_RANK[current]:
            daily_worst[record_date] = candidate
    return daily_worst


def _image_series(record: dict[str, Any]) -> str:
    """Classify one record by the provenance of its image reference.

    Args:
        record: One validated result record.

    Returns:
        ``published`` for a repo-qualified image users can pull, otherwise
        ``dev`` for local images and records without a reference.
    """
    reference = record.get("image_reference")
    if isinstance(reference, str) and "/" in reference:
        return "published"
    return "dev"


def _series_breakdown(records: Sequence[dict[str, Any]]) -> dict[str, dict[str, int]]:
    """Count outcome statuses per image series.

    Args:
        records: Chronologically ordered result records.

    Returns:
        Series names mapped to pass/fail/incomplete counters.
    """
    breakdown: dict[str, dict[str, int]] = {}
    for record in records:
        series = _image_series(record)
        counts = breakdown.setdefault(
            series, {"pass": 0, "fail": 0, "incomplete": 0}
        )
        counts[_result_status(record)] += 1
    return breakdown


def _full_archive_bytes(record: dict[str, Any]) -> float | None:
    """Return the exact full-archive byte size when available.

    Args:
        record: One validated result record.

    Returns:
        Archive bytes, or ``None`` when the record predates byte measurements.
    """
    value = record.get("full_size_bytes")
    if value is not None:
        return float(value)
    gib_value = record.get("full_size_gib")
    if gib_value is not None:
        return float(gib_value) * 2**30
    gb_value = record.get("full_size_gb")
    if gb_value is not None:
        return float(gb_value) * 1_000_000_000
    return None


def _source_bytes(record: dict[str, Any]) -> float | None:
    """Return the source dataset byte size when available.

    Args:
        record: One validated result record.

    Returns:
        Source bytes, or ``None`` when absent from the schema version.
    """
    value = record.get("source_bytes")
    return float(value) if value is not None else None


def _memory_mib(record: dict[str, Any]) -> dict[str, float | None]:
    """Normalize peak process memory measurements to MiB.

    Args:
        record: One validated result record.

    Returns:
        Process names mapped to peak RSS in MiB, or ``None`` when unknown.
    """
    raw_mib = record.get("memory_mib")
    if isinstance(raw_mib, dict):
        return {
            key: (float(value) if value is not None else None)
            for key, value in raw_mib.items()
        }
    raw_mb = record.get("memory_mb")
    if isinstance(raw_mb, dict):
        return {
            key: (float(value) / MIB_TO_MB_FACTOR if value is not None else None)
            for key, value in raw_mb.items()
        }
    return {}


def _peak_rss_mib(record: dict[str, Any]) -> float | None:
    """Return the largest named-process peak RSS for one record.

    Args:
        record: One validated result record.

    Returns:
        Peak RSS in MiB, or ``None`` when no measurement exists.
    """
    values = [value for value in _memory_mib(record).values() if value is not None]
    return max(values) if values else None


def _format_bytes(value: float | None) -> str:
    """Format a byte count with binary units for compact display.

    Args:
        value: Byte count, or ``None`` when unavailable.

    Returns:
        Human-readable byte count, or an em dash.
    """
    if value is None:
        return "\u2014"
    if value >= 2**30:
        return f"{value / 2**30:.1f} GiB"
    if value >= 2**20:
        return f"{value / 2**20:.1f} MiB"
    return f"{value:.0f} B"


def _format_axis_bytes(value: float, position: int) -> str:
    """Format a log-axis byte tick as a compact binary-unit label.

    Args:
        value: Tick value in bytes.
        position: Tick position required by matplotlib's ``FuncFormatter``.

    Returns:
        Short human-readable label using TiB, GiB, MiB, or KiB.
    """
    if value >= 2**40:
        return f"{value / 2**40:.1f} TiB"
    if value >= 2**30:
        return f"{value / 2**30:.1f} GiB"
    if value >= 2**20:
        return f"{value / 2**20:.1f} MiB"
    if value >= 2**10:
        return f"{value / 2**10:.1f} KiB"
    return f"{value:.0f} B"


def _format_seconds(value: float | None) -> str:
    """Format an integer-oriented duration for table display.

    Args:
        value: Elapsed seconds, or ``None`` when unavailable.

    Returns:
        Whole-second display, or an em dash.
    """
    if value is None:
        return "\u2014"
    return f"{round(float(value)):,}"


def _format_duration(value: float | None) -> str:
    """Format a duration with hours and minutes for the latest-run card.

    Args:
        value: Elapsed seconds, or ``None`` when unavailable.

    Returns:
        Compact ``1h 23m``-style duration, or an em dash.
    """
    if value is None:
        return "\u2014"
    total = int(round(float(value)))
    hours, remainder = divmod(total, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {seconds}s"
    return f"{seconds}s"


def _display_text(record: dict[str, Any], key: str) -> str:
    """Return a non-empty string field for table display.

    Args:
        record: One validated result record.
        key: Record key to display.

    Returns:
        The field value, or an em dash when absent or empty.
    """
    value = record.get(key)
    return value if isinstance(value, str) and value else "\u2014"


def _bitrot_method(record: dict[str, Any]) -> str:
    """Describe the bitrot injection methodology for one record.

    Args:
        record: One validated result record.

    Returns:
        ``mode @ corruption%`` when known, or an em dash.
    """
    mode: str | None = None
    corruption_percent: float | None = None

    configuration = record.get("configuration")
    if isinstance(configuration, dict):
        bitrot = configuration.get("bitrot")
        if isinstance(bitrot, dict):
            mode = bitrot.get("mode")
            corruption_percent = bitrot.get("corruption_percent")

    evidence = record.get("bitrot_evidence")
    if isinstance(evidence, dict):
        for kind in ("full", "diff", "incr"):
            section = evidence.get(kind)
            if not isinstance(section, dict):
                continue
            if mode is None:
                mode = section.get("mode")
            if corruption_percent is None:
                corruption_percent = section.get("corruption_percent")

    if mode is None and corruption_percent is None:
        return "\u2014"
    if mode is None:
        return f"{corruption_percent}%"
    if corruption_percent is None:
        return str(mode)
    return f"{mode} @ {corruption_percent}%"


def _bitrot_extent(record: dict[str, Any]) -> str:
    """Summarize the total corrupted bytes and regions for one record.

    Args:
        record: One validated result record.

    Returns:
        ``bytes / N regions`` when evidence exists, or an em dash.
    """
    evidence = record.get("bitrot_evidence")
    if not isinstance(evidence, dict):
        return "\u2014"

    total_bytes = 0.0
    total_regions = 0
    bytes_found = False
    regions_found = False
    for kind in ("full", "diff", "incr"):
        section = evidence.get(kind)
        if not isinstance(section, dict):
            continue
        length_bytes = section.get("length_bytes")
        region_count = section.get("region_count")
        if isinstance(length_bytes, (int, float)):
            total_bytes += float(length_bytes)
            bytes_found = True
        if isinstance(region_count, (int, float)):
            total_regions += int(region_count)
            regions_found = True

    if not bytes_found and not regions_found:
        return "\u2014"
    parts: list[str] = []
    if bytes_found:
        parts.append(_format_bytes(total_bytes))
    if regions_found:
        parts.append(f"{total_regions} regions")
    return " / ".join(parts)


def _render_charts(
    records: Sequence[dict[str, Any]], chart_dir: Path
) -> tuple[list[Path], str | None]:
    """Render PNG charts into ``chart_dir`` when matplotlib is available.

    Args:
        records: Chronologically ordered result records.
        chart_dir: Destination directory for chart images.

    Returns:
        Chart paths and a human-readable reason when charts were skipped.
    """
    mpl_config_dir = Path(tempfile.mkdtemp(prefix="mplconfig-"))
    previous_mpl_config = os.environ.get("MPLCONFIGDIR")
    os.environ["MPLCONFIGDIR"] = str(mpl_config_dir)
    try:
        try:
            import matplotlib

            matplotlib.use("Agg")
            import matplotlib.dates as mdates
            import matplotlib.pyplot as plt
            from matplotlib.patches import Patch
            from matplotlib.ticker import FuncFormatter
        except ImportError:
            return [], "matplotlib is not installed; charts were skipped"

        chart_dir.mkdir(parents=True, exist_ok=True)
        chart_paths: list[Path] = []

        series_records: dict[str, list[dict[str, Any]]] = {}
        for record in records:
            series_records.setdefault(_image_series(record), []).append(record)

        for series in sorted(series_records):
            series_data = series_records[series]
            series_run_dates = [
                date.fromisoformat(record["date"]) for record in series_data
            ]
            series_x = mdates.date2num(series_run_dates)

            status_chart = chart_dir / f"status-timeline-{series}.png"
            figure, axis = plt.subplots(figsize=(10, 1.8))
            daily_worst = _daily_worst_status(series_data)
            for run_date, run_status in sorted(daily_worst.items()):
                axis.bar(
                    mdates.date2num(date.fromisoformat(run_date)),
                    1.0,
                    width=0.85,
                    color=STATUS_COLORS[run_status],
                    align="center",
                )
            axis.set_ylim(0, 1)
            axis.set_yticks([])
            axis.set_title(f"Run outcome over time ({series}, worst per day)")
            axis.legend(
                handles=[
                    Patch(facecolor=STATUS_COLORS[key], label=label)
                    for key, label in STATUS_LABELS.items()
                ],
                loc="upper left",
                ncol=3,
                frameon=False,
                fontsize="small",
            )
            axis.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
            figure.autofmt_xdate()
            figure.savefig(status_chart, dpi=144, bbox_inches="tight")
            plt.close(figure)
            chart_paths.append(status_chart)

            durations_chart = chart_dir / f"durations-{series}.png"
            figure, axis = plt.subplots(figsize=(10, 4))
            axis.plot(
                series_x,
                [record.get("overall_elapsed_s") for record in series_data],
                marker="o",
                markersize=3,
                label="overall",
            )
            axis.plot(
                series_x,
                [record.get("full_elapsed_s") for record in series_data],
                marker=".",
                markersize=2,
                linestyle="--",
                label="full backup",
            )
            axis.set_ylabel("Elapsed seconds")
            axis.set_title(f"Elapsed time over time ({series})")
            axis.legend()
            axis.grid(alpha=0.3)
            axis.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
            figure.autofmt_xdate()
            figure.savefig(durations_chart, dpi=144, bbox_inches="tight")
            plt.close(figure)
            chart_paths.append(durations_chart)

            sizes_chart = chart_dir / f"sizes-{series}.png"
            figure, axis = plt.subplots(figsize=(10, 4))
            axis.semilogy(
                series_x,
                [_source_bytes(record) for record in series_data],
                marker="o",
                markersize=3,
                label="source dataset",
            )
            axis.semilogy(
                series_x,
                [_full_archive_bytes(record) for record in series_data],
                marker=".",
                markersize=2,
                linestyle="--",
                label="full archive",
            )
            axis.set_ylabel("Size (log scale)")
            axis.yaxis.set_major_formatter(FuncFormatter(_format_axis_bytes))
            axis.set_title(f"Data sizes over time ({series})")
            axis.legend()
            axis.grid(alpha=0.3, which="both")
            axis.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
            figure.autofmt_xdate()
            figure.savefig(sizes_chart, dpi=144, bbox_inches="tight")
            plt.close(figure)
            chart_paths.append(sizes_chart)

            memory_chart = chart_dir / f"memory-{series}.png"
            figure, axis = plt.subplots(figsize=(10, 4))
            memories = [_memory_mib(record) for record in series_data]
            for process in PROCESS_ORDER:
                axis.plot(
                    series_x,
                    [measurement.get(process) for measurement in memories],
                    marker=".",
                    markersize=2,
                    label=process,
                    color=PROCESS_COLORS[process],
                )
            axis.set_ylabel("Peak RSS (MiB)")
            axis.set_title(f"Peak process memory over time ({series})")
            axis.legend()
            axis.grid(alpha=0.3)
            axis.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
            figure.autofmt_xdate()
            figure.savefig(memory_chart, dpi=144, bbox_inches="tight")
            plt.close(figure)
            chart_paths.append(memory_chart)
    finally:
        if previous_mpl_config is None:
            os.environ.pop("MPLCONFIGDIR", None)
        else:
            os.environ["MPLCONFIGDIR"] = previous_mpl_config
        shutil.rmtree(mpl_config_dir, ignore_errors=True)

    return chart_paths, None


def _render_chart_table(chart_refs: Sequence[str]) -> list[str]:
    """Render chart references as a two-column dev/published table.

    Args:
        chart_refs: Chart image references relative to the output file.

    Returns:
        Markdown lines for the two-column chart table.
    """
    refs_by_stem = {Path(reference).stem: reference for reference in chart_refs}
    lines = [
        '<table width="100%">',
        "<tr><th>Dev</th><th>Published</th></tr>",
    ]
    for chart_type in CHART_TYPES:
        cells: list[str] = []
        for series in IMAGE_SERIES_ORDER:
            reference = refs_by_stem.get(f"{chart_type}-{series}")
            if reference is None:
                cells.append("\u2014")
            else:
                label = chart_type.replace("-", " ").capitalize()
                cells.append(
                    f'<img src="{reference}" alt="{label} ({series})" width="100%">'
                )
        lines.append("<tr>")
        for cell in cells:
            lines.append('<td width="50%">')
            lines.append(cell)
            lines.append("</td>")
        lines.append("</tr>")
    lines.append("</table>")
    lines.append("")
    return lines


def _render_markdown(
    records: Sequence[dict[str, Any]],
    source_path: Path,
    generated_at: str,
    chart_refs: Sequence[str],
    charts_note: str | None,
) -> str:
    """Render the complete Markdown overview document.

    Args:
        records: Chronologically ordered result records.
        source_path: Input JSONL path for the provenance header.
        generated_at: ISO timestamp of generation.
        chart_refs: Chart image references relative to the output file.
        charts_note: Optional note explaining skipped charts.

    Returns:
        Rendered Markdown document.
    """
    statuses = [_result_status(record) for record in records]
    pass_count = statuses.count("pass")
    fail_count = statuses.count("fail")
    incomplete_count = statuses.count("incomplete")
    series_breakdown = _series_breakdown(records)
    dates = [record["date"] for record in records]
    versions = sorted({record.get("dar_backup_version") for record in records if record.get("dar_backup_version")})
    operating_systems = sorted({record.get("os_desc") for record in records if record.get("os_desc")})
    kernels = sorted({record.get("kernel") for record in records if record.get("kernel")})
    test_names = sorted(
        {record.get("test_name") for record in records if record.get("test_name")}
    )

    latest = max(records, key=lambda item: (item["date"], item.get("datestamp", "")))
    latest_status = _result_status(latest)

    lines: list[str] = []
    lines.append(GENERATED_FILE_LICENSE_HEADER)
    lines.append("")
    lines.append("# Test reports at a page")
    lines.append("")
    lines.append(
        f"_Generated {generated_at} from "
        f"`{source_path}` ({len(records)} runs)._"
    )
    lines.append("")

    lines.append("## Summary")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("| --- | --- |")
    lines.append(f"| Runs | {len(records)} |")
    lines.append(
        f"| Outcome | {STATUS_EMOJI['pass']} {pass_count} pass, "
        f"{STATUS_EMOJI['fail']} {fail_count} fail, "
        f"{STATUS_EMOJI['incomplete']} {incomplete_count} incomplete |"
    )
    for series in IMAGE_SERIES_ORDER:
        counts = series_breakdown.get(series)
        if counts is None:
            continue
        total = sum(counts.values())
        detail = ", ".join(
            f"{counts[key]} {STATUS_LABELS[key].lower()}"
            for key in ("pass", "fail", "incomplete")
        )
        lines.append(f"| {series.capitalize()} runs | {total} ({detail}) |")
    lines.append(f"| Date range | {min(dates)} to {max(dates)} |")
    lines.append(f"| dar-backup versions | {', '.join(versions)} |")
    lines.append(f"| Test profiles | {', '.join(test_names) or '\u2014'} |")
    lines.append(f"| Operating systems | {', '.join(operating_systems) or '\u2014'} |")
    lines.append(f"| Kernels | {', '.join(kernels) or '\u2014'} |")
    lines.append("")

    lines.append("## Latest run")
    lines.append("")
    lines.append("| Field | Value |")
    lines.append("| --- | --- |")
    lines.append(f"| Date | {latest['date']} |")
    lines.append(f"| Test | {_display_text(latest, 'test_name')} |")
    lines.append(f"| Image version | {_display_text(latest, 'image_version')} |")
    lines.append(f"| dar-backup | {_display_text(latest, 'dar_backup_version')} |")
    lines.append(f"| Result | {STATUS_EMOJI[latest_status]} {STATUS_LABELS[latest_status]} |")
    lines.append(f"| Full backup | {_format_duration(latest.get('full_elapsed_s'))} |")
    lines.append(f"| Overall | {_format_duration(latest.get('overall_elapsed_s'))} |")
    lines.append(f"| Source dataset | {_format_bytes(_source_bytes(latest))} |")
    lines.append(f"| Full archive | {_format_bytes(_full_archive_bytes(latest))} |")
    peak_rss = _peak_rss_mib(latest)
    peak_rss_text = f"{peak_rss:.1f} MiB" if peak_rss is not None else "\u2014"
    lines.append(f"| Peak RSS | {peak_rss_text} |")
    lines.append(f"| Bitrot method | {_bitrot_method(latest)} |")
    lines.append(f"| Bitrot extent | {_bitrot_extent(latest)} |")
    lines.append("")

    lines.append("## Runs")
    lines.append("")
    lines.append(
        "| Date | Test | Image | dar-backup | Result | Full (s) | Overall (s) | "
        "Source | Archive | Peak RSS | Bitrot method | Bitrot extent |"
    )
    lines.append(
        "| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- |"
    )
    for record in records:
        status = _result_status(record)
        peak = _peak_rss_mib(record)
        peak_text = f"{peak:.1f} MiB" if peak is not None else "\u2014"
        lines.append(
            f"| {record['date']} | {_display_text(record, 'test_name')} | "
            f"{_display_text(record, 'image_version')} | "
            f"{_display_text(record, 'dar_backup_version')} | "
            f"{STATUS_EMOJI[status]} {STATUS_LABELS[status]} | "
            f"{_format_seconds(record.get('full_elapsed_s'))} | "
            f"{_format_seconds(record.get('overall_elapsed_s'))} | "
            f"{_format_bytes(_source_bytes(record))} | "
            f"{_format_bytes(_full_archive_bytes(record))} | {peak_text} | "
            f"{_bitrot_method(record)} | {_bitrot_extent(record)} |"
        )
    lines.append("")

    problem_records = [record for record in records if _result_status(record) != "pass"]
    if problem_records:
        lines.append("## Failures and incomplete runs")
        lines.append("")
        lines.append("| Date | Test | Result | Aborted phase | Exit code | Failures |")
        lines.append("| --- | --- | --- | --- | ---: | ---: |")
        for record in problem_records:
            status = _result_status(record)
            exit_code = record.get("exit_code")
            failures = record.get("failures")
            lines.append(
                f"| {record['date']} | {_display_text(record, 'test_name')} | "
                f"{STATUS_EMOJI[status]} {STATUS_LABELS[status]} | "
                f"{_display_text(record, 'aborted_phase')} | "
                f"{exit_code if exit_code is not None else '\u2014'} | "
                f"{failures if failures is not None else '\u2014'} |"
            )
        lines.append("")

    lines.append("## Charts")
    lines.append("")
    if chart_refs:
        lines.extend(_render_chart_table(chart_refs))
    if charts_note:
        lines.append(f"> {charts_note}")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("_Generated by `scripts/test_reports_at_a_page.py`._")
    lines.append("")
    return "\n".join(lines)


def build_report(
    input_path: Path,
    output_path: Path,
    chart_dir: Path | None,
    with_graphs: bool,
) -> dict[str, Any]:
    """Parse the results file and write the Markdown overview.

    Args:
        input_path: JSONL test results file.
        output_path: Markdown file to write.
        chart_dir: Directory for chart images, or ``None`` to disable charts.
        with_graphs: Whether charts are requested.

    Returns:
        Report metadata including the number of records and rendered charts.

    Raises:
        ValueError: If the input file is invalid or no records are present.
    """
    records = _parse_records(input_path)

    chart_refs: list[str] = []
    charts_note: str | None = None
    if with_graphs and chart_dir is not None:
        chart_paths, charts_note = _render_charts(records, chart_dir)
        output_parent = output_path.parent
        chart_refs = [os.path.relpath(path, output_parent) for path in chart_paths]
    elif with_graphs:
        charts_note = "chart directory not configured; charts were skipped"

    generated_at = datetime.now().astimezone().isoformat(timespec="seconds")
    markdown = _render_markdown(
        records,
        input_path,
        generated_at,
        chart_refs,
        charts_note,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown, encoding="utf-8")
    return {
        "records": len(records),
        "charts": chart_refs,
        "charts_note": charts_note,
        "output": str(output_path),
    }


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments for the report generator.

    Args:
        argv: Command-line arguments, or ``None`` to use ``sys.argv``.

    Returns:
        Parsed argument namespace.
    """
    parser = argparse.ArgumentParser(
        description="Render a one-page Markdown overview of large-scale test results."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("doc/test-report/large-scale-results.jsonl"),
        help="JSONL test results file (default: %(default)s)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("doc/test-report/test-reports-at-a-page.md"),
        help="Markdown report to write (default: %(default)s)",
    )
    parser.add_argument(
        "--chart-dir",
        type=Path,
        default=Path("doc/test-report/charts"),
        help="Directory for chart images (default: %(default)s)",
    )
    parser.add_argument(
        "--no-graphs",
        action="store_true",
        help="Disable chart rendering even when matplotlib is available",
    )
    return parser.parse_args(argv)


def main() -> int:
    """Run the report generator from the command line.

    Returns:
        Zero on success and two for invalid input.
    """
    args = _parse_args()
    try:
        result = build_report(
            input_path=args.input,
            output_path=args.output,
            chart_dir=args.chart_dir,
            with_graphs=not args.no_graphs,
        )
    except ValueError as error:
        LOGGER.error("Unable to build test report: %s", error)
        return 2

    LOGGER.info(
        "Wrote %s from %d records", result["output"], result["records"]
    )
    if result["charts"]:
        LOGGER.info("Rendered %d chart image(s)", len(result["charts"]))
    if result["charts_note"]:
        LOGGER.warning("%s", result["charts_note"])
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    raise SystemExit(main())
