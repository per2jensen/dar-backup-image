#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later

set -euo pipefail

fail() {
    >&2 echo "ERROR: $1"
    exit 2
}

validate_arguments() {
    if [[ "$#" -ne 2 ]]; then
        fail "usage: $0 <repository> <refresh-version>"
    fi

    if [[ ! "$1" =~ ^[^[:space:]@:]+$ ]]; then
        fail "repository must be a nonempty name without whitespace, a tag, or a digest"
    fi
    if [[ ! "$2" =~ ^[0-9]+\.[0-9]+\.[0-9]+-[1-9][0-9]*$ ]]; then
        fail "refresh version must be x.y.z-N with a positive canonical N"
    fi
}

verify_docker_tag_available() {
    local -r repository="$1"
    local -r refresh_version="$2"
    local -r image="${repository}:${refresh_version}"
    local manifest_output

    if manifest_output="$(docker manifest inspect "${image}" 2>&1)"; then
        fail "Docker tag ${image} already exists and will not be overwritten"
    fi

    if grep -Eqi 'manifest unknown|no such manifest|manifest[^[:cntrl:]]*not found' \
        <<< "${manifest_output}"; then
        echo "Docker tag is available: ${image}"
        return
    fi

    if [[ -z "${manifest_output}" ]]; then
        manifest_output="no diagnostic output"
    fi
    fail "could not prove Docker tag ${image} is available: ${manifest_output}"
}

main() {
    validate_arguments "$@"
    verify_docker_tag_available "$1" "$2"
}

main "$@"
