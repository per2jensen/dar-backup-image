#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later

set -euo pipefail

# === Config ===
IMAGE="dar-backup:dev"

# Allow override of working directory for testing (e.g. from Makefile)
WORKDIR="${WORKDIR:-}"
if [[ -z "$WORKDIR" ]]; then
  # Use the directory of the script itself as fallback
  WORKDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fi

BASE_DIR="$WORKDIR"

export RUN_AS_UID=$(id -u)
export DAR_BACKUP_DIR="$BASE_DIR/backups"
export DAR_BACKUP_D_DIR="$BASE_DIR/backup.d"
export DAR_BACKUP_DATA_DIR="$BASE_DIR/data"
export DAR_BACKUP_RESTORE_DIR="$BASE_DIR/restore"



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
echo "Base directory:                  {$BASE_DIR}/"
echo "Backup type:                     {$BACKUP_TYPE}"
echo "DAR backup directory:            $DAR_BACKUP_DIR"
echo "DAR backup definition directory: $DAR_BACKUP_D_DIR"
echo "DAR backup data directory:       $DAR_BACKUP_DATA_DIR"
echo "DAR backup restore directory:    $DAR_BACKUP_RESTORE_DIR"


# === Setup required directories ===
mkdir -p "$DAR_BACKUP_DIR" "$DAR_BACKUP_D_DIR" "$DAR_BACKUP_DATA_DIR" "$DAR_BACKUP_RESTORE_DIR"

# === Sample data ===
echo "Sample file" > "$DAR_BACKUP_DATA_DIR/hello.txt"

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
  -e RUN_AS_UID="$RUN_AS_UID" \
  -v "$DAR_BACKUP_DIR":/backups \
  -v "$DAR_BACKUP_D_DIR":/backup.d \
  -v "$DAR_BACKUP_DATA_DIR":/data \
  -v "$DAR_BACKUP_RESTORE_DIR":/restore \
  "$IMAGE" \
  "$BACKUP_FLAG" --log-stdout
