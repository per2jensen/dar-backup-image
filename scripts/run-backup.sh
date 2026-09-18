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
#      | $WORKDIR/data                    | /data:ro         | Source data to back up           |
#      | $WORKDIR/restore                 | /restore         | Destination for restore verification |
#
#    - Source data is mounted read-only. /backup.d remains writable because
#      the current dar-backup preflight requires write access there.
#    - WORKDIR *must* be set, otherwise the script exits with an error.
#
#    - Override any of these via:
#        DAR_BACKUP_DIR, DAR_BACKUP_D_DIR, DAR_BACKUP_DATA_DIR, DAR_BACKUP_RESTORE_DIR
#    - FUSE-backed host paths are not covered by the integration tests and may
#      be inaccessible to the Docker daemon. The daemon prepares bind mounts
#      before the container's RUN_AS_UID and RUN_AS_GID take effect.
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
#    - To force a rerun, use dar-backup's cleanup command so slices, PAR2 data,
#      and catalogue state remain consistent.
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

for required_command in docker jq; do
  if ! command -v "$required_command" &>/dev/null; then
    echo "ERROR: required command not found in PATH: $required_command" >&2
    exit 127
  fi
done

# === Config ===
IMAGE="${IMAGE:-per2jensen/dar-backup:latest}"
DOCKER_PULL="${DOCKER_PULL:-false}"

if [[ -z "$IMAGE" || "$IMAGE" =~ [[:space:]] ]]; then
  echo "ERROR: IMAGE must be a non-empty image reference without whitespace" >&2
  exit 1
fi

case "$DOCKER_PULL" in
  true|false) ;;
  *)
    echo "ERROR: DOCKER_PULL must be 'true' or 'false', got: $DOCKER_PULL" >&2
    exit 1
    ;;
esac

WORKDIR="${WORKDIR:-}"
if [[ -z "$WORKDIR" ]]; then
  echo "ERROR: WORKDIR is not set, exiting." >&2
  exit 1
fi
if [[ "$WORKDIR" != /* || "$WORKDIR" == "/" ]]; then
  echo "ERROR: WORKDIR must be an absolute path other than /, got: '$WORKDIR'" >&2
  exit 1
fi


RUN_AS_UID="${RUN_AS_UID:-$(id -u)}"
RUN_AS_GID="${RUN_AS_GID:-$(id -g)}"

if [[ ! "$RUN_AS_UID" =~ ^[1-9][0-9]*$ ]]; then
  echo "ERROR: RUN_AS_UID must be a positive canonical integer; root is not allowed, got: '$RUN_AS_UID'" >&2
  exit 1
fi
if [[ ! "$RUN_AS_GID" =~ ^(0|[1-9][0-9]*)$ ]]; then
  echo "ERROR: RUN_AS_GID must be a canonical non-negative integer, got: '$RUN_AS_GID'" >&2
  exit 1
fi
if (( 10#$RUN_AS_UID > 4294967294 || 10#$RUN_AS_GID > 4294967294 )); then
  echo "ERROR: RUN_AS_UID or RUN_AS_GID is outside the supported Linux ID range" >&2
  exit 1
fi

BASE_DIR="$WORKDIR"

DAR_BACKUP_DIR="${DAR_BACKUP_DIR:-$BASE_DIR/backups}"
DAR_BACKUP_D_DIR="${DAR_BACKUP_D_DIR:-$BASE_DIR/backup.d}"
DAR_BACKUP_DATA_DIR="${DAR_BACKUP_DATA_DIR:-$BASE_DIR/data}"
DAR_BACKUP_RESTORE_DIR="${DAR_BACKUP_RESTORE_DIR:-$BASE_DIR/restore}"

for d in "$DAR_BACKUP_DIR" "$DAR_BACKUP_D_DIR" "$DAR_BACKUP_DATA_DIR" "$DAR_BACKUP_RESTORE_DIR"; do
  if [[ "$d" != /* || "$d" == "/" ]]; then
    echo "ERROR: backup paths must be absolute and must not be /: '$d'" >&2
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

if [[ $# -gt 0 ]]; then
  echo "ERROR: unexpected argument after --: $1" >&2
  usage
fi


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

# Pull before inspecting so DOCKER_PULL=true also supports a first run where
# the selected image is not present in the local Docker image store.
if [[ "$DOCKER_PULL" == "true" ]]; then
  if ! docker pull "$IMAGE"; then
    echo "ERROR: unable to pull requested image: $IMAGE" >&2
    exit 1
  fi
fi

echo "Using image: $IMAGE"
if ! IMAGE_INFO=$(docker inspect "$IMAGE"); then
  echo "ERROR: unable to inspect requested image: $IMAGE" >&2
  exit 1
fi
if ! REPO_DIGEST=$(jq -er '.[0].RepoDigests[0] // empty | split("@")[1]' \
    <<< "$IMAGE_INFO" 2>/dev/null); then
  REPO_DIGEST=""
fi
if [[ -n "$REPO_DIGEST" ]]; then
  echo "Image Digest: $REPO_DIGEST"
else
  if ! IMAGE_ID=$(jq -er '.[0].Id | select(type == "string" and length > 0)' \
      <<< "$IMAGE_INFO"); then
    echo "ERROR: Docker inspect returned no image ID for: $IMAGE" >&2
    exit 1
  fi
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

if ! mkdir -p \
    "$DAR_BACKUP_DIR" \
    "$DAR_BACKUP_D_DIR" \
    "$DAR_BACKUP_DATA_DIR" \
    "$DAR_BACKUP_RESTORE_DIR"; then
  echo "ERROR: unable to create one or more backup directories under $BASE_DIR" >&2
  exit 1
fi

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

if docker run --rm \
    --user "$RUN_AS_UID:$RUN_AS_GID" \
    -e RUN_AS_UID="$RUN_AS_UID" \
    -e RUN_AS_GID="$RUN_AS_GID" \
    -v "$DAR_BACKUP_DIR":/backups \
    -v "$DAR_BACKUP_D_DIR":/backup.d \
    -v "$DAR_BACKUP_DATA_DIR":/data:ro \
    -v "$DAR_BACKUP_RESTORE_DIR":/restore \
    "$IMAGE" \
    "${DOCKER_ARGS[@]}"; then
  echo "✅ dar-backup ${BACKUP_TYPE_LC} operation completed successfully"
else
  operation_status=$?
  echo "ERROR: dar-backup ${BACKUP_TYPE_LC} operation failed with exit status ${operation_status}" >&2
  exit "$operation_status"
fi
