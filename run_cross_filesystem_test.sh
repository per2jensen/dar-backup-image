#!/usr/bin/env bash

# CFT_* state is exported by name to the Python result writer.
# shellcheck disable=SC2034

# SPDX-FileCopyrightText: 2025-2026 Per Jensen
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This file is part of dar-backup-image:
# https://github.com/per2jensen/dar-backup-image
#
# License terms and warranty disclaimer:
# https://github.com/per2jensen/dar-backup-image/blob/main/LICENSE
#
# Cross-filesystem FULL backup and restore verification for dar-backup.
# Usage: run_cross_filesystem_test.sh [OPTIONS]

set -euo pipefail

SCRIPT_VERSION="1"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCENARIO="etc-to-home"
BACKUP_USER="pj"
IMAGE="dar-backup:dev"
BUILD_IMAGE=0
KEEP=0
BASE_DIR="/data/tmp/dar-backup-cross-filesystem-test"
HOME_ROOT="/home/pj"
HOME_RESTORE_BASE="/home/pj/tmp/restore-test"
SLICE_SIZE="1G"
PAR2_RATIO="5"
TIMEOUT="86400"
DATASET_ID=""
HOME_SOURCES=()
HOME_RELATIVE_SOURCES=()

RESULT_INITIALIZED=0
RESULT_WRITTEN=0
RUN_COMPLETED=0
CURRENT_PHASE="argument_validation"
RUN_STARTED_EPOCH="$(date +%s)"
RUN_STARTED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)-$$"
RUN_DIR=""
HOME_RESTORE_DIR=""
RESULTS_FILE="${BASE_DIR}/results/cross-filesystem-results.jsonl"
BACKUP_UID=""
BACKUP_GID=""
BACKUP_GROUPS=()
DOCKER_IDENTITY_ARGS=()

CFT_IMAGE_ID="unknown"
CFT_IMAGE_REPO_DIGEST=""
CFT_IMAGE_REVISION=""
CFT_IMAGE_VERSION=""
CFT_GIT_COMMIT="unknown"
CFT_GIT_DIRTY=0

usage() {
    sed -n 's/^# Usage: /Usage: /p; s/^#   /  /p' "$0"
    cat <<'EOF'

Options:
  --scenario etc-to-home|home-to-data|both
  --backup-user pj|root
  --home-source ABSOLUTE_PATH       Repeatable; required for home-to-data
  --dataset-id ID                  Opaque result-history cohort label
  --image IMAGE                    Default: dar-backup:dev
  --build                          Run `make dev` before image inspection
  --keep                           Retain archives, logs, and restored trees
  --base-dir PATH                  Default: /data/tmp/dar-backup-cross-filesystem-test
  --home-restore-base PATH         Default: /home/pj/tmp/restore-test
  --slice SIZE                     Default: 1G
  --par2-ratio PERCENT             Default: 5
  --timeout SECONDS                Default: 86400
  -h, --help

Examples:
  ./run_cross_filesystem_test.sh
  ./run_cross_filesystem_test.sh --backup-user root
  ./run_cross_filesystem_test.sh --scenario home-to-data \
    --home-source /home/pj/Documents --dataset-id documents
EOF
}

info() {
    echo "INFO: $*"
}

pass() {
    echo "PASS: $*"
}

error() {
    echo "ERROR: $*" >&2
}

set_phase() {
    CURRENT_PHASE="$1"
    info "Phase: ${CURRENT_PHASE}"
}

parse_arguments() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --scenario) [[ $# -ge 2 ]] || { error "--scenario requires a value"; return 2; }; SCENARIO="$2"; shift 2 ;;
            --backup-user) [[ $# -ge 2 ]] || { error "--backup-user requires a value"; return 2; }; BACKUP_USER="$2"; shift 2 ;;
            --home-source) [[ $# -ge 2 ]] || { error "--home-source requires a value"; return 2; }; HOME_SOURCES+=("$2"); shift 2 ;;
            --dataset-id) [[ $# -ge 2 ]] || { error "--dataset-id requires a value"; return 2; }; DATASET_ID="$2"; shift 2 ;;
            --image) [[ $# -ge 2 ]] || { error "--image requires a value"; return 2; }; IMAGE="$2"; shift 2 ;;
            --build) BUILD_IMAGE=1; shift ;;
            --keep) KEEP=1; shift ;;
            --base-dir) [[ $# -ge 2 ]] || { error "--base-dir requires a value"; return 2; }; BASE_DIR="$2"; shift 2 ;;
            --home-restore-base) [[ $# -ge 2 ]] || { error "--home-restore-base requires a value"; return 2; }; HOME_RESTORE_BASE="$2"; shift 2 ;;
            --slice) [[ $# -ge 2 ]] || { error "--slice requires a value"; return 2; }; SLICE_SIZE="$2"; shift 2 ;;
            --par2-ratio) [[ $# -ge 2 ]] || { error "--par2-ratio requires a value"; return 2; }; PAR2_RATIO="$2"; shift 2 ;;
            --timeout) [[ $# -ge 2 ]] || { error "--timeout requires a value"; return 2; }; TIMEOUT="$2"; shift 2 ;;
            -h|--help) usage; exit 0 ;;
            *) error "unknown option: $1"; return 2 ;;
        esac
    done
    RESULTS_FILE="${BASE_DIR}/results/cross-filesystem-results.jsonl"
}

validate_arguments() {
    case "$SCENARIO" in
        etc-to-home|home-to-data|both) ;;
        *) error "--scenario must be etc-to-home, home-to-data, or both"; return 2 ;;
    esac
    case "$BACKUP_USER" in
        pj|root) ;;
        *) error "--backup-user must be pj or root"; return 2 ;;
    esac
    [[ "$BASE_DIR" == /* && "$BASE_DIR" != "/" ]] || { error "--base-dir must be an absolute path other than /"; return 2; }
    [[ "$HOME_RESTORE_BASE" == /* && "$HOME_RESTORE_BASE" != "/" ]] || { error "--home-restore-base must be an absolute path other than /"; return 2; }
    [[ "$SLICE_SIZE" =~ ^[1-9][0-9]*[kKmMgGtT]$ ]] || { error "--slice must be a positive size with K, M, G, or T units"; return 2; }
    [[ "$PAR2_RATIO" =~ ^([1-9]|[1-9][0-9]|100)$ ]] || { error "--par2-ratio must be an integer from 1 through 100"; return 2; }
    [[ "$TIMEOUT" =~ ^[1-9][0-9]*$ ]] || { error "--timeout must be a positive integer"; return 2; }
    if [[ -n "$DATASET_ID" && ! "$DATASET_ID" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$ ]]; then
        error "--dataset-id must be 1-128 characters using letters, digits, '.', '_', or '-'"
        return 2
    fi
    if [[ "$SCENARIO" == "home-to-data" || "$SCENARIO" == "both" ]]; then
        [[ ${#HOME_SOURCES[@]} -gt 0 ]] || { error "${SCENARIO} requires at least one --home-source"; return 2; }
    elif [[ ${#HOME_SOURCES[@]} -gt 0 ]]; then
        error "--home-source requires --scenario home-to-data or both"
        return 2
    fi
}

existing_ancestor() {
    local candidate="$1"
    while [[ ! -e "$candidate" ]]; do
        [[ "$candidate" != "/" ]] || break
        candidate="$(dirname "$candidate")"
    done
    printf '%s\n' "$candidate"
}

filesystem_type() {
    local target="$1"
    local ancestor
    ancestor="$(existing_ancestor "$target")"
    findmnt -n -o FSTYPE --target "$ancestor"
}

require_filesystem_type() {
    local target="$1"
    local expected="$2"
    local label="$3"
    local actual
    actual="$(filesystem_type "$target")"
    if [[ "$actual" != "$expected" ]]; then
        error "${label} must be on ${expected}, got ${actual:-unknown}: ${target}"
        return 1
    fi
}

path_device() {
    stat -c %d -- "$1"
}

validate_home_source_argument() {
    [[ $# -eq 1 ]] || { error "validate_home_source_argument requires exactly one path"; return 2; }
    local source_path="$1"
    local normalized_source normalized_home normalized_restore normalized_base
    [[ "$source_path" == /* ]] || { error "--home-source must be absolute"; return 2; }
    [[ "$source_path" != *$'\n'* && "$source_path" != *$'\r'* ]] || { error "--home-source must not contain line breaks"; return 2; }
    [[ ! -L "$source_path" ]] || { error "a top-level --home-source must not be a symbolic link: ${source_path}"; return 2; }

    # Use canonicalized paths without requiring them to exist so unsafe arguments
    # fail before host-specific identity and filesystem checks.
    normalized_home="$(readlink -m -- "$HOME_ROOT")"
    normalized_source="$(readlink -m -- "$source_path")"
    [[ "$normalized_source" != "$normalized_home" && "$normalized_source" == "$normalized_home"/* ]] || { error "--home-source must be below ${normalized_home}, not the whole home directory"; return 2; }

    normalized_restore="$(readlink -m -- "$HOME_RESTORE_BASE")"
    if [[ "$normalized_restore" == "$normalized_source" || "$normalized_restore" == "$normalized_source"/* || "$normalized_source" == "$normalized_restore"/* ]]; then
        error "--home-source overlaps the home restore base"
        return 2
    fi

    normalized_base="$(readlink -m -- "$BASE_DIR")"
    if [[ "$normalized_base" == "$normalized_source" || "$normalized_base" == "$normalized_source"/* || "$normalized_source" == "$normalized_base"/* ]]; then
        error "--home-source overlaps the archive base"
        return 2
    fi
    return 0
}

validate_home_source_arguments() {
    local source_path
    for source_path in "${HOME_SOURCES[@]}"; do
        validate_home_source_argument "$source_path" || return $?
    done
    return 0
}

validate_home_sources() {
    local source_path resolved_source resolved_home resolved_restore resolved_base existing
    local -a candidates=()
    resolved_home="$(readlink -e -- "$HOME_ROOT")"
    for source_path in "${HOME_SOURCES[@]}"; do
        [[ "$source_path" == /* ]] || { error "--home-source must be absolute"; return 2; }
        [[ "$source_path" != *$'\n'* && "$source_path" != *$'\r'* ]] || { error "--home-source must not contain line breaks"; return 2; }
        [[ ! -L "$source_path" ]] || { error "a top-level --home-source must not be a symbolic link: ${source_path}"; return 2; }
        resolved_source="$(readlink -e -- "$source_path")" || { error "--home-source does not exist: ${source_path}"; return 2; }
        [[ "$resolved_source" != "$resolved_home" && "$resolved_source" == "$resolved_home"/* ]] || { error "--home-source must be below ${resolved_home}, not the whole home directory"; return 2; }
        require_filesystem_type "$resolved_source" "btrfs" "home source" || return 1
        resolved_restore="$(readlink -m -- "$HOME_RESTORE_BASE")"
        if [[ "$resolved_restore" == "$resolved_source" || "$resolved_restore" == "$resolved_source"/* || "$resolved_source" == "$resolved_restore"/* ]]; then
            error "--home-source overlaps the home restore base"
            return 2
        fi
        resolved_base="$(readlink -m -- "$BASE_DIR")"
        if [[ "$resolved_base" == "$resolved_source" || "$resolved_base" == "$resolved_source"/* || "$resolved_source" == "$resolved_base"/* ]]; then
            error "--home-source overlaps the archive base"
            return 2
        fi
        candidates+=("$resolved_source")
    done

    HOME_SOURCES=()
    HOME_RELATIVE_SOURCES=()
    while IFS= read -r source_path; do
        [[ -n "$source_path" ]] || continue
        for existing in "${HOME_SOURCES[@]}"; do
            if [[ "$source_path" == "$existing" || "$source_path" == "$existing"/* ]]; then
                source_path=""
                break
            fi
        done
        [[ -n "$source_path" ]] || continue
        HOME_SOURCES+=("$source_path")
        HOME_RELATIVE_SOURCES+=("${source_path#"$resolved_home"/}")
    done < <(printf '%s\n' "${candidates[@]}" | sort -u)
    [[ ${#HOME_SOURCES[@]} -gt 0 ]] || { error "no home selections remain after validation"; return 2; }
}

resolve_identity() {
    if [[ "$BACKUP_USER" == "root" ]]; then
        BACKUP_UID=0
        BACKUP_GID=0
        BACKUP_GROUPS=(0)
    else
        getent passwd pj >/dev/null || { error "host user 'pj' does not exist"; return 1; }
        BACKUP_UID="$(id -u pj)"
        BACKUP_GID="$(id -g pj)"
        read -r -a BACKUP_GROUPS <<< "$(id -G pj)"
    fi
    DOCKER_IDENTITY_ARGS=(--user "${BACKUP_UID}:${BACKUP_GID}")
    local group_id
    for group_id in "${BACKUP_GROUPS[@]}"; do
        [[ "$group_id" == "$BACKUP_GID" ]] && continue
        DOCKER_IDENTITY_ARGS+=(--group-add "$group_id")
    done
}

initialize_scenario_state() {
    local prefix="$1"
    local requested="$2"
    local expected="$3"
    local status="skipped"
    local check_status="skipped"
    [[ "$requested" -eq 0 ]] || { status="not_run"; check_status="not_run"; }
    printf -v "CFT_${prefix}_STATUS" '%s' "$status"
    printf -v "CFT_${prefix}_EXPECTED_OUTCOME" '%s' "$expected"
    printf -v "CFT_${prefix}_OBSERVED_OUTCOME" '%s' "not_run"
    printf -v "CFT_${prefix}_FAILURE_REASON" '%s' ""
    printf -v "CFT_${prefix}_SELECTION_COUNT" '%s' "0"
    printf -v "CFT_${prefix}_DEFINITION_SHA256" '%s' ""
    local field
    for field in SOURCE_ENTRIES SOURCE_FILES SOURCE_BYTES SOURCE_FSTYPE SOURCE_DEVICE ARCHIVE_BYTES ARCHIVE_SLICES ARCHIVE_FSTYPE ARCHIVE_DEVICE RESTORE_FSTYPE RESTORE_DEVICE RESTORE_ENTRIES RESTORE_FILES RESTORE_BYTES RESTORE_XATTRS RESTORE_HARD_LINK_GROUPS BACKUP_SECONDS VERIFY_SECONDS RESTORE_SECONDS TOTAL_SECONDS; do
        printf -v "CFT_${prefix}_${field}" '%s' ""
    done
    local check
    for check in MANAGER_DATABASE BACKUP DAR_INTEGRITY PAR2_FILES PAR2_VERIFY SOURCE_STABILITY RESTORE_EXECUTION CONTENT METADATA OVERALL; do
        printf -v "CFT_${prefix}_CHECK_${check}" '%s' "$check_status"
    done
}

set_scenario_value() {
    local prefix="$1"
    local field="$2"
    local value="$3"
    printf -v "CFT_${prefix}_${field}" '%s' "$value"
}

set_scenario_check() {
    local prefix="$1"
    local check="$2"
    local value="$3"
    printf -v "CFT_${prefix}_CHECK_${check}" '%s' "$value"
}

mark_scenario_failed() {
    local prefix="$1"
    local reason="$2"
    set_scenario_value "$prefix" STATUS "failed"
    set_scenario_value "$prefix" FAILURE_REASON "$reason"
    set_scenario_check "$prefix" OVERALL "failed"
}

initialize_result_state() {
    local etc_requested=0 home_requested=0 etc_expected="success"
    [[ "$SCENARIO" == "etc-to-home" || "$SCENARIO" == "both" ]] && etc_requested=1
    [[ "$SCENARIO" == "home-to-data" || "$SCENARIO" == "both" ]] && home_requested=1
    [[ "$BACKUP_USER" != "pj" ]] || etc_expected="permission_denied"
    initialize_scenario_state ETC "$etc_requested" "$etc_expected"
    initialize_scenario_state HOME "$home_requested" "success"
    if [[ "$etc_requested" -eq 1 ]]; then
        set_scenario_value ETC SELECTION_COUNT "1"
    fi
    set_scenario_value HOME SELECTION_COUNT "${#HOME_RELATIVE_SOURCES[@]}"
}

initialize_run_directories() {
    umask 077
    local base_parent
    [[ ! -L "$BASE_DIR" ]] || { error "archive base must not be a symbolic link: ${BASE_DIR}"; return 1; }
    base_parent="$(existing_ancestor "$BASE_DIR")"
    require_filesystem_type "$base_parent" "zfs" "archive base" || return 1
    mkdir -p -- "$BASE_DIR/results" "$BASE_DIR/runs"
    chmod 0700 -- "$BASE_DIR" "$BASE_DIR/results" "$BASE_DIR/runs"
    RUN_DIR="$(mktemp -d "${BASE_DIR}/runs/${RUN_ID}.XXXXXX")"
    printf '%s\n' "$RUN_ID" > "${RUN_DIR}/.cross-filesystem-test-run"
    RESULT_INITIALIZED=1
    trap on_exit EXIT
    trap 'exit 130' INT
    trap 'exit 143' TERM
}

inspect_image_and_checkout() {
    if [[ "$BUILD_IMAGE" -eq 1 ]]; then
        info "Building ${IMAGE}"
        make -C "$SCRIPT_DIR" dev
    fi
    command -v docker >/dev/null || { error "docker is required"; return 1; }
    docker image inspect "$IMAGE" >/dev/null 2>&1 || { error "local image is unavailable: ${IMAGE}"; return 1; }
    # These values are consumed dynamically by write_result().
    # shellcheck disable=SC2034
    CFT_IMAGE_ID="$(docker image inspect "$IMAGE" --format '{{.Id}}')"
    CFT_IMAGE_REPO_DIGEST="$(docker image inspect "$IMAGE" --format '{{if .RepoDigests}}{{index .RepoDigests 0}}{{end}}' | sed 's/^.*@//' || true)"
    CFT_IMAGE_REVISION="$(docker image inspect "$IMAGE" --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' 2>/dev/null || true)"
    CFT_IMAGE_VERSION="$(docker image inspect "$IMAGE" --format '{{index .Config.Labels "org.opencontainers.image.version"}}' 2>/dev/null || true)"
    [[ "$CFT_IMAGE_REPO_DIGEST" != "<no value>" ]] || CFT_IMAGE_REPO_DIGEST=""
    [[ "$CFT_IMAGE_REVISION" != "<no value>" ]] || CFT_IMAGE_REVISION=""
    [[ "$CFT_IMAGE_VERSION" != "<no value>" ]] || CFT_IMAGE_VERSION=""
    # shellcheck disable=SC2034
    CFT_GIT_COMMIT="$(git -C "$SCRIPT_DIR" rev-parse HEAD 2>/dev/null || echo unknown)"
    if [[ -n "$(git -C "$SCRIPT_DIR" status --porcelain 2>/dev/null || true)" ]]; then
        # shellcheck disable=SC2034
        CFT_GIT_DIRTY=1
    fi
}

prepare_scenario_directories() {
    local scenario_dir="$1"
    mkdir -p -- "$scenario_dir/backups" "$scenario_dir/par2" "$scenario_dir/backup.d" "$scenario_dir/manager" "$scenario_dir/internal-restore"
    chmod 0700 -- "$scenario_dir" "$scenario_dir"/*
}

write_scenario_config() {
    local scenario_dir="$1"
    cat > "${scenario_dir}/dar-backup.conf" <<EOF
[MISC]
LOGFILE_LOCATION = /backups/dar-backup.log
MAX_SIZE_VERIFICATION_MB = 200
MIN_SIZE_VERIFICATION_MB = 1
NO_FILES_VERIFICATION = 5
COMMAND_TIMEOUT_SECS = ${TIMEOUT}
COMMAND_CAPTURE_MAX_BYTES = 102400
METRICS_DB_PATH = /manager/dar-backup-metrics.db
RESTORE_OWNERSHIP = yes
[DIRECTORIES]
BACKUP_DIR = /backups
BACKUP.D_DIR = /backup.d
TEST_RESTORE_DIR = /internal-restore
MANAGER_DB_DIR = /manager
[AGE]
DIFF_AGE = 50
INCR_AGE = 30
[PAR2]
ERROR_CORRECTION_PERCENT = ${PAR2_RATIO}
ENABLED = True
PAR2_DIR = /par2
EOF
}

definition_quote() {
    python3 -c 'import shlex, sys; print(shlex.quote(sys.argv[1]))' "$1"
}

write_scenario_definition() {
    local scenario_dir="$1"
    shift
    local definition="${scenario_dir}/backup.d/cross-filesystem"
    {
        echo "-R /source"
        echo "-s ${SLICE_SIZE}"
        echo "-z6"
        echo "-am"
        local selection
        for selection in "$@"; do
            printf '%s %s\n' "-g" "$(definition_quote "$selection")"
        done
    } > "$definition"
    sha256sum "$definition" | awk '{print $1}'
}

manifest_capture() {
    local source_root="$1"
    local scenario_dir="$2"
    local ownership_check="$3"
    shift 3
    local -a selection_args=()
    local selection group_id
    for selection in "$@"; do selection_args+=(--selection "$selection"); done
    local -a ownership_args=()
    if [[ "$ownership_check" -eq 1 ]]; then
        ownership_args+=(--required-uid "$BACKUP_UID")
        for group_id in "${BACKUP_GROUPS[@]}"; do ownership_args+=(--allowed-gid "$group_id"); done
    fi
    docker run --rm "${DOCKER_IDENTITY_ARGS[@]}" \
        -v "${source_root}:/tree:ro" \
        -v "${scenario_dir}:/work" \
        -v "${SCRIPT_DIR}/scripts/cross_filesystem_manifest.py:/harness/manifest.py:ro" \
        --entrypoint /opt/venv/bin/python3 \
        "$IMAGE" /harness/manifest.py capture --source-root /tree \
        "${selection_args[@]}" "${ownership_args[@]}" --output /work/source-manifest.json
}

manifest_verify() {
    local root="$1"
    local scenario_dir="$2"
    local strict_extra="$3"
    local -a extra_args=()
    [[ "$strict_extra" -eq 0 ]] || extra_args+=(--strict-extra)
    docker run --rm "${DOCKER_IDENTITY_ARGS[@]}" \
        -v "${root}:/tree:ro" \
        -v "${scenario_dir}:/work:ro" \
        -v "${SCRIPT_DIR}/scripts/cross_filesystem_manifest.py:/harness/manifest.py:ro" \
        --entrypoint /opt/venv/bin/python3 \
        "$IMAGE" /harness/manifest.py verify --manifest /work/source-manifest.json \
        --root /tree "${extra_args[@]}"
}

docker_backup() {
    local source_root="$1"
    local scenario_dir="$2"
    local mount_name="${3:-}"
    local -a source_mounts=()
    if [[ -n "$mount_name" ]]; then
        mkdir -p -- "${scenario_dir}/source-root/${mount_name}"
        source_mounts+=(
            -v "${scenario_dir}/source-root:/source:ro"
            -v "${source_root}:/source/${mount_name}:ro"
        )
    else
        source_mounts+=(-v "${source_root}:/source:ro")
    fi
    docker run --rm "${DOCKER_IDENTITY_ARGS[@]}" \
        -e RUN_AS_UID="$BACKUP_UID" -e RUN_AS_GID="$BACKUP_GID" \
        -e DAR_BACKUP_CONFIG=/config/dar-backup.conf \
        -e DAR_BACKUP_DIR=/backups -e DAR_BACKUP_D_DIR=/backup.d \
        -e DAR_BACKUP_DATA_DIR=/source -e DAR_BACKUP_RESTORE_DIR=/internal-restore \
        "${source_mounts[@]}" \
        -v "${scenario_dir}/backups:/backups" \
        -v "${scenario_dir}/par2:/par2" \
        -v "${scenario_dir}/backup.d:/backup.d" \
        -v "${scenario_dir}/manager:/manager" \
        -v "${scenario_dir}/internal-restore:/internal-restore" \
        -v "${scenario_dir}/dar-backup.conf:/config/dar-backup.conf:ro" \
        "$IMAGE" -F -d cross-filesystem --config /config/dar-backup.conf --log-stdout --verbose
}

find_archive_base() {
    local backup_dir="$1"
    local -a first_slices=()
    mapfile -t first_slices < <(find "$backup_dir" -maxdepth 1 -type f -name 'cross-filesystem_FULL_*.1.dar' -print)
    [[ ${#first_slices[@]} -eq 1 ]] || { error "expected one FULL archive, found ${#first_slices[@]}"; return 1; }
    printf '%s\n' "${first_slices[0]%.1.dar}"
}

verify_archive() {
    local scenario_dir="$1"
    local archive_base="$2"
    docker run --rm "${DOCKER_IDENTITY_ARGS[@]}" \
        -v "${scenario_dir}/backups:/backups:ro" \
        --entrypoint /usr/local/bin/dar "$IMAGE" \
        -t "/backups/$(basename "$archive_base")" -N -Q
}

verify_par2() {
    local scenario_dir="$1"
    local -a par2_files=()
    mapfile -t par2_files < <(find "${scenario_dir}/par2" -maxdepth 1 -type f -name '*.dar.par2' -print | sort)
    [[ ${#par2_files[@]} -gt 0 ]] || { error "no per-slice PAR2 files were produced"; return 1; }
    local par2_file
    for par2_file in "${par2_files[@]}"; do
        docker run --rm "${DOCKER_IDENTITY_ARGS[@]}" \
            -v "${scenario_dir}/backups:/backups:ro" \
            -v "${scenario_dir}/par2:/par2:ro" \
            --entrypoint /usr/bin/par2 "$IMAGE" \
            verify -B /backups -q "/par2/$(basename "$par2_file")"
    done
}

restore_archive() {
    local scenario_dir="$1"
    local restore_dir="$2"
    local source_root="$3"
    local mount_name="$4"
    shift 4
    local -a source_mounts=()
    if [[ -n "$mount_name" ]]; then
        source_mounts+=(
            -v "${scenario_dir}/source-root:/source:ro"
            -v "${source_root}:/source/${mount_name}:ro"
        )
    else
        source_mounts+=(-v "${source_root}:/source:ro")
    fi
    local restore_path
    for restore_path in "$@"; do
        docker run --rm "${DOCKER_IDENTITY_ARGS[@]}" \
            -e HOME=/tmp \
            -v "${scenario_dir}/backups:/backups" \
            -v "${scenario_dir}/backup.d:/backup.d:ro" \
            -v "${scenario_dir}/manager:/manager" \
            -v "${scenario_dir}/dar-backup.conf:/config/dar-backup.conf:ro" \
            -v "${restore_dir}:/restore" \
            "${source_mounts[@]}" \
            --entrypoint /opt/venv/bin/manager "$IMAGE" \
            --config-file /config/dar-backup.conf -d cross-filesystem \
            --restore-path "$restore_path" --when now --target /restore \
            --preserve-ownership --log-stdout --verbose
    done
}

prepare_restore_identity() {
    local restore_dir="$1"
    local actual_uid actual_gid
    actual_uid="$(stat -c %u -- "$restore_dir")"
    actual_gid="$(stat -c %g -- "$restore_dir")"
    if [[ "$actual_uid" == "$BACKUP_UID" && "$actual_gid" == "$BACKUP_GID" ]]; then
        return 0
    fi
    if [[ "$BACKUP_UID" -ne 0 ]]; then
        error "restore directory ownership ${actual_uid}:${actual_gid} does not match ${BACKUP_UID}:${BACKUP_GID}"
        return 1
    fi
    docker run --rm --user 0:0 -v "${restore_dir}:${restore_dir}" \
        --entrypoint /bin/chown "$IMAGE" 0:0 "$restore_dir"
}

write_run_marker() {
    local target="$1"
    if [[ -w "$target" ]]; then
        printf '%s\n' "$RUN_ID" > "${target}/.cross-filesystem-test-run"
        return 0
    fi
    local host_uid host_gid
    host_uid="$(id -u)"
    host_gid="$(id -g)"
    docker run --rm --user 0:0 -v "${target}:/target" \
        --entrypoint /bin/sh "$IMAGE" -c \
        'printf "%s\n" "$1" > /target/.cross-filesystem-test-run; chown "$2:$3" /target' \
        sh "$RUN_ID" "$host_uid" "$host_gid"
}

parse_manifest_summary() {
    local prefix="$1"
    local category="$2"
    local summary_json="$3"
    local entry_count file_count byte_count xattr_count hard_link_count
    IFS=$'\t' read -r entry_count file_count byte_count xattr_count hard_link_count < <(
        python3 -c 'import json,sys; d=json.loads(sys.argv[1]); print(*(d[k] for k in ("entry_count","file_count","bytes","xattr_count","hard_link_group_count")), sep="\t")' "$summary_json"
    )
    if [[ "$category" == "SOURCE" ]]; then
        set_scenario_value "$prefix" SOURCE_ENTRIES "$entry_count"
        set_scenario_value "$prefix" SOURCE_FILES "$file_count"
        set_scenario_value "$prefix" SOURCE_BYTES "$byte_count"
    else
        set_scenario_value "$prefix" RESTORE_ENTRIES "$entry_count"
        set_scenario_value "$prefix" RESTORE_FILES "$file_count"
        set_scenario_value "$prefix" RESTORE_BYTES "$byte_count"
        set_scenario_value "$prefix" RESTORE_XATTRS "$xattr_count"
        set_scenario_value "$prefix" RESTORE_HARD_LINK_GROUPS "$hard_link_count"
    fi
}

record_filesystems() {
    local prefix="$1"
    local source_root="$2"
    local restore_dir="$3"
    set_scenario_value "$prefix" SOURCE_FSTYPE "$(filesystem_type "$source_root")"
    set_scenario_value "$prefix" SOURCE_DEVICE "$(path_device "$source_root")"
    set_scenario_value "$prefix" ARCHIVE_FSTYPE "$(filesystem_type "$RUN_DIR")"
    set_scenario_value "$prefix" ARCHIVE_DEVICE "$(path_device "$RUN_DIR")"
    set_scenario_value "$prefix" RESTORE_FSTYPE "$(filesystem_type "$restore_dir")"
    set_scenario_value "$prefix" RESTORE_DEVICE "$(path_device "$restore_dir")"
}

run_success_scenario() {
    local prefix="$1"
    local scenario_name="$2"
    local source_root="$3"
    local restore_dir="$4"
    local mount_name="$5"
    shift 5
    local -a selections=("$@")
    local -a definition_selections=("${selections[@]}")
    local -a restore_paths=()
    local comparison_root="$restore_dir"
    if [[ -n "$mount_name" ]]; then
        definition_selections=("$mount_name")
        restore_paths=("${mount_name}/")
        comparison_root="${restore_dir}/${mount_name}"
    else
        local selection
        for selection in "${selections[@]}"; do
            if [[ -d "${source_root}/${selection}" ]]; then
                restore_paths+=("${selection}/")
            else
                restore_paths+=("$selection")
            fi
        done
    fi
    local scenario_dir="${RUN_DIR}/${scenario_name}"
    local scenario_started backup_started verify_started restore_started
    local summary_json archive_base
    scenario_started="$(date +%s)"
    prepare_scenario_directories "$scenario_dir"
    write_scenario_config "$scenario_dir"
    set_scenario_value "$prefix" DEFINITION_SHA256 "$(write_scenario_definition "$scenario_dir" "${definition_selections[@]}")"
    record_filesystems "$prefix" "$source_root" "$restore_dir"

    set_phase "${scenario_name}_source_capture"
    local ownership_check=0
    [[ "$BACKUP_USER" != "pj" || "$prefix" != "HOME" ]] || ownership_check=1
    if ! summary_json="$(manifest_capture "$source_root" "$scenario_dir" "$ownership_check" "${selections[@]}")"; then
        mark_scenario_failed "$prefix" "source_manifest_failed"
        return 1
    fi
    parse_manifest_summary "$prefix" SOURCE "$summary_json"

    set_phase "${scenario_name}_backup"
    backup_started="$(date +%s)"
    if ! docker_backup "$source_root" "$scenario_dir" "$mount_name" 2>&1 | tee "${scenario_dir}/backup-output.log"; then
        set_scenario_value "$prefix" OBSERVED_OUTCOME "failure"
        set_scenario_check "$prefix" BACKUP "failed"
        mark_scenario_failed "$prefix" "backup_failed"
        return 1
    fi
    set_scenario_value "$prefix" BACKUP_SECONDS "$(( $(date +%s) - backup_started ))"
    set_scenario_value "$prefix" OBSERVED_OUTCOME "success"
    set_scenario_check "$prefix" BACKUP "passed"
    if find "${scenario_dir}/manager" -mindepth 1 -print -quit | grep -q .; then
        set_scenario_check "$prefix" MANAGER_DATABASE "passed"
    else
        set_scenario_check "$prefix" MANAGER_DATABASE "failed"
        mark_scenario_failed "$prefix" "manager_database_missing"
        return 1
    fi
    archive_base="$(find_archive_base "${scenario_dir}/backups")" || { mark_scenario_failed "$prefix" "archive_not_unique"; return 1; }
    set_scenario_value "$prefix" ARCHIVE_SLICES "$(find "${scenario_dir}/backups" -maxdepth 1 -type f -name "$(basename "$archive_base").*.dar" | wc -l)"
    set_scenario_value "$prefix" ARCHIVE_BYTES "$(find "${scenario_dir}/backups" -maxdepth 1 -type f -name "$(basename "$archive_base").*.dar" -printf '%s\n' | awk '{sum += $1} END {print sum + 0}')"

    set_phase "${scenario_name}_archive_verification"
    verify_started="$(date +%s)"
    if verify_archive "$scenario_dir" "$archive_base"; then set_scenario_check "$prefix" DAR_INTEGRITY "passed"; else set_scenario_check "$prefix" DAR_INTEGRITY "failed"; mark_scenario_failed "$prefix" "dar_integrity_failed"; return 1; fi
    if find "${scenario_dir}/par2" -maxdepth 1 -type f -name '*.dar.par2' -print -quit | grep -q .; then set_scenario_check "$prefix" PAR2_FILES "passed"; else set_scenario_check "$prefix" PAR2_FILES "failed"; mark_scenario_failed "$prefix" "par2_files_missing"; return 1; fi
    if verify_par2 "$scenario_dir"; then set_scenario_check "$prefix" PAR2_VERIFY "passed"; else set_scenario_check "$prefix" PAR2_VERIFY "failed"; mark_scenario_failed "$prefix" "par2_verify_failed"; return 1; fi
    set_scenario_value "$prefix" VERIFY_SECONDS "$(( $(date +%s) - verify_started ))"

    set_phase "${scenario_name}_restore"
    restore_started="$(date +%s)"
    if ! prepare_restore_identity "$restore_dir"; then
        set_scenario_check "$prefix" RESTORE_EXECUTION "failed"
        mark_scenario_failed "$prefix" "restore_identity_failed"
        return 1
    fi
    if restore_archive "$scenario_dir" "$restore_dir" "$source_root" "$mount_name" "${restore_paths[@]}"; then set_scenario_check "$prefix" RESTORE_EXECUTION "passed"; else set_scenario_check "$prefix" RESTORE_EXECUTION "failed"; mark_scenario_failed "$prefix" "restore_failed"; return 1; fi
    set_scenario_value "$prefix" RESTORE_SECONDS "$(( $(date +%s) - restore_started ))"

    set_phase "${scenario_name}_comparison"
    if manifest_verify "$source_root" "$scenario_dir" 0 >/dev/null; then set_scenario_check "$prefix" SOURCE_STABILITY "passed"; else set_scenario_check "$prefix" SOURCE_STABILITY "failed"; mark_scenario_failed "$prefix" "source_changed"; return 1; fi
    if ! summary_json="$(manifest_verify "$comparison_root" "$scenario_dir" 1)"; then
        set_scenario_check "$prefix" CONTENT "failed"
        set_scenario_check "$prefix" METADATA "failed"
        mark_scenario_failed "$prefix" "restore_comparison_failed"
        return 1
    fi
    parse_manifest_summary "$prefix" RESTORE "$summary_json"
    set_scenario_check "$prefix" CONTENT "passed"
    set_scenario_check "$prefix" METADATA "passed"
    set_scenario_check "$prefix" OVERALL "passed"
    set_scenario_value "$prefix" STATUS "passed"
    set_scenario_value "$prefix" TOTAL_SECONDS "$(( $(date +%s) - scenario_started ))"
    pass "${scenario_name} completed"
}

discover_unreadable_etc() {
    local scenario_dir="$1"
    docker run --rm "${DOCKER_IDENTITY_ARGS[@]}" -v /etc:/source:ro \
        --entrypoint /usr/bin/find "$IMAGE" /source -xdev \
        \( -type f ! -readable -o -type d ! -readable -o -type d ! -executable \) -print \
        > "${scenario_dir}/unreadable-etc.txt"
    [[ -s "${scenario_dir}/unreadable-etc.txt" ]]
}

classify_expected_permission_failure() {
    local backup_status="$1"
    local output_file="$2"
    local usable_archive="$3"
    [[ "$backup_status" =~ ^[0-9]+$ ]] || { error "backup status must be a non-negative integer"; return 2; }
    [[ "$usable_archive" == "0" || "$usable_archive" == "1" ]] || { error "usable archive flag must be 0 or 1"; return 2; }
    if [[ "$backup_status" -eq 0 ]]; then
        error "the expected non-root /etc backup unexpectedly succeeded"
        return 1
    fi
    [[ -f "$output_file" ]] || { error "backup diagnostic output is missing"; return 1; }
    if ! grep -Eiq 'permission denied|operation not permitted|cannot (read|open)|not saved|failed to (read|save)' "$output_file"; then
        error "the /etc backup failed for a reason unrelated to access permissions"
        return 1
    fi
    if [[ "$usable_archive" -eq 1 ]]; then
        error "the denied /etc backup still produced a usable FULL archive"
        return 1
    fi
}

run_expected_etc_denial() {
    local prefix="ETC"
    local scenario_name="etc-to-home"
    local scenario_dir="${RUN_DIR}/${scenario_name}"
    local started backup_started backup_status=0
    started="$(date +%s)"
    prepare_scenario_directories "$scenario_dir"
    write_scenario_config "$scenario_dir"
    set_scenario_value "$prefix" DEFINITION_SHA256 "$(write_scenario_definition "$scenario_dir" etc)"
    record_filesystems "$prefix" /etc "$HOME_RESTORE_BASE"
    set_phase "etc-to-home_permission_preflight"
    if ! discover_unreadable_etc "$scenario_dir"; then
        mark_scenario_failed "$prefix" "no_unreadable_etc_entries"
        return 1
    fi
    info "Unreadable /etc entries detected for pj: $(wc -l < "${scenario_dir}/unreadable-etc.txt")"
    set_phase "etc-to-home_expected_backup_failure"
    backup_started="$(date +%s)"
    docker_backup /etc "$scenario_dir" etc > "${scenario_dir}/backup-output.log" 2>&1 || backup_status=$?
    set_scenario_value "$prefix" BACKUP_SECONDS "$(( $(date +%s) - backup_started ))"
    local archive_base=""
    local usable_archive=0
    if archive_base="$(find_archive_base "${scenario_dir}/backups" 2>/dev/null)"; then
        set_scenario_value "$prefix" ARCHIVE_SLICES "$(find "${scenario_dir}/backups" -maxdepth 1 -type f -name "$(basename "$archive_base").*.dar" | wc -l)"
        set_scenario_value "$prefix" ARCHIVE_BYTES "$(find "${scenario_dir}/backups" -maxdepth 1 -type f -name "$(basename "$archive_base").*.dar" -printf '%s\n' | awk '{sum += $1} END {print sum + 0}')"
        if verify_archive "$scenario_dir" "$archive_base" >/dev/null 2>&1; then
            usable_archive=1
        fi
    fi
    if ! classify_expected_permission_failure "$backup_status" "${scenario_dir}/backup-output.log" "$usable_archive"; then
        if [[ "$backup_status" -eq 0 ]]; then
            set_scenario_value "$prefix" OBSERVED_OUTCOME "success"
            set_scenario_value "$prefix" FAILURE_REASON "unexpected_backup_success"
        elif [[ "$usable_archive" -eq 1 ]]; then
            set_scenario_value "$prefix" OBSERVED_OUTCOME "permission_denied"
            set_scenario_value "$prefix" FAILURE_REASON "usable_archive_from_denied_source"
        else
            set_scenario_value "$prefix" OBSERVED_OUTCOME "failure"
            set_scenario_value "$prefix" FAILURE_REASON "failure_was_not_access_related"
        fi
        set_scenario_check "$prefix" BACKUP "failed"
        set_scenario_value "$prefix" STATUS "failed"
        set_scenario_check "$prefix" OVERALL "failed"
        return 1
    fi
    set_scenario_value "$prefix" OBSERVED_OUTCOME "permission_denied"
    if find "${scenario_dir}/manager" -mindepth 1 -print -quit | grep -q .; then
        set_scenario_check "$prefix" MANAGER_DATABASE "passed"
    else
        set_scenario_check "$prefix" MANAGER_DATABASE "not_run"
    fi
    set_scenario_check "$prefix" BACKUP "passed"
    set_scenario_check "$prefix" DAR_INTEGRITY "skipped"
    set_scenario_check "$prefix" PAR2_FILES "skipped"
    set_scenario_check "$prefix" PAR2_VERIFY "skipped"
    set_scenario_check "$prefix" SOURCE_STABILITY "skipped"
    set_scenario_check "$prefix" RESTORE_EXECUTION "skipped"
    set_scenario_check "$prefix" CONTENT "skipped"
    set_scenario_check "$prefix" METADATA "skipped"
    set_scenario_check "$prefix" OVERALL "passed"
    set_scenario_value "$prefix" STATUS "passed"
    set_scenario_value "$prefix" TOTAL_SECONDS "$(( $(date +%s) - started ))"
    pass "etc-to-home observed the expected pj permission failure"
}

validate_cleanup_target() {
    local target="$1"
    local parent="$2"
    local resolved_target resolved_parent marker
    [[ -n "$target" && -d "$target" && ! -L "$target" ]] || return 1
    resolved_target="$(readlink -e -- "$target")"
    resolved_parent="$(readlink -e -- "$parent")"
    [[ "$resolved_target" == "$resolved_parent"/* ]] || return 1
    marker="${resolved_target}/.cross-filesystem-test-run"
    [[ -f "$marker" && "$(<"$marker")" == "$RUN_ID" ]]
}

cleanup_target() {
    local target="$1"
    local parent="$2"
    validate_cleanup_target "$target" "$parent" || { error "refusing to clean unvalidated directory: ${target}"; return 1; }
    docker run --rm --user 0:0 -v "${target}:${target}" \
        --entrypoint /usr/bin/find "$IMAGE" "$target" -mindepth 1 -delete
    rmdir -- "$target"
}

write_result() {
    local exit_status="$1"
    [[ "$RESULT_INITIALIZED" -eq 1 && "$RESULT_WRITTEN" -eq 0 ]] || return 0
    RESULT_WRITTEN=1
    # The result helper reads this deliberately isolated CFT_* namespace.
    # shellcheck disable=SC2034
    CFT_RUN_ID="$RUN_ID"
    CFT_STARTED_AT="$RUN_STARTED_AT"
    CFT_FINISHED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    CFT_COMPLETED="$RUN_COMPLETED"
    CFT_ABORTED_PHASE=""
    [[ "$RUN_COMPLETED" -eq 1 ]] || CFT_ABORTED_PHASE="$CURRENT_PHASE"
    CFT_EXIT_CODE="$exit_status"
    CFT_PASSED=0
    [[ "$exit_status" -eq 0 && "$RUN_COMPLETED" -eq 1 ]] && CFT_PASSED=1
    CFT_REQUESTED_SCENARIO="$SCENARIO"
    CFT_BACKUP_USER="$BACKUP_USER"
    CFT_BACKUP_UID="$BACKUP_UID"
    CFT_BACKUP_GID="$BACKUP_GID"
    CFT_DATASET_ID="$DATASET_ID"
    CFT_IMAGE_REFERENCE="$IMAGE"
    CFT_SLICE_SIZE="$SLICE_SIZE"
    CFT_PAR2_RATIO="$PAR2_RATIO"
    CFT_TIMEOUT="$TIMEOUT"
    CFT_KEEP="$KEEP"
    CFT_ELAPSED_SECONDS="$(( $(date +%s) - RUN_STARTED_EPOCH ))"
    CFT_SCRIPT_VERSION="$SCRIPT_VERSION"
    local variable_name
    while IFS= read -r variable_name; do
        # Export the variable whose name is held in variable_name.
        # shellcheck disable=SC2163
        export "$variable_name"
    done < <(compgen -A variable CFT_)
    python3 "${SCRIPT_DIR}/scripts/cross_filesystem_result.py" --output "$RESULTS_FILE"
}

on_exit() {
    local exit_status=$?
    trap - EXIT INT TERM
    if [[ "$RESULT_INITIALIZED" -eq 1 ]]; then
        if ! write_result "$exit_status"; then
            error "unable to persist JSONL result; preserving run artifacts"
            exit_status=1
        elif [[ "$exit_status" -eq 0 && "$RUN_COMPLETED" -eq 1 && "$KEEP" -eq 0 ]]; then
            local cleanup_failed=0
            if [[ -n "$HOME_RESTORE_DIR" && -d "$HOME_RESTORE_DIR" ]]; then
                cleanup_target "$HOME_RESTORE_DIR" "$HOME_RESTORE_BASE" || cleanup_failed=1
            fi
            cleanup_target "$RUN_DIR" "$BASE_DIR/runs" || cleanup_failed=1
            if [[ "$cleanup_failed" -ne 0 ]]; then
                error "cleanup was incomplete; retained paths require manual inspection"
                exit_status=1
            fi
        fi
        info "JSONL result: ${RESULTS_FILE}"
        if [[ "$exit_status" -ne 0 || "$KEEP" -eq 1 ]]; then
            [[ -z "$RUN_DIR" ]] || info "Retained run directory: ${RUN_DIR}"
            [[ -z "$HOME_RESTORE_DIR" ]] || info "Retained home restore directory: ${HOME_RESTORE_DIR}"
        fi
    fi
    exit "$exit_status"
}

main() {
    parse_arguments "$@"
    validate_arguments
    for command_name in python3 findmnt stat readlink getent id sha256sum awk find grep sort wc mktemp; do
        command -v "$command_name" >/dev/null || { error "required command is unavailable: ${command_name}"; return 1; }
    done
    if [[ "$SCENARIO" == "home-to-data" || "$SCENARIO" == "both" ]]; then
        validate_home_source_arguments
    fi
    resolve_identity
    if [[ "$SCENARIO" == "home-to-data" || "$SCENARIO" == "both" ]]; then
        validate_home_sources
    fi
    initialize_result_state
    initialize_run_directories
    set_phase "image_preflight"
    inspect_image_and_checkout

    if [[ "$SCENARIO" == "etc-to-home" || "$SCENARIO" == "both" ]]; then
        [[ ! -L "$HOME_RESTORE_BASE" ]] || { error "home restore base must not be a symbolic link: ${HOME_RESTORE_BASE}"; return 1; }
        require_filesystem_type "$HOME_RESTORE_BASE" "btrfs" "home restore base"
        mkdir -p -- "$HOME_RESTORE_BASE"
        chmod 0700 -- "$HOME_RESTORE_BASE"
        HOME_RESTORE_DIR="$(mktemp -d "${HOME_RESTORE_BASE}/${RUN_ID}.XXXXXX")"
        printf '%s\n' "$RUN_ID" > "${HOME_RESTORE_DIR}/.cross-filesystem-test-run"
        if [[ "$BACKUP_USER" == "pj" ]]; then
            run_expected_etc_denial
        else
            rm -- "${HOME_RESTORE_DIR}/.cross-filesystem-test-run"
            run_success_scenario ETC etc-to-home /etc "$HOME_RESTORE_DIR" etc
            write_run_marker "$HOME_RESTORE_DIR"
        fi
    fi

    if [[ "$SCENARIO" == "home-to-data" || "$SCENARIO" == "both" ]]; then
        local data_restore_dir="${RUN_DIR}/home-to-data-restore"
        mkdir -p -- "$data_restore_dir"
        require_filesystem_type "$data_restore_dir" "zfs" "data restore target"
        run_success_scenario HOME home-to-data "$HOME_ROOT" "$data_restore_dir" "" "${HOME_RELATIVE_SOURCES[@]}"
    fi

    RUN_COMPLETED=1
    CURRENT_PHASE="complete"
    pass "all requested cross-filesystem checks passed"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
