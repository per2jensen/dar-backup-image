# SPDX-FileCopyrightText: 2025-2026 Per Jensen
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This file is part of dar-backup-image:
# https://github.com/per2jensen/dar-backup-image
#
# License terms and warranty disclaimer:
# https://github.com/per2jensen/dar-backup-image/blob/main/LICENSE

"""Subprocess tests for non-mutating existing-release verification."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).parents[1]
VERIFY_SCRIPT = REPOSITORY_ROOT / "scripts" / "verify_existing_release.py"
DIGEST = "sha256:" + ("a" * 64)
SOURCE_SHA = "b" * 40
IDENTITY = (
    "https://github.com/example/project/.github/workflows/"
    "release.yml@refs/heads/main"
)
ISSUER = "https://token.actions.githubusercontent.com"


def _create_fake_tools(tmp_path: Path) -> Path:
    """Create deterministic Docker and Cosign subprocess shims.

    Args:
        tmp_path: Temporary directory owned by the test.

    Returns:
        Directory containing fake executable tools.
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    tool = bin_dir / "fake-tool"
    tool.write_text(
        """#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

name = Path(sys.argv[0]).name
arguments = sys.argv[1:]
with Path(os.environ["FAKE_TOOL_LOG"]).open("a", encoding="utf-8") as handle:
    handle.write(json.dumps([name, *arguments]) + "\\n")

if name == "docker":
    if arguments[0] == "image" and "RepoDigests" in arguments[2]:
        print(json.dumps([os.environ["FAKE_TAG_DIGEST"]]))
    elif arguments[0] == "run":
        print("dar-backup 1.4.5")
    elif arguments[0] == "image" and "image.version" in arguments[2]:
        print("1.2.3-rc1")
    elif arguments[0] == "image" and "image.revision" in arguments[2]:
        print(os.environ["FAKE_SOURCE_SHA"])
elif name == "cosign" and os.environ.get("FAKE_COSIGN_FAILURE") == arguments[0]:
    print("forced cosign failure", file=sys.stderr)
    raise SystemExit(17)
""",
        encoding="utf-8",
    )
    tool.chmod(0o755)
    (bin_dir / "docker").symlink_to(tool)
    (bin_dir / "cosign").symlink_to(tool)
    return bin_dir


def _run_verifier(
    tmp_path: Path,
    *,
    tag_digest: str | None = None,
    source_sha: str = SOURCE_SHA,
    cosign_failure: str = "",
) -> tuple[subprocess.CompletedProcess[str], list[list[str]]]:
    """Run the verifier with controlled external command behavior.

    Args:
        tmp_path: Temporary directory owned by the test.
        tag_digest: Qualified digest returned for the version tag.
        source_sha: OCI revision label returned by Docker.
        cosign_failure: Optional Cosign subcommand forced to fail.

    Returns:
        Completed verifier and ordered external command log.
    """
    bin_dir = _create_fake_tools(tmp_path)
    command_log = tmp_path / "commands.jsonl"
    environment = os.environ.copy()
    environment.update(
        {
            "PATH": f"{bin_dir}:{environment['PATH']}",
            "FAKE_TOOL_LOG": str(command_log),
            "FAKE_TAG_DIGEST": tag_digest or f"example/image@{DIGEST}",
            "FAKE_SOURCE_SHA": source_sha,
            "FAKE_COSIGN_FAILURE": cosign_failure,
        }
    )
    result = subprocess.run(
        [
            "python3",
            str(VERIFY_SCRIPT),
            "--repository",
            "example/image",
            "--version",
            "1.2.3-rc1",
            "--digest",
            DIGEST,
            "--expected-cli-version",
            "1.4.5",
            "--expected-source-sha",
            SOURCE_SHA,
            "--certificate-identity",
            IDENTITY,
            "--certificate-oidc-issuer",
            ISSUER,
        ],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        env=environment,
        text=True,
    )
    commands = [
        json.loads(line)
        for line in command_log.read_text(encoding="utf-8").splitlines()
    ]
    return result, commands


def test_verifier_matching_release_checks_digest_runtime_labels_and_sigstore(
    tmp_path: Path,
) -> None:
    """A consistent existing release passes every read-only verification."""
    result, commands = _run_verifier(tmp_path)
    digest_reference = f"example/image@{DIGEST}"

    assert result.returncode == 0, result.stderr
    assert ["docker", "pull", "example/image:1.2.3-rc1"] in commands
    assert ["docker", "pull", digest_reference] in commands
    assert [
        "cosign",
        "verify",
        "--certificate-identity",
        IDENTITY,
        "--certificate-oidc-issuer",
        ISSUER,
        digest_reference,
    ] in commands
    assert [
        "cosign",
        "verify-attestation",
        "--type",
        "cyclonedx",
        "--certificate-identity",
        IDENTITY,
        "--certificate-oidc-issuer",
        ISSUER,
        digest_reference,
    ] in commands
    assert not any(
        command[:2] == ["docker", "push"] or command[:2] == ["cosign", "sign"]
        for command in commands
    )


def test_verifier_version_tag_digest_mismatch_stops_before_runtime(
    tmp_path: Path,
) -> None:
    """A moved Docker version tag cannot be finalized as the recorded release."""
    wrong_digest = "example/image@sha256:" + ("c" * 64)

    result, commands = _run_verifier(tmp_path, tag_digest=wrong_digest)

    assert result.returncode == 2
    assert "version tag does not resolve" in result.stderr
    assert not any(command[:2] == ["docker", "run"] for command in commands)
    assert not any(command[0] == "cosign" for command in commands)


def test_verifier_source_label_mismatch_stops_before_sigstore(
    tmp_path: Path,
) -> None:
    """An image from a different source commit cannot be finalized."""
    result, commands = _run_verifier(tmp_path, source_sha="c" * 40)

    assert result.returncode == 2
    assert "OCI label org.opencontainers.image.revision mismatch" in result.stderr
    assert not any(command[0] == "cosign" for command in commands)
