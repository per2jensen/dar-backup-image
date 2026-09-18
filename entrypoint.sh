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

# Ensure dar-backup virtualenv is active
export PATH="/opt/venv/bin:$PATH"

# Documentation and image metadata must remain available without backup
# configuration, writable volumes, root privileges, or network access.
case "${1:-}" in
  docs)
    shift
    exec dar-backup-image-docs "$@"
    ;;
  info)
    shift
    exec dar-backup-image-info "$@"
    ;;
esac

# A bare image invocation is a discovery operation, not an incomplete backup.
if [[ "$#" -eq 0 ]]; then
  exec dar-backup-image-docs --list
fi

# === Defaults ===
DEFAULT_UID=1000                # UID for daruser (default container user)
LOG_FILE="/tmp/dar_backup_completer.log"
CONFIG_PATH="${DAR_BACKUP_CONFIG:-/etc/dar-backup/dar-backup.conf}"
export RUN_AS_UID="${RUN_AS_UID:-$DEFAULT_UID}"
export RUN_AS_GID="${RUN_AS_GID:-$RUN_AS_UID}"   # default GID matches UID; override if they differ

CURRENT_UID=$(id -u)
CURRENT_GID=$(id -g)

# If container is run with --user <UID>, respect that user instead of daruser
if [ "$CURRENT_UID" -ne 0 ] && [ "$CURRENT_UID" -ne "$DEFAULT_UID" ]; then
  RUN_AS_UID="$CURRENT_UID"
  RUN_AS_GID="$CURRENT_GID"
fi

if [[ ! "$RUN_AS_UID" =~ ^(0|[1-9][0-9]*)$ ]]; then
  echo "ERROR: RUN_AS_UID must be a canonical non-negative integer, got '$RUN_AS_UID'" >&2
  exit 2
fi
if [[ ! "$RUN_AS_GID" =~ ^(0|[1-9][0-9]*)$ ]]; then
  echo "ERROR: RUN_AS_GID must be a canonical non-negative integer, got '$RUN_AS_GID'" >&2
  exit 2
fi
if (( 10#$RUN_AS_UID > 4294967294 )); then
  echo "ERROR: RUN_AS_UID is outside the supported Linux UID range: '$RUN_AS_UID'" >&2
  exit 2
fi
if (( 10#$RUN_AS_GID > 4294967294 )); then
  echo "ERROR: RUN_AS_GID is outside the supported Linux GID range: '$RUN_AS_GID'" >&2
  exit 2
fi

DAR_BACKUP_FIX_PERMS="${DAR_BACKUP_FIX_PERMS:-0}"
if [[ "$DAR_BACKUP_FIX_PERMS" != "0" && "$DAR_BACKUP_FIX_PERMS" != "1" ]]; then
  echo "ERROR: DAR_BACKUP_FIX_PERMS must be '0' or '1', got '$DAR_BACKUP_FIX_PERMS'" >&2
  exit 2
fi

# Ensure configuration file exists
if [[ ! -f "$CONFIG_PATH" ]]; then
  echo "❌ Missing configuration file: $CONFIG_PATH" >&2
  exit 1
fi

# Ensure required directories exist
for directory_variable in \
  DAR_BACKUP_DIR DAR_BACKUP_D_DIR DAR_BACKUP_DATA_DIR DAR_BACKUP_RESTORE_DIR; do
  dir="${!directory_variable:-}"
  if [ -z "$dir" ]; then
    echo "ERROR: required directory variable is empty: $directory_variable" >&2
    exit 1
  fi
  mkdir -p "$dir" \
    || { echo "ERROR: failed to create required directory from $directory_variable: $dir" >&2; exit 1; }
done

# Only fix ownership if explicitly requested and running as root
if [ "$CURRENT_UID" -eq 0 ] && [ "$DAR_BACKUP_FIX_PERMS" -eq 1 ]; then
  echo "🔧 Fixing directory permissions for UID $RUN_AS_UID / GID $RUN_AS_GID"
  for dir in "$DAR_BACKUP_DIR" "$DAR_BACKUP_D_DIR" "$DAR_BACKUP_DATA_DIR" "$DAR_BACKUP_RESTORE_DIR"; do
    if ! chown -R "$RUN_AS_UID:$RUN_AS_GID" "$dir"; then
      echo "ERROR: unable to set ownership of '$dir' to UID $RUN_AS_UID / GID $RUN_AS_GID" >&2
      exit 1
    fi
  done
  echo "✅ Directory permissions prepared for UID $RUN_AS_UID / GID $RUN_AS_GID"
fi

# Log file handling
if [ "$CURRENT_UID" -eq 0 ]; then
  if ! touch "$LOG_FILE"; then
    echo "WARNING: optional completion log could not be created: $LOG_FILE" >&2
  elif ! chmod 644 "$LOG_FILE"; then
    echo "WARNING: optional completion log permissions could not be set: $LOG_FILE" >&2
  fi
  if ! chown "$RUN_AS_UID:$RUN_AS_GID" "$LOG_FILE"; then
    echo "WARNING: optional completion log ownership could not be changed: $LOG_FILE" >&2
  fi
else
  if ! touch "$LOG_FILE" 2>/dev/null || ! chmod 644 "$LOG_FILE" 2>/dev/null; then
    echo "WARNING: optional completion log is unavailable: $LOG_FILE" >&2
  fi
fi

# Build arguments for dar-backup
# Note: --config detection uses prefix-space matching, so --config=value (equals-form)
# is not supported here; always pass --config as a separate argument.
ARGS=()
if [[ ! " $* " =~ " --config " ]]; then
  ARGS+=(--config "$CONFIG_PATH")
fi
ARGS+=("$@")

export HOME="/tmp"

# === Execution ===
if [ "$CURRENT_UID" -eq 0 ]; then
  # Initialise the backup database as the target UID.
  # --create-db is idempotent: it creates the DB if absent, and verifies
  # integrity (detecting corruption) if it already exists — safe to run
  # on every invocation.
  setpriv --reuid="$RUN_AS_UID" --regid="$RUN_AS_GID" \
    --clear-groups --no-new-privs \
    manager --create-db --config "$CONFIG_PATH"

  # Run dar-backup as target UID
  exec setpriv --reuid="$RUN_AS_UID" --regid="$RUN_AS_GID" \
    --clear-groups --no-new-privs \
    dar-backup "${ARGS[@]}"
else
  # Non-root case: initialise/verify DB as the current user, then run.
  # --create-db is idempotent: creates if absent, checks integrity if present.
  manager --create-db --config "$CONFIG_PATH"
  exec dar-backup "${ARGS[@]}"
fi
