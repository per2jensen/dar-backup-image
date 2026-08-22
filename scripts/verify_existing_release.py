#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Verify an existing signed Docker release without modifying it."""

from __future__ import annotations

import argparse
import json
import logging
import re
from dataclasses import dataclass

from publish_image import PublicationError, parse_cli_version, run_command


logging.basicConfig(level=logging.INFO, format="%(message)s")
LOGGER = logging.getLogger(__name__)

IMAGE_REFERENCE_PATTERN = re.compile(
    r"^[a-z0-9]+(?:[._-][a-z0-9]+)*(?:/[a-z0-9]+(?:[._-][a-z0-9]+)*)+$"
)
VERSION_PATTERN = re.compile(
    r"^[0-9]+\.[0-9]+\.[0-9]+(?:\.[0-9]+)?"
    r"(?:-[0-9A-Za-z]+(?:[.-][0-9A-Za-z]+)*)?$"
)
FULL_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")


@dataclass(frozen=True)
class ExistingReleaseConfig:
    """Validated inputs for non-mutating release verification.

    Args:
        repository: Docker repository without a tag.
        version: Existing release version.
        digest: Expected sha256 digest without the repository prefix.
        expected_cli_version: Exact ``dar-backup --version`` value.
        expected_source_sha: Full OCI revision-label value.
        certificate_identity: Exact GitHub Actions signing identity.
        certificate_oidc_issuer: Expected certificate issuer.
    """

    repository: str
    version: str
    digest: str
    expected_cli_version: str
    expected_source_sha: str
    certificate_identity: str
    certificate_oidc_issuer: str

    @property
    def digest_reference(self) -> str:
        """Return the fully qualified immutable image reference.

        Returns:
            Docker ``repository@sha256`` reference.
        """
        return f"{self.repository}@{self.digest}"


def parse_args() -> argparse.Namespace:
    """Parse existing-release verification arguments.

    Returns:
        Parsed command-line arguments.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--digest", required=True)
    parser.add_argument("--expected-cli-version", required=True)
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--certificate-identity", required=True)
    parser.add_argument("--certificate-oidc-issuer", required=True)
    return parser.parse_args()


def validate_config(arguments: argparse.Namespace) -> ExistingReleaseConfig:
    """Validate all recovery verification inputs.

    Args:
        arguments: Parsed command-line arguments.

    Returns:
        Immutable validated verification configuration.

    Raises:
        ValueError: If any value is missing or malformed.
    """
    repository = arguments.repository.strip()
    version = arguments.version.strip()
    digest = arguments.digest.strip()
    cli_version = arguments.expected_cli_version.strip()
    source_sha = arguments.expected_source_sha.strip()
    identity = arguments.certificate_identity.strip()
    issuer = arguments.certificate_oidc_issuer.strip()

    if not IMAGE_REFERENCE_PATTERN.fullmatch(repository):
        raise ValueError(f"invalid Docker repository: {repository!r}")
    if not VERSION_PATTERN.fullmatch(version):
        raise ValueError(f"unsupported release version: {version!r}")
    if not DIGEST_PATTERN.fullmatch(digest):
        raise ValueError(f"invalid image digest: {digest!r}")
    if not cli_version or any(character.isspace() for character in cli_version):
        raise ValueError("expected CLI version must not contain whitespace")
    if not FULL_SHA_PATTERN.fullmatch(source_sha):
        raise ValueError("expected source SHA must contain 40 lowercase hex characters")
    if not identity or any(character.isspace() for character in identity):
        raise ValueError("certificate identity must be non-empty without whitespace")
    if not issuer.startswith("https://") or any(
        character.isspace() for character in issuer
    ):
        raise ValueError("certificate OIDC issuer must be an HTTPS URL")

    return ExistingReleaseConfig(
        repository=repository,
        version=version,
        digest=digest,
        expected_cli_version=cli_version,
        expected_source_sha=source_sha,
        certificate_identity=identity,
        certificate_oidc_issuer=issuer,
    )


def verify_tag_digest(config: ExistingReleaseConfig) -> None:
    """Pull the version tag and require its repository digest to match history.

    Args:
        config: Validated verification configuration.

    Raises:
        PublicationError: If Docker cannot pull or reports a different digest.
    """
    tagged_image = f"{config.repository}:{config.version}"
    run_command(["docker", "pull", tagged_image], "pull-version-tag")
    raw_digests = run_command(
        [
            "docker",
            "image",
            "inspect",
            "--format={{json .RepoDigests}}",
            tagged_image,
        ],
        "verify-version-digest",
    ).strip()
    try:
        repo_digests = json.loads(raw_digests)
    except json.JSONDecodeError as error:
        raise PublicationError(
            "verify-version-digest",
            f"Docker returned invalid RepoDigests JSON: {raw_digests!r}",
        ) from error
    if not isinstance(repo_digests, list) or not all(
        isinstance(item, str) for item in repo_digests
    ):
        raise PublicationError(
            "verify-version-digest", "Docker returned invalid RepoDigests data"
        )
    if config.digest_reference not in repo_digests:
        raise PublicationError(
            "verify-version-digest",
            f"version tag does not resolve to {config.digest_reference}; "
            f"got {repo_digests!r}",
        )


def verify_runtime_and_labels(config: ExistingReleaseConfig) -> None:
    """Pull the immutable digest and verify its CLI and OCI labels.

    Args:
        config: Validated verification configuration.

    Raises:
        PublicationError: If the image cannot run or reports unexpected metadata.
    """
    reference = config.digest_reference
    run_command(["docker", "pull", reference], "pull-digest")
    cli_output = run_command(
        [
            "docker",
            "run",
            "--rm",
            "--entrypoint",
            "dar-backup",
            reference,
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

    expected_labels = {
        "org.opencontainers.image.version": config.version,
        "org.opencontainers.image.revision": config.expected_source_sha,
    }
    for label, expected_value in expected_labels.items():
        actual_value = run_command(
            [
                "docker",
                "image",
                "inspect",
                f"--format={{{{ index .Config.Labels \"{label}\" }}}}",
                reference,
            ],
            f"verify-{label.rsplit('.', maxsplit=1)[-1]}-label",
        ).strip()
        if actual_value != expected_value:
            raise PublicationError(
                f"verify-{label.rsplit('.', maxsplit=1)[-1]}-label",
                f"OCI label {label} mismatch: expected {expected_value!r}, "
                f"got {actual_value!r}",
            )


def verify_sigstore(config: ExistingReleaseConfig) -> None:
    """Verify the release signature and CycloneDX attestation.

    Args:
        config: Validated verification configuration.

    Raises:
        PublicationError: If Cosign rejects either verification.
    """
    certificate_arguments = [
        "--certificate-identity",
        config.certificate_identity,
        "--certificate-oidc-issuer",
        config.certificate_oidc_issuer,
    ]
    run_command(
        ["cosign", "verify", *certificate_arguments, config.digest_reference],
        "verify-signature",
    )
    run_command(
        [
            "cosign",
            "verify-attestation",
            "--type",
            "cyclonedx",
            *certificate_arguments,
            config.digest_reference,
        ],
        "verify-attestation",
    )


def verify_existing_release(config: ExistingReleaseConfig) -> None:
    """Run all non-mutating remote-release verification stages.

    Args:
        config: Validated verification configuration.

    Raises:
        PublicationError: If any Docker or Sigstore check fails.
    """
    verify_tag_digest(config)
    verify_runtime_and_labels(config)
    verify_sigstore(config)


def main() -> int:
    """Validate inputs and verify an existing release.

    Returns:
        Zero on success and two on validation or verification failure.
    """
    try:
        config = validate_config(parse_args())
        verify_existing_release(config)
    except (ValueError, PublicationError) as error:
        LOGGER.error("ERROR: %s", error)
        return 2
    LOGGER.info("✅ Existing signed release verified: %s", config.digest_reference)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
