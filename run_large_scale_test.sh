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
#
# BASE_DIR must live at least two directories deep (see scripts/large_scale_test.sh
# for why), and SOURCE_GLOB must resolve to real data under BASE_DIR's own
# top-level directory (e.g. BASE_DIR=/data/... pairs with SOURCE_GLOB paths
# under /data/...) — see doc/demo-large-scale-test.md for a worked example.
#
# For anything beyond SOURCE_GLOB/SLICE_SIZE/COMPRESSION (exclude patterns,
# several -g lines, a different -am mode, ...), set DEFINITION to a complete
# backup-definition body and it's used verbatim instead of the pieced-together
# one below. Its own -R must still match BASE_DIR's derived mount root, e.g.:
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
SOURCE_GLOB="${SOURCE_GLOB:-billeder/2013/2013-06}"     # real data to back up, relative to BASE_DIR's top-level directory
SLICE_SIZE="${SLICE_SIZE:-10G}"                         # dar -s slice size
COMPRESSION="${COMPRESSION:-6}"                         # dar -z compression level (1-9)
BITROT="${BITROT:-true}"                                # set to "false" to skip the bitrot-inject/par2-repair phases
DEFINITION="${DEFINITION:-}"                            # full backup-definition body; overrides SOURCE_GLOB/SLICE_SIZE/COMPRESSION entirely when set (see examples above)

# large_scale_test.sh requires the definition's -R to match the mount root it
# derives from BASE_DIR's own top-level directory (e.g. "/data/tmp/foo" ->
# "/data") — computed the same way here so overriding BASE_DIR to a different
# top-level directory (e.g. /home/...) still produces a matching -R.
MOUNT_ROOT="/$(echo "$BASE_DIR" | cut -d/ -f2)"

if [[ "$BUILD_IMAGE" == "true" ]]; then
    echo "Building ${IMAGE}..."
    make -C "${SCRIPT_DIR}" dev
else
    echo "BUILD_IMAGE=false — skipping build, using existing image ${IMAGE}"
fi

ARGS=(--base "${BASE_DIR}" --image "${IMAGE}")
[[ "$BITROT" == "true" ]] && ARGS+=(--bitrot)

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

# Run the script completely natively in the foreground
"${SCRIPT_DIR}/scripts/large_scale_test.sh" \
    "${ARGS[@]}" \
    "$@" \
    --definition "$DEFINITION"
