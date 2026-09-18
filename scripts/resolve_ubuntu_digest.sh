#!/bin/bash

# SPDX-FileCopyrightText: 2025-2026 Per Jensen
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This file is part of dar-backup-image:
# https://github.com/per2jensen/dar-backup-image
#
# License terms and warranty disclaimer:
# https://github.com/per2jensen/dar-backup-image/blob/main/LICENSE

set -euo pipefail

fail() {
    >&2 echo "ERROR: $1"
    exit 2
}

validate_digest() {
    local digest="$1"

    if [[ ! "${digest}" =~ ^sha256:[0-9a-f]{64}$ ]]; then
        fail "Ubuntu image digest must be sha256 followed by 64 lowercase hexadecimal characters"
    fi
}

main() {
    if [[ "$#" -ne 3 ]]; then
        fail "usage: $0 <docker-command> <ubuntu-image> <optional-pinned-digest>"
    fi

    local docker_command="$1"
    local image="$2"
    local pinned_digest="$3"
    local inspect_output
    local digest

    if [[ -z "${docker_command}" || "${docker_command}" =~ [[:space:]] ]] \
        || ! command -v "${docker_command}" >/dev/null 2>&1; then
        fail "docker command must name an available executable without arguments"
    fi
    if [[ ! "${image}" =~ ^ubuntu:[0-9]+\.[0-9]+$ ]]; then
        fail "Ubuntu image must use the canonical ubuntu:X.Y form, got '${image}'"
    fi

    if [[ -n "${pinned_digest}" ]]; then
        validate_digest "${pinned_digest}"
        printf '%s\n' "${pinned_digest}"
        return 0
    fi

    >&2 echo "Resolving immutable digest for ${image}..."
    if ! "${docker_command}" pull "${image}" >&2; then
        fail "unable to pull ${image} with ${docker_command}"
    fi
    if ! inspect_output="$("${docker_command}" image inspect \
        --format '{{range .RepoDigests}}{{println .}}{{end}}' \
        "${image}" 2>&1)"; then
        fail "unable to inspect ${image}: ${inspect_output}"
    fi

    digest=""
    while IFS= read -r repository_digest; do
        if [[ "${repository_digest}" =~ ^ubuntu@(sha256:[0-9a-f]{64})$ ]]; then
            digest="${BASH_REMATCH[1]}"
            break
        fi
    done <<< "${inspect_output}"
    if [[ -z "${digest}" ]]; then
        fail "${image} has no canonical ubuntu@sha256 repository digest"
    fi
    validate_digest "${digest}"
    >&2 echo "Resolved ${image} to ${digest}"
    printf '%s\n' "${digest}"
}

main "$@"
