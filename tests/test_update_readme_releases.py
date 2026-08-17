"""Tests for the build-history-driven README release table."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Sequence


SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "update_readme_releases.py"
REAL_HISTORY_PATH = Path(__file__).parents[1] / "doc" / "build-history.json"
REAL_README_PATH = Path(__file__).parents[1] / "README.md"
START_MARKER = "<!-- BEGIN GENERATED RELEASE TABLE -->"
END_MARKER = "<!-- END GENERATED RELEASE TABLE -->"
RELEASE_TAG_PATTERN = re.compile(
    r"^\d+(?:\.\d+){2,3}(?:-rc[1-9]\d*)?$"
)
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


def _rendered_release_tags(content: str) -> list[str]:
    """Extract release tags from the generated Markdown table.

    Args:
        content: README content containing one generated release table.

    Returns:
        Release tags in rendered row order.

    Raises:
        ValueError: If the generated table markers are missing or reversed.
    """
    if not isinstance(content, str):
        raise ValueError("README content must be a string")
    start_index = content.index(START_MARKER) + len(START_MARKER)
    end_index = content.index(END_MARKER)
    if end_index <= start_index:
        raise ValueError("README generated release-table markers are reversed")
    table = content[start_index:end_index]
    return [
        line.split("|")[1].strip()
        for line in table.splitlines()
        if line.startswith("| ") and not line.startswith("| Tag ")
    ]


def _generated_table_region(content: str) -> str:
    """Extract the marker-bounded generated table region.

    Args:
        content: README content containing one generated release table.

    Returns:
        Generated table including its boundary markers.

    Raises:
        ValueError: If the generated table markers are missing or reversed.
    """
    if not isinstance(content, str):
        raise ValueError("README content must be a string")
    start_index = content.index(START_MARKER)
    end_index = content.index(END_MARKER)
    if end_index <= start_index:
        raise ValueError("README generated release-table markers are reversed")
    return content[start_index : end_index + len(END_MARKER)]


def test_generator_renders_newest_five_releases_with_utc_dates(
    tmp_path: Path,
) -> None:
    """Generation includes RCs while excluding refresh and test tags.

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
        _entry("1.0.0-rc1", 31),
    ]
    history_path, readme_path = _write_inputs(tmp_path, entries)

    result = _run_generator(history_path, readme_path)

    assert result.returncode == 0, result.stderr
    content = readme_path.read_text(encoding="utf-8")
    assert _rendered_release_tags(content) == [
        "1.0.0-rc1",
        "0.5.28",
        "0.5.27",
        "0.5.26",
        "0.5.25.1",
    ]
    assert "| 1.0.0-rc1 | 1.1.31 | 2.7.21 |" in content
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


def test_generator_duplicate_release_tag_fails(tmp_path: Path) -> None:
    """Duplicate release tags are rejected as ambiguous canonical history.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    history_path, readme_path = _write_inputs(
        tmp_path, [_entry("0.5.28", 28), _entry("0.5.28", 29)]
    )

    result = _run_generator(history_path, readme_path)

    assert result.returncode == 2
    assert "Duplicate release tag" in result.stderr


def test_generator_history_without_release_fails(tmp_path: Path) -> None:
    """Refresh-only history cannot produce the release table.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    history_path, readme_path = _write_inputs(
        tmp_path, [_entry("0.5.28-1", 29)]
    )

    result = _run_generator(history_path, readme_path)

    assert result.returncode == 2
    assert "no release entries" in result.stderr


def test_generator_real_history_matches_latest_displayable_releases(
    tmp_path: Path,
) -> None:
    """Repository history and README agree on the newest five release tags.

    Args:
        tmp_path: Isolated pytest temporary directory.
    """
    readme_path = tmp_path / "README.md"
    readme_path.write_text(README_TEMPLATE, encoding="utf-8")

    result = _run_generator(REAL_HISTORY_PATH, readme_path)

    assert result.returncode == 0, result.stderr
    content = readme_path.read_text(encoding="utf-8")
    history = json.loads(REAL_HISTORY_PATH.read_text(encoding="utf-8"))
    displayable_entries = [
        entry
        for entry in history
        if isinstance(entry.get("tag"), str)
        and RELEASE_TAG_PATTERN.fullmatch(entry["tag"])
    ]
    expected_tags = [
        entry["tag"]
        for entry in sorted(
            displayable_entries,
            key=lambda entry: entry["build_number"],
            reverse=True,
        )[:5]
    ]

    assert _rendered_release_tags(content) == expected_tags
    assert all(not re.fullmatch(r".+-\d+", tag) for tag in expected_tags)
    assert _generated_table_region(content) == _generated_table_region(
        REAL_README_PATH.read_text(encoding="utf-8")
    )
