"""Tests for the build-history-driven README release table."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Sequence


SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "update_readme_releases.py"
REAL_HISTORY_PATH = Path(__file__).parents[1] / "doc" / "build-history.json"
START_MARKER = "<!-- BEGIN GENERATED RELEASE TABLE -->"
END_MARKER = "<!-- END GENERATED RELEASE TABLE -->"
README_TEMPLATE = f"""Before table.

{START_MARKER}
stale table
{END_MARKER}

After table.
"""


def _entry(
    tag: str,
    build_number: int,
    created: str = "2026-07-08T17:32:09Z",
) -> dict[str, Any]:
    """Build one complete synthetic history entry.

    Args:
        tag: Image release or refresh tag.
        build_number: Monotonic history build number.
        created: ISO-8601 build timestamp.

    Returns:
        JSON-serializable build-history entry.
    """
    return {
        "tag": tag,
        "build_number": build_number,
        "created": created,
        "dar_backup_version": f"1.1.{build_number}",
        "dar_version": "2.7.21",
        "git_revision": f"revision{build_number}",
        "dockerhub_tag_url": (
            f"https://hub.docker.com/layers/example/dar-backup/{tag}/images/"
            f"sha256:digest{build_number}"
        ),
    }


def _write_inputs(
    tmp_path: Path,
    entries: Sequence[dict[str, Any]],
    readme_content: str = README_TEMPLATE,
) -> tuple[Path, Path]:
    """Write isolated history and README inputs.

    Args:
        tmp_path: Isolated pytest temporary directory.
        entries: History entries to serialize.
        readme_content: Initial README text.

    Returns:
        A ``(history_path, readme_path)`` tuple.
    """
    history_path = tmp_path / "build-history.json"
    readme_path = tmp_path / "README.md"
    history_path.write_text(json.dumps(entries), encoding="utf-8")
    readme_path.write_text(readme_content, encoding="utf-8")
    return history_path, readme_path


def _run_generator(
    history_path: Path, readme_path: Path, *arguments: str
) -> subprocess.CompletedProcess[str]:
    """Run the real generator CLI against isolated files.

    Args:
        history_path: Input build-history file.
        readme_path: README file to update or verify.
        arguments: Additional generator arguments.

    Returns:
        Completed subprocess result without an automatic return-code check.
    """
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--history",
            str(history_path),
            "--readme",
            str(readme_path),
            *arguments,
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def test_generator_renders_newest_five_releases_with_utc_dates(
    tmp_path: Path,
) -> None:
    """Generation orders releases and excludes refresh and test tags.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    entries = [
        _entry("0.0.1-releasetest", 1),
        _entry("0.5.24", 24),
        _entry("0.5.25", 25),
        _entry("0.5.25.1", 26),
        _entry("0.5.26", 27),
        _entry("0.5.27", 28),
        _entry("0.5.28", 29, "2026-07-09T00:30:00+02:00"),
        _entry("0.5.28-1", 30),
    ]
    history_path, readme_path = _write_inputs(tmp_path, entries)

    result = _run_generator(history_path, readme_path)

    assert result.returncode == 0, result.stderr
    content = readme_path.read_text(encoding="utf-8")
    release_rows = [line for line in content.splitlines() if line.startswith("| 0.")]
    assert [row.split("|")[1].strip() for row in release_rows] == [
        "0.5.28",
        "0.5.27",
        "0.5.26",
        "0.5.25.1",
        "0.5.25",
    ]
    assert "| 0.5.28 | 1.1.29 | 2.7.21 | 2026-07-08 |" in content
    assert "0.5.28-1" not in content
    assert "0.0.1-releasetest" not in content
    assert content.startswith("Before table.\n")
    assert content.endswith("\nAfter table.\n")


def test_generator_second_update_is_idempotent_and_check_passes(
    tmp_path: Path,
) -> None:
    """Repeated generation is byte-identical and accepted by check mode.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    history_path, readme_path = _write_inputs(tmp_path, [_entry("0.5.28", 28)])

    first_result = _run_generator(history_path, readme_path)
    first_content = readme_path.read_bytes()
    second_result = _run_generator(history_path, readme_path)
    check_result = _run_generator(history_path, readme_path, "--check")

    assert first_result.returncode == 0, first_result.stderr
    assert second_result.returncode == 0, second_result.stderr
    assert check_result.returncode == 0, check_result.stderr
    assert readme_path.read_bytes() == first_content


def test_generator_check_stale_table_fails_without_writing(tmp_path: Path) -> None:
    """Check mode detects drift while leaving README untouched.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    history_path, readme_path = _write_inputs(tmp_path, [_entry("0.5.28", 28)])
    original = readme_path.read_bytes()

    result = _run_generator(history_path, readme_path, "--check")

    assert result.returncode == 1
    assert "README release table is stale" in result.stderr
    assert readme_path.read_bytes() == original


def test_generator_missing_markers_fails_without_replacing_readme(
    tmp_path: Path,
) -> None:
    """Generation refuses to guess a replacement region without markers.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    history_path, readme_path = _write_inputs(
        tmp_path, [_entry("0.5.28", 28)], "README without markers\n"
    )
    original = readme_path.read_bytes()

    result = _run_generator(history_path, readme_path)

    assert result.returncode == 2
    assert "exactly one generated release-table marker pair" in result.stderr
    assert readme_path.read_bytes() == original


def test_generator_malformed_history_json_fails(tmp_path: Path) -> None:
    """Malformed canonical history produces a clear input error.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    history_path, readme_path = _write_inputs(tmp_path, [])
    history_path.write_text("{not-json", encoding="utf-8")

    result = _run_generator(history_path, readme_path)

    assert result.returncode == 2
    assert "Malformed build-history JSON" in result.stderr


def test_generator_selected_release_missing_required_field_fails(
    tmp_path: Path,
) -> None:
    """A selected release without its creation timestamp is rejected.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    entry = _entry("0.5.28", 28)
    del entry["created"]
    history_path, readme_path = _write_inputs(tmp_path, [entry])

    result = _run_generator(history_path, readme_path)

    assert result.returncode == 2
    assert "field 'created' must be a non-empty string" in result.stderr


def test_generator_selected_release_malformed_date_fails(tmp_path: Path) -> None:
    """A malformed release timestamp cannot silently become a table date.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    history_path, readme_path = _write_inputs(
        tmp_path, [_entry("0.5.28", 28, "not-a-timestamp")]
    )

    result = _run_generator(history_path, readme_path)

    assert result.returncode == 2
    assert "invalid 'created' timestamp" in result.stderr


def test_generator_duplicate_stable_release_tag_fails(tmp_path: Path) -> None:
    """Duplicate stable tags are rejected as ambiguous canonical history.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    history_path, readme_path = _write_inputs(
        tmp_path, [_entry("0.5.28", 28), _entry("0.5.28", 29)]
    )

    result = _run_generator(history_path, readme_path)

    assert result.returncode == 2
    assert "Duplicate stable release tag" in result.stderr


def test_generator_history_without_stable_release_fails(tmp_path: Path) -> None:
    """Refresh-only history cannot produce the stable-release table.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    history_path, readme_path = _write_inputs(
        tmp_path, [_entry("0.5.28-1", 29)]
    )

    result = _run_generator(history_path, readme_path)

    assert result.returncode == 2
    assert "no stable release entries" in result.stderr


def test_generator_real_history_restores_current_release_as_first_row(
    tmp_path: Path,
) -> None:
    """Repository history renders 0.5.28 ahead of the four prior releases.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    readme_path = tmp_path / "README.md"
    readme_path.write_text(README_TEMPLATE, encoding="utf-8")

    result = _run_generator(REAL_HISTORY_PATH, readme_path)

    assert result.returncode == 0, result.stderr
    content = readme_path.read_text(encoding="utf-8")
    release_rows = [line for line in content.splitlines() if line.startswith("| 0.")]
    assert [row.split("|")[1].strip() for row in release_rows] == [
        "0.5.28",
        "0.5.27",
        "0.5.26",
        "0.5.25.1",
        "0.5.25",
    ]
    assert "| 0.5.28 | 1.1.10 | 2.7.21 | 2026-07-08 | c2b576e |" in content
