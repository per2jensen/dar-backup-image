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
"""Publish, sign, attest, pull, and verify one Docker image digest."""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


logging.basicConfig(level=logging.INFO, format="%(message)s")
LOGGER = logging.getLogger(__name__)

IMAGE_REFERENCE_PATTERN = re.compile(
    r"^[a-z0-9]+(?:[._-][a-z0-9]+)*(?:/[a-z0-9]+(?:[._-][a-z0-9]+)*)+$"
)
TAG_PATTERN = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$")
DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
REKOR_INDEX_PATTERN = re.compile(r"tlog entry created with index:\s*([0-9]+)")
PUSH_DIGEST_PATTERN = re.compile(r"digest:\s*(sha256:[0-9a-f]{64})")


class PublicationError(RuntimeError):
    """Describe a failed publication stage.

    Args:
        stage: Stable name of the failed publication stage.
        message: Diagnostic error message.
        result: Partial publication state available at failure time.
    """

    def __init__(
        self,
        stage: str,
        message: str,
        result: PublicationResult | None = None,
    ) -> None:
        """Initialize a publication failure.

        Args:
            stage: Stable name of the failed publication stage.
            message: Diagnostic error message.
            result: Partial publication state available at failure time.

        Raises:
            ValueError: If either value is empty.
        """
        if not stage:
            raise ValueError("publication failure stage must not be empty")
        if not message:
            raise ValueError("publication failure message must not be empty")
        super().__init__(message)
        self.stage = stage
        self.result = result


@dataclass(frozen=True)
class PublicationConfig:
    """Validated inputs for one image publication.

    Args:
        local_image: Existing local Docker image reference.
        repository: Remote Docker repository without a tag.
        version: Version tag to publish.
        expected_cli_version: Exact version expected from ``dar-backup --version``.
        sbom_file: CycloneDX JSON file to attest.
        dockerhub_username: Docker Hub account name.
        dockerhub_token: Docker Hub password or access token.
    """

    local_image: str
    repository: str
    version: str
    expected_cli_version: str
    sbom_file: Path
    dockerhub_username: str
    dockerhub_token: str


@dataclass(frozen=True)
class PublicationResult:
    """Outputs and rollback state from one publication attempt.

    Args:
        digest: Immutable remote image reference, when known.
        rekor_url: Sigstore transparency-log URL, when reported by cosign.
        rekor_index: Sigstore transparency-log index, when reported by cosign.
        failure_stage: Stable failed-stage name, or an empty string on success.
        candidate_push_attempted: Whether the versioned candidate push began.
        candidate_verified: Whether the remote digest passed its runtime checks.
        latest_promoted: Whether ``:latest`` was pushed and verified.
    """

    digest: str = ""
    rekor_url: str = ""
    rekor_index: str = ""
    failure_stage: str = ""
    candidate_push_attempted: bool = False
    candidate_verified: bool = False
    latest_promoted: bool = False


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
        Parsed publication arguments.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--local-image", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--expected-cli-version", required=True)
    parser.add_argument("--sbom-file", required=True, type=Path)
    return parser.parse_args()


def validate_config(arguments: argparse.Namespace) -> PublicationConfig:
    """Validate CLI arguments and credentials before publication starts.

    Args:
        arguments: Parsed command-line arguments.

    Returns:
        Fully validated publication configuration.

    Raises:
        ValueError: If a reference, version, file, or credential is invalid.
    """
    local_image = arguments.local_image.strip()
    repository = arguments.repository.strip()
    version = arguments.version.strip()
    expected_cli_version = arguments.expected_cli_version.strip()
    sbom_file = arguments.sbom_file.resolve()
    username = os.environ.get("DOCKERHUB_USER", "").strip()
    token = os.environ.get("DOCKERHUB_TOKEN", "")

    if not local_image or any(character.isspace() for character in local_image):
        raise ValueError("local image must be a non-empty reference without whitespace")
    if not IMAGE_REFERENCE_PATTERN.fullmatch(repository):
        raise ValueError(f"invalid Docker repository: {repository!r}")
    if not TAG_PATTERN.fullmatch(version):
        raise ValueError(f"invalid Docker tag: {version!r}")
    if not expected_cli_version or any(
        character.isspace() for character in expected_cli_version
    ):
        raise ValueError("expected CLI version must be non-empty without whitespace")
    if not sbom_file.is_file():
        raise ValueError(f"SBOM file does not exist: {sbom_file}")
    if not username:
        raise ValueError("DOCKERHUB_USER must be set")
    if not token:
        raise ValueError("DOCKERHUB_TOKEN must be set")

    return PublicationConfig(
        local_image=local_image,
        repository=repository,
        version=version,
        expected_cli_version=expected_cli_version,
        sbom_file=sbom_file,
        dockerhub_username=username,
        dockerhub_token=token,
    )


def run_command(
    command: list[str],
    stage: str,
    *,
    standard_input: str | None = None,
) -> str:
    """Run one external command and return its combined diagnostic output.

    Args:
        command: Executable and individual arguments without shell expansion.
        stage: Stable publication-stage name used in failures.
        standard_input: Optional text supplied to the process on standard input.

    Returns:
        Standard output followed by standard error.

    Raises:
        PublicationError: If the executable is missing or exits unsuccessfully.
    """
    if not command or not command[0]:
        raise ValueError("command must contain an executable")
    if not stage:
        raise ValueError("command stage must not be empty")

    try:
        completed = subprocess.run(
            command,
            check=True,
            capture_output=True,
            input=standard_input,
            text=True,
        )
    except FileNotFoundError as error:
        raise PublicationError(stage, f"required command not found: {command[0]}") from error
    except subprocess.CalledProcessError as error:
        output = "\n".join(part.strip() for part in (error.stdout, error.stderr) if part)
        detail = output or f"command exited with status {error.returncode}"
        raise PublicationError(stage, detail) from error

    output = "\n".join(
        part.strip() for part in (completed.stdout, completed.stderr) if part
    )
    if output:
        LOGGER.info("%s", output)
    return output


def parse_push_digest(output: str, repository: str, stage: str) -> str:
    """Extract and validate the digest emitted by ``docker push``.

    Args:
        output: Combined Docker push output.
        repository: Remote repository without a tag.
        stage: Publication stage to report if parsing fails.

    Returns:
        Fully qualified ``repository@sha256:...`` reference.

    Raises:
        PublicationError: If Docker did not report one valid digest.
    """
    matches = PUSH_DIGEST_PATTERN.findall(output)
    if not matches:
        raise PublicationError(stage, "docker push did not report an image digest")
    digest = matches[-1]
    if not DIGEST_PATTERN.fullmatch(digest):
        raise PublicationError(stage, f"docker push returned an invalid digest: {digest!r}")
    return f"{repository}@{digest}"


def parse_cli_version(output: str, stage: str) -> str:
    """Extract the version token from ``dar-backup --version`` output.

    Args:
        output: Captured CLI output.
        stage: Publication stage to report if parsing fails.

    Returns:
        The CLI version token.

    Raises:
        PublicationError: If the first non-empty line has fewer than two tokens.
    """
    first_line = next((line.strip() for line in output.splitlines() if line.strip()), "")
    fields = first_line.split()
    if len(fields) < 2:
        raise PublicationError(stage, f"unexpected dar-backup version output: {first_line!r}")
    return fields[1]


def parse_rekor(output: str) -> tuple[str, str]:
    """Extract optional Rekor metadata from cosign output.

    Args:
        output: Combined cosign output.

    Returns:
        Rekor index and corresponding search URL, or two empty strings.
    """
    match = REKOR_INDEX_PATTERN.search(output)
    if match is None:
        return "", ""
    index = match.group(1)
    return index, f"https://search.sigstore.dev/?logIndex={index}"


def verify_remote_candidate(config: PublicationConfig, digest: str) -> None:
    """Pull and execute the immutable remote candidate.

    Args:
        config: Validated publication inputs.
        digest: Fully qualified remote digest reference.

    Raises:
        PublicationError: If pulling, CLI execution, or label verification fails.
    """
    run_command(["docker", "pull", digest], "pull-digest")
    cli_output = run_command(
        [
            "docker",
            "run",
            "--rm",
            "--entrypoint",
            "dar-backup",
            digest,
            "--version",
        ],
        "verify-cli-version",
    )
    actual_cli_version = parse_cli_version(cli_output, "verify-cli-version")
    if actual_cli_version != config.expected_cli_version:
        raise PublicationError(
            "verify-cli-version",
            "remote CLI version mismatch: "
            f"expected {config.expected_cli_version!r}, got {actual_cli_version!r}",
        )

    image_version = run_command(
        [
            "docker",
            "image",
            "inspect",
            "--format={{ index .Config.Labels \"org.opencontainers.image.version\" }}",
            digest,
        ],
        "verify-image-version",
    ).strip()
    if image_version != config.version:
        raise PublicationError(
            "verify-image-version",
            f"remote image version mismatch: expected {config.version!r}, got {image_version!r}",
        )


def verify_latest_digest(config: PublicationConfig, digest: str) -> None:
    """Pull ``:latest`` and require it to contain the signed digest.

    Args:
        config: Validated publication inputs.
        digest: Expected fully qualified remote digest reference.

    Raises:
        PublicationError: If the pull or digest comparison fails.
    """
    latest = f"{config.repository}:latest"
    run_command(["docker", "pull", latest], "pull-latest")
    raw_digests = run_command(
        ["docker", "image", "inspect", "--format={{json .RepoDigests}}", latest],
        "verify-latest",
    ).strip()
    try:
        repo_digests = json.loads(raw_digests)
    except json.JSONDecodeError as error:
        raise PublicationError(
            "verify-latest", f"Docker returned invalid RepoDigests JSON: {raw_digests!r}"
        ) from error
    if not isinstance(repo_digests, list) or not all(
        isinstance(item, str) for item in repo_digests
    ):
        raise PublicationError("verify-latest", "Docker returned invalid RepoDigests data")
    if digest not in repo_digests:
        raise PublicationError(
            "verify-latest",
            f":latest does not resolve to signed digest {digest}; got {repo_digests!r}",
        )


def publish_image(config: PublicationConfig) -> PublicationResult:
    """Run the ordered candidate publication and promotion transaction.

    Args:
        config: Validated publication inputs.

    Returns:
        Successful publication metadata.

    Raises:
        PublicationError: If any publication or verification stage fails.
    """
    candidate = f"{config.repository}:{config.version}"
    latest = f"{config.repository}:latest"

    run_command(
        ["docker", "login", "--username", config.dockerhub_username, "--password-stdin"],
        "docker-login",
        standard_input=f"{config.dockerhub_token}\n",
    )
    run_command(["docker", "tag", config.local_image, candidate], "tag-candidate")
    try:
        push_output = run_command(["docker", "push", candidate], "push-candidate")
        digest = parse_push_digest(push_output, config.repository, "capture-digest")
    except PublicationError as error:
        raise PublicationError(
            error.stage,
            str(error),
            PublicationResult(
                failure_stage=error.stage,
                candidate_push_attempted=True,
            ),
        ) from error

    rekor_index = ""
    rekor_url = ""
    try:
        sign_output = run_command(["cosign", "sign", "--yes", digest], "sign")
        rekor_index, rekor_url = parse_rekor(sign_output)
        run_command(
            [
                "cosign",
                "attest",
                "--yes",
                "--predicate",
                str(config.sbom_file),
                "--type",
                "cyclonedx",
                digest,
            ],
            "attest",
        )
        verify_remote_candidate(config, digest)
    except PublicationError as error:
        raise PublicationError(
            error.stage,
            str(error),
            PublicationResult(
                digest=digest,
                rekor_url=rekor_url,
                rekor_index=rekor_index,
                failure_stage=error.stage,
                candidate_push_attempted=True,
            ),
        ) from error

    verified_result = PublicationResult(
        digest=digest,
        rekor_url=rekor_url,
        rekor_index=rekor_index,
        candidate_push_attempted=True,
        candidate_verified=True,
    )
    try:
        run_command(["docker", "tag", digest, latest], "tag-latest")
        latest_push_output = run_command(["docker", "push", latest], "push-latest")
        latest_digest = parse_push_digest(
            latest_push_output, config.repository, "capture-latest-digest"
        )
        if latest_digest != digest:
            raise PublicationError(
                "capture-latest-digest",
                f":latest push reported {latest_digest}, expected {digest}",
            )
        verify_latest_digest(config, digest)
    except PublicationError as error:
        raise PublicationError(
            error.stage,
            str(error),
            PublicationResult(
                digest=verified_result.digest,
                rekor_url=verified_result.rekor_url,
                rekor_index=verified_result.rekor_index,
                failure_stage=error.stage,
                candidate_push_attempted=True,
                candidate_verified=True,
            ),
        ) from error

    return PublicationResult(
        digest=digest,
        rekor_url=rekor_url,
        rekor_index=rekor_index,
        candidate_push_attempted=True,
        candidate_verified=True,
        latest_promoted=True,
    )


def write_github_outputs(output_file: Path, result: PublicationResult) -> None:
    """Append publication metadata to the GitHub Actions output file.

    Args:
        output_file: File path supplied by GitHub Actions.
        result: Publication metadata to serialize.

    Raises:
        ValueError: If an output contains a newline.
        OSError: If the output file cannot be written.
    """
    outputs = {
        "digest": result.digest,
        "rekor_url": result.rekor_url,
        "rekor_index": result.rekor_index,
        "failure_stage": result.failure_stage,
        "candidate_push_attempted": str(result.candidate_push_attempted).lower(),
        "candidate_verified": str(result.candidate_verified).lower(),
        "latest_promoted": str(result.latest_promoted).lower(),
    }
    if any("\n" in value or "\r" in value for value in outputs.values()):
        raise ValueError("GitHub Actions output values must not contain newlines")
    with output_file.open("a", encoding="utf-8") as handle:
        for key, value in outputs.items():
            handle.write(f"{key}={value}\n")


def main() -> int:
    """Run the publisher and always expose rollback-safe action outputs.

    Returns:
        Zero on success and one on validation or publication failure.
    """
    result = PublicationResult(failure_stage="validate-inputs")
    try:
        config = validate_config(parse_args())
        result = publish_image(config)
    except ValueError as error:
        LOGGER.error("ERROR [validate-inputs]: %s", error)
    except OSError as error:
        LOGGER.error("ERROR [validate-inputs]: unable to access an input: %s", error)
    except PublicationError as error:
        LOGGER.error("ERROR [%s]: %s", error.stage, error)
        result = error.result or PublicationResult(failure_stage=error.stage)
    else:
        LOGGER.info("✅ Published and verified %s", result.digest)

    output_path = os.environ.get("GITHUB_OUTPUT", "").strip()
    if not output_path:
        LOGGER.error("ERROR [validate-inputs]: GITHUB_OUTPUT must be set")
        return 1
    try:
        write_github_outputs(Path(output_path), result)
    except (OSError, ValueError) as error:
        LOGGER.error("ERROR [write-outputs]: %s", error)
        return 1
    return 0 if result.latest_promoted else 1


if __name__ == "__main__":
    raise SystemExit(main())
