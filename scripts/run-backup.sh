#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This script is part of the dar-backup-image project, which provides a Docker
# image for running `dar` backups with sensible defaults and easy configuration.
#
# See more at the project's GitHub repository:
#   https://github.com/per2jensen/dar-backup-image
#
# Features and behavior:
# -----------------------
# 1. Uses the baked-in dar-backup.conf and PyPI .darrc (unless overridden).
#
# 2. Mounts host directories for backups, definitions, data, and restore verification
#
#      | Host Directory (default)        | Container Mount  | Purpose                           |
#      |----------------------------------|------------------|-----------------------------------|
#      | $WORKDIR/backups                 | /backups         | DAR archives and log files       |
#      | $WORKDIR/backup.d                | /backup.d        | Backup definition files          |
#      | $WORKDIR/data                    | /data            | Source data to back up           |
#      | $WORKDIR/restore                 | /restore         | Destination for restore verification |
#
#    - WORKDIR *must* be set, otherwise the script exits with an error.
#
#    - Override any of these via:
#        DAR_BACKUP_DIR, DAR_BACKUP_D_DIR, DAR_BACKUP_DATA_DIR, DAR_BACKUP_RESTORE_DIR
#
# 3. UID/GID handling:
#    - Defaults to your current UID/GID via `id -u` and `id -g`.
#    - Passed to Docker with `--user "$RUN_AS_UID:$RUN_AS_GID"` so files aren’t root-owned.
#    - Running as root (UID 0) is blocked; the script exits with an error.
#    - Override for service accounts or group setups:
#         RUN_AS_GID=$(getent group backupgrp | cut -d: -f3)
#         RUN_AS_UID=1050 RUN_AS_GID=1050 ./run-backup.sh -t FULL
#
# 4. Backup definitions:
#    - Stored in $DAR_BACKUP_D_DIR (default: $WORKDIR/backup.d).
#    - Select one with `-d <name>` or `--backup-definition <name>`.
#    - Falls back to `default` (auto-created if missing).
#    - Example:
#         WORKDIR=/mnt/backups ./run-backup.sh -t DIFF -d projects
#
# 5. Daily backup rule:
#    - Only **one FULL, one DIFF, and one INCR per definition per day**.
#    - All three can run on the same day (FULL → DIFF → INCR).
#    - A second run of the same type for the same day will be skipped.
#    - To force a rerun, move or delete the day’s .dar files for that definition.
#
# Quick start examples:
# ----------------------
#   # Full backup into default layout
#   WORKDIR=$HOME/dar-backup ./run-backup.sh -t FULL
#
#   # Differential backup using a custom definition
#   WORKDIR=$HOME/dar-backup ./run-backup.sh -t DIFF -d projects
#
#   # FULL → DIFF → INCR chain (one after another)
#   WORKDIR=$HOME/dar-backup ./run-backup.sh -t FULL
#   WORKDIR=$HOME/dar-backup ./run-backup.sh -t DIFF
#   WORKDIR=$HOME/dar-backup ./run-backup.sh -t INCR
#
# Environment variables:
# -----------------------
#   IMAGE                  Docker image tag (default: per2jensen/dar-backup:latest)
#   WORKDIR                Base directory for all backups
#   RUN_AS_UID             UID for container (default: current user’s UID)
#   RUN_AS_GID             GID for container (default: current user’s GID)
#   DAR_BACKUP_DIR         Override for $WORKDIR/backups
#   DAR_BACKUP_D_DIR       Override for $WORKDIR/backup.d
#   DAR_BACKUP_DATA_DIR    Override for $WORKDIR/data
#   DAR_BACKUP_RESTORE_DIR Override for $WORKDIR/restore
#   DOCKER_PULL            default: `false`. A first run will pull if the image is not present locally.
#                          Set to `true` to pull a newer image before running the backup.
#
# Default directory structure:
# ----------------------------
#   WORKDIR/
#     ├── backups/     # DAR archives and logs
#     ├── backup.d/    # Backup definition files
#     ├── data/        # Source data to back up
#     └── restore/     # Restore verification target
#
#
# Example of specified WORKDIR and DAR_BACKUP_DATA_DIR:
# -----------------------------------------------------
#   export WORKDIR=/tmp/dar-backup-image-demo
#   export DAR_BACKUP_DATA_DIR=$HOME/tmp/some-data-to-backup/
#   run-backup.sh -t FULL
#
#   #Check the command log:
#   cat "$WORKDIR"/backups/dar-backup-commands.log
#   
set -euo pipefail

if ! command -v docker &>/dev/null; then
    echo "❌ docker not found, exiting."
    exit 1
fi

# === Config ===
IMAGE="${IMAGE:-per2jensen/dar-backup:latest}"

WORKDIR="${WORKDIR:-}"
if [[ -z "$WORKDIR" ]]; then
  echo "❌ WORKDIR is not set, exiting."
  exit 1
fi


RUN_AS_UID="${RUN_AS_UID:-$(id -u)}"
RUN_AS_GID="${RUN_AS_GID:-$(id -g)}"

if [[ "$RUN_AS_UID" -eq 0 ]]; then
  echo "❌ running as root not allowed, exiting."
  exit 1
fi

BASE_DIR="$WORKDIR"

DAR_BACKUP_DIR="${DAR_BACKUP_DIR:-$BASE_DIR/backups}"
DAR_BACKUP_D_DIR="${DAR_BACKUP_D_DIR:-$BASE_DIR/backup.d}"
DAR_BACKUP_DATA_DIR="${DAR_BACKUP_DATA_DIR:-$BASE_DIR/data}"
DAR_BACKUP_RESTORE_DIR="${DAR_BACKUP_RESTORE_DIR:-$BASE_DIR/restore}"

for d in "$DAR_BACKUP_DIR" "$DAR_BACKUP_D_DIR" "$DAR_BACKUP_DATA_DIR" "$DAR_BACKUP_RESTORE_DIR"; do
  if [[ "$d" == "/" ]]; then
    echo "❌ Refusing to use / as a directory"
    exit 1
  fi
done

# === Parse args ===
BACKUP_TYPE=""
BACKUP_DEF=""

usage() {
  echo "Usage: $0 -t FULL|DIFF|INCR [-d <backup-definition>]"
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -t|--type)
      [[ -z "${2:-}" || "${2:-}" == -* ]] && { echo "❌ -t requires an argument"; usage; }
      BACKUP_TYPE="$2"
      shift 2
      ;;
    -d|--backup-definition)
      [[ -z "${2:-}" || "${2:-}" == -* ]] && { echo "❌ -d requires an argument"; usage; }
      BACKUP_DEF="$2"
      shift 2
      ;;
    -h|--help)
      usage
      ;;
    --)
      shift
      break
      ;;
    -*)
      echo "❌ Unknown option: $1"
      usage
      ;;
    *)
      echo "❌ Unexpected argument: $1"
      usage
      ;;
  esac
done


if [[ -z "$BACKUP_TYPE" ]]; then
  echo "❌ Missing required option: -t FULL|DIFF|INCR"
  usage
fi

BACKUP_TYPE_LC=$(echo "$BACKUP_TYPE" | tr '[:upper:]' '[:lower:]')

case "$BACKUP_TYPE_LC" in
  full) BACKUP_FLAG="--full-backup" ;;
  diff) BACKUP_FLAG="--differential-backup" ;;
  incr|incremental) BACKUP_FLAG="--incremental-backup" ;;
  *) echo "❌ Invalid backup type: $BACKUP_TYPE" ; usage ;;
esac

echo "Using image: $IMAGE"
IMAGE_INFO=$(docker inspect "$IMAGE")
REPO_DIGEST=$(echo "$IMAGE_INFO" | jq -r '.[0].RepoDigests[0] // empty | split("@")[1]')
if [[ -n "$REPO_DIGEST" ]]; then
  echo "Image Digest: $REPO_DIGEST"
else
  IMAGE_ID=$(echo "$IMAGE_INFO" | jq -r '.[0].Id')
  echo "Image Id:     $IMAGE_ID"
fi
echo "Base directory:                  ${BASE_DIR}/"
echo "Backup type:                     ${BACKUP_TYPE}"
echo "DAR backup directory:            $DAR_BACKUP_DIR"
echo "DAR backup definition directory: $DAR_BACKUP_D_DIR"
echo "DAR backup data directory:       $DAR_BACKUP_DATA_DIR"
echo "DAR backup restore directory:    $DAR_BACKUP_RESTORE_DIR"
if [[ -n "$BACKUP_DEF" ]]; then
  echo "Backup definition file:        $BACKUP_DEF"
else
  echo "Backup definition file:        (default)"
fi

mkdir -p "$DAR_BACKUP_DIR" "$DAR_BACKUP_D_DIR" "$DAR_BACKUP_DATA_DIR" "$DAR_BACKUP_RESTORE_DIR"

if [[ ! -f "$DAR_BACKUP_D_DIR/default" ]]; then
  cat <<EOF > "$DAR_BACKUP_D_DIR/default"
# Basic ordered selection
-am
-R /data
-z5
-n
--slice 7G
--cache-directory-tagging
EOF
fi

echo "Running dar-backup with type: $BACKUP_TYPE_LC"
echo

# Build docker args safely
DOCKER_ARGS=( "$BACKUP_FLAG" "--log-stdout" "--verbose" )
if [[ -n "$BACKUP_DEF" ]]; then
    DOCKER_ARGS+=( "--backup-definition" "$BACKUP_DEF" )
fi

# check environment variable to avoid unwanted pulls, if you have a tried and tested image.
DOCKER_PULL=${DOCKER_PULL:-false}
# only pull if you state so
if [[ "$DOCKER_PULL" == "true" ]]; then
  docker pull "$IMAGE"
fi

docker run --rm \
  --user "$RUN_AS_UID:$RUN_AS_GID" \
  -e RUN_AS_UID="$RUN_AS_UID" \
  -e RUN_AS_GID="$RUN_AS_GID" \
  -v "$DAR_BACKUP_DIR":/backups \
  -v "$DAR_BACKUP_D_DIR":/backup.d \
  -v "$DAR_BACKUP_DATA_DIR":/data \
  -v "$DAR_BACKUP_RESTORE_DIR":/restore \
  "$IMAGE" \
  "${DOCKER_ARGS[@]}"
