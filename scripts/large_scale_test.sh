#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
#
# large_scale_test.sh — pre-release torture test for dar-backup

set -euo pipefail

# ── defaults ────────────────────────────────────────────────────────────────
# All of these are dumped by print_run_variables() near the start of MAIN
# ORCHESTRATION, into the tee'd $SUMMARY file — so a run's exact configuration
# and derived paths are always on record, even if --keep wasn't used and the
# run directory itself is gone afterward. If you add a new top-level variable,
# add its name to RUN_VARIABLES (below the directory-layout block) too.

RUN_STARTED_EPOCH=$(date +%s)                       # Wall-clock start used for overall_elapsed_s, including preflight and every lifecycle phase
DATESTAMP=$(date '+%Y-%m-%d_%H-%M-%S')             # Run identifier: used in RUN_DIR, LOGFILE, SUMMARY filenames, and the JSONL record
DATE_OF_RUN=$(date '+%Y-%m-%d')                    # Calendar date only (pinned once at startup) for run-level result reporting; archive dates may advance across midnight
BASE_DIR="/data/tmp/image-large-scale-test"         # --base: root directory for runs/, results/, and the diff-primer directory. Must be at least two directories deep and have MIN_FREE_MULTIPLIER x source-size free space
IMAGE="dar-backup:dev"                              # --image: the dar-backup Docker image under test; must already be built (e.g. `make dev`)
DEFINITION_ROOT=""                                  # Set after option parsing from the definition's `-R <path>` line; must equal MOUNT_ROOT (see validation below)
MOUNT_ROOT=""                                       # Set after option parsing from BASE_DIR's top-level directory; identity-mounted read-only into every container as the source-data volume
DEFINITION_NAME="large-scale-test"                  # Backup definition name (also the archive filename prefix); fixed, not currently a CLI option
DEFINITION_CONTENT=""                               # --definition (required): the backup definition body (-R/-g/etc. lines) supplied by the caller
SLICE_SIZE="10G"                                    # --slice: dar -s slice size; only injected into DEFINITION_CONTENT if it doesn't already set one
PAR2_RATIO=5                                        # --par2-ratio: PAR2 ERROR_CORRECTION_PERCENT written into the generated config
DO_BITROT=0                                         # --bitrot: when 1, runs do_bitrot_test (corrupt + par2 repair) on FULL, DIFF, and INCR
BITROT_SEED=""                                      # --bitrot-seed: optional unsigned 64-bit seed; generated once per run when omitted
BITROT_MODE="contiguous"                            # --bitrot-mode: contiguous (default), fragmented, or edges
BITROT_MODE_EXPLICIT=0                              # Tracks whether --bitrot-mode was supplied so it can require --bitrot
BITROT_PERCENT=2                                    # Fixed percentage of one selected slice corrupted per bitrot phase
BITROT_BUFFER_BYTES=1048576                         # 1 MiB dd buffer while preserving exact byte offsets and lengths
SLICE_SIZE_SOURCE="fallback"                        # Set to definition when the supplied definition contains its own validated slice option
ADVERTISE_REQUESTED=0                               # --advertise: requests publication; the result writer still enforces success and source-size eligibility
TEST_NAME="Large scale torture test"                 # --test-name: human-readable badge label stored with every result
ADVERTISE_CLASS=""                                  # --advertise-class: tested version/class; defaults from image metadata after preflight
KEEP=0                                              # --keep: when 1, RUN_DIR is left on disk after the run instead of being deleted by cleanup()
SMOKETEST=0                                         # --smoketest: when 1, skips mirroring this run's JSONL record into the tracked repo history file
TIMEOUT=86400                                       # --timeout: COMMAND_TIMEOUT_SECS written into the generated config (dar/par2/manager command timeout, seconds)
FULL_RESTORE_MODE="auto"                            # --full-restore-mode: auto below threshold, forced at any size, or disabled
FULL_RESTORE_THRESHOLD_GIB=25                       # --full-restore-threshold-gib: inclusive source-size limit used only by auto mode
FULL_RESTORE_THRESHOLD_BYTES=$((25 * 1024 * 1024 * 1024)) # Derived again after option validation and stored as exact result evidence
FULL_RESTORE_SELECTED=0                             # Decision made after source measurement; separate from whether execution is reached
FULL_RESTORE_PERFORMED=0                            # Set only immediately before complete-tree PITR execution
FULL_RESTORE_DECISION_REASON="not_evaluated"        # Stable machine-readable explanation for selection or skip
FULL_RESTORE_FILE_COUNT=""                          # Regular-file paths checksum-compared by the complete restore
FULL_RESTORE_BYTES=""                               # Apparent restored bytes checksum-compared by the complete restore
SCRIPT_VERSION="18"                                 # Bumped whenever this script's behavior changes in a way worth tracking alongside JSONL history
MIN_FREE_MULTIPLIER=2                               # --min-free-multiplier: required free space under BASE_DIR, as a multiple of the estimated source data size
DIFF_PRIMER_DIR=""                                  # Set below to "${BASE_DIR}/diff-primer"; synthetic data mutated at each phase to exercise DIFF/INCR/restore logic
PRIMER_NON_LINK_COUNT=0                             # Set by create_diff_primer(); expected-modified-file-count threshold used by verify_diff_contents/verify_incr_contents
DAR_BACKUP_VERSION=""                               # Set by preflight() from the image's org.dar-backup.version label
GIT_COMMIT=""                                       # Set by preflight() from `git rev-parse --short HEAD` in REPO_DIR (this repo, dar-backup-image)
HARNESS_GIT_COMMIT=""                               # Full commit for the harness checkout; unlike GIT_COMMIT, this is unambiguous provenance
HARNESS_GIT_DIRTY=0                                 # Whether tracked or untracked harness files differed from HARNESS_GIT_COMMIT before the run
REPO_DIR=""                                         # Set by preflight() to the dar-backup-image repo root; also the JSONL-mirror target (unless SMOKETEST=1)
IMAGE_ID=""                                         # Immutable local Docker image config digest
IMAGE_REPO_DIGEST=""                                # Registry manifest digest when the image was pulled/pushed; empty for local-only dev images
IMAGE_REVISION=""                                   # OCI source-revision label embedded in the image
IMAGE_VERSION=""                                    # OCI image-version label embedded in the image
DAR_VERSION=""                                      # Set by preflight() from the image's org.dar.version label
PAR2_VERSION=""                                     # Set by preflight() from `par2 --version`, run inside the image
PYTHON_VERSION=""                                   # Set by preflight() from `python3 --version`, run inside the image
OS_DESC=""                                           # Set by preflight() from `lsb_release -d` (describes the Docker host, not the image)
KERNEL=""                                           # Set by preflight() from `uname -r` (the Docker host's kernel)
SOURCE_FILE_COUNT=""                                # Regular-file count across effective -g source paths, captured before FULL
SOURCE_BYTES=""                                     # Apparent regular-file bytes across effective -g source paths, captured before FULL
BACKUP_DEFINITION_SHA256=""                         # Hash of the effective generated backup definition, including injected primer and slice options

# Explicit lifecycle state is serialized by the EXIT trap. Values use the
# schema-v4 status vocabulary: passed, failed, skipped, or not_run.
CURRENT_PHASE="preflight"
RUN_RESULT_READY=0
RUN_COMPLETED=0
RESULT_WRITTEN=0
MANAGER_DB_STATUS="not_run"
FULL_BACKUP_STATUS="not_run"; DIFF_BACKUP_STATUS="not_run"; INCR_BACKUP_STATUS="not_run"
FULL_ARCHIVE_STATUS="not_run"; DIFF_ARCHIVE_STATUS="not_run"; INCR_ARCHIVE_STATUS="not_run"
FULL_PAR2_FILES_STATUS="not_run"; DIFF_PAR2_FILES_STATUS="not_run"; INCR_PAR2_FILES_STATUS="not_run"
FULL_PAR2_VERIFY_STATUS="not_run"; DIFF_PAR2_VERIFY_STATUS="not_run"; INCR_PAR2_VERIFY_STATUS="not_run"
FULL_BITROT_STATUS="not_run"; DIFF_BITROT_STATUS="not_run"; INCR_BITROT_STATUS="not_run"
DIFF_CONTENTS_STATUS="not_run"; INCR_CONTENTS_STATUS="not_run"
PITR_EXECUTION_STATUS="not_run"; PITR_STRUCTURE_STATUS="not_run"
PITR_CHECKSUM_STATUS="not_run"; PITR_OVERALL_STATUS="not_run"
FULL_RESTORE_EXECUTION_STATUS="not_run"; FULL_RESTORE_CONTENT_STATUS="not_run"
FULL_RESTORE_OVERALL_STATUS="not_run"

# ── colours ─────────────────────────────────────────────────────────────────
RED='\033[31m'; GREEN='\033[32m'
CYAN='\033[36m'; BOLD='\033[1m'; RESET='\033[0m'

pass()   { echo -e "${GREEN}  PASS${RESET}  $*"; }
fail()   { echo -e "${RED}  FAIL${RESET}  $*"; FAILURES=$((FAILURES+1)); }
info()   { echo -e "${CYAN}  INFO${RESET}  $*"; }
banner() { echo -e "\n${BOLD}${CYAN}══════════════════════════════════════════${RESET}"
           echo -e "${BOLD}${CYAN}  $*${RESET}"
           echo -e "${BOLD}${CYAN}══════════════════════════════════════════${RESET}"; }

FAILURES=0

usage() {
    grep '^#' "$0" | grep -v '#!/' | sed 's/^# \{0,2\}//'
    exit 0
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --definition) DEFINITION_CONTENT="$2"; shift 2 ;;
        --base)       BASE_DIR="$2";           shift 2 ;;
        --image)      IMAGE="$2";              shift 2 ;;
        --slice)      SLICE_SIZE="$2";         shift 2 ;;
        --par2-ratio) PAR2_RATIO="$2";         shift 2 ;;
        --bitrot)     DO_BITROT=1;             shift   ;;
        --bitrot-seed) BITROT_SEED="$2";       shift 2 ;;
        --bitrot-mode) BITROT_MODE="$2"; BITROT_MODE_EXPLICIT=1; shift 2 ;;
        --advertise)  ADVERTISE_REQUESTED=1; shift ;;
        --test-name)  TEST_NAME="$2"; shift 2 ;;
        --advertise-class) ADVERTISE_CLASS="$2"; shift 2 ;;
        --keep)       KEEP=1;                  shift   ;;
        --smoketest)  SMOKETEST=1;             shift   ;;
        --timeout)    TIMEOUT="$2";            shift 2 ;;
        --min-free-multiplier) MIN_FREE_MULTIPLIER="$2"; shift 2 ;;
        --full-restore-mode) FULL_RESTORE_MODE="$2"; shift 2 ;;
        --full-restore-threshold-gib) FULL_RESTORE_THRESHOLD_GIB="$2"; shift 2 ;;
        --help|-h)    usage ;;
        *) echo "Unknown option: $1"; usage ;;
    esac
done

[[ -z "$DEFINITION_CONTENT" ]] && { echo "ERROR: --definition is required"; exit 1; }
[[ -z "$TEST_NAME" ]] && { echo "ERROR: --test-name must not be empty" >&2; exit 1; }
[[ $DO_BITROT -eq 0 && -n "$BITROT_SEED" ]] && { echo "ERROR: --bitrot-seed requires --bitrot" >&2; exit 1; }
[[ $DO_BITROT -eq 0 && $BITROT_MODE_EXPLICIT -eq 1 ]] && { echo "ERROR: --bitrot-mode requires --bitrot" >&2; exit 1; }
case "$BITROT_MODE" in
    contiguous|fragmented|edges) ;;
    *) echo "ERROR: --bitrot-mode must be contiguous, fragmented, or edges" >&2; exit 1 ;;
esac
case "$FULL_RESTORE_MODE" in
    auto|forced|disabled) ;;
    *) echo "ERROR: --full-restore-mode must be auto, forced, or disabled" >&2; exit 1 ;;
esac
[[ "$FULL_RESTORE_THRESHOLD_GIB" =~ ^[1-9][0-9]*$ ]] || { echo "ERROR: --full-restore-threshold-gib must be a positive integer" >&2; exit 1; }
[[ "$FULL_RESTORE_THRESHOLD_GIB" -le 8589934591 ]] || { echo "ERROR: --full-restore-threshold-gib is too large" >&2; exit 1; }
FULL_RESTORE_THRESHOLD_BYTES=$((10#$FULL_RESTORE_THRESHOLD_GIB * 1024 * 1024 * 1024))

slice_resolution=""
if ! slice_resolution=$(python3 "$(dirname "${BASH_SOURCE[0]}")/large_scale_definition.py" \
        --definition "$DEFINITION_CONTENT" \
        --fallback "$SLICE_SIZE"); then
    exit 1
fi
IFS=$'\t' read -r SLICE_SIZE_SOURCE SLICE_SIZE <<< "$slice_resolution"
if [[ -z "$SLICE_SIZE_SOURCE" || -z "$SLICE_SIZE" ]]; then
    echo "ERROR: unable to resolve the effective slice size" >&2
    exit 1
fi

if [[ $DO_BITROT -eq 0 ]]; then
    FULL_BITROT_STATUS="skipped"
    DIFF_BITROT_STATUS="skipped"
    INCR_BITROT_STATUS="skipped"
fi
if [[ "$FULL_RESTORE_MODE" == "disabled" ]]; then
    FULL_RESTORE_DECISION_REASON="disabled_by_user"
    FULL_RESTORE_EXECUTION_STATUS="skipped"
    FULL_RESTORE_CONTENT_STATUS="skipped"
    FULL_RESTORE_OVERALL_STATUS="skipped"
fi

# MOUNT_ROOT is the host directory identity-mounted read-only into every
# container as the source-data volume (derived from BASE_DIR's own top-level
# directory, e.g. "/data/tmp/foo" -> "/data"), so BASE_DIR must live under it
# for the diff-primer (created under BASE_DIR) to be reachable via -R "$MOUNT_ROOT".
MOUNT_ROOT="/$(echo "$BASE_DIR" | cut -d/ -f2)"
case "$BASE_DIR" in
    "$MOUNT_ROOT"/*) ;;
    *) echo "ERROR: --base ('$BASE_DIR') must be at least two directories deep (e.g. '/data/tmp/...') so it has a mountable parent"; exit 1 ;;
esac

# The definition's -R must match MOUNT_ROOT (the host directory actually
# identity-mounted into every container, above) so the container-side -R
# resolves against real, visible files. dar-backup's
# manager._is_directory_path()/_detect_directory() now correctly resolve PITR
# catalog paths against whatever -R was really used (fixed upstream — it used
# to hardcode "/", silently breaking directory-chain PITR restore for any
# other root; see v2/BUG.txt in the dar-backup repo). A definition using a
# root that doesn't match what's actually mounted would still break restore
# detection, just against the wrong assumed root instead of a hardcoded one.
DEFINITION_ROOT=$(python3 -c "
import re
import sys

for line in sys.argv[1].splitlines():
    match = re.match(r'^\s*-R\s+(.*)', line.strip())
    if not match:
        continue
    value = match.group(1).strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ('\"', \"'\", '\`'):
        value = value[1:-1]
    print(value)
    break
" "$DEFINITION_CONTENT")
[[ "$DEFINITION_ROOT" != "$MOUNT_ROOT" ]] && { echo "ERROR: --definition's '-R' must match the mount root '${MOUNT_ROOT}' (derived from --base '${BASE_DIR}'), got '${DEFINITION_ROOT:-<none>}'."; exit 1; }

# ── preflight checks ──────────────────────────────────────────────────────────
preflight() {
    local errors=0
    if ! command -v docker &>/dev/null; then
        echo "ERROR: docker not found"; errors=$((errors+1))
    fi
    if [[ $errors -eq 0 ]] && ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
        echo "ERROR: image '${IMAGE}' not found locally — build it first (e.g. 'make dev')"
        errors=$((errors+1))
    fi
    [[ $errors -gt 0 ]] && exit 1

    REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
    GIT_COMMIT=$(git -C "$REPO_DIR" rev-parse --short HEAD 2>/dev/null || echo "unknown")
    HARNESS_GIT_COMMIT=$(git -C "$REPO_DIR" rev-parse HEAD 2>/dev/null || echo "unknown")
    [[ -n "$(git -C "$REPO_DIR" status --porcelain --untracked-files=normal 2>/dev/null)" ]] && HARNESS_GIT_DIRTY=1
    IMAGE_ID=$(docker image inspect -f '{{.Id}}' "$IMAGE")
    IMAGE_REPO_DIGEST=$(docker image inspect -f '{{range .RepoDigests}}{{println .}}{{end}}' "$IMAGE" | head -n 1)
    IMAGE_REVISION=$(docker image inspect -f '{{ index .Config.Labels "org.opencontainers.image.revision" }}' "$IMAGE" 2>/dev/null || true)
    IMAGE_VERSION=$(docker image inspect -f '{{ index .Config.Labels "org.opencontainers.image.version" }}' "$IMAGE" 2>/dev/null || true)
    [[ "$IMAGE_REVISION" == "<no value>" ]] && IMAGE_REVISION=""
    [[ "$IMAGE_VERSION" == "<no value>" ]] && IMAGE_VERSION=""
    if [[ -z "$ADVERTISE_CLASS" ]]; then
        if [[ -n "$IMAGE_VERSION" ]]; then
            ADVERTISE_CLASS="$IMAGE_VERSION"
        elif [[ -n "$IMAGE_REVISION" ]]; then
            ADVERTISE_CLASS="$IMAGE_REVISION"
        else
            ADVERTISE_CLASS="$GIT_COMMIT"
        fi
    fi
    DAR_BACKUP_VERSION=$(docker inspect -f '{{ index .Config.Labels "org.dar-backup.version" }}' "$IMAGE" 2>/dev/null || echo "unknown")
    DAR_VERSION=$(docker inspect -f '{{ index .Config.Labels "org.dar.version" }}' "$IMAGE" 2>/dev/null || echo "unknown")
    PAR2_VERSION=$(docker run --rm --entrypoint /usr/bin/par2 "$IMAGE" --version 2>/dev/null | head -1 || echo "unknown")
    PYTHON_VERSION=$(docker run --rm --entrypoint /opt/venv/bin/python3 "$IMAGE" --version 2>/dev/null || echo "unknown")
    OS_DESC=$(lsb_release -d 2>/dev/null | awk -F':	' '{print $2}' || echo "unknown")
    KERNEL=$(uname -r)
}
preflight

if [[ $DO_BITROT -eq 1 ]]; then
    if [[ -z "$BITROT_SEED" ]]; then
        BITROT_SEED=$(python3 -c 'import secrets; print(secrets.randbits(64))')
    fi
    if ! python3 "${REPO_DIR}/scripts/large_scale_bitrot.py" validate-seed \
        --seed "$BITROT_SEED" >/dev/null; then
        echo "ERROR: --bitrot-seed must be an unsigned 64-bit integer" >&2
        exit 1
    fi
fi

# ── disk-space preflight ──────────────────────────────────────────────────────
# Estimates the real source data size from the backup definition's -R/-g paths and
# fails fast if BASE_DIR's filesystem doesn't have MIN_FREE_MULTIPLIER times that much
# free — a multi-hour run has no business discovering "disk full" three phases in.
decide_full_restore() {
    if [[ "$FULL_RESTORE_MODE" == "disabled" ]]; then
        info "Complete restore disabled by user."
        return 0
    fi
    if [[ "$FULL_RESTORE_MODE" == "forced" ]]; then
        FULL_RESTORE_SELECTED=1
        FULL_RESTORE_DECISION_REASON="forced_by_user"
        info "Complete restore forced for ${SOURCE_BYTES} source byte(s); automatic threshold is ignored."
        return 0
    fi
    if [[ "$SOURCE_BYTES" -le "$FULL_RESTORE_THRESHOLD_BYTES" ]]; then
        FULL_RESTORE_SELECTED=1
        FULL_RESTORE_DECISION_REASON="source_within_threshold"
        info "Complete restore selected automatically: ${SOURCE_BYTES} <= ${FULL_RESTORE_THRESHOLD_BYTES} byte(s)."
        return 0
    fi
    FULL_RESTORE_SELECTED=0
    FULL_RESTORE_DECISION_REASON="source_exceeds_threshold"
    FULL_RESTORE_EXECUTION_STATUS="skipped"
    FULL_RESTORE_CONTENT_STATUS="skipped"
    FULL_RESTORE_OVERALL_STATUS="skipped"
    info "Complete restore skipped automatically: ${SOURCE_BYTES} > ${FULL_RESTORE_THRESHOLD_BYTES} byte(s)."
}

check_disk_space() {
    local def_file="${BACKUP_D_DIR}/${DEFINITION_NAME}"
    # -R is already validated to equal MOUNT_ROOT above, so it's used directly
    # rather than re-parsed here (the previous `awk '{print $2}'` re-parse
    # silently truncated any -R/-g value containing a space to its first
    # word — confirmed broken against a real quoted -R/-g).
    local root_path="$MOUNT_ROOT"

    local total_bytes=0
    # -g values may also be quoted (same reference-file convention as -R); a
    # small quote-aware parser mirrors the -R parsing above rather than
    # repeating the naive awk approach.
    local glob_paths
    glob_paths=$(DEF_FILE="$def_file" python3 -c "
import os
import re

with open(os.environ['DEF_FILE']) as f:
    lines = f.readlines()
for line in lines:
    match = re.match(r'^\s*-g\s+(.*)', line.strip())
    if not match:
        continue
    value = match.group(1).strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ('\"', \"'\", '\`'):
        value = value[1:-1]
    print(value)
")
    local -a source_paths=()
    if [[ -z "$glob_paths" ]]; then
        source_paths+=("$root_path")
    else
        while IFS= read -r g; do
            [[ -z "$g" ]] && continue
            local full_path="${root_path%/}/${g}"
            if [[ ! -e "$full_path" ]]; then
                echo "ERROR: source path from backup definition does not exist: ${full_path}" >&2
                return 1
            fi
            source_paths+=("$full_path")
        done <<< "$glob_paths"
    fi

    if [[ ${#source_paths[@]} -gt 0 ]]; then
        # Measure regular files by unique absolute path so overlapping -g entries
        # are not counted twice. Symlink targets are deliberately not followed.
        local source_measurement
        if ! source_measurement=$(python3 - "${source_paths[@]}" << 'PYEOF'
import os
import stat
import sys

def raise_walk_error(error: OSError) -> None:
    """Propagate an os.walk error instead of silently skipping source data.

    Args:
        error: Filesystem error raised while walking a source directory.

    Raises:
        OSError: Always, using the original walk error.
    """
    raise error

seen_paths = set()
file_count = 0
total_bytes = 0

for source_path in sys.argv[1:]:
    if os.path.isfile(source_path):
        candidates = [source_path]
    else:
        candidates = (
            os.path.join(directory, filename)
            for directory, _, filenames in os.walk(
                source_path, followlinks=False, onerror=raise_walk_error
            )
            for filename in filenames
        )
    for candidate in candidates:
        absolute_path = os.path.abspath(candidate)
        if absolute_path in seen_paths:
            continue
        seen_paths.add(absolute_path)
        file_stat = os.stat(absolute_path, follow_symlinks=False)
        if stat.S_ISREG(file_stat.st_mode):
            file_count += 1
            total_bytes += file_stat.st_size

print(file_count, total_bytes)
PYEOF
        ); then
            echo "ERROR: failed to measure source files for release evidence" >&2
            return 1
        fi
        read -r SOURCE_FILE_COUNT SOURCE_BYTES <<< "$source_measurement"
        if [[ ! "$SOURCE_FILE_COUNT" =~ ^[0-9]+$ || ! "$SOURCE_BYTES" =~ ^[0-9]+$ ]]; then
            echo "ERROR: invalid source measurement: '${source_measurement}'" >&2
            return 1
        fi
        total_bytes="${SOURCE_BYTES:-0}"
    fi

    decide_full_restore

    if [[ "${total_bytes:-0}" -le 0 ]]; then
        info "Could not estimate source data size; skipping disk-space preflight."
        return
    fi

    local required_bytes=$(( total_bytes * MIN_FREE_MULTIPLIER ))
    local available_bytes; available_bytes=$(df --output=avail -B1 "$BASE_DIR" 2>/dev/null | tail -1 | tr -d ' ')
    if [[ -z "$available_bytes" ]]; then
        info "Could not determine available disk space for '${BASE_DIR}'; skipping preflight check."
        return
    fi

    local total_gb required_gb available_gb
    total_gb=$(awk -v b="$total_bytes" 'BEGIN{printf "%.2f", b/1024/1024/1024}')
    required_gb=$(awk -v b="$required_bytes" 'BEGIN{printf "%.2f", b/1024/1024/1024}')
    available_gb=$(awk -v b="$available_bytes" 'BEGIN{printf "%.2f", b/1024/1024/1024}')

    if [[ "$available_bytes" -lt "$required_bytes" ]]; then
        echo "ERROR: insufficient disk space under '${BASE_DIR}'."
        echo "  Source data size: ~${total_gb} GB"
        echo "  Required (${MIN_FREE_MULTIPLIER}x source, for archive+PAR2+restore copy): ~${required_gb} GB"
        echo "  Available:        ~${available_gb} GB"
        exit 1
    fi
    info "Disk-space preflight OK: source ~${total_gb} GB, need ~${required_gb} GB (${MIN_FREE_MULTIPLIER}x), have ~${available_gb} GB free under '${BASE_DIR}'."
}

# ── directory layout ─────────────────────────────────────────────────────────
# Note the split: RUN_DIR (backups/par2/restore/backup.d) is deleted by cleanup()
# unless --keep is given. RESULTS_DIR (and everything under it — LOGFILE, SUMMARY,
# METRICS_DB, the JSONL history) is NOT under RUN_DIR and always survives — so a
# run's transcript/log outlives the run, but the actual archives do not unless
# --keep was used. This is exactly why print_run_variables() below matters: even
# without --keep, you at least always know what RUN_DIR *was*.
RUN_DIR="${BASE_DIR}/runs/${DATESTAMP}"             # This run's private working directory; wiped by cleanup() unless --keep
BACKUP_DIR="${RUN_DIR}/backups"                     # Where the FULL/DIFF/INCR .dar slices are written — gone after the run unless --keep
PAR2_DIR="${RUN_DIR}/par2"                          # Where PAR2 redundancy files + manifest are written — gone after the run unless --keep
RESTORE_DIR="${RUN_DIR}/restore"                    # Phase 3a restore target directory — gone after the run unless --keep
FULL_RESTORE_DIR="${RUN_DIR}/full-restore"           # Optional Phase 3b complete archive-root restore target — gone after the run unless --keep
BACKUP_D_DIR="${RUN_DIR}/backup.d"                  # Holds the generated backup definition file (DEFINITION_NAME) — gone after the run unless --keep
RESULTS_DIR="${BASE_DIR}/results"                   # NOT under RUN_DIR — persists across every run regardless of --keep
METRICS_DB="${RESULTS_DIR}/dar-backup-metrics.db"   # dar-backup's own METRICS_DB_PATH for this run (persists)
LOGFILE="${RESULTS_DIR}/large-scale-test-${DATESTAMP}.dar-backup.log"  # dar-backup's own LOGFILE_LOCATION for this run (persists)
SUMMARY="${RESULTS_DIR}/summary-${DATESTAMP}.txt"   # Full tee'd transcript of this script's own output, including this variable dump (persists)
CONFIG_FILE="${RUN_DIR}/dar-backup.conf"            # Generated dar-backup.conf for this run — gone after the run unless --keep
DARRC="${RUN_DIR}/.darrc"                           # Copied/generated .darrc for this run — gone after the run unless --keep
RSS_LOGFILE="${RUN_DIR}/rss.log"                    # Raw per-process RSS samples written by start_rss_monitor — gone after the run unless --keep
CID_FILE="${RUN_DIR}/current-container.cid"         # Written by docker_run_backup/docker_run_tool for each invocation; scopes start_rss_monitor to this run's own container instead of a host-wide process scan
BITROT_EVIDENCE_FILE="${RUN_DIR}/bitrot-evidence.json" # Incrementally persisted evidence included in the JSONL record by the EXIT trap
DIFF_PRIMER_DIR="${BASE_DIR}/diff-primer"           # NOT under RUN_DIR — reused/reset by create_diff_primer() at the start of every run

mkdir -p "$BACKUP_DIR" "$PAR2_DIR" "$RESTORE_DIR" "$FULL_RESTORE_DIR" "$BACKUP_D_DIR" "$RESULTS_DIR" "$DIFF_PRIMER_DIR"

# ── variable dump ──────────────────────────────────────────────────────────
# Explicit list rather than a blanket `set`/`env` dump, so this stays a readable
# summary of *this script's* configuration and derived paths, not shell noise.
# Add new top-level variables here when you add them above.
RUN_VARIABLES=(
    DATESTAMP DATE_OF_RUN SCRIPT_VERSION RUN_STARTED_EPOCH
    IMAGE DEFINITION_ROOT MOUNT_ROOT
    BASE_DIR DEFINITION_NAME DEFINITION_CONTENT SLICE_SIZE SLICE_SIZE_SOURCE PAR2_RATIO
    DO_BITROT BITROT_SEED BITROT_MODE BITROT_PERCENT BITROT_BUFFER_BYTES
    ADVERTISE_REQUESTED TEST_NAME ADVERTISE_CLASS
    KEEP SMOKETEST TIMEOUT MIN_FREE_MULTIPLIER
    FULL_RESTORE_MODE FULL_RESTORE_THRESHOLD_GIB FULL_RESTORE_THRESHOLD_BYTES
    DAR_BACKUP_VERSION GIT_COMMIT HARNESS_GIT_COMMIT HARNESS_GIT_DIRTY REPO_DIR
    IMAGE_ID IMAGE_REPO_DIGEST IMAGE_REVISION IMAGE_VERSION DAR_VERSION PAR2_VERSION
    PYTHON_VERSION OS_DESC KERNEL
    RUN_DIR BACKUP_DIR PAR2_DIR RESTORE_DIR FULL_RESTORE_DIR BACKUP_D_DIR
    RESULTS_DIR METRICS_DB LOGFILE SUMMARY CONFIG_FILE DARRC RSS_LOGFILE CID_FILE
    BITROT_EVIDENCE_FILE
    DIFF_PRIMER_DIR
)

print_run_variables() {
    banner "Run configuration"
    for name in "${RUN_VARIABLES[@]}"; do
        printf '  %-22s = %s\n' "$name" "${!name}"
    done
}

# ── docker invocation helpers ─────────────────────────────────────────────────
# docker_run_backup: runs dar-backup through the image's default entrypoint
# (entrypoint.sh) exactly as a real user would invoke the image — exercising
# the same UID-drop logic used in production. Mounts MOUNT_ROOT read-only (real
# + synthetic source data) and BASE_DIR read-write as a second, more specific
# bind mount on top of it; since both are identity mounts (same path on host
# and in-container), CONFIG_FILE's paths and the definition's -R (validated to
# equal MOUNT_ROOT above) need no translation.
# Both helpers below write their container's ID to CID_FILE via --cidfile so
# start_rss_monitor() can scope its sampling to *this run's own* container
# (via `docker top`) instead of a host-wide `ps` scan by command name — this
# machine also runs the user's own scheduled dar-backup jobs, and a
# system-wide scan can't tell "this test's dar" from "an unrelated concurrent
# dar-backup cron run" apart.
docker_run_backup() {
    rm -f "$CID_FILE"
    docker run --rm \
        --cidfile "$CID_FILE" \
        -e RUN_AS_UID="$(id -u)" \
        -e RUN_AS_GID="$(id -g)" \
        -v "${MOUNT_ROOT}":"${MOUNT_ROOT}":ro \
        -v "${BASE_DIR}":"${BASE_DIR}" \
        "$IMAGE" "$@"
    local rc=$?
    rm -f "$CID_FILE"
    return $rc
}

# docker_run_tool: runs a single binary (manager/dar/par2) directly inside the
# image, bypassing entrypoint.sh — same pattern scripts/backup-restore-compare.sh
# uses for these tools. Only needs BASE_DIR; none of these operate on MOUNT_ROOT.
docker_run_tool() {
    local tool_entrypoint="$1"; shift
    rm -f "$CID_FILE"
    docker run --rm \
        --cidfile "$CID_FILE" \
        --user "$(id -u):$(id -g)" \
        -e HOME=/tmp \
        --entrypoint "$tool_entrypoint" \
        -v "${BASE_DIR}":"${BASE_DIR}" \
        "$IMAGE" "$@"
    local rc=$?
    rm -f "$CID_FILE"
    return $rc
}

# Tee all output to the summary file from this point forward so every run
# leaves a self-contained record alongside the structured dar/par2 log.
exec > >(tee "$SUMMARY") 2>&1


# ── RSS monitor ──────────────────────────────────────────────────────────────
RSS_MONITOR_PID=""
stop_rss_monitor() {
    if [[ -n "${RSS_MONITOR_PID:-}" ]]; then
        kill "$RSS_MONITOR_PID" 2>/dev/null || true
        wait "$RSS_MONITOR_PID" 2>/dev/null || true
        RSS_MONITOR_PID=""
    fi
}
start_rss_monitor() {
    # Scoped to *this run's own* container (via `docker top` against whatever
    # container ID docker_run_backup/docker_run_tool currently holds in
    # CID_FILE), not a host-wide `ps` scan by command name. This machine also
    # runs the user's own scheduled dar-backup jobs — a system-wide scan can't
    # tell "this test's dar" apart from a concurrent unrelated dar-backup cron
    # run, and a real one was misattributed to this test's peak RSS on
    # 2026-07-07 before this fix. `docker top` needs a plain header row (`ps`'s
    # header-suppressing "=" suffix breaks its own PID-column detection), so
    # the header line is skipped with `tail -n +2` instead.
    (
        while true; do
            if [[ -s "$CID_FILE" ]]; then
                cid=$(cat "$CID_FILE" 2>/dev/null)
                if [[ -n "$cid" ]]; then
                    while read -r pid cmd rss vsz; do
                        [[ -z "$pid" ]] && continue
                        if [[ "$cmd" =~ ^(dar|dar-backup|par2|manager)$ ]]; then
                            [[ "$rss" -gt 0 ]] && printf '%s pid=%-6s rss=%-8s kB peak=%-8s kB cmd=%s\n' \
                                "$(date '+%H:%M:%S')" "$pid" "$rss" "$vsz" "$cmd"
                        fi
                    done < <(docker top "$cid" -eo pid,comm,rss,vsz 2>/dev/null | tail -n +2)
                fi
            fi
            sleep 0.5
        done
    ) >> "${RSS_LOGFILE:-/dev/null}" 2>/dev/null &
    RSS_MONITOR_PID=$!
}

write_config() {
    cat > "$CONFIG_FILE" << EOF
[MISC]
LOGFILE_LOCATION = ${LOGFILE}
MAX_SIZE_VERIFICATION_MB = 200
MIN_SIZE_VERIFICATION_MB = 1
NO_FILES_VERIFICATION = 5
COMMAND_TIMEOUT_SECS = ${TIMEOUT}
COMMAND_CAPTURE_MAX_BYTES = 102400
METRICS_DB_PATH = ${METRICS_DB}
RESTORETEST_EXCLUDE_PREFIXES = .cache/, .local/share/Trash/
RESTORETEST_EXCLUDE_SUFFIXES = .log, .tmp, .lock
[DIRECTORIES]
BACKUP_DIR = ${BACKUP_DIR}
BACKUP.D_DIR = ${BACKUP_D_DIR}
TEST_RESTORE_DIR = ${RESTORE_DIR}
[AGE]
DIFF_AGE = 50
INCR_AGE = 30
[PAR2]
ERROR_CORRECTION_PERCENT = ${PAR2_RATIO}
ENABLED = True
PAR2_DIR = ${PAR2_DIR}
EOF
}

write_backup_def() {
    local content="$DEFINITION_CONTENT"
    if [[ "$SLICE_SIZE_SOURCE" == "fallback" ]]; then
        content="-s ${SLICE_SIZE}"$'\n'"$content"
    fi
    content="${content}"$'\n'"-g ${DIFF_PRIMER_DIR#"$MOUNT_ROOT"/}"
    printf '%s\n' "$content" > "${BACKUP_D_DIR}/${DEFINITION_NAME}"
    BACKUP_DEFINITION_SHA256=$(sha256sum "${BACKUP_D_DIR}/${DEFINITION_NAME}" | awk '{print $1}')
}

create_diff_primer() {
    info "Creating diff-primer data..."
    rm -rf "${DIFF_PRIMER_DIR:?}"/*
    for i in $(seq 1 100); do dd if=/dev/urandom of="${DIFF_PRIMER_DIR}/small_${i}.bin" bs=4096 count=1 2>/dev/null; done
    for i in $(seq 1 10); do dd if=/dev/urandom of="${DIFF_PRIMER_DIR}/medium_${i}.bin" bs=1M count=2 2>/dev/null; done
    for i in $(seq 1 5); do dd if=/dev/urandom of="${DIFF_PRIMER_DIR}/large_${i}.NEF" bs=1M count=55 2>/dev/null; done
    echo "Original static content stream for hard link verification tracking." > "${DIFF_PRIMER_DIR}/link_original.txt"
    ln "${DIFF_PRIMER_DIR}/link_original.txt" "${DIFF_PRIMER_DIR}/link_target1.txt"
    # Count non-link files; used as the expected-modified threshold in verify_diff_contents.
    PRIMER_NON_LINK_COUNT=$(find "${DIFF_PRIMER_DIR}" -type f ! -name "link_*" | wc -l)
}

update_diff_primer() {
    info "Updating diff-primer data..."
    find "$DIFF_PRIMER_DIR" -type f | grep -v "link_" | while read -r f; do
        dd if=/dev/urandom of="$f" bs="$(stat -c%s "$f")" count=1 2>/dev/null
    done || true
    rm "${DIFF_PRIMER_DIR}/link_original.txt"
    echo "Appended text block mutating target1 inode before execution of DIFF backup." >> "${DIFF_PRIMER_DIR}/link_target1.txt"
    ln "${DIFF_PRIMER_DIR}/link_target1.txt" "${DIFF_PRIMER_DIR}/link_target2.txt"
    dd if=/dev/urandom of="${DIFF_PRIMER_DIR}/diff_new_$(date +%s).bin" bs=1M count=2 2>/dev/null
}

verify_diff_contents() {
    local diff_base="$2" primer_rel="${DIFF_PRIMER_DIR#"$MOUNT_ROOT"/}"
    local ok=1
    banner "Phase 2b — DIFF contents verification"
    local diff_saved; diff_saved=$(docker_run_tool /usr/local/bin/dar -l "${BACKUP_DIR}/${diff_base}" --noconf -am -as -Q 2>/dev/null | grep "\[Saved\]" | grep "${primer_rel}" || true)
    # grep -c already prints "0" (with exit 1) on no match; the `|| true` below only
    # guards against set -e aborting the script, it must not print a second fallback
    # value the way `|| echo 0` used to (which silently corrupted the count to "0\n0").
    local modified_count; modified_count=$(echo "$diff_saved" | grep -v "diff_new_" | { grep -c "${primer_rel}" || true; } 2>/dev/null)
    local new_count; new_count=$(echo "$diff_saved" | { grep -c "diff_new_" || true; } 2>/dev/null)
    if [[ "${modified_count}" -ge "${PRIMER_NON_LINK_COUNT}" ]]; then
        pass "Modified file count OK (${modified_count})"
    else
        fail "Modified file count LOW (${modified_count}, expected >=${PRIMER_NON_LINK_COUNT})"
        ok=0
    fi
    if [[ "${new_count}" -ge 1 ]]; then
        pass "New file count OK"
    else
        fail "New file missing from DIFF"
        ok=0
    fi
    return $((1 - ok))
}

update_incr_primer() {
    info "Updating diff-primer data for INCR..."
    find "$DIFF_PRIMER_DIR" -type f | grep -v "link_" | while read -r f; do
        dd if=/dev/urandom of="$f" bs="$(stat -c%s "$f")" count=1 2>/dev/null
    done || true
    # Remove one of the two current hardlink names; the underlying inode/content
    # survives via link_target2.txt, extending the hardlink-tracking chain one tier.
    rm "${DIFF_PRIMER_DIR}/link_target1.txt"
    ln "${DIFF_PRIMER_DIR}/link_target2.txt" "${DIFF_PRIMER_DIR}/link_target3.txt"
    dd if=/dev/urandom of="${DIFF_PRIMER_DIR}/incr_new_$(date +%s).bin" bs=1M count=2 2>/dev/null
}

verify_incr_contents() {
    local diff_base="$1" incr_base="$2" primer_rel="${DIFF_PRIMER_DIR#"$MOUNT_ROOT"/}"
    local ok=1
    banner "Phase 2c — INCR contents verification"
    local incr_saved; incr_saved=$(docker_run_tool /usr/local/bin/dar -l "${BACKUP_DIR}/${incr_base}" --noconf -am -as -Q 2>/dev/null | grep "\[Saved\]" | grep "${primer_rel}" || true)
    local modified_count; modified_count=$(echo "$incr_saved" | grep -v "incr_new_" | { grep -c "${primer_rel}" || true; } 2>/dev/null)
    local new_count; new_count=$(echo "$incr_saved" | { grep -c "incr_new_" || true; } 2>/dev/null)
    if [[ "${modified_count}" -ge "${PRIMER_NON_LINK_COUNT}" ]]; then
        pass "Modified file count OK (${modified_count})"
    else
        fail "Modified file count LOW (${modified_count}, expected >=${PRIMER_NON_LINK_COUNT})"
        ok=0
    fi
    if [[ "${new_count}" -ge 1 ]]; then
        pass "New file count OK"
    else
        fail "New file missing from INCR"
        ok=0
    fi
    return $((1 - ok))
}

# ── content checksum tracking ─────────────────────────────────────────────────
# Captures the final source state right before the Phase 3a restore, so the restore
# can be proven byte-for-byte correct rather than just "produced a file of that name".
declare -A PRIMER_SHA256
capture_primer_checksums() {
    info "Capturing sha256 checksums of current primer files for restore verification..."
    PRIMER_SHA256=()
    while IFS= read -r -d '' f; do
        local rel="${f#"$DIFF_PRIMER_DIR"/}"
        PRIMER_SHA256["$rel"]=$(sha256sum "$f" | awk '{print $1}')
    done < <(find "$DIFF_PRIMER_DIR" -type f -print0)
}

verify_primer_checksums() {
    banner "Phase 3a — Content checksum verification"
    local ok=1 checked=0
    for rel in "${!PRIMER_SHA256[@]}"; do
        local restored="${RESTORE_PRIMER_PATH}/${rel}"
        if [[ ! -f "$restored" ]]; then
            fail "Checksum verification: restored file missing: ${rel}"
            ok=0
            continue
        fi
        local actual; actual=$(sha256sum "$restored" | awk '{print $1}')
        if [[ "$actual" == "${PRIMER_SHA256[$rel]}" ]]; then
            checked=$((checked+1))
        else
            fail "Checksum mismatch for ${rel} (expected ${PRIMER_SHA256[$rel]}, got ${actual})"
            ok=0
        fi
    done
    [[ $ok -eq 1 ]] && pass "All ${checked} restored file(s) match source sha256 checksums"
    return $((1 - ok))
}

write_darrc() {
    if docker run --rm --entrypoint /bin/sh "$IMAGE" \
         -c 'cat /opt/venv/lib/python3*/site-packages/dar_backup/.darrc' \
         > "$DARRC" 2>/dev/null && [[ -s "$DARRC" ]]; then
        info "Using .darrc bundled in ${IMAGE}"
    else
        cat > "$DARRC" << 'EOF'
verbose:
 -vd
 -vf
compress-exclusion:
-an
-ag
-Z "*.gz" -Z "*.bz2" -Z "*.xz" -Z "*.zip" -Z "*.jpg" -Z "*.jpeg" -Z "*.png" -Z "*.NEF" -Z "*.mp4" -Z "*.mkv" -Z "*.dar"
-acase
EOF
    fi
}

check_par2_per_slice() {
    local archive_base="$1" slice_count="$2" ok=1
    for i in $(seq 1 "$slice_count"); do
        [[ ! -f "${PAR2_DIR}/${archive_base}.${i}.dar.par2" ]] && { fail "Missing par2 slice ${i}"; ok=0; }
    done
    [[ -f "${PAR2_DIR}/${archive_base}.par2" ]] && { fail "Archive-level par2 found (regression)"; ok=0; }
    if [[ -f "${PAR2_DIR}/${archive_base}.par2.manifest.ini" ]]; then
        pass "Manifest present"
    else
        fail "Manifest missing"
        ok=0
    fi
    return $((1 - ok))
}

check_dar_integrity() {
    info "Running dar -t on $2..."
    if docker_run_tool /usr/local/bin/dar -t "${BACKUP_DIR}/${1}" -N -Q >> "$LOGFILE" 2>&1; then
        pass "dar -t passed: $2"
        return 0
    fi
    fail "dar -t failed: $2"
    return 1
}

check_par2_verify() {
    local archive_base="$1" label="$2" all_ok=1

    # Enable safe globbing transitions
    shopt -s nullglob
    local par2_files=("${PAR2_DIR}/${archive_base}".*.dar.par2)
    shopt -u nullglob

    if [[ ${#par2_files[@]} -eq 0 ]]; then
        fail "No par2 slice files found for ${label} verification"
        return 1
    fi

    for par2_file in "${par2_files[@]}"; do
        docker_run_tool /usr/bin/par2 verify -B "$BACKUP_DIR" -q "$par2_file" >> "$LOGFILE" 2>&1 || { fail "par2 verify FAILED: $(basename "$par2_file")"; all_ok=0; }
    done
    [[ $all_ok -eq 1 ]] && pass "par2 verify passed all slices: ${label}"
    return $((1 - all_ok))
}



update_bitrot_phase_evidence() {
    local phase="$1"
    shift
    python3 "${REPO_DIR}/scripts/large_scale_bitrot.py" update-phase \
        --file "$BITROT_EVIDENCE_FILE" --phase "$phase" "$@"
}

mark_bitrot_phase_failed() {
    local phase="$1"
    if ! update_bitrot_phase_evidence "$phase" --status failed; then
        echo "ERROR: unable to record failed bitrot evidence for phase '${phase}'" >&2
    fi
}

do_bitrot_test() {
    local archive_base="$1"
    local phase="$2"
    local helper="${REPO_DIR}/scripts/large_scale_bitrot.py"
    local -a slice_files=()
    local -a segment_lines=()
    local -a segment_paths=()
    local -a segment_slice_numbers=()
    local -A affected_slice_seen=()
    local selection_json segment_output

    banner "Bitrot test on ${archive_base}"

    shopt -s nullglob
    slice_files=("${BACKUP_DIR}/${archive_base}".*.dar)
    shopt -u nullglob
    if [[ ${#slice_files[@]} -eq 0 ]]; then
        fail "No DAR slices found for bitrot selection"
        return 1
    fi

    if ! selection_json=$(python3 "$helper" select \
        --seed "$BITROT_SEED" \
        --phase "$phase" \
        --percent "$BITROT_PERCENT" \
        --mode "$BITROT_MODE" \
        "${slice_files[@]}"); then
        fail "Unable to select safe bitrot regions"
        return 1
    fi
    if ! python3 "$helper" init \
        --file "$BITROT_EVIDENCE_FILE" \
        --phase "$phase" \
        --selection "$selection_json" \
        --buffer-bytes "$BITROT_BUFFER_BYTES"; then
        fail "Unable to initialize bitrot evidence"
        return 1
    fi
    if ! segment_output=$(python3 "$helper" segments --selection "$selection_json"); then
        fail "Unable to decode selected bitrot segments"
        mark_bitrot_phase_failed "$phase"
        return 1
    fi
    mapfile -t segment_lines <<< "$segment_output"
    if [[ ${#segment_lines[@]} -eq 0 ]]; then
        fail "Bitrot selection contained no segments"
        mark_bitrot_phase_failed "$phase"
        return 1
    fi

    info "Injecting bitrot mode=${BITROT_MODE}, seed=${BITROT_SEED}, segments=${#segment_lines[@]}..."
    local injection_started_ns injection_elapsed_ms
    injection_started_ns=$(date +%s%N)
    local line segment_index region_index slice_path slice_number slice_bytes offset_bytes length_bytes
    for line in "${segment_lines[@]}"; do
        IFS=$'\t' read -r segment_index region_index slice_path slice_number slice_bytes offset_bytes length_bytes <<< "$line"
        if [[ -z "$segment_index" || -z "$region_index" || -z "$slice_path" || -z "$slice_number" || -z "$offset_bytes" || -z "$length_bytes" ]]; then
            fail "Malformed bitrot segment from selection helper"
            mark_bitrot_phase_failed "$phase"
            return 1
        fi
        info "Corrupting $(basename "$slice_path"): region=${region_index}, offset=${offset_bytes}, bytes=${length_bytes}, slice_bytes=${slice_bytes}"
        if ! dd if=/dev/urandom of="$slice_path" \
            bs=1M iflag=fullblock,count_bytes oflag=seek_bytes \
            seek="$offset_bytes" count="$length_bytes" \
            conv=notrunc status=none >> "$LOGFILE" 2>&1; then
            fail "Unable to inject bitrot into $(basename "$slice_path")"
            mark_bitrot_phase_failed "$phase"
            return 1
        fi
        if [[ -z "${affected_slice_seen[$slice_path]+present}" ]]; then
            affected_slice_seen["$slice_path"]=1
            segment_paths+=("$slice_path")
            segment_slice_numbers+=("$slice_number")
        fi
    done
    injection_elapsed_ms=$(( ($(date +%s%N) - injection_started_ns) / 1000000 ))
    if ! update_bitrot_phase_evidence "$phase" \
        --injection-elapsed-ms "$injection_elapsed_ms"; then
        fail "Unable to record bitrot injection timing"
        mark_bitrot_phase_failed "$phase"
        return 1
    fi

    if docker_run_tool /usr/local/bin/dar -t "${BACKUP_DIR}/${archive_base}" -N -Q >> "$LOGFILE" 2>&1; then
        fail "dar -t missed corruption"
        if ! update_bitrot_phase_evidence "$phase" \
            --dar-detected-corruption failed --status failed; then
            echo "ERROR: unable to record DAR corruption-detection failure" >&2
        fi
        return 1
    fi
    if ! update_bitrot_phase_evidence "$phase" --dar-detected-corruption passed; then
        fail "Unable to record DAR corruption detection"
        mark_bitrot_phase_failed "$phase"
        return 1
    fi
    pass "dar -t correctly detected corruption"

    info "Repairing ${#segment_paths[@]} affected slice(s) with PAR2..."
    local repair_all_started_ns repair_all_elapsed_ms
    local repair_started_ns repair_elapsed_ms repair_output repair_status
    local par2_file block_counts found_blocks total_blocks repair_rc
    local array_index
    repair_all_started_ns=$(date +%s%N)
    for array_index in "${!segment_paths[@]}"; do
        slice_path="${segment_paths[$array_index]}"
        slice_number="${segment_slice_numbers[$array_index]}"
        par2_file="${PAR2_DIR}/$(basename "$slice_path").par2"
        if [[ ! -f "$par2_file" ]]; then
            fail "PAR2 file missing for affected slice: $(basename "$slice_path")"
            mark_bitrot_phase_failed "$phase"
            return 1
        fi

        repair_started_ns=$(date +%s%N)
        if repair_output=$(docker_run_tool /usr/bin/par2 repair \
            -B "$BACKUP_DIR" -q "$par2_file" 2>&1); then
            repair_rc=0
            repair_status="passed"
        else
            repair_rc=$?
            repair_status="failed"
        fi
        repair_elapsed_ms=$(( ($(date +%s%N) - repair_started_ns) / 1000000 ))
        printf '%s\n' "$repair_output" >> "$LOGFILE"

        if ! block_counts=$(printf '%s\n' "$repair_output" | python3 "$helper" parse-blocks); then
            fail "Unable to parse PAR2 data-block counts for $(basename "$slice_path")"
            mark_bitrot_phase_failed "$phase"
            return 1
        fi
        IFS=$'\t' read -r found_blocks total_blocks <<< "$block_counts"
        if ! python3 "$helper" update-slice \
            --file "$BITROT_EVIDENCE_FILE" \
            --phase "$phase" \
            --slice-number "$slice_number" \
            --found "$found_blocks" \
            --total "$total_blocks" \
            --repair-elapsed-ms "$repair_elapsed_ms" \
            --repair-status "$repair_status"; then
            fail "Unable to record PAR2 repair evidence for $(basename "$slice_path")"
            mark_bitrot_phase_failed "$phase"
            return 1
        fi
        if [[ $repair_rc -ne 0 ]]; then
            fail "par2 repair failed for $(basename "$slice_path")"
            mark_bitrot_phase_failed "$phase"
            return 1
        fi
    done
    repair_all_elapsed_ms=$(( ($(date +%s%N) - repair_all_started_ns) / 1000000 ))
    if ! update_bitrot_phase_evidence "$phase" \
        --repair-elapsed-ms "$repair_all_elapsed_ms"; then
        fail "Unable to record total PAR2 repair timing"
        mark_bitrot_phase_failed "$phase"
        return 1
    fi
    pass "par2 repair succeeded for ${#segment_paths[@]} affected slice(s)"

    if docker_run_tool /usr/local/bin/dar -t "${BACKUP_DIR}/${archive_base}" -N -Q >> "$LOGFILE" 2>&1; then
        if ! update_bitrot_phase_evidence "$phase" \
            --dar-verify-after-repair passed --status passed; then
            fail "Unable to record post-repair DAR verification"
            mark_bitrot_phase_failed "$phase"
            return 1
        fi
        pass "dar -t passed after repair"
        return 0
    fi
    fail "dar -t still fails after repair"
    if ! update_bitrot_phase_evidence "$phase" \
        --dar-verify-after-repair failed --status failed; then
        echo "ERROR: unable to record post-repair DAR verification failure" >&2
    fi
    return 1
}

count_slices() {
    local archive_base="$1"
    local -a slice_files
    shopt -s nullglob
    slice_files=("${BACKUP_DIR}/${archive_base}".*.dar)
    shopt -u nullglob
    echo "${#slice_files[@]}"
}
init_manager_db() {
    if docker_run_tool /opt/venv/bin/manager --create-db --config-file "$CONFIG_FILE" --log-stdout >> "$LOGFILE" 2>&1; then
        pass "manager --create-db succeeded"
        return 0
    fi
    fail "manager --create-db failed"
    return 1
}

# ── find archive base for a backup type ───────────────────────────────────────
find_archive_base() {
    local type="$1"

    # Each backup invocation chooses its own calendar date. Discover the exact
    # archive written in this run's private directory so midnight rollovers do
    # not make a successful phase look missing.
    python3 "${REPO_DIR}/scripts/large_scale_archive.py" \
        --backup-dir "$BACKUP_DIR" \
        --definition-name "$DEFINITION_NAME" \
        --backup-type "$type"
}

calc_max_rss() {
    local target_cmd="$1"
    local log_path="${RSS_LOGFILE:-}"

    if [[ -n "$log_path" && -f "$log_path" ]]; then
        awk -v target="cmd=$target_cmd" '
            $7 == target {
                split($3, rss_val, "=");
                if (rss_val[2] > max) max = rss_val[2]
            }
            END { if (max > 0) printf "%.1f MB", max / 1024; else print "N/A" }
        ' "$log_path"
        return 0
    fi
    echo "N/A"
}

calc_archive_bytes() {
    local prefix="$1"
    local target_dir="${BACKUP_DIR:-}"
    local def_name="${DEFINITION_NAME:-}"
    local total_bytes=0

    if [[ -z "$target_dir" || ! -d "$target_dir" || -z "$def_name" ]]; then
        echo ""
        return 0
    fi

    shopt -s nullglob
    local archive_files=("${target_dir}/${def_name}_${prefix}_"*.dar)
    shopt -u nullglob
    if [[ ${#archive_files[@]} -eq 0 ]]; then
        echo ""
        return 0
    fi

    local archive_file file_bytes
    for archive_file in "${archive_files[@]}"; do
        file_bytes=$(stat -c%s "$archive_file")
        total_bytes=$((total_bytes + file_bytes))
    done
    echo "$total_bytes"
}

bytes_to_gb() {
    local byte_count="${1:-}"
    if [[ -z "$byte_count" ]]; then
        echo ""
        return 0
    fi
    awk -v bytes="$byte_count" 'BEGIN { printf "%.2f", bytes / 1024 / 1024 / 1024 }'
}

prepare_result_metrics() {
    MAX_DAR_BACKUP=$(calc_max_rss "dar-backup")
    MAX_DAR=$(calc_max_rss "dar")
    MAX_PAR2=$(calc_max_rss "par2")
    MAX_MANAGER=$(calc_max_rss "manager")

    FULL_SIZE_BYTES=$(calc_archive_bytes "FULL")
    DIFF_SIZE_BYTES=$(calc_archive_bytes "DIFF")
    INCR_SIZE_BYTES=$(calc_archive_bytes "INCR")
    FULL_SIZE_GB=$(bytes_to_gb "$FULL_SIZE_BYTES")
    DIFF_SIZE_GB=$(bytes_to_gb "$DIFF_SIZE_BYTES")
    INCR_SIZE_GB=$(bytes_to_gb "$INCR_SIZE_BYTES")
    OVERALL_ELAPSED=$(( $(date +%s) - RUN_STARTED_EPOCH ))
}

# Invoked indirectly from the EXIT trap via on_exit.
# shellcheck disable=SC2317
write_json_record() {
    local exit_status="$1"
    local effective_repo_dir="${REPO_DIR:-}"
    local db_mb dar_mb_value par2_mb manager_mb

    db_mb=$(awk '{print $1}' <<< "${MAX_DAR_BACKUP:-N/A}")
    dar_mb_value=$(awk '{print $1}' <<< "${MAX_DAR:-N/A}")
    par2_mb=$(awk '{print $1}' <<< "${MAX_PAR2:-N/A}")
    manager_mb=$(awk '{print $1}' <<< "${MAX_MANAGER:-N/A}")

    if [[ $SMOKETEST -eq 1 ]]; then
        effective_repo_dir=""
        info "Smoketest mode: not mirroring this run into the tracked repo history file."
    fi

    RESULT_WRITTEN=1
    LST_DATESTAMP="${DATESTAMP:-}" \
    LST_DATE="${DATE_OF_RUN:-}" \
    LST_ADVERTISE_REQUESTED="${ADVERTISE_REQUESTED:-0}" \
    LST_TEST_NAME="${TEST_NAME:-Large scale torture test}" \
    LST_ADVERTISE_CLASS="${ADVERTISE_CLASS:-unknown}" \
    LST_GIT_COMMIT="${GIT_COMMIT:-unknown}" \
    LST_DAR_BACKUP_VER="${DAR_BACKUP_VERSION:-unknown}" \
    LST_DAR_VER="${DAR_VERSION:-unknown}" \
    LST_PAR2_VER="${PAR2_VERSION:-unknown}" \
    LST_PYTHON_VER="${PYTHON_VERSION:-unknown}" \
    LST_OS_DESC="${OS_DESC:-unknown}" \
    LST_KERNEL="${KERNEL:-unknown}" \
    LST_FULL_ELAPSED="${full_elapsed:-0}" \
    LST_FULL_GB="${FULL_SIZE_GB:-}" \
    LST_DIFF_ELAPSED="${diff_elapsed:-0}" \
    LST_DIFF_GB="${DIFF_SIZE_GB:-}" \
    LST_INCR_ELAPSED="${incr_elapsed:-0}" \
    LST_INCR_GB="${INCR_SIZE_GB:-}" \
    LST_DB_MB="$db_mb" \
    LST_DAR_MB="$dar_mb_value" \
    LST_PAR2_MB="$par2_mb" \
    LST_MGR_MB="$manager_mb" \
    LST_FAILURES="${FAILURES:-0}" \
    LST_SCRIPT_VERSION="$SCRIPT_VERSION" \
    LST_HARNESS_GIT_COMMIT="${HARNESS_GIT_COMMIT:-unknown}" \
    LST_HARNESS_GIT_DIRTY="${HARNESS_GIT_DIRTY:-0}" \
    LST_IMAGE_REFERENCE="$IMAGE" \
    LST_IMAGE_ID="${IMAGE_ID:-unknown}" \
    LST_IMAGE_REPO_DIGEST="${IMAGE_REPO_DIGEST:-}" \
    LST_IMAGE_REVISION="${IMAGE_REVISION:-}" \
    LST_IMAGE_VERSION="${IMAGE_VERSION:-}" \
    LST_SOURCE_FILE_COUNT="${SOURCE_FILE_COUNT:-}" \
    LST_SOURCE_BYTES="${SOURCE_BYTES:-}" \
    LST_BACKUP_DEFINITION_SHA256="${BACKUP_DEFINITION_SHA256:-}" \
    LST_FULL_BYTES="${FULL_SIZE_BYTES:-}" \
    LST_DIFF_BYTES="${DIFF_SIZE_BYTES:-}" \
    LST_INCR_BYTES="${INCR_SIZE_BYTES:-}" \
    LST_OVERALL_ELAPSED="${OVERALL_ELAPSED:-0}" \
    LST_COMPLETED="${RUN_COMPLETED:-0}" \
    LST_CURRENT_PHASE="${CURRENT_PHASE:-unknown}" \
    LST_EXIT_CODE="$exit_status" \
    LST_MANAGER_DB_STATUS="$MANAGER_DB_STATUS" \
    LST_FULL_BACKUP_STATUS="$FULL_BACKUP_STATUS" \
    LST_DIFF_BACKUP_STATUS="$DIFF_BACKUP_STATUS" \
    LST_INCR_BACKUP_STATUS="$INCR_BACKUP_STATUS" \
    LST_FULL_ARCHIVE_STATUS="$FULL_ARCHIVE_STATUS" \
    LST_DIFF_ARCHIVE_STATUS="$DIFF_ARCHIVE_STATUS" \
    LST_INCR_ARCHIVE_STATUS="$INCR_ARCHIVE_STATUS" \
    LST_FULL_PAR2_FILES_STATUS="$FULL_PAR2_FILES_STATUS" \
    LST_DIFF_PAR2_FILES_STATUS="$DIFF_PAR2_FILES_STATUS" \
    LST_INCR_PAR2_FILES_STATUS="$INCR_PAR2_FILES_STATUS" \
    LST_FULL_PAR2_VERIFY_STATUS="$FULL_PAR2_VERIFY_STATUS" \
    LST_DIFF_PAR2_VERIFY_STATUS="$DIFF_PAR2_VERIFY_STATUS" \
    LST_INCR_PAR2_VERIFY_STATUS="$INCR_PAR2_VERIFY_STATUS" \
    LST_FULL_BITROT_STATUS="$FULL_BITROT_STATUS" \
    LST_DIFF_BITROT_STATUS="$DIFF_BITROT_STATUS" \
    LST_INCR_BITROT_STATUS="$INCR_BITROT_STATUS" \
    LST_DIFF_CONTENTS_STATUS="$DIFF_CONTENTS_STATUS" \
    LST_INCR_CONTENTS_STATUS="$INCR_CONTENTS_STATUS" \
    LST_PITR_EXECUTION_STATUS="$PITR_EXECUTION_STATUS" \
    LST_PITR_STRUCTURE_STATUS="$PITR_STRUCTURE_STATUS" \
    LST_PITR_CHECKSUM_STATUS="$PITR_CHECKSUM_STATUS" \
    LST_PITR_OVERALL_STATUS="$PITR_OVERALL_STATUS" \
    LST_FULL_RESTORE_MODE="$FULL_RESTORE_MODE" \
    LST_FULL_RESTORE_THRESHOLD_BYTES="$FULL_RESTORE_THRESHOLD_BYTES" \
    LST_FULL_RESTORE_PERFORMED="$FULL_RESTORE_PERFORMED" \
    LST_FULL_RESTORE_DECISION_REASON="$FULL_RESTORE_DECISION_REASON" \
    LST_FULL_RESTORE_EXECUTION_STATUS="$FULL_RESTORE_EXECUTION_STATUS" \
    LST_FULL_RESTORE_CONTENT_STATUS="$FULL_RESTORE_CONTENT_STATUS" \
    LST_FULL_RESTORE_OVERALL_STATUS="$FULL_RESTORE_OVERALL_STATUS" \
    LST_FULL_RESTORE_FILE_COUNT="${FULL_RESTORE_FILE_COUNT:-}" \
    LST_FULL_RESTORE_BYTES="${FULL_RESTORE_BYTES:-}" \
    LST_BITROT_SEED="${BITROT_SEED:-}" \
    LST_BITROT_EVIDENCE_FILE="${BITROT_EVIDENCE_FILE:-}" \
    LST_RESULTS_DIR="$RESULTS_DIR" \
    LST_REPO_DIR="$effective_repo_dir" \
    python3 "${REPO_DIR}/scripts/large_scale_result.py"
    local result_status=$?
    if [[ $result_status -ne 0 ]]; then
        return "$result_status"
    fi

    info "Structured result written to: ${RESULTS_DIR}/large-scale-results.jsonl"
    if [[ -n "$effective_repo_dir" ]]; then
        info "Structured result mirrored to: ${effective_repo_dir}/doc/test-report/large-scale-results.jsonl"
    fi
}

# Invoked indirectly from the EXIT trap via on_exit.
# shellcheck disable=SC2317
cleanup() {
    if [[ $KEEP -eq 0 ]]; then
        rm -rf "${RUN_DIR:?}"
        return 0
    fi
    info "Keeping run directory: $RUN_DIR"
}

# Static analysis cannot follow function names registered as trap handlers.
# shellcheck disable=SC2317
on_exit() {
    local exit_status=$?
    local writer_status=0

    trap - EXIT HUP INT QUIT TERM
    set +e
    stop_rss_monitor
    if [[ $RUN_RESULT_READY -eq 1 && $RESULT_WRITTEN -eq 0 ]]; then
        prepare_result_metrics
        write_json_record "$exit_status"
        writer_status=$?
        if [[ $writer_status -ne 0 ]]; then
            echo "ERROR: failed to write structured JSON result (exit ${writer_status})" >&2
            [[ $exit_status -eq 0 ]] && exit_status=$writer_status
        fi
    fi
    cleanup
    exit "$exit_status"
}

# Static analysis cannot follow function names registered as trap handlers.
# shellcheck disable=SC2317
on_interrupt() {
    local signal_exit_code="$1"
    CURRENT_PHASE="${CURRENT_PHASE}:interrupted"
    exit "$signal_exit_code"
}

full_elapsed=0; diff_elapsed=0; incr_elapsed=0
FULL_BASE=""; DIFF_BASE=""; INCR_BASE=""; FULL_SLICES=0

RUN_RESULT_READY=1
trap on_exit EXIT
trap 'on_interrupt 129' HUP
trap 'on_interrupt 130' INT
trap 'on_interrupt 131' QUIT
trap 'on_interrupt 143' TERM

# ════════════════════════════════════════════════════════════════════════════════
# MAIN ORCHESTRATION
# ════════════════════════════════════════════════════════════════════════════════
banner "dar-backup large-scale test  ${DATESTAMP}"

print_run_variables

CURRENT_PHASE="setup"
write_config
create_diff_primer
write_backup_def
check_disk_space
write_darrc
if init_manager_db; then
    MANAGER_DB_STATUS="passed"
else
    MANAGER_DB_STATUS="failed"
fi
start_rss_monitor

# ── PHASE 1 ──
CURRENT_PHASE="full_backup"
banner "Phase 1 — FULL backup"
t0=$(date +%s)
if docker_run_backup -F -d "$DEFINITION_NAME" --config-file "$CONFIG_FILE" --darrc "$DARRC" --log-level debug; then
    full_elapsed=$(( $(date +%s) - t0 ))
    FULL_BACKUP_STATUS="passed"
    pass "FULL backup completed in ${full_elapsed}s"
else
    full_elapsed=$(( $(date +%s) - t0 ))
    FULL_BACKUP_STATUS="failed"
    fail "FULL backup failed after ${full_elapsed}s; see ${LOGFILE}"
    exit 1
fi

if ! FULL_BASE=$(find_archive_base "FULL"); then
    fail "No unique FULL base found"
    exit 1
fi
FULL_SLICES=$(count_slices "$FULL_BASE")

CURRENT_PHASE="full_verification"
if check_dar_integrity "$FULL_BASE" "FULL"; then FULL_ARCHIVE_STATUS="passed"; else FULL_ARCHIVE_STATUS="failed"; fi
if check_par2_per_slice "$FULL_BASE" "$FULL_SLICES"; then FULL_PAR2_FILES_STATUS="passed"; else FULL_PAR2_FILES_STATUS="failed"; fi
if check_par2_verify "$FULL_BASE" "FULL"; then FULL_PAR2_VERIFY_STATUS="passed"; else FULL_PAR2_VERIFY_STATUS="failed"; fi
if [[ $DO_BITROT -eq 1 ]]; then
    if do_bitrot_test "$FULL_BASE" "full"; then FULL_BITROT_STATUS="passed"; else FULL_BITROT_STATUS="failed"; fi
fi

# ── PHASE 2 ──
CURRENT_PHASE="diff_backup"
banner "Phase 2 — DIFF backup"
update_diff_primer
t0=$(date +%s)
if docker_run_backup -D -d "$DEFINITION_NAME" --config-file "$CONFIG_FILE" --darrc "$DARRC" --log-level debug; then
    diff_elapsed=$(( $(date +%s) - t0 ))
    DIFF_BACKUP_STATUS="passed"
    pass "DIFF backup completed in ${diff_elapsed}s"
else
    diff_elapsed=$(( $(date +%s) - t0 ))
    DIFF_BACKUP_STATUS="failed"
    fail "DIFF backup failed after ${diff_elapsed}s; see ${LOGFILE}"
    exit 1
fi

if ! DIFF_BASE=$(find_archive_base "DIFF"); then
    fail "No unique DIFF base found"
    exit 1
fi
DIFF_SLICES=$(count_slices "$DIFF_BASE")
CURRENT_PHASE="diff_verification"
if check_dar_integrity "$DIFF_BASE" "DIFF"; then DIFF_ARCHIVE_STATUS="passed"; else DIFF_ARCHIVE_STATUS="failed"; fi
if check_par2_per_slice "$DIFF_BASE" "$DIFF_SLICES"; then DIFF_PAR2_FILES_STATUS="passed"; else DIFF_PAR2_FILES_STATUS="failed"; fi
if check_par2_verify "$DIFF_BASE" "DIFF"; then DIFF_PAR2_VERIFY_STATUS="passed"; else DIFF_PAR2_VERIFY_STATUS="failed"; fi
if [[ $DO_BITROT -eq 1 ]]; then
    if do_bitrot_test "$DIFF_BASE" "diff"; then DIFF_BITROT_STATUS="passed"; else DIFF_BITROT_STATUS="failed"; fi
fi
if verify_diff_contents "$FULL_BASE" "$DIFF_BASE"; then DIFF_CONTENTS_STATUS="passed"; else DIFF_CONTENTS_STATUS="failed"; fi

# ── PHASE 2c ──
CURRENT_PHASE="incr_backup"
banner "Phase 2c — INCR backup"
info "Waiting ~2-3 minutes before mutating data for INCR (keeps primer mtimes cleanly separated in the log)..."
sleep 150
update_incr_primer
t0=$(date +%s)
if docker_run_backup -I -d "$DEFINITION_NAME" --config-file "$CONFIG_FILE" --darrc "$DARRC" --log-level debug; then
    incr_elapsed=$(( $(date +%s) - t0 ))
    INCR_BACKUP_STATUS="passed"
    pass "INCR backup completed in ${incr_elapsed}s"
else
    incr_elapsed=$(( $(date +%s) - t0 ))
    INCR_BACKUP_STATUS="failed"
    fail "INCR backup failed after ${incr_elapsed}s; see ${LOGFILE}"
    exit 1
fi

if ! INCR_BASE=$(find_archive_base "INCR"); then
    fail "No unique INCR base found"
    exit 1
fi
INCR_SLICES=$(count_slices "$INCR_BASE")
CURRENT_PHASE="incr_verification"
if check_dar_integrity "$INCR_BASE" "INCR"; then INCR_ARCHIVE_STATUS="passed"; else INCR_ARCHIVE_STATUS="failed"; fi
if check_par2_per_slice "$INCR_BASE" "$INCR_SLICES"; then INCR_PAR2_FILES_STATUS="passed"; else INCR_PAR2_FILES_STATUS="failed"; fi
if check_par2_verify "$INCR_BASE" "INCR"; then INCR_PAR2_VERIFY_STATUS="passed"; else INCR_PAR2_VERIFY_STATUS="failed"; fi
if [[ $DO_BITROT -eq 1 ]]; then
    if do_bitrot_test "$INCR_BASE" "incr"; then INCR_BITROT_STATUS="passed"; else INCR_BITROT_STATUS="failed"; fi
fi
if verify_incr_contents "$DIFF_BASE" "$INCR_BASE"; then INCR_CONTENTS_STATUS="passed"; else INCR_CONTENTS_STATUS="failed"; fi

capture_primer_checksums

# ── PHASE 3 ──
CURRENT_PHASE="pitr_restore"
banner "Phase 3a — Point-In-Time Restore Validation (latest state)"

info "Cleaning restore target directory to satisfy manager safety checks..."
rm -rf "$RESTORE_DIR"
mkdir -p "$RESTORE_DIR"

info "Invoking manager to process PITR extraction for diff-primer data..."

# Using the exact CLI arguments from restoring.md to restore our relative primer directory
if docker_run_tool /opt/venv/bin/manager --config-file "$CONFIG_FILE" \
           -d "$DEFINITION_NAME" \
           --restore-path "${DIFF_PRIMER_DIR#"$MOUNT_ROOT"/}/" \
           --when "now" \
           --target "$RESTORE_DIR" \
           --log-stdout --verbose >> "$LOGFILE" 2>&1; then
    PITR_EXECUTION_STATUS="passed"
    pass "Restore sequence completed execution via manager"
else
    PITR_EXECUTION_STATUS="failed"
    fail "manager PITR restore dropped an error exit code"
fi

RESTORE_PRIMER_PATH="${RESTORE_DIR}/${DIFF_PRIMER_DIR#"$MOUNT_ROOT"/}"
pitr_structure_ok=1

if [[ -f "${RESTORE_PRIMER_PATH}/link_original.txt" ]]; then
    fail "link_original.txt present in latest-state restore (should have been deleted by DIFF)"
    pitr_structure_ok=0
else
    pass "link_original.txt correctly absent from latest-state restore"
fi
if [[ -f "${RESTORE_PRIMER_PATH}/link_target1.txt" ]]; then
    fail "link_target1.txt present in latest-state restore (should have been deleted by INCR)"
    pitr_structure_ok=0
else
    pass "link_target1.txt correctly absent from latest-state restore"
fi
if [[ -f "${RESTORE_PRIMER_PATH}/link_target2.txt" && -f "${RESTORE_PRIMER_PATH}/link_target3.txt" ]]; then
    inode2=$(stat -c %i "${RESTORE_PRIMER_PATH}/link_target2.txt")
    inode3=$(stat -c %i "${RESTORE_PRIMER_PATH}/link_target3.txt")
    if [[ "$inode2" -eq "$inode3" ]]; then
        pass "Hard Link Inodes match (${inode2})"
    else
        fail "Inodes mismatched (Cloned data!)"
        pitr_structure_ok=0
    fi
else
    fail "Hard-link targets missing"
    pitr_structure_ok=0
fi
if compgen -G "${RESTORE_PRIMER_PATH}/incr_new_*.bin" > /dev/null; then
    pass "INCR-tier new file present in latest-state restore"
else
    fail "INCR-tier new file missing from latest-state restore"
    pitr_structure_ok=0
fi

if [[ $pitr_structure_ok -eq 1 ]]; then PITR_STRUCTURE_STATUS="passed"; else PITR_STRUCTURE_STATUS="failed"; fi
if verify_primer_checksums; then PITR_CHECKSUM_STATUS="passed"; else PITR_CHECKSUM_STATUS="failed"; fi
if [[ "$PITR_EXECUTION_STATUS" == "passed" && "$PITR_STRUCTURE_STATUS" == "passed" && "$PITR_CHECKSUM_STATUS" == "passed" ]]; then
    PITR_OVERALL_STATUS="passed"
else
    PITR_OVERALL_STATUS="failed"
fi

# ── PHASE 3b ──
banner "Phase 3b — Complete Point-In-Time Restore Validation"
if [[ $FULL_RESTORE_SELECTED -eq 1 ]]; then
    CURRENT_PHASE="full_restore"
    info "Cleaning the complete restore target..."
    rm -rf "$FULL_RESTORE_DIR"
    mkdir -p "$FULL_RESTORE_DIR"
    FULL_RESTORE_PERFORMED=1

    info "Restoring the complete archive root via manager..."
    if docker_run_tool /opt/venv/bin/manager --config-file "$CONFIG_FILE" \
               -d "$DEFINITION_NAME" \
               --restore-path . \
               --when "now" \
               --target "$FULL_RESTORE_DIR" \
               --log-stdout --verbose >> "$LOGFILE" 2>&1; then
        FULL_RESTORE_EXECUTION_STATUS="passed"
        pass "Complete archive-root restore executed successfully"
    else
        FULL_RESTORE_EXECUTION_STATUS="failed"
        FULL_RESTORE_OVERALL_STATUS="failed"
        fail "Complete archive-root restore returned an error exit code"
    fi

    if [[ "$FULL_RESTORE_EXECUTION_STATUS" == "passed" ]]; then
        comparison_json=""
        if comparison_json=$(python3 "${REPO_DIR}/scripts/large_scale_restore_compare.py" \
                --source-root "$MOUNT_ROOT" \
                --restored-root "$FULL_RESTORE_DIR" \
                --required-relative-path "${DIFF_PRIMER_DIR#"$MOUNT_ROOT"/}" \
                2>> "$LOGFILE"); then
            read -r FULL_RESTORE_FILE_COUNT FULL_RESTORE_BYTES <<< "$(python3 -c '
import json
import sys
result = json.loads(sys.argv[1])
print(result["restored_file_count"], result["restored_bytes"])
' "$comparison_json")"
            FULL_RESTORE_CONTENT_STATUS="passed"
            FULL_RESTORE_OVERALL_STATUS="passed"
            pass "All ${FULL_RESTORE_FILE_COUNT} restored regular-file path(s) (${FULL_RESTORE_BYTES} byte(s)) match the live source"
        else
            FULL_RESTORE_CONTENT_STATUS="failed"
            FULL_RESTORE_OVERALL_STATUS="failed"
            fail "Complete restore content comparison failed; see ${LOGFILE}"
        fi
    fi
else
    info "Complete restore not selected (${FULL_RESTORE_DECISION_REASON})."
fi

# ── SUMMARY ───────────────────────────────────────────────────────────────────
CURRENT_PHASE="summary"
banner "Summary"

stop_rss_monitor
prepare_result_metrics

# Compile final analytics screen layout using matched variable casing
echo -e "dar-backup test pass: ${DATESTAMP:-}"
echo -e "FULL elapsed: ${full_elapsed:-0}s (~${FULL_SIZE_GB:-N/A} GB)"
echo -e "DIFF elapsed: ${diff_elapsed:-0}s (~${DIFF_SIZE_GB:-N/A} GB)"
echo -e "INCR elapsed: ${incr_elapsed:-0}s (~${INCR_SIZE_GB:-N/A} GB)"
echo -e "Complete restore: ${FULL_RESTORE_OVERALL_STATUS} (${FULL_RESTORE_DECISION_REASON})"
echo -e "Peak Engine Memory Consumption:"
echo -e "  ├── dar-backup : ${MAX_DAR_BACKUP}"
echo -e "  ├── dar backend: ${MAX_DAR}"
echo -e "  ├── par2 engine: ${MAX_PAR2}"
echo -e "  └── db manager : ${MAX_MANAGER}"
echo -e "Failures:      ${FAILURES:-0}"

# Final status validation routing
RUN_COMPLETED=1
CURRENT_PHASE="completed"
if [ "${FAILURES:-0}" -eq 0 ]; then
    echo -e "\n${GREEN}${BOLD}✓ ALL TESTS PASSED SUCCESSFULLY${RESET}\n"
    exit 0
else
    echo -e "\n${RED}${BOLD}✗ TEST SUITE FAILED WITH ${FAILURES} ERRORS${RESET}\n"
    exit 1
fi
