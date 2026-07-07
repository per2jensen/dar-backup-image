#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Personal wrapper for scripts/large_scale_test.sh
#
# Builds a fresh dar-backup:dev image, then runs the large-scale test against
# it. All file operations happen under BASE_DIR (which must live at least two
# directories deep, see scripts/large_scale_test.sh for why).
#
# SOURCE_GLOB picks how much real photo data to back up (relative to -R /data,
# i.e. under /data/billeder). Defaults to a small subdirectory for quick runs;
# override for a full-size soak test, e.g.:
#   SOURCE_GLOB=billeder/2013 ./run_large_scale_test.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="/data/tmp/image-large-scale-test"
IMAGE="dar-backup:dev"
SOURCE_GLOB="${SOURCE_GLOB:-billeder/2013/2013-06}"

echo "Building ${IMAGE}..."
make -C "${SCRIPT_DIR}" dev

# Run the script completely natively in the foreground
"${SCRIPT_DIR}/scripts/large_scale_test.sh" \
    --base "${BASE_DIR}" \
    --image "${IMAGE}" \
    --bitrot \
    "$@" \
    --definition "$(cat << EOF
-R /data
-s 10G
-z6
-am
--cache-directory-tagging
-g ${SOURCE_GLOB}
EOF
)"
