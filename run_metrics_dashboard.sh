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

usage() {
    >&2 echo "Usage: $0"
    >&2 echo "Environment: RESULTS_JSONL, BACKUP_METRICS_DB, DASHBOARD_OUTPUT, DASHBOARD_PORT, DASHBOARD_IMAGE, DOCKER"
}

validate_safe_path_for_docker_mount() {
    local path="$1"
    local label="$2"
    if [[ -z "$path" || "$path" == *","* ]]; then
        >&2 echo "ERROR: ${label} must be a non-empty path without commas: '${path}'"
        return 2
    fi
}

main() {
    if (( $# != 0 )); then
        usage
        return 2
    fi

    local repo_dir
    repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    local results_jsonl="${RESULTS_JSONL:-${repo_dir}/doc/test-report/large-scale-results.jsonl}"
    local dashboard_output="${DASHBOARD_OUTPUT:-${repo_dir}/.cache/dar-backup-dashboard/large-scale-dashboard.db}"
    local dashboard_port="${DASHBOARD_PORT:-8001}"
    local dashboard_image="${DASHBOARD_IMAGE:-dar-backup-metrics-dashboard:dev}"
    local docker_command="${DOCKER:-docker}"
    local operational_metrics_db=""

    if [[ -v BACKUP_METRICS_DB ]]; then
        operational_metrics_db="${BACKUP_METRICS_DB}"
    elif [[ -f /data/tmp/image-large-scale-test/results/dar-backup-metrics.db ]]; then
        operational_metrics_db="/data/tmp/image-large-scale-test/results/dar-backup-metrics.db"
    fi

    if ! [[ "$dashboard_port" =~ ^[1-9][0-9]*$ ]] \
        || (( 10#$dashboard_port > 65535 )); then
        >&2 echo "ERROR: DASHBOARD_PORT must be an integer between 1 and 65535"
        return 2
    fi
    if [[ -z "$dashboard_image" || "$dashboard_image" == -* \
        || "$dashboard_image" =~ [[:space:]] ]]; then
        >&2 echo "ERROR: DASHBOARD_IMAGE must be a non-empty image reference without whitespace"
        return 2
    fi
    if [[ -z "$docker_command" || "$docker_command" =~ [[:space:]] ]] \
        || ! command -v "$docker_command" >/dev/null 2>&1; then
        >&2 echo "ERROR: DOCKER must name an available executable without arguments"
        return 127
    fi
    if [[ ! -f "$results_jsonl" ]]; then
        >&2 echo "ERROR: RESULTS_JSONL is not a file: '${results_jsonl}'"
        return 2
    fi
    if [[ -n "$operational_metrics_db" && ! -f "$operational_metrics_db" ]]; then
        >&2 echo "ERROR: BACKUP_METRICS_DB is not a file: '${operational_metrics_db}'"
        return 2
    fi

    results_jsonl="$(realpath "$results_jsonl")"
    local output_parent
    output_parent="$(dirname "$dashboard_output")"
    mkdir -p "$output_parent"
    dashboard_output="$(realpath -m "$dashboard_output")"
    local metadata_file="${repo_dir}/dashboard/metadata.json"
    validate_safe_path_for_docker_mount "$dashboard_output" "DASHBOARD_OUTPUT"
    validate_safe_path_for_docker_mount "$metadata_file" "dashboard metadata path"

    local builder_arguments=(
        "${repo_dir}/scripts/build_large_scale_dashboard.py"
        --results-jsonl "$results_jsonl"
        --output "$dashboard_output"
    )
    if [[ -n "$operational_metrics_db" ]]; then
        operational_metrics_db="$(realpath "$operational_metrics_db")"
        builder_arguments+=(--operational-metrics-db "$operational_metrics_db")
    fi

    python3 "${builder_arguments[@]}"

    >&2 echo "Building Datasette dashboard image '${dashboard_image}'..."
    "$docker_command" build \
        --file "${repo_dir}/dashboard/Dockerfile" \
        --tag "$dashboard_image" \
        "${repo_dir}/dashboard"

    >&2 echo "Dashboard: http://127.0.0.1:${dashboard_port}/-/dashboards/large-scale"
    >&2 echo "Press Ctrl-C to stop Datasette."
    exec "$docker_command" run --rm --init --read-only \
        --cap-drop ALL \
        --security-opt no-new-privileges:true \
        --tmpfs /tmp:rw,noexec,nosuid,size=16m \
        --publish "127.0.0.1:${dashboard_port}:8001" \
        --mount "type=bind,src=${dashboard_output},dst=/data/large-scale-dashboard.db,readonly" \
        --mount "type=bind,src=${metadata_file},dst=/config/metadata.json,readonly" \
        "$dashboard_image" \
        --immutable /data/large-scale-dashboard.db \
        --metadata /config/metadata.json \
        --host 0.0.0.0 \
        --port 8001 \
        --setting default_page_size 50 \
        --setting sql_time_limit_ms 10000 \
        --setting max_returned_rows 5000
}

main "$@"
