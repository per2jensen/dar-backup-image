#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later

set -e

# Ensure dar-backup virtualenv is active
export PATH="/opt/venv/bin:$PATH"

# === Defaults ===
DEFAULT_UID=1000                # UID for daruser (default container user)
LOG_FILE="/tmp/dar_backup_completer.log"
CONFIG_PATH="${DAR_BACKUP_CONFIG:-/etc/dar-backup/dar-backup.conf}"
export RUN_AS_UID="${RUN_AS_UID:-$DEFAULT_UID}"

CURRENT_UID=$(id -u)
CURRENT_GID=$(id -g)

# If container is run with --user <UID>, respect that user instead of daruser
if [ "$CURRENT_UID" -ne 0 ] && [ "$CURRENT_UID" -ne "$DEFAULT_UID" ]; then
  RUN_AS_UID="$CURRENT_UID"
fi

# Ensure configuration file exists
if [[ ! -f "$CONFIG_PATH" ]]; then
  echo "❌ Missing configuration file: $CONFIG_PATH" >&2
  exit 1
fi

# Ensure required directories exist
for dir in "$DAR_BACKUP_DIR" "$DAR_BACKUP_D_DIR" "$DAR_BACKUP_DATA_DIR" "$DAR_BACKUP_RESTORE_DIR"; do
  [ -z "$dir" ] && echo "❌ Required env var for directory not set" && exit 1
  mkdir -p "$dir" || { echo "❌ Failed to create $dir"; exit 1; }
done

# Only fix ownership if explicitly requested and running as root
if [ "$CURRENT_UID" -eq 0 ] && [ "${DAR_BACKUP_FIX_PERMS:-0}" -eq 1 ]; then
  echo "🔧 Fixing directory permissions for UID $RUN_AS_UID"
  chown -R "$RUN_AS_UID:$RUN_AS_UID" \
    "$DAR_BACKUP_DIR" "$DAR_BACKUP_D_DIR" "$DAR_BACKUP_DATA_DIR" "$DAR_BACKUP_RESTORE_DIR" || true
fi

# Log file handling
if [ "$CURRENT_UID" -eq 0 ]; then
  touch "$LOG_FILE"
  chown "$RUN_AS_UID:$RUN_AS_UID" "$LOG_FILE" || true
  chmod 644 "$LOG_FILE"
else
  touch "$LOG_FILE" 2>/dev/null || true
  chmod 644 "$LOG_FILE" 2>/dev/null || true
fi

# Build arguments for dar-backup
ARGS=()
if [[ ! " $* " =~ " --config " ]]; then
  ARGS+=(--config "$CONFIG_PATH")
fi
ARGS+=("$@")

export HOME="/tmp"

# === Execution ===
if [ "$CURRENT_UID" -eq 0 ]; then
  # Initialize database as target UID (safe privilege drop)
  setpriv --reuid="$RUN_AS_UID" --regid="$RUN_AS_UID" \
    --clear-groups --no-new-privs \
    manager --create-db --config "$CONFIG_PATH"

  # Run dar-backup as target UID
  exec setpriv --reuid="$RUN_AS_UID" --regid="$RUN_AS_UID" \
    --clear-groups --no-new-privs \
    dar-backup "${ARGS[@]}"
else
  # Non-root case: still initialize manager as current user
  manager --create-db --config "$CONFIG_PATH"
  exec dar-backup "${ARGS[@]}"
fi
