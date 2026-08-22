#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later

set -euo pipefail

readonly TARGET_BRANCH="main"

fail() {
    >&2 echo "ERROR: $1"
    exit 2
}

validate_arguments() {
    if [[ "$#" -ne 7 ]]; then
        fail "usage: $0 <version> <application-sha> <image-digest> <history> <sarif> <sbom> <badge>"
    fi

    if [[ ! "$1" =~ ^[0-9]+\.[0-9]+\.[0-9]+-[1-9][0-9]*$ ]]; then
        fail "refresh version must be x.y.z-N with a positive canonical N"
    fi
    if [[ ! "$2" =~ ^[0-9a-f]{40}$ ]]; then
        fail "application SHA must contain exactly 40 lowercase hexadecimal characters"
    fi
    if [[ ! "$3" =~ ^[^[:space:]@]+@sha256:[0-9a-f]{64}$ ]]; then
        fail "image digest must be a qualified repository@sha256 reference"
    fi

    local evidence_path
    for evidence_path in "$4" "$5" "$6" "$7"; do
        if [[ ! -f "${evidence_path}" ]]; then
            fail "housekeeping file does not exist: ${evidence_path}"
        fi
    done
}

commit_and_push() {
    local version="$1"
    local application_sha="$2"
    local image_digest="$3"
    local history_path="$4"
    local sarif_path="$5"
    local sbom_path="$6"
    local badge_path="$7"
    local tag="v${version}"
    local metadata_sha

    git config user.name "github-actions"
    git config user.email "actions@github.com"

    # Audit evidence is intentionally ignored for local development. Force only
    # the two validated workflow outputs into this housekeeping transaction.
    git add -- "${history_path}" "${badge_path}"
    git add -f -- "${sarif_path}" "${sbom_path}"
    if git diff --cached --quiet; then
        fail "housekeeping produced no changes to commit"
    fi

    git commit -m "refresh: ${version} metadata, evidence, and badge"
    metadata_sha=$(git rev-parse HEAD)
    if git rev-parse --verify "refs/tags/${tag}" >/dev/null 2>&1; then
        fail "Git tag ${tag} already exists locally"
    fi

    git tag -a "${tag}" \
        -m "Weekly image refresh ${tag}" \
        -m "Application source: ${application_sha}" \
        -m "Image digest: ${image_digest}" \
        "${metadata_sha}"

    # The history commit and its tag must either both become visible or neither
    # does. The tag targets current housekeeping, avoiding historical workflow
    # trees that GITHUB_TOKEN is not permitted to expose through a new ref.
    git push --atomic origin \
        "HEAD:refs/heads/${TARGET_BRANCH}" \
        "refs/tags/${tag}"

    echo "✅ Published housekeeping ${metadata_sha} and ${tag} atomically"
}

main() {
    validate_arguments "$@"
    commit_and_push "$@"
}

main "$@"
