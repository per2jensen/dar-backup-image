# SPDX-FileCopyrightText: 2025-2026 Per Jensen
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This file is part of dar-backup-image:
# https://github.com/per2jensen/dar-backup-image
#
# License terms and warranty disclaimer:
# https://github.com/per2jensen/dar-backup-image/blob/main/LICENSE

"""Container tests for interactive completion and command manual pages."""

from __future__ import annotations

import subprocess

import pytest


DAR_MANUALS = (
    "dar",
    "dar_cp",
    "dar_manager",
    "dar_slave",
    "dar_split",
    "dar_xform",
)
PAR2_COMMANDS = (
    "par2",
    "par2create",
    "par2repair",
    "par2verify",
)


def _run_bash(
    image: str,
    command: str,
    *,
    interactive: bool,
) -> subprocess.CompletedProcess[str]:
    """Run Bash inside an image with captured text output.

    Args:
        image: Docker image reference under test.
        command: Bash command text to execute.
        interactive: Whether Bash should load its interactive startup files.

    Returns:
        Completed Docker subprocess without an automatic status check.
    """
    bash_option = "-ic" if interactive else "-lc"
    return subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--entrypoint",
            "/bin/bash",
            image,
            bash_option,
            command,
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def _complete_doc_prefix(image: str, prefix: str) -> subprocess.CompletedProcess[str]:
    """Request dar-backup documentation completions from a fresh shell.

    Args:
        image: Docker image reference under test.
        prefix: Partial documentation name to complete.

    Returns:
        Completed Docker subprocess containing one candidate per output line.
    """
    command = f"""
_completion_loader dar-backup >/dev/null 2>&1 || true
COMP_WORDS=(dar-backup --doc {prefix!r})
COMP_CWORD=2
COMP_LINE={f'dar-backup --doc {prefix}'!r}
COMP_POINT=${{#COMP_LINE}}
_python_argcomplete dar-backup {prefix!r} --doc
printf '%s\n' "${{COMPREPLY[@]}}"
"""
    return _run_bash(image, command, interactive=True)


def _complete_option_prefix(
    image: str,
    prefix: str,
) -> subprocess.CompletedProcess[str]:
    """Request dar-backup option completions from a fresh shell.

    Args:
        image: Docker image reference under test.
        prefix: Partial option name to complete.

    Returns:
        Completed Docker subprocess containing one candidate per output line.
    """
    command = f"""
_completion_loader dar-backup >/dev/null 2>&1 || true
COMP_WORDS=(dar-backup {prefix!r})
COMP_CWORD=1
COMP_LINE={f'dar-backup {prefix}'!r}
COMP_POINT=${{#COMP_LINE}}
_python_argcomplete dar-backup {prefix!r}
printf '%s\n' "${{COMPREPLY[@]}}"
"""
    return _run_bash(image, command, interactive=True)


def _packaged_doc_topics(
    image: str,
    prefix: str,
) -> subprocess.CompletedProcess[str]:
    """List documentation topics physically present in the installed package.

    Args:
        image: Docker image reference under test.
        prefix: Documentation prefix used to filter package files.

    Returns:
        Completed Docker subprocess containing one package topic per line.
    """
    script = """
from pathlib import Path
import sys

import dar_backup

doc_dir = Path(dar_backup.__file__).parent / "doc"
topics = sorted(
    path.stem
    for path in doc_dir.glob("*.md")
    if path.stem.startswith(sys.argv[1])
)
print("\\n".join(topics))
"""
    return subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--entrypoint",
            "/opt/venv/bin/python3",
            image,
            "-c",
            script,
            prefix,
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def _nonempty_lines(output: str) -> set[str]:
    """Convert command output into a set of nonempty lines.

    Args:
        output: Captured command output.

    Returns:
        Stripped, nonempty output lines.
    """
    return {line.strip() for line in output.splitlines() if line.strip()}


def test_container_option_completion_is_registered(image: str) -> None:
    """A fresh interactive shell loads dar-backup option completion.

    Args:
        image: Docker image fixture.
    """
    result = _complete_option_prefix(image, "--ver")

    assert result.returncode == 0, result.stderr
    assert "--version" in _nonempty_lines(result.stdout)


def test_container_doc_completion_matches_packaged_topics(image: str) -> None:
    """Documentation completion exactly reflects files in the installed wheel.

    Args:
        image: Docker image fixture.
    """
    packaged_result = _packaged_doc_topics(image, "restoring")
    completion_result = _complete_doc_prefix(image, "restoring")

    assert packaged_result.returncode == 0, packaged_result.stderr
    assert completion_result.returncode == 0, completion_result.stderr

    packaged_topics = _nonempty_lines(packaged_result.stdout)
    completed_topics = _nonempty_lines(completion_result.stdout)
    assert completed_topics == packaged_topics

    if "restoring" in packaged_topics:
        assert packaged_topics >= {
            "restoring",
            "restoring-advanced",
            "restoring-pitr",
        }


def test_container_doc_completion_unknown_prefix_returns_no_topic(image: str) -> None:
    """An unknown documentation prefix produces no fabricated completion.

    Args:
        image: Docker image fixture.
    """
    result = _complete_doc_prefix(image, "definitely-not-a-doc")

    assert result.returncode == 0, result.stderr
    assert not _nonempty_lines(result.stdout)


@pytest.mark.parametrize("manual_name", DAR_MANUALS)
def test_container_dar_manual_renders(image: str, manual_name: str) -> None:
    """Every manual generated by DAR renders through the real man system.

    Args:
        image: Docker image fixture.
        manual_name: DAR manual basename to render.
    """
    result = _run_bash(
        image,
        f"MANPAGER=cat PAGER=cat man {manual_name}",
        interactive=False,
    )

    assert result.returncode == 0, result.stderr
    assert manual_name.upper() in result.stdout


@pytest.mark.parametrize("command_name", PAR2_COMMANDS)
def test_container_par2_command_and_manual_are_available(
    image: str,
    command_name: str,
) -> None:
    """Every PAR2 command alias runs and has a renderable manual.

    Args:
        image: Docker image fixture.
        command_name: PAR2 command alias and manual basename to verify.
    """
    command_result = _run_bash(
        image,
        f"{command_name} --help",
        interactive=False,
    )
    manual_result = _run_bash(
        image,
        f"MANPAGER=cat PAGER=cat man {command_name}",
        interactive=False,
    )

    assert command_result.returncode == 0, command_result.stderr
    assert "Usage:" in command_result.stdout
    assert manual_result.returncode == 0, manual_result.stderr
    assert "PAR2" in manual_result.stdout


@pytest.mark.parametrize("command_name", PAR2_COMMANDS)
def test_container_par2_command_rejects_unknown_option(
    image: str,
    command_name: str,
) -> None:
    """Every PAR2 command alias reports an invalid option as an error.

    Args:
        image: Docker image fixture.
        command_name: PAR2 command alias to invoke.
    """
    result = _run_bash(
        image,
        f"{command_name} --definitely-invalid",
        interactive=False,
    )

    assert result.returncode != 0


def test_container_unknown_manual_fails(image: str) -> None:
    """The man system rejects a nonexistent page instead of using its stub.

    Args:
        image: Docker image fixture.
    """
    result = _run_bash(
        image,
        "MANPAGER=cat PAGER=cat man definitely-not-a-manual",
        interactive=False,
    )

    assert result.returncode != 0
    assert "No manual entry" in result.stderr
