#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPT_DIR

fail() {
    >&2 echo "ERROR: $1"
    exit 2
}

validate_arguments() {
    if [[ "$#" -ne 5 ]]; then
        fail "usage: $0 <source-dir> <base-version> <final-version> <dar-backup-version> <dar-version>"
    fi

    if [[ ! -d "$1" ]]; then
        fail "application source directory does not exist: $1"
    fi
    if [[ ! -f "$1/Makefile" ]]; then
        fail "application source Makefile does not exist: $1/Makefile"
    fi
    if [[ -z "$2" || -z "$3" || -z "$4" || -z "$5" ]]; then
        fail "version arguments must not be empty"
    fi
}

finalize_refresh_image() {
    local source_dir="$1"
    local base_version="$2"
    local final_version="$3"
    local dar_backup_version="$4"
    local dar_version="$5"
    local -a make_arguments=(
        "FINAL_VERSION=${final_version}"
        "DAR_BACKUP_VERSION=${dar_backup_version}"
        "DAR_VERSION=${dar_version}"
    )

    if grep -Eq '^refresh-final-noscan:' "${source_dir}/Makefile"; then
        make -C "${source_dir}" \
            "${make_arguments[@]}" \
            "BASE_VERSION=${base_version}" \
            refresh-final-noscan
        return
    fi

    # Compatibility for stable tags created before refresh-final-noscan. The
    # base was selected from build history, so IMAGE_VERSION is intentionally
    # irrelevant at this boundary.
    python3 "${SCRIPT_DIR}/validate_image_version.py" refresh \
        --base-version "${base_version}" \
        --final-version "${final_version}"
    make -C "${source_dir}" "${make_arguments[@]}" final-noscan
}

main() {
    validate_arguments "$@"
    finalize_refresh_image "$@"
}

main "$@"
