#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Personal wrapper for scripts/large_scale_test.sh — also doubles as a demo of
# running dar-backup's full FULL->DIFF->INCR->bitrot-repair->PITR-restore
# lifecycle entirely inside Docker against real data. See
# doc/demo-large-scale-test.md for a full user-facing walkthrough.
#
# Every value below can be overridden via an environment variable of the same
# name; the assignments here are just the defaults. Examples:
# 1.
#   BASE_DIR=/home/alice/dar-backup-test SOURCE_GLOB=alice/photos ./run_large_scale_test.sh
# 2.
#   IMAGE=per2jensen/dar-backup:latest BUILD_IMAGE=false ./run_large_scale_test.sh
# 3.
#   SLICE_SIZE=20G COMPRESSION=9 BITROT=false ./run_large_scale_test.sh
# 4. Replay the exact random bitrot choices from an earlier result:
#   BITROT_SEED=123456789 ./run_large_scale_test.sh
# 5. Spread the 2% corruption budget over reproducible separated regions:
#   BITROT_MODE=fragmented ./run_large_scale_test.sh
# 6. Corrupt the beginning of slice 1 and the end of the final slice:
#   BITROT_MODE=edges ./run_large_scale_test.sh
# 7. Request publication if the completed run passes and is at least 100 GiB:
#   ADVERTISE=true ADVERTISE_CLASS=v0.5.29 ./run_large_scale_test.sh
# 8. Force a complete archive-root restore even for a very large source:
#   FULL_RESTORE_MODE=forced ./run_large_scale_test.sh
#
# BASE_DIR must live at least two directories deep (see scripts/large_scale_test.sh
# for why), and SOURCE_GLOB must resolve to real data under BASE_DIR's own
# top-level directory (e.g. BASE_DIR=/data/... pairs with SOURCE_GLOB paths
# under /data/...) — see doc/demo-large-scale-test.md for a worked example.
#
# For several literal -g paths and literal -P subtrees, set DEFINITION to a
# complete backup-definition body. The harness intentionally accepts only the
# selection subset documented in doc/demo-large-scale-test.md; it is not a
# general DAR selection parser. Its -R must match BASE_DIR's mount root, e.g.:
#   DEFINITION="$(cat <<'EOF'
#   -R /data
#   -s 10G
#   -z6
#   -am
#   --cache-directory-tagging
#   -g billeder/2013
#   -P billeder/2013/.recycle
#   EOF
#   )" ./run_large_scale_test.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="${BASE_DIR:-/data/tmp/image-large-scale-test}"
IMAGE="${IMAGE:-dar-backup:dev}"
BUILD_IMAGE="${BUILD_IMAGE:-true}"                      # set to "false" to skip `make dev`, e.g. when IMAGE already points at a pulled/pre-built image
SOURCE_GLOB="${SOURCE_GLOB:-billeder/2013}"     # real data to back up, relative to BASE_DIR's top-level directory
SLICE_SIZE="${SLICE_SIZE:-10G}"                         # dar -s slice size
COMPRESSION="${COMPRESSION:-6}"                         # dar -z compression level (1-9)
BITROT="${BITROT:-true}"                                # set to "false" to skip the bitrot-inject/par2-repair phases
BITROT_SEED="${BITROT_SEED:-}"                          # optional unsigned 64-bit replay seed; empty generates and records a new seed
BITROT_MODE="${BITROT_MODE:-contiguous}"                # contiguous (default), fragmented, or edges
ADVERTISE="${ADVERTISE:-false}"                         # true requests badge publication; success and size are still enforced by the harness
TEST_NAME="${TEST_NAME:-Large scale torture test}"      # human-readable badge label recorded with the result
ADVERTISE_CLASS="${ADVERTISE_CLASS:-}"                  # tested version/class; empty derives it from the image metadata
FULL_RESTORE_MODE="${FULL_RESTORE_MODE:-auto}"          # auto at/below threshold, forced at any size, or disabled
FULL_RESTORE_THRESHOLD_GIB="${FULL_RESTORE_THRESHOLD_GIB:-25}" # inclusive auto-mode source-size limit in GiB
DEFINITION="${DEFINITION:-}"                            # full backup-definition body; overrides pieced-together options; SLICE_SIZE remains the fallback when it has no slice option

case "$ADVERTISE" in
    true|false) ;;
    *) echo "ERROR: ADVERTISE must be 'true' or 'false', got '${ADVERTISE}'" >&2; exit 1 ;;
esac
case "$FULL_RESTORE_MODE" in
    auto|forced|disabled) ;;
    *) echo "ERROR: FULL_RESTORE_MODE must be 'auto', 'forced', or 'disabled', got '${FULL_RESTORE_MODE}'" >&2; exit 1 ;;
esac
[[ "$FULL_RESTORE_THRESHOLD_GIB" =~ ^[1-9][0-9]*$ ]] || { echo "ERROR: FULL_RESTORE_THRESHOLD_GIB must be a positive integer, got '${FULL_RESTORE_THRESHOLD_GIB}'" >&2; exit 1; }

# large_scale_test.sh requires the definition's -R to match the mount root it
# derives from BASE_DIR's own top-level directory (e.g. "/data/tmp/foo" ->
# "/data") — computed the same way here so overriding BASE_DIR to a different
# top-level directory (e.g. /home/...) still produces a matching -R.
MOUNT_ROOT="/$(echo "$BASE_DIR" | cut -d/ -f2)"

if [[ -z "$DEFINITION" ]]; then
    DEFINITION="$(cat << EOF
-R ${MOUNT_ROOT}
-s ${SLICE_SIZE}
-z${COMPRESSION}
-am
--cache-directory-tagging
-g ${SOURCE_GLOB}
EOF
)"
fi

# The internal harness parses passthrough arguments after wrapper defaults, so
# the last --slice supplied here is the fallback that will actually take effect.
EFFECTIVE_SLICE_FALLBACK="$SLICE_SIZE"
PASSTHROUGH_ARGUMENTS=("$@")
for ((argument_index = 0; argument_index < ${#PASSTHROUGH_ARGUMENTS[@]}; argument_index++)); do
    if [[ "${PASSTHROUGH_ARGUMENTS[$argument_index]}" != "--slice" ]]; then
        continue
    fi
    next_index=$((argument_index + 1))
    if [[ $next_index -ge ${#PASSTHROUGH_ARGUMENTS[@]} ]]; then
        echo "ERROR: --slice requires a value" >&2
        exit 1
    fi
    EFFECTIVE_SLICE_FALLBACK="${PASSTHROUGH_ARGUMENTS[$next_index]}"
done
if ! python3 "${SCRIPT_DIR}/scripts/large_scale_definition.py" \
        --definition "$DEFINITION" \
        --fallback "$EFFECTIVE_SLICE_FALLBACK" >/dev/null; then
    exit 1
fi
DEFINITION_ROOT=""
if ! DEFINITION_ROOT=$(python3 "${SCRIPT_DIR}/scripts/large_scale_definition.py" \
        --definition "$DEFINITION" \
        --selection-root); then
    exit 1
fi
if [[ "$DEFINITION_ROOT" != "$MOUNT_ROOT" ]]; then
    echo "ERROR: DEFINITION's -R must match mount root '${MOUNT_ROOT}', got '${DEFINITION_ROOT}'" >&2
    exit 1
fi

if [[ "$BUILD_IMAGE" == "true" ]]; then
    echo "Building ${IMAGE}..."
    make -C "${SCRIPT_DIR}" dev
else
    echo "BUILD_IMAGE=false — skipping build, using existing image ${IMAGE}"
fi

ARGS=(--base "${BASE_DIR}" --image "${IMAGE}" --slice "$SLICE_SIZE")
[[ "$BITROT" == "true" ]] && ARGS+=(--bitrot)
[[ "$BITROT" == "true" && -n "$BITROT_SEED" ]] && ARGS+=(--bitrot-seed "$BITROT_SEED")
[[ "$BITROT" == "true" ]] && ARGS+=(--bitrot-mode "$BITROT_MODE")
[[ "$ADVERTISE" == "true" ]] && ARGS+=(--advertise)
ARGS+=(--test-name "$TEST_NAME")
[[ -n "$ADVERTISE_CLASS" ]] && ARGS+=(--advertise-class "$ADVERTISE_CLASS")
ARGS+=(--full-restore-mode "$FULL_RESTORE_MODE")
ARGS+=(--full-restore-threshold-gib "$FULL_RESTORE_THRESHOLD_GIB")

# Run the script completely natively in the foreground
"${SCRIPT_DIR}/scripts/large_scale_test.sh" \
    "${ARGS[@]}" \
    "$@" \
    --definition "$DEFINITION"
