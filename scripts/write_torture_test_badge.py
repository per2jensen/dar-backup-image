#!/usr/bin/env python3
"""Generate a Shields endpoint badge from advertised torture-test results."""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import tempfile
import unicodedata
from datetime import date
from pathlib import Path
from typing import Any, Mapping, Sequence


LOGGER = logging.getLogger(__name__)
DEFAULT_TEST_NAME = "Large scale torture test"
LABEL_COLOR = "#6f42c1"
SUCCESS_COLOR = "#2ea043"
NEUTRAL_COLOR = "lightgrey"
MAX_LABEL_LENGTH = 80
MAX_COMPONENT_LENGTH = 80
MAX_MESSAGE_LENGTH = 240
PHASE_NAMES = ("full", "diff", "incr")
PORTABLE_RESTORE_FILESYSTEMS = {"ext4", "btrfs", "zfs"}


def _reject_json_constant(value: str) -> None:
    """Reject non-standard JSON numeric constants.

    Args:
        value: Non-standard constant encountered by ``json.loads``.

    Returns:
        This function never returns.

    Raises:
        ValueError: Always, because JSONL records must use standard JSON.
    """
    raise ValueError(f"Non-standard JSON constant {value!r}")


def load_records(path: Path) -> tuple[list[dict[str, Any]], int, int]:
    """Load valid JSON objects from a JSONL history defensively.

    Args:
        path: Existing JSONL history file.

    Returns:
        Valid records, non-blank lines scanned, and malformed lines skipped.

    Raises:
        OSError: If the history cannot be opened or read.
        ValueError: If ``path`` is ``None``.
    """
    if path is None:
        raise ValueError("path must not be None")

    records: list[dict[str, Any]] = []
    scanned = 0
    malformed = 0
    with path.open(encoding="utf-8") as history_file:
        for line_number, line in enumerate(history_file, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            scanned += 1
            try:
                decoded = json.loads(stripped, parse_constant=_reject_json_constant)
            except (json.JSONDecodeError, ValueError) as error:
                malformed += 1
                LOGGER.warning(
                    "Skipping malformed JSONL record at %s:%d: %s",
                    path,
                    line_number,
                    error,
                )
                continue
            if not isinstance(decoded, dict):
                malformed += 1
                LOGGER.warning(
                    "Skipping non-object JSONL record at %s:%d", path, line_number
                )
                continue
            records.append(decoded)
    return records, scanned, malformed


def select_latest_advertised(
    records: Sequence[Mapping[str, Any]],
) -> tuple[Mapping[str, Any] | None, int]:
    """Select the last record explicitly marked for advertisement.

    Args:
        records: Valid JSON objects in append order.

    Returns:
        The last record whose ``advertise`` value is exactly ``True``, and the
        total number of such records.

    Raises:
        ValueError: If ``records`` is ``None``.
    """
    if records is None:
        raise ValueError("records must not be None")

    selected: Mapping[str, Any] | None = None
    candidate_count = 0
    for record in records:
        if record.get("advertise") is not True:
            continue
        selected = record
        candidate_count += 1
    return selected, candidate_count


def safe_get(record: Mapping[str, Any], *keys: str) -> Any | None:
    """Read a nested value without assuming intermediate objects exist.

    Args:
        record: Root object to inspect.
        *keys: Nested string keys to follow.

    Returns:
        The nested value, or ``None`` when the path is unavailable.

    Raises:
        ValueError: If ``record`` is ``None`` or a key is empty.
    """
    if record is None:
        raise ValueError("record must not be None")
    if any(not key for key in keys):
        raise ValueError("safe_get keys must not be empty")

    value: Any = record
    for key in keys:
        if not isinstance(value, Mapping):
            return None
        value = value.get(key)
    return value


def _clean_text(value: Any, max_length: int) -> str | None:
    """Normalize a bounded human-readable string for badge presentation.

    Args:
        value: Candidate value.
        max_length: Maximum number of Unicode code points to retain.

    Returns:
        Clean text, or ``None`` for unavailable or invalid input.

    Raises:
        ValueError: If ``max_length`` is not positive.
    """
    if max_length <= 0:
        raise ValueError("max_length must be positive")
    if not isinstance(value, str):
        return None

    visible = "".join(
        " " if unicodedata.category(character).startswith("C") else character
        for character in value
    )
    cleaned = " ".join(visible.split())
    if not cleaned:
        return None
    if len(cleaned) <= max_length:
        return cleaned
    return cleaned[: max_length - 1].rstrip() + "…"


def _positive_number(value: Any, maximum: float | None = None) -> float | None:
    """Return a finite positive numeric value within an optional bound.

    Args:
        value: Candidate numeric value.
        maximum: Optional inclusive upper bound.

    Returns:
        A validated float, or ``None`` when invalid.

    Raises:
        ValueError: If ``maximum`` is not positive when supplied.
    """
    if maximum is not None and maximum <= 0:
        raise ValueError("maximum must be positive")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        return None
    if maximum is not None and number > maximum:
        return None
    return number


def _format_number(value: float) -> str:
    """Format a finite display number without unnecessary decimal zeros.

    Args:
        value: Validated finite number.

    Returns:
        Compact decimal text.

    Raises:
        ValueError: If ``value`` is not finite.
    """
    if not math.isfinite(value):
        raise ValueError("value must be finite")
    if value.is_integer():
        return str(int(value))
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _dataset_size_component(record: Mapping[str, Any]) -> str | None:
    """Build the source-dataset size component.

    Args:
        record: Advertised result record.

    Returns:
        A GiB component, or ``None`` when source bytes are unavailable.

    Raises:
        ValueError: If ``record`` is ``None``.
    """
    if record is None:
        raise ValueError("record must not be None")
    source_bytes = _positive_number(record.get("source_bytes"))
    if source_bytes is None:
        return None
    return f"{source_bytes / 1024**3:.1f} GiB"


def _bitrot_component(record: Mapping[str, Any]) -> str | None:
    """Build a truthful aggregate bitrot evidence component.

    Args:
        record: Advertised result record.

    Returns:
        Concise bitrot evidence, or ``None`` when phase evidence is missing or
        conflicts.

    Raises:
        ValueError: If ``record`` is ``None``.
    """
    if record is None:
        raise ValueError("record must not be None")
    evidence = record.get("bitrot_evidence")
    if not isinstance(evidence, Mapping):
        return None

    phases = [evidence.get(name) for name in PHASE_NAMES]
    available = [phase for phase in phases if isinstance(phase, Mapping)]
    if not available:
        return None

    modes = [_clean_text(phase.get("mode"), MAX_COMPONENT_LENGTH) for phase in available]
    percentages = [
        _positive_number(phase.get("corruption_percent"), maximum=100.0)
        for phase in available
    ]
    if any(mode is None for mode in modes) or len(set(modes)) != 1:
        return None
    if any(percent is None for percent in percentages) or len(set(percentages)) != 1:
        return None

    mode = modes[0]
    percent = percentages[0]
    if mode is None or percent is None:
        return None
    repaired = all(phase.get("status") == "passed" for phase in available)
    suffix = " repaired" if repaired else ""
    if mode == "edges":
        edge_percentages = [
            _positive_number(phase.get("edge_percent"), maximum=50.0)
            for phase in available
        ]
        region_counts = [phase.get("region_count") for phase in available]
        has_consistent_edges = (
            not any(edge_percent is None for edge_percent in edge_percentages)
            and len(set(edge_percentages)) == 1
            and all(
                isinstance(region_count, int)
                and not isinstance(region_count, bool)
                and region_count == 2
                for region_count in region_counts
            )
        )
        if has_consistent_edges:
            edge_percent = edge_percentages[0]
            if edge_percent is not None and all(
                math.isclose(
                    phase_percent,
                    edge_percent * 2,
                    rel_tol=0.0,
                    abs_tol=1e-9,
                )
                for phase_percent in percentages
            ):
                return (
                    f"{_format_number(edge_percent)}% bitrot{suffix} "
                    "at both archive edges"
                )
        return f"archive-edge bitrot{suffix}"
    return f"{_format_number(percent)}% {mode} bitrot{suffix}"


def _all_available_checks_passed(value: Any) -> bool:
    """Determine whether a check object has only explicit passed outcomes.

    Args:
        value: Candidate mapping of check names to statuses.

    Returns:
        ``True`` when at least one status exists and every status is ``passed``.

    Raises:
        This function does not raise exceptions.
    """
    if not isinstance(value, Mapping) or not value:
        return False
    statuses = list(value.values())
    return bool(statuses) and all(status == "passed" for status in statuses)


def _full_restore_component(record: Mapping[str, Any]) -> str | None:
    """Build a badge claim from internally consistent full-restore evidence.

    Args:
        record: Advertised schema-v6-or-later result record.

    Returns:
        A concise success component, or ``None`` when evidence is absent,
        incomplete, skipped, failed, or contradictory.

    Raises:
        ValueError: If ``record`` is ``None``.
    """
    if record is None:
        raise ValueError("record must not be None")
    evidence = safe_get(record, "checks", "full_restore")
    if not isinstance(evidence, Mapping):
        return None
    if evidence.get("performed") is not True:
        return None
    if any(
        evidence.get(key) != "passed"
        for key in ("execution", "content_comparison", "overall")
    ):
        return None

    schema_version = record.get("schema_version")
    if (
        isinstance(schema_version, int)
        and not isinstance(schema_version, bool)
        and schema_version >= 8
        and not _portable_metadata_evidence_is_consistent(evidence)
    ):
        return None

    restored_file_count = evidence.get("restored_file_count")
    restored_bytes = evidence.get("restored_bytes")
    threshold_bytes = evidence.get("threshold_bytes")
    evidence_source_bytes = evidence.get("source_bytes")
    record_source_bytes = record.get("source_bytes")
    positive_integers = (
        restored_file_count,
        restored_bytes,
        threshold_bytes,
        evidence_source_bytes,
        record_source_bytes,
    )
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value <= 0
        for value in positive_integers
    ):
        return None
    if evidence_source_bytes != record_source_bytes:
        return None

    mode = evidence.get("mode")
    decision_reason = evidence.get("decision_reason")
    if mode == "auto":
        if decision_reason != "source_within_threshold":
            return None
        if evidence_source_bytes > threshold_bytes:
            return None
    elif mode == "forced":
        if decision_reason != "forced_by_user":
            return None
    else:
        return None
    return "Full restore verified ✓"


def _portable_metadata_evidence_is_consistent(evidence: Mapping[str, Any]) -> bool:
    """Validate the additional same-filesystem schema-v8 restore contract.

    Args:
        evidence: Full-restore check object from an advertised record.

    Returns:
        ``True`` only for complete, internally consistent portable metadata
        evidence.

    Raises:
        ValueError: If ``evidence`` is ``None``.
    """
    if evidence is None:
        raise ValueError("evidence must not be None")
    if evidence.get("portable_metadata") != "passed":
        return False
    if evidence.get("metadata_profile") != "portable-posix-v1":
        return False
    if evidence.get("same_filesystem") is not True:
        return False

    source_filesystem = _clean_text(
        evidence.get("source_filesystem"), MAX_COMPONENT_LENGTH
    )
    restore_filesystem = _clean_text(
        evidence.get("restore_filesystem"), MAX_COMPONENT_LENGTH
    )
    if source_filesystem is None or source_filesystem != restore_filesystem:
        return False
    if source_filesystem not in PORTABLE_RESTORE_FILESYSTEMS:
        return False

    source_device = evidence.get("source_filesystem_device")
    restore_device = evidence.get("restore_filesystem_device")
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value < 0
        for value in (source_device, restore_device)
    ):
        return False
    if source_device != restore_device:
        return False

    entry_count = evidence.get("restored_entry_count")
    ownership_count = evidence.get("ownership_entry_count")
    permission_count = evidence.get("permission_entry_count")
    acl_count = evidence.get("posix_acl_count")
    xattr_count = evidence.get("portable_xattr_count")
    hard_link_count = evidence.get("hard_link_group_count")
    counts = (
        entry_count,
        ownership_count,
        permission_count,
        acl_count,
        xattr_count,
        hard_link_count,
    )
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value < 0
        for value in counts
    ):
        return False
    if entry_count <= 0 or ownership_count != entry_count:
        return False
    if permission_count <= 0 or permission_count > entry_count:
        return False
    if acl_count < 2 or xattr_count < 3 or hard_link_count < 1:
        return False
    return True


def _date_component(record: Mapping[str, Any]) -> str | None:
    """Extract a valid ISO calendar date.

    Args:
        record: Advertised result record.

    Returns:
        ISO date text, or ``None`` when unavailable or invalid.

    Raises:
        ValueError: If ``record`` is ``None``.
    """
    if record is None:
        raise ValueError("record must not be None")
    value = _clean_text(record.get("date"), MAX_COMPONENT_LENGTH)
    if value is None:
        return None
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return None
    return parsed.isoformat()


def _bounded_message(components: Sequence[str]) -> str:
    """Join message components without exceeding the badge length limit.

    Args:
        components: Ordered non-empty presentation components.

    Returns:
        A bounded message, or ``published result`` when no component exists.

    Raises:
        ValueError: If ``components`` is ``None``.
    """
    if components is None:
        raise ValueError("components must not be None")
    accepted: list[str] = []
    for component in components:
        candidate = " · ".join([*accepted, component])
        if len(candidate) > MAX_MESSAGE_LENGTH:
            break
        accepted.append(component)
    return " · ".join(accepted) if accepted else "published result"


def build_badge_payload(record: Mapping[str, Any] | None) -> dict[str, Any]:
    """Build Shields endpoint presentation data for one selected record.

    Args:
        record: Selected advertised result, or ``None`` for the neutral state.

    Returns:
        Shields-compatible endpoint JSON data.

    Raises:
        This function does not raise exceptions for record content.
    """
    if record is None:
        return {
            "schemaVersion": 1,
            "label": DEFAULT_TEST_NAME,
            "message": "no published result",
            "labelColor": LABEL_COLOR,
            "color": NEUTRAL_COLOR,
        }

    label = _clean_text(record.get("test_name"), MAX_LABEL_LENGTH)
    advertise_class = _clean_text(record.get("advertise_class"), MAX_COMPONENT_LENGTH)
    components = [
        component
        for component in (
            advertise_class,
            _dataset_size_component(record),
            _bitrot_component(record),
            "PAR2 ✓" if _all_available_checks_passed(safe_get(record, "checks", "par2_verify")) else None,
            "PITR ✓" if safe_get(record, "checks", "pitr_restore", "overall") == "passed" else None,
            _full_restore_component(record),
            _date_component(record),
        )
        if component is not None
    ]
    return {
        "schemaVersion": 1,
        "label": label or DEFAULT_TEST_NAME,
        "message": _bounded_message(components),
        "labelColor": LABEL_COLOR,
        "color": SUCCESS_COLOR,
    }


def write_badge(path: Path, payload: Mapping[str, Any]) -> bool:
    """Atomically write deterministic badge JSON only when content changed.

    Args:
        path: Destination JSON path.
        payload: JSON-serializable Shields endpoint data.

    Returns:
        ``True`` when the destination changed, otherwise ``False``.

    Raises:
        OSError: If the destination cannot be read, created, or replaced.
        TypeError: If ``payload`` is not JSON serializable.
        ValueError: If a required argument is ``None``.
    """
    if path is None:
        raise ValueError("path must not be None")
    if payload is None:
        raise ValueError("payload must not be None")

    encoded = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") == encoded:
        return False

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            delete=False,
        ) as temporary_file:
            temporary_file.write(encoded)
            temporary_path = Path(temporary_file.name)
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
    return True


def _argument_parser() -> argparse.ArgumentParser:
    """Build the command-line parser.

    Returns:
        Configured parser for history and output paths.

    Raises:
        This function does not raise exceptions.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--history",
        type=Path,
        default=Path("doc/test-report/large-scale-results.jsonl"),
        help="JSONL result history",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("doc/test-report/torture-test-badge.json"),
        help="Shields endpoint JSON destination",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Generate the endpoint and emit concise processing diagnostics.

    Args:
        argv: Optional command-line arguments excluding the program name.

    Returns:
        Zero on success and one for a read or publication failure.

    Raises:
        This function converts expected operational failures into an exit code.
    """
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    arguments = _argument_parser().parse_args(argv)
    try:
        records, scanned, malformed = load_records(arguments.history)
        selected, candidate_count = select_latest_advertised(records)
        payload = build_badge_payload(selected)
        changed = write_badge(arguments.output, payload)
    except (OSError, TypeError, ValueError) as error:
        LOGGER.error("Unable to generate torture-test badge: %s", error)
        return 1

    LOGGER.info("JSONL records scanned: %d", scanned)
    LOGGER.info("Malformed records skipped: %d", malformed)
    LOGGER.info("advertise=true records found: %d", candidate_count)
    if selected is not None:
        LOGGER.info("Selected record timestamp: %s", selected.get("datestamp"))
        LOGGER.info("Selected test_name: %s", payload["label"])
        LOGGER.info("Selected advertise_class: %s", selected.get("advertise_class"))
    LOGGER.info("Generated badge message: %s", payload["message"])
    LOGGER.info("Badge JSON changed: %s", "yes" if changed else "no")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
