"""Integration tests for the shared Docker publication state machine."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).parents[1]
PUBLISH_SCRIPT = REPOSITORY_ROOT / "scripts" / "publish_image.py"
TEST_DIGEST = "sha256:" + ("a" * 64)


def _create_fake_tools(tmp_path: Path) -> Path:
    """Create stateful fake Docker and cosign executables.

    Args:
        tmp_path: Temporary directory owned by the test.

    Returns:
        Directory containing the executable command shims.
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
log_path = Path(os.environ["FAKE_TOOL_LOG"])
with log_path.open("a", encoding="utf-8") as handle:
    handle.write(json.dumps([name, *arguments]) + "\\n")

failure = os.environ.get("FAKE_FAILURE_STAGE", "")
digest = os.environ["FAKE_DIGEST"]
repository = os.environ["FAKE_REPOSITORY"]
if name == "docker":
    command = arguments[0]
    if failure == command:
        print(f"forced {command} failure", file=sys.stderr)
        raise SystemExit(23)
    if command == "push":
        print(f"latest: digest: {digest} size: 1234")
    elif command == "run":
        cli_version = os.environ.get("FAKE_CLI_VERSION", "1.2.3")
        print(f"dar-backup {cli_version}")
    elif command == "image" and arguments[1] == "inspect":
        if "RepoDigests" in arguments[2]:
            latest_digest = os.environ.get("FAKE_LATEST_DIGEST", digest)
            print(json.dumps([f"{repository}@{latest_digest}"]))
        else:
            print(os.environ.get("FAKE_IMAGE_VERSION", "9.8.7"))
elif name == "cosign":
    command = arguments[0]
    if failure == command:
        print(f"forced {command} failure", file=sys.stderr)
        raise SystemExit(24)
    if command == "sign":
        print("tlog entry created with index: 4567")
""",
        encoding="utf-8",
    )
    tool.chmod(0o755)
    (bin_dir / "docker").symlink_to(tool)
    (bin_dir / "cosign").symlink_to(tool)
    return bin_dir


def _run_publisher(
    tmp_path: Path,
    *,
    failure_stage: str = "",
    cli_version: str = "1.2.3",
    image_version: str = "9.8.7",
    repository: str = "example/image",
    latest_digest: str = TEST_DIGEST,
) -> tuple[subprocess.CompletedProcess[str], dict[str, str], list[list[str]]]:
    """Run the real publisher with deterministic subprocess shims.

    Args:
        tmp_path: Temporary directory owned by the test.
        failure_stage: Optional fake command name that should fail.
        cli_version: Version emitted by the fake remote image.
        image_version: OCI version label emitted by the fake remote image.
        repository: Repository argument supplied to the publisher.
        latest_digest: Digest exposed after pulling the mutable latest tag.

    Returns:
        Completed process, parsed action outputs, and ordered command log.
    """
    bin_dir = _create_fake_tools(tmp_path)
    sbom = tmp_path / "sbom.json"
    sbom.write_text("{}\n", encoding="utf-8")
    output_file = tmp_path / "github-output"
    command_log = tmp_path / "commands.jsonl"
    environment = os.environ.copy()
    environment.update(
        {
            "PATH": f"{bin_dir}:{environment['PATH']}",
            "DOCKERHUB_USER": "test-user",
            "DOCKERHUB_TOKEN": "secret-token",
            "GITHUB_OUTPUT": str(output_file),
            "FAKE_TOOL_LOG": str(command_log),
            "FAKE_FAILURE_STAGE": failure_stage,
            "FAKE_CLI_VERSION": cli_version,
            "FAKE_IMAGE_VERSION": image_version,
            "FAKE_DIGEST": TEST_DIGEST,
            "FAKE_LATEST_DIGEST": latest_digest,
            "FAKE_REPOSITORY": "example/image",
        }
    )
    result = subprocess.run(
        [
            "python3",
            str(PUBLISH_SCRIPT),
            "--local-image",
            "dar-backup:9.8.7",
            "--repository",
            repository,
            "--version",
            "9.8.7",
            "--expected-cli-version",
            "1.2.3",
            "--sbom-file",
            str(sbom),
        ],
        check=False,
        capture_output=True,
        env=environment,
        text=True,
    )
    outputs = {}
    if output_file.exists():
        outputs = dict(
            line.split("=", maxsplit=1)
            for line in output_file.read_text(encoding="utf-8").splitlines()
        )
    commands = []
    if command_log.exists():
        commands = [
            json.loads(line)
            for line in command_log.read_text(encoding="utf-8").splitlines()
        ]
    return result, outputs, commands


def test_publish_image_success_verifies_digest_before_promoting_latest(
    tmp_path: Path,
) -> None:
    """A candidate is signed and remotely executed before latest is pushed."""
    result, outputs, commands = _run_publisher(tmp_path)
    digest_reference = f"example/image@{TEST_DIGEST}"

    assert result.returncode == 0, result.stderr
    assert outputs == {
        "digest": digest_reference,
        "rekor_url": "https://search.sigstore.dev/?logIndex=4567",
        "rekor_index": "4567",
        "failure_stage": "",
        "candidate_push_attempted": "true",
        "candidate_verified": "true",
        "latest_promoted": "true",
    }
    candidate_push = commands.index(["docker", "push", "example/image:9.8.7"])
    signing = commands.index(["cosign", "sign", "--yes", digest_reference])
    digest_pull = commands.index(["docker", "pull", digest_reference])
    remote_run = commands.index(
        [
            "docker",
            "run",
            "--rm",
            "--entrypoint",
            "dar-backup",
            digest_reference,
            "--version",
        ]
    )
    latest_push = commands.index(["docker", "push", "example/image:latest"])
    latest_pull = commands.index(["docker", "pull", "example/image:latest"])
    assert candidate_push < signing < digest_pull < remote_run < latest_push < latest_pull
    assert all("secret-token" not in argument for command in commands for argument in command)


def test_publish_image_sign_failure_marks_candidate_for_rollback(
    tmp_path: Path,
) -> None:
    """A signing failure exposes rollback state and never moves latest."""
    result, outputs, commands = _run_publisher(tmp_path, failure_stage="sign")

    assert result.returncode == 1
    assert outputs["failure_stage"] == "sign"
    assert outputs["candidate_push_attempted"] == "true"
    assert outputs["candidate_verified"] == "false"
    assert outputs["latest_promoted"] == "false"
    assert ["docker", "push", "example/image:latest"] not in commands


def test_publish_image_partial_push_failure_marks_candidate_for_rollback(
    tmp_path: Path,
) -> None:
    """A failed candidate push remains eligible for defensive tag deletion."""
    result, outputs, commands = _run_publisher(tmp_path, failure_stage="push")

    assert result.returncode == 1
    assert outputs["failure_stage"] == "push-candidate"
    assert outputs["candidate_push_attempted"] == "true"
    assert outputs["candidate_verified"] == "false"
    assert commands.count(["docker", "push", "example/image:9.8.7"]) == 1
    assert ["docker", "push", "example/image:latest"] not in commands


def test_publish_image_remote_cli_mismatch_stops_before_latest(
    tmp_path: Path,
) -> None:
    """A pulled image reporting the wrong CLI version is not promoted."""
    result, outputs, commands = _run_publisher(tmp_path, cli_version="0.0.0")

    assert result.returncode == 1
    assert outputs["failure_stage"] == "verify-cli-version"
    assert outputs["candidate_push_attempted"] == "true"
    assert outputs["candidate_verified"] == "false"
    assert ["docker", "push", "example/image:latest"] not in commands
    assert "remote CLI version mismatch" in result.stderr


def test_publish_image_latest_digest_mismatch_preserves_verified_candidate(
    tmp_path: Path,
) -> None:
    """A failed latest check reports failure without deleting a good version."""
    unexpected_digest = "sha256:" + ("b" * 64)
    result, outputs, commands = _run_publisher(
        tmp_path,
        latest_digest=unexpected_digest,
    )

    assert result.returncode == 1
    assert outputs["failure_stage"] == "verify-latest"
    assert outputs["candidate_push_attempted"] == "true"
    assert outputs["candidate_verified"] == "true"
    assert outputs["latest_promoted"] == "false"
    assert ["docker", "push", "example/image:latest"] in commands
    assert ":latest does not resolve to signed digest" in result.stderr


def test_publish_image_invalid_repository_fails_before_external_commands(
    tmp_path: Path,
) -> None:
    """An invalid repository is rejected without invoking Docker or cosign."""
    result, outputs, commands = _run_publisher(tmp_path, repository="BAD REPOSITORY")

    assert result.returncode == 1
    assert outputs["failure_stage"] == "validate-inputs"
    assert outputs["candidate_push_attempted"] == "false"
    assert commands == []
