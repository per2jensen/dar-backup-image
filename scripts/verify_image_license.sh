#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later

set -euo pipefail

fail() {
    >&2 echo "ERROR: $1"
    exit 2
}

validate_arguments() {
    if [[ "$#" -ne 2 ]]; then
        fail "usage: $0 <image> <expected-license-sha256>"
    fi

    if [[ -z "$1" ]]; then
        fail "image must not be empty"
    fi
    if [[ ! "$2" =~ ^[0-9a-f]{64}$ ]]; then
        fail "expected LICENSE SHA-256 must be 64 lowercase hexadecimal characters"
    fi
}

verify_image_license() {
    local -r image="$1"
    local -r expected_sha256="$2"
    local actual_output
    local actual_sha256

    if ! actual_output="$(docker run --rm \
        --entrypoint sha256sum \
        "${image}" \
        /LICENSE)"; then
        fail "could not calculate /LICENSE SHA-256 in image ${image}"
    fi

    read -r actual_sha256 _ <<< "${actual_output}"
    if [[ ! "${actual_sha256}" =~ ^[0-9a-f]{64}$ ]]; then
        fail "image ${image} returned an invalid /LICENSE SHA-256: '${actual_sha256}'"
    fi
    if [[ "${actual_sha256}" != "${expected_sha256}" ]]; then
        >&2 echo "ERROR: /LICENSE SHA-256 mismatch in image ${image}"
        >&2 echo "       expected: '${expected_sha256}'"
        >&2 echo "       actual:   '${actual_sha256}'"
        exit 2
    fi

    echo "Embedded /LICENSE SHA-256 verified in image ${image}: ${actual_sha256}"
}

main() {
    validate_arguments "$@"
    verify_image_license "$1" "$2"
}

main "$@"
