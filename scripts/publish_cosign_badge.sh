#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later

set -euo pipefail

readonly TARGET_BRANCH="main"
readonly MAX_PUSH_ATTEMPTS=3

fail() {
    >&2 echo "ERROR: $1"
    exit 2
}

validate_arguments() {
    if [[ "$#" -ne 2 ]]; then
        fail "usage: $0 <ok|failed> <commit-message>"
    fi

    if [[ "$1" != "ok" && "$1" != "failed" ]]; then
        fail "badge status must be 'ok' or 'failed'"
    fi

    if [[ -z "$2" ]]; then
        fail "commit message must not be empty"
    fi
}

write_badge() {
    local status="$1"

    if [[ "${status}" == "failed" ]]; then
        python3 scripts/write_cosign_badge.py --failed
        return
    fi

    python3 scripts/write_cosign_badge.py
}

publish_badge() {
    local status="$1"
    local commit_message="$2"
    local attempt

    git config user.name "github-actions"
    git config user.email "actions@github.com"

    for ((attempt = 1; attempt <= MAX_PUSH_ATTEMPTS; attempt++)); do
        if ! git fetch origin "${TARGET_BRANCH}"; then
            >&2 echo "ERROR: unable to fetch origin/${TARGET_BRANCH} (attempt ${attempt}/${MAX_PUSH_ATTEMPTS})"
            continue
        fi

        git checkout -B "${TARGET_BRANCH}" "refs/remotes/origin/${TARGET_BRANCH}"
        write_badge "${status}"
        scripts/git_commit_if_changed.sh "${commit_message}" doc/cosign_badge.json

        if git push origin "HEAD:refs/heads/${TARGET_BRANCH}"; then
            echo "✅ Published cosign badge '${status}' to ${TARGET_BRANCH}"
            return
        fi

        >&2 echo "ERROR: badge push raced with another update (attempt ${attempt}/${MAX_PUSH_ATTEMPTS})"
    done

    fail "unable to publish cosign badge after ${MAX_PUSH_ATTEMPTS} attempts"
}

main() {
    validate_arguments "$@"
    publish_badge "$1" "$2"
}

main "$@"
