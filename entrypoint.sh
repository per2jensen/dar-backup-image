#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later

set -e

# === Defaults ===
DEFAULT_UID=1000
LOG_FILE="/tmp/dar_backup_completer.log"
CONFIG_PATH="${DAR_BACKUP_CONFIG:-/etc/dar-backup/dar-backup.conf}"
export RUN_AS_UID="${RUN_AS_UID:-$DEFAULT_UID}"

# === Determine effective UID ===
if [ "$(id -u)" -ne 0 ]; then
  RUN_AS_UID="$(id -u)"
fi

# === Ensure configuration file exists ===
if [[ ! -f "$CONFIG_PATH" ]]; then
  echo "❌ Configuration file not found: $CONFIG_PATH" >&2
  exit 1
fi

# === Ensure required directories exist ===
for dir in "$DAR_BACKUP_DIR" "$DAR_BACKUP_D_DIR" "$DAR_BACKUP_DATA_DIR" "$DAR_BACKUP_RESTORE_DIR"; do
  [ -z "$dir" ] && echo "❌ Required env var not set" && exit 1
  mkdir -p "$dir" || { echo "❌ Failed to create $dir"; exit 1; }
done

# === Fix ownership and permissions if root ===
if [ "$(id -u)" -eq 0 ]; then
  chmod -R 0770 "$DAR_BACKUP_DIR" "$DAR_BACKUP_D_DIR" "$DAR_BACKUP_DATA_DIR" "$DAR_BACKUP_RESTORE_DIR" || {
    echo "❌ Failed to chmod directories"
    exit 1
  }

  chown -R "$RUN_AS_UID:$RUN_AS_UID" "$DAR_BACKUP_DIR" "$DAR_BACKUP_D_DIR" "$DAR_BACKUP_DATA_DIR" "$DAR_BACKUP_RESTORE_DIR" || {
    echo "❌ Failed to chown directories"
    exit 1
  }

  touch "$LOG_FILE"
  chown "$RUN_AS_UID:$RUN_AS_UID" "$LOG_FILE" || true
  chmod 644 "$LOG_FILE"
else
  touch "$LOG_FILE" 2>/dev/null || true
  chmod 644 "$LOG_FILE" 2>/dev/null || true
fi

# === Build argument list ===
ARGS=()
if [[ ! " $* " =~ " --config " ]]; then
  ARGS+=(--config "$CONFIG_PATH")
fi
ARGS+=("$@")

# Set HOME defensively to avoid /root/.darrc access when running as non-root
export HOME="/tmp"

# Run as specified user using setpriv (no shell re-parsing)
if [ "$(id -u)" -eq 0 ]; then
  # Pre-run manager directly
  setpriv --reuid="$RUN_AS_UID" --regid="$RUN_AS_UID"  --clear-groups  --no-new-privs \
    manager --create-db --config "$CONFIG_PATH"

  # Then exec dar-backup directly with preserved arguments
  exec setpriv --reuid="$RUN_AS_UID" --regid="$RUN_AS_UID"  --clear-groups  --no-new-privs \
    dar-backup "${ARGS[@]}"
else
  manager --create-db --config "$CONFIG_PATH"
  exec dar-backup "${ARGS[@]}"
fi

