#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later

set -euo pipefail

fail() {
    >&2 echo "ERROR: $1"
    exit 2
}

validate_arguments() {
    if [[ "$#" -ne 2 ]]; then
        fail "usage: $0 <image> <expected-application-sha>"
    fi

    if [[ -z "$1" ]]; then
        fail "image must not be empty"
    fi
    if [[ ! "$2" =~ ^[0-9a-f]{40}$ ]]; then
        fail "expected application SHA must be 40 lowercase hexadecimal characters"
    fi
}

verify_image_revision() {
    local -r image="$1"
    local -r expected_revision="$2"
    local actual_revision

    if ! actual_revision="$(docker inspect \
        --format '{{ index .Config.Labels "org.opencontainers.image.revision" }}' \
        "${image}" 2>&1)"; then
        fail "could not inspect revision label on image ${image}: ${actual_revision}"
    fi

    if [[ ! "${actual_revision}" =~ ^[0-9a-f]{40}$ ]]; then
        fail "image ${image} has an invalid revision label: '${actual_revision}'"
    fi
    if [[ "${actual_revision}" != "${expected_revision}" ]]; then
        >&2 echo "ERROR: image revision mismatch on ${image}"
        >&2 echo "       expected: '${expected_revision}'"
        >&2 echo "       actual:   '${actual_revision}'"
        exit 2
    fi

    echo "Image revision verified on ${image}: ${actual_revision}"
}

main() {
    validate_arguments "$@"
    verify_image_revision "$1" "$2"
}

main "$@"
