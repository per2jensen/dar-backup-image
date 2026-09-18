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

inspect_label() {
    local image="$1"
    local label="$2"
    local output

    if ! output="$("${DOCKER}" image inspect \
        --format "{{ index .Config.Labels \"${label}\" }}" \
        "${image}" 2>&1)"; then
        fail "unable to inspect label ${label} on ${image}: ${output}"
    fi
    if [[ -z "${output}" || "${output}" == "<no value>" ]]; then
        fail "image ${image} has a missing or empty ${label} label"
    fi
    printf '%s\n' "${output}"
}

verify_exact_label() {
    local image="$1"
    local label="$2"
    local expected="$3"
    local actual

    actual="$(inspect_label "${image}" "${label}")"
    if [[ "${actual}" != "${expected}" ]]; then
        >&2 echo "ERROR: ${label} mismatch on ${image}"
        >&2 echo "       expected: '${expected}'"
        >&2 echo "       actual:   '${actual}'"
        exit 2
    fi
    echo "Verified ${label}: ${actual}"
}

validate_arguments() {
    if [[ "$#" -ne 8 ]]; then
        fail "usage: $0 <image> <revision> <image-version> <dar-backup-version> <dar-version> <ubuntu-digest> <install-source> <wheel-sha256>"
    fi
    if [[ -z "$1" || "$1" =~ [[:space:]] ]]; then
        fail "image reference must be non-empty and contain no whitespace"
    fi
    if [[ ! "$2" =~ ^[0-9a-f]{40}$ ]]; then
        fail "expected revision must be a full lowercase commit SHA"
    fi
    if [[ -z "$3" || -z "$4" || -z "$5" ]]; then
        fail "image, dar-backup, and DAR versions must not be empty"
    fi
    if [[ ! "$6" =~ ^sha256:[0-9a-f]{64}$ ]]; then
        fail "expected Ubuntu digest must be a canonical sha256 digest"
    fi
    if [[ "$7" != "pypi" && "$7" != "local" ]]; then
        fail "install source must be 'pypi' or 'local'"
    fi
    if [[ "$7" == "pypi" && "$8" != "not-applicable" ]]; then
        fail "PyPI images must use wheel SHA-256 value 'not-applicable'"
    fi
    if [[ "$7" == "local" && ! "$8" =~ ^[0-9a-f]{64}$ ]]; then
        fail "local-wheel images must use a 64-character lowercase wheel SHA-256"
    fi
}

main() {
    validate_arguments "$@"

    local image="$1"
    local revision="$2"
    local image_version="$3"
    local dar_backup_version="$4"
    local dar_version="$5"
    local ubuntu_digest="$6"
    local install_source="$7"
    local wheel_sha256="$8"

    DOCKER="${DOCKER:-docker}"
    if [[ -z "${DOCKER}" || "${DOCKER}" =~ [[:space:]] ]] \
        || ! command -v "${DOCKER}" >/dev/null 2>&1; then
        fail "DOCKER must name an available executable without arguments"
    fi

    verify_exact_label "${image}" "org.opencontainers.image.revision" "${revision}"
    verify_exact_label "${image}" "org.opencontainers.image.version" "${image_version}"
    verify_exact_label "${image}" "org.opencontainers.image.ref.name" \
        "per2jensen/dar-backup:${image_version}"
    verify_exact_label "${image}" "org.opencontainers.image.base.digest" "${ubuntu_digest}"
    verify_exact_label "${image}" "org.opencontainers.image.licenses" "GPL-3.0-or-later"
    verify_exact_label "${image}" "org.dar-backup.install-source" "${install_source}"
    verify_exact_label "${image}" "org.dar-backup.version" "${dar_backup_version}"
    verify_exact_label "${image}" "org.dar-backup.wheel.sha256" "${wheel_sha256}"
    verify_exact_label "${image}" "org.dar.version" "${dar_version}"
    echo "Image metadata verified for ${image}"
}

main "$@"
