#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later

set -euo pipefail

fail() {
    >&2 echo "ERROR: $1"
    exit 2
}

validate_arguments() {
    if [[ "$#" -ne 2 ]]; then
        fail "usage: $0 <source-sha> <dispatch-ref>"
    fi

    if [[ ! "$1" =~ ^[0-9a-f]{40}$ ]]; then
        fail "source SHA is not a full lowercase commit SHA: '$1'"
    fi

    if [[ "$2" != "refs/heads/main" ]]; then
        fail "releases must be dispatched from main, not '$2'"
    fi
}

validate_checkout() {
    local source_sha="$1"
    local actual_sha

    if ! git rev-parse --verify "${source_sha}^{commit}" >/dev/null 2>&1; then
        fail "source SHA does not identify a commit: '${source_sha}'"
    fi

    actual_sha="$(git rev-parse HEAD)"
    if [[ "${actual_sha}" != "${source_sha}" ]]; then
        fail "checked-out source '${actual_sha}' does not match '${source_sha}'"
    fi
}

validate_remote_main() {
    local source_sha="$1"
    local remote_main_sha

    if ! git fetch origin main; then
        fail "unable to fetch origin/main"
    fi

    remote_main_sha="$(git rev-parse refs/remotes/origin/main)"
    if [[ "${remote_main_sha}" != "${source_sha}" ]]; then
        >&2 echo "ERROR: main advanced after this release was dispatched"
        >&2 echo "  selected:     ${source_sha}"
        >&2 echo "  current main: ${remote_main_sha}"
        exit 2
    fi
}

main() {
    validate_arguments "$@"
    validate_checkout "$1"
    validate_remote_main "$1"
    echo "✅ Immutable release source verified: $1"
}

main "$@"
