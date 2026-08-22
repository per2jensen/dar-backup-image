#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later

set -euo pipefail

readonly TARGET_BRANCH="main"

fail() {
    >&2 echo "ERROR: $1"
    exit 2
}

validate_arguments() {
    if [[ "$#" -ne 10 ]]; then
        fail "usage: $0 <version> <source-sha> <image-digest> <history> <sarif> <sbom> <readme> <badge> <pages> <annotation>"
    fi

    if [[ ! "$1" =~ ^[0-9]+\.[0-9]+\.[0-9]+(\.[0-9]+)?(-[0-9A-Za-z]+([.-][0-9A-Za-z]+)*)?$ ]]; then
        fail "release version is not supported"
    fi
    if [[ ! "$2" =~ ^[0-9a-f]{40}$ ]]; then
        fail "source SHA must contain exactly 40 lowercase hexadecimal characters"
    fi
    if [[ ! "$3" =~ ^[^[:space:]@]+@sha256:[0-9a-f]{64}$ ]]; then
        fail "image digest must be a qualified repository@sha256 reference"
    fi

    local required_path
    for required_path in "${@:4}"; do
        if [[ ! -s "${required_path}" ]]; then
            fail "housekeeping file does not exist or is empty: ${required_path}"
        fi
    done
}

validate_checkout() {
    local source_sha="$1"
    local head_sha

    head_sha=$(git rev-parse HEAD)
    if [[ "${head_sha}" != "${source_sha}" ]]; then
        fail "housekeeping checkout must start at source SHA ${source_sha}; found ${head_sha}"
    fi
}

commit_and_push() {
    local version="$1"
    local source_sha="$2"
    local image_digest="$3"
    local history_path="$4"
    local sarif_path="$5"
    local sbom_path="$6"
    local readme_path="$7"
    local badge_path="$8"
    local pages_path="$9"
    local annotation_path="${10}"
    local tag="v${version}"
    local housekeeping_sha

    git config user.name "github-actions"
    git config user.email "actions@github.com"

    # Audit evidence is ignored during local development. Force only the two
    # validated workflow outputs into the release housekeeping transaction.
    git add -- \
        "${history_path}" \
        "${readme_path}" \
        "${badge_path}" \
        "${pages_path}" \
        "${annotation_path}"
    git add -f -- "${sarif_path}" "${sbom_path}"

    local staged_path
    local allowed_path
    local is_allowed
    while IFS= read -r staged_path; do
        is_allowed="false"
        for allowed_path in \
            "${history_path}" \
            "${sarif_path}" \
            "${sbom_path}" \
            "${readme_path}" \
            "${badge_path}" \
            "${pages_path}" \
            "${annotation_path}"; do
            if [[ "${staged_path}" == "${allowed_path}" ]]; then
                is_allowed="true"
                break
            fi
        done
        if [[ "${is_allowed}" != "true" ]]; then
            fail "unexpected staged housekeeping path: ${staged_path}"
        fi
    done < <(git diff --cached --name-only)

    if ! git diff --quiet || [[ -n "$(git ls-files --others --exclude-standard)" ]]; then
        git status --short
        fail "housekeeping contains changes outside the validated release files"
    fi
    if git diff --cached --quiet; then
        fail "housekeeping produced no changes to commit"
    fi

    git commit -m "release: ${version} metadata, evidence, and documentation"
    housekeeping_sha=$(git rev-parse HEAD)

    if git rev-parse --verify "refs/tags/${tag}" >/dev/null 2>&1; then
        fail "Git tag ${tag} already exists locally"
    fi

    git tag -a "${tag}" \
        -m "Release version ${tag}" \
        -m "Application source: ${source_sha}" \
        -m "Housekeeping commit: ${housekeeping_sha}" \
        -m "Image digest: ${image_digest}" \
        "${source_sha}"

    # The audit commit and source-pointing release tag must either both become
    # visible or neither does. A concurrent main update rejects both refs.
    git push --atomic origin \
        "HEAD:refs/heads/${TARGET_BRANCH}" \
        "refs/tags/${tag}"

    echo "✅ Published housekeeping ${housekeeping_sha} and ${tag} atomically"
}

main() {
    validate_arguments "$@"
    validate_checkout "$2"
    commit_and_push "$@"
}

main "$@"
