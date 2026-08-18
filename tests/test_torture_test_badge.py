"""Tests for defensive torture-test badge generation."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any


MODULE_PATH = Path(__file__).parents[1] / "scripts" / "write_torture_test_badge.py"
MODULE_SPEC = importlib.util.spec_from_file_location("write_torture_test_badge", MODULE_PATH)
if MODULE_SPEC is None or MODULE_SPEC.loader is None:
    raise RuntimeError(f"Unable to load badge generator from {MODULE_PATH}")
BADGE_MODULE = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(BADGE_MODULE)
build_badge_payload = BADGE_MODULE.build_badge_payload
load_records = BADGE_MODULE.load_records
select_latest_advertised = BADGE_MODULE.select_latest_advertised
write_badge = BADGE_MODULE.write_badge


def _base_record() -> dict[str, Any]:
    """Build a complete advertised result using the current engineering layout.

    Returns:
        One representative advertised result.
    """
    phase = {
        "mode": "fragmented",
        "corruption_percent": 2,
        "status": "passed",
    }
    return {
        "schema_version": 8,
        "advertise": True,
        "test_name": "Large scale torture test",
        "advertise_class": "v0.5.29",
        "source_bytes": 522_454_998_584,
        "date": "2026-08-11",
        "datestamp": "2026-08-11_20-14-21",
        "checks": {
            "par2_verify": {"full": "passed", "diff": "passed", "incr": "passed"},
            "pitr_restore": {"overall": "passed"},
            "full_restore": {
                "mode": "forced",
                "threshold_bytes": 25 * 1024**3,
                "source_bytes": 522_454_998_584,
                "performed": True,
                "decision_reason": "forced_by_user",
                "execution": "passed",
                "content_comparison": "passed",
                "portable_metadata": "passed",
                "overall": "passed",
                "restored_file_count": 220_487,
                "restored_bytes": 522_459_193_040,
                "restored_entry_count": 220_500,
                "ownership_entry_count": 220_500,
                "permission_entry_count": 220_499,
                "posix_acl_count": 2,
                "portable_xattr_count": 3,
                "hard_link_group_count": 1,
                "metadata_profile": "portable-posix-v1",
                "source_filesystem": "btrfs",
                "restore_filesystem": "btrfs",
                "source_filesystem_device": 44,
                "restore_filesystem_device": 44,
                "same_filesystem": True,
            },
        },
        "bitrot_evidence": {
            "full": dict(phase),
            "diff": dict(phase),
            "incr": dict(phase),
        },
    }


def _write_jsonl(path: Path, records: list[Any]) -> None:
    """Write JSON-serializable values as an isolated JSONL history.

    Args:
        path: Destination history path.
        records: Values to encode one per line.
    """
    encoded = "".join(json.dumps(record) + "\n" for record in records)
    path.write_text(encoded, encoding="utf-8")


def test_build_badge_complete_result_includes_available_evidence() -> None:
    """A complete result produces the intended concise evidence message."""
    payload = build_badge_payload(_base_record())

    assert payload == {
        "schemaVersion": 1,
        "label": "Large scale torture test",
        "message": (
            "v0.5.29 · 486.6 GiB · 2% fragmented bitrot repaired · "
            "PAR2 ✓ · PITR ✓ · Full restore verified ✓ · 2026-08-11"
        ),
        "labelColor": "#6f42c1",
        "color": "#2ea043",
    }


def test_build_badge_missing_pitr_omits_pitr_component() -> None:
    """Missing PITR evidence is omitted rather than reported as failure."""
    record = _base_record()
    del record["checks"]["pitr_restore"]

    payload = build_badge_payload(record)

    assert "PITR" not in payload["message"]


def test_build_badge_passed_full_restore_includes_component() -> None:
    """Complete coherent restore evidence produces an explicit badge claim."""
    payload = build_badge_payload(_base_record())

    assert "Full restore verified ✓" in payload["message"]


def test_build_badge_passed_auto_full_restore_includes_component() -> None:
    """A coherent automatic restore receives the same truthful success claim."""
    record = _base_record()
    record["checks"]["full_restore"].update(
        {
            "mode": "auto",
            "threshold_bytes": 500 * 1024**3,
            "decision_reason": "source_within_threshold",
        }
    )

    payload = build_badge_payload(record)

    assert "Full restore verified ✓" in payload["message"]


def test_build_badge_skipped_full_restore_omits_component() -> None:
    """A size-based full-restore skip cannot produce a success claim."""
    record = _base_record()
    record["checks"]["full_restore"].update(
        {
            "mode": "auto",
            "performed": False,
            "decision_reason": "source_exceeds_threshold",
            "execution": "skipped",
            "content_comparison": "skipped",
            "overall": "skipped",
            "restored_file_count": None,
            "restored_bytes": None,
        }
    )

    payload = build_badge_payload(record)

    assert "Full restore" not in payload["message"]


def test_build_badge_failed_full_restore_omits_component() -> None:
    """A failed content comparison cannot produce a success claim."""
    record = _base_record()
    record["checks"]["full_restore"]["content_comparison"] = "failed"
    record["checks"]["full_restore"]["overall"] = "failed"

    payload = build_badge_payload(record)

    assert "Full restore" not in payload["message"]


def test_build_badge_failed_portable_metadata_omits_component() -> None:
    """Schema-v8 metadata failure cannot produce a full-restore claim."""
    record = _base_record()
    record["checks"]["full_restore"]["portable_metadata"] = "failed"

    payload = build_badge_payload(record)

    assert "Full restore" not in payload["message"]


def test_build_badge_cross_filesystem_schema_v8_omits_component() -> None:
    """Schema-v8 evidence must honor the same-filesystem contract."""
    record = _base_record()
    record["checks"]["full_restore"].update(
        {
            "restore_filesystem": "zfs",
            "restore_filesystem_device": 45,
            "same_filesystem": False,
        }
    )

    payload = build_badge_payload(record)

    assert "Full restore" not in payload["message"]


def test_build_badge_schema_v6_full_restore_remains_compatible() -> None:
    """Earlier coherent full-restore evidence retains its published claim."""
    record = _base_record()
    record["schema_version"] = 6
    for key in (
        "portable_metadata",
        "restored_entry_count",
        "ownership_entry_count",
        "permission_entry_count",
        "posix_acl_count",
        "portable_xattr_count",
        "hard_link_group_count",
        "metadata_profile",
        "source_filesystem",
        "restore_filesystem",
        "source_filesystem_device",
        "restore_filesystem_device",
        "same_filesystem",
    ):
        del record["checks"]["full_restore"][key]

    payload = build_badge_payload(record)

    assert "Full restore verified ✓" in payload["message"]


def test_build_badge_contradictory_full_restore_omits_component() -> None:
    """Performed/status evidence without positive measurements is rejected."""
    record = _base_record()
    record["checks"]["full_restore"]["restored_file_count"] = 0

    payload = build_badge_payload(record)

    assert "Full restore" not in payload["message"]


def test_build_badge_legacy_record_without_full_restore_remains_publishable() -> None:
    """Older advertised records remain valid without gaining a false claim."""
    record = _base_record()
    record["schema_version"] = 5
    del record["checks"]["full_restore"]

    payload = build_badge_payload(record)

    assert "PITR ✓" in payload["message"]
    assert "Full restore" not in payload["message"]


def test_build_badge_missing_par2_omits_par2_component() -> None:
    """Missing PAR2 evidence is omitted rather than reported as failure."""
    record = _base_record()
    del record["checks"]["par2_verify"]

    payload = build_badge_payload(record)

    assert "PAR2" not in payload["message"]


def test_build_badge_missing_bitrot_omits_bitrot_component() -> None:
    """Missing bitrot evidence leaves the remaining badge facts intact."""
    record = _base_record()
    del record["bitrot_evidence"]

    payload = build_badge_payload(record)

    assert "bitrot" not in payload["message"]


def test_build_badge_missing_dataset_size_omits_size_component() -> None:
    """Missing source bytes never fall back to an archive-size field."""
    record = _base_record()
    del record["source_bytes"]
    record["full_size_bytes"] = 999_999_999_999

    payload = build_badge_payload(record)

    assert "GiB" not in payload["message"]


def test_build_badge_missing_date_omits_date_component() -> None:
    """Missing dates do not prevent publication of other evidence."""
    record = _base_record()
    del record["date"]

    payload = build_badge_payload(record)

    assert "2026-08-11" not in payload["message"]


def test_build_badge_unknown_fields_do_not_change_payload() -> None:
    """Unrelated future engineering fields are ignored."""
    original = _base_record()
    changed = _base_record()
    changed["future"] = {"deep": [{"unknown": True}]}

    assert build_badge_payload(changed) == build_badge_payload(original)


def test_build_badge_null_optional_values_are_omitted() -> None:
    """Null optional values are treated as unavailable."""
    record = _base_record()
    record.update(
        {
            "source_bytes": None,
            "date": None,
            "advertise_class": None,
            "bitrot_evidence": None,
            "checks": None,
        }
    )

    payload = build_badge_payload(record)

    assert payload["message"] == "published result"


def test_load_records_malformed_line_followed_by_valid_result_is_tolerated(
    tmp_path: Path,
) -> None:
    """One damaged line is skipped while a later valid candidate is retained.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    history = tmp_path / "results.jsonl"
    history.write_text("{broken\n" + json.dumps(_base_record()) + "\n", encoding="utf-8")

    records, scanned, malformed = load_records(history)
    selected, candidate_count = select_latest_advertised(records)

    assert scanned == 2
    assert malformed == 1
    assert candidate_count == 1
    assert selected == _base_record()


def test_select_latest_advertised_uses_last_candidate_in_file_order() -> None:
    """Append order wins even when candidate date strings suggest otherwise."""
    first = _base_record()
    first["advertise_class"] = "first"
    first["date"] = "2099-01-01"
    second = _base_record()
    second["advertise_class"] = "second"
    second["date"] = "2000-01-01"

    selected, candidate_count = select_latest_advertised([first, second])

    assert candidate_count == 2
    assert selected is second


def test_select_latest_advertised_ignores_false_and_missing_markers() -> None:
    """False and absent advertisement markers are not candidates."""
    false_record = _base_record()
    false_record["advertise"] = False
    missing_record = _base_record()
    del missing_record["advertise"]

    selected, candidate_count = select_latest_advertised([false_record, missing_record])

    assert selected is None
    assert candidate_count == 0


def test_select_latest_advertised_rejects_truthy_non_boolean_markers() -> None:
    """Strings and integers cannot impersonate the exact publication boolean."""
    string_record = _base_record()
    string_record["advertise"] = "true"
    integer_record = _base_record()
    integer_record["advertise"] = 1

    selected, candidate_count = select_latest_advertised([string_record, integer_record])

    assert selected is None
    assert candidate_count == 0


def test_build_badge_no_advertised_record_produces_neutral_payload() -> None:
    """An empty publication state is explicit and does not fabricate success."""
    payload = build_badge_payload(None)

    assert payload["message"] == "no published result"
    assert payload["color"] == "lightgrey"


def test_build_badge_missing_test_name_uses_default_label() -> None:
    """A malformed advertised record still receives the stable default label."""
    record = _base_record()
    del record["test_name"]

    payload = build_badge_payload(record)

    assert payload["label"] == "Large scale torture test"


def test_build_badge_custom_test_name_is_used() -> None:
    """A specialized test can provide its own public label."""
    record = _base_record()
    record["test_name"] = "DAR 2.7 archive restore using DAR 2.8"

    payload = build_badge_payload(record)

    assert payload["label"] == "DAR 2.7 archive restore using DAR 2.8"


def test_build_badge_missing_advertise_class_preserves_other_evidence() -> None:
    """A missing class is omitted without discarding a selected result."""
    record = _base_record()
    del record["advertise_class"]

    payload = build_badge_payload(record)

    assert payload["message"].startswith("486.6 GiB")


def test_build_badge_specialized_future_record_needs_only_publication_envelope() -> None:
    """A substantially different future record remains publishable."""
    record = {
        "advertise": True,
        "test_name": "Cross-version restore",
        "advertise_class": "2.7-to-2.8",
        "future_evidence": [{"result": "excellent"}],
    }

    payload = build_badge_payload(record)

    assert payload["label"] == "Cross-version restore"
    assert payload["message"] == "2.7-to-2.8"


def test_build_badge_conflicting_bitrot_phases_omit_aggregate_claim() -> None:
    """Different per-phase corruption patterns are not misrepresented as one."""
    record = _base_record()
    record["bitrot_evidence"]["incr"]["mode"] = "edges"

    payload = build_badge_payload(record)

    assert "bitrot" not in payload["message"]


def test_build_badge_invalid_numeric_types_are_omitted() -> None:
    """Boolean, negative, and non-finite measurements are not displayed."""
    record = _base_record()
    record["source_bytes"] = True
    record["bitrot_evidence"]["full"]["corruption_percent"] = float("inf")

    payload = build_badge_payload(record)

    assert "GiB" not in payload["message"]
    assert "bitrot" not in payload["message"]


def test_write_badge_identical_payload_is_unchanged(tmp_path: Path) -> None:
    """A second deterministic write reports no byte-level change.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    output = tmp_path / "badge.json"
    payload = build_badge_payload(_base_record())

    first_changed = write_badge(output, payload)
    first_bytes = output.read_bytes()
    second_changed = write_badge(output, payload)

    assert first_changed is True
    assert second_changed is False
    assert output.read_bytes() == first_bytes


def test_load_records_ignores_non_object_and_nonstandard_numeric_lines(
    tmp_path: Path,
) -> None:
    """Arrays and non-standard NaN records count as malformed input.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    history = tmp_path / "results.jsonl"
    history.write_text("[]\n{\"source_bytes\":NaN}\n", encoding="utf-8")

    records, scanned, malformed = load_records(history)

    assert records == []
    assert scanned == 2
    assert malformed == 2
