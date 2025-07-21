#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later

#  This script runs a backup using the dar-backup Docker image.
# 
#  It runs a backup based on the specified type (FULL, DIFF, INCR)
#  with the following features:
#
#  1. using the baked in dar-backup.conf file (se repo).
#
#  2. uses the .darrc file from the PyPI package added to the image,
#     see image details here:
#     https://github.com/per2jensen/dar-backup-image/blob/main/doc/build-history.json
#     
#     .darrc contents:
#      https://github.com/per2jensen/dar-backup/blob/main/v2/src/dar_backup/.darrc
#  3. It print log messages to stdout.
#
#  4. Expected directory structure when running this script:
#     WORKDIR/
#       ├── backups/           # Where backups are stored
#       ├── backup.d/          # Backup definitions
#       ├── data/              # Data to backup
#       └── restore/           # Where restored files will be placed
#
#     If envvar WORKDIR is set, the script uses that as the base directory.
#
#     If WORKDIR is not set, the script uses the directory where the script
#     is located as the base directory.
#
#  5. if IMAGE is not set, the script defaults to "dar-backup:dev".
#     You can see available images on Docker Hub here:
#     https://hub.docker.com/r/per2jensen/dar-backup/tags 
#
#     If RUN_AS_UID is not set, it defaults to the current user's UID.
#        - running the script as root is not allowed, the script will exit with an error.
#
#  6. You can configure the directory layout by setting the following environment variables:
#     - DAR_BACKUP_DIR: Directory for backups (default: WORKDIR/backups)
#     - DAR_BACKUP_DATA_DIR: Directory for data to backup (default: WORKDIR/data) 
#     - DAR_BACKUP_D_DIR: Directory for backup definitions (default: WORKDIR/backup.d)
#     - DAR_BACKUP_RESTORE_DIR: Directory for restored files (default: WORKDIR/restore)
#
#  Usage:
#  WORKDIR=/path/to/your/workdir IMAGE=<image> ./run-backup.sh -t FULL|DIFF|INCR 
#
set -euo pipefail

# === Config ===
IMAGE="${IMAGE:-dar-backup:dev}"

# Allow override of working directory for testing (e.g. from Makefile)
WORKDIR="${WORKDIR:-}"
if [[ -z "$WORKDIR" ]]; then
  # Use the directory of the script itself as fallback
  WORKDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fi


export RUN_AS_UID="${RUN_AS_UID:-$(id -u)}"
export RUN_AS_GID="${RUN_AS_GID:-$(id -g)}"

# === Drop privileges if running as root ===
if [ "$RUN_AS_UID" -eq 0 ]; then
  echo "❌ running as root not allowed, exciting."
  exit 1
fi


# Configure directory layout here
BASE_DIR="$WORKDIR"

export DAR_BACKUP_DIR="${DAR_BACKUP_DIR:-$BASE_DIR/backups}"
export DAR_BACKUP_D_DIR="${DAR_BACKUP_D_DIR:-$BASE_DIR/backup.d}"
export DAR_BACKUP_DATA_DIR="${DAR_BACKUP_DATA_DIR:-$BASE_DIR/data}"
export DAR_BACKUP_RESTORE_DIR="${DAR_BACKUP_RESTORE_DIR:-$BASE_DIR/restore}"


# === Parse args ===
BACKUP_TYPE=""

usage() {
  echo "Usage: $0 -t FULL|DIFF|INCR"
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -t|--type)
      BACKUP_TYPE="${2:-}"
      shift 2
      ;;
    -*)
      echo "Unknown option: $1"
      usage
      ;;
    *)
      break
      ;;
  esac
done

# === Validate type ===
if [[ -z "$BACKUP_TYPE" ]]; then
  echo "❌ Missing required option: -t FULL|DIFF|INCR"
  usage
fi

# Convert to lowercase and validate
BACKUP_TYPE_LC=$(echo "$BACKUP_TYPE" | tr '[:upper:]' '[:lower:]')

case "$BACKUP_TYPE_LC" in
  full)
    BACKUP_FLAG="--full-backup"
    ;;
  diff)
    BACKUP_FLAG="--differential-backup"
    ;;
  incr|incremental)
    BACKUP_FLAG="--incremental-backup"
    ;;
  *)
    echo "❌ Invalid backup type: $BACKUP_TYPE"
    usage
    ;;
esac


echo "Using image: $IMAGE"
echo "Base directory:                  ${BASE_DIR}/"
echo "Backup type:                     ${BACKUP_TYPE}"
echo "DAR backup directory:            $DAR_BACKUP_DIR"
echo "DAR backup definition directory: $DAR_BACKUP_D_DIR"
echo "DAR backup data directory:       $DAR_BACKUP_DATA_DIR"
echo "DAR backup restore directory:    $DAR_BACKUP_RESTORE_DIR"


# === Setup required directories ===
mkdir -p "$DAR_BACKUP_DIR" "$DAR_BACKUP_D_DIR" "$DAR_BACKUP_DATA_DIR" "$DAR_BACKUP_RESTORE_DIR"

# === Sample backup definition file ===
cat <<EOF > "$DAR_BACKUP_D_DIR/default"
# Basic ordered selection
-am

# Root of backup
-R /data

# Compression level
-z5

# No overwrite
-n

# Slice size
--slice 7G

--cache-directory-tagging
EOF

# === Run container ===
echo "Running dar-backup test with type: $BACKUP_TYPE_LC"
echo



docker run --rm \
  --user "$RUN_AS_UID:$RUN_AS_GID" \
  -e RUN_AS_UID="$RUN_AS_UID" \
  -v "$DAR_BACKUP_DIR":/backups \
  -v "$DAR_BACKUP_D_DIR":/backup.d \
  -v "$DAR_BACKUP_DATA_DIR":/data \
  -v "$DAR_BACKUP_RESTORE_DIR":/restore \
  "$IMAGE" \
  "$BACKUP_FLAG" --log-stdout --verbose
