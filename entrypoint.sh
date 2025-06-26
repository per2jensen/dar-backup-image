#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later

set -e

DEFAULT_UID=1000
LOG_FILE="/tmp/dar_backup_completer.log"

# === Determine effective UID ===
if [ "$(id -u)" -eq 0 ]; then
  echo "Running as root — will drop to UID ${RUN_AS_UID:-$DEFAULT_UID}"
  export RUN_AS_UID="${RUN_AS_UID:-$DEFAULT_UID}"
else
  echo "Already running as non-root UID $(id -u)"
  export RUN_AS_UID="$(id -u)"
fi

# === Resolve config file ===
DEFAULT_CONFIG="/etc/dar-backup/dar-backup.conf"
CONFIG_PATH="${DAR_BACKUP_CONFIG:-$DEFAULT_CONFIG}"

if [[ ! -f "$CONFIG_PATH" ]]; then
  echo "❌ Configuration file not found: $CONFIG_PATH" >&2
  exit 1
fi

# === Ensure required directories exist ===
for dir in "$DAR_BACKUP_DIR" "$DAR_BACKUP_D_DIR" "$DAR_BACKUP_DATA_DIR" "$DAR_BACKUP_RESTORE_DIR"; do
  [ -z "$dir" ] && echo "❌ Required env var not set" && exit 1
  mkdir -p "$dir" || { echo "❌ Failed to create $dir"; exit 1; }
done

# === Fix permissions and ownership (only if root) ===
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


# Run dar-backup as the specified user, dropping privileges if necessary
if [ "$(id -u)" -eq 0 ]; then
  echo "Running as root — will drop to UID ${RUN_AS_UID:-$DEFAULT_UID}"
  export RUN_AS_UID="${RUN_AS_UID:-$DEFAULT_UID}"
  gosu "$RUN_AS_UID" bash <<EOF
echo "dar-backup: \$(which dar-backup)"
echo "manager:    \$(which manager)"
echo "Creating catalog databases if needed..."
manager --create-db --log-stdout --config "$CONFIG_PATH"
echo "Running dar-backup with args: ${ARGS[*]}"
exec dar-backup ${ARGS[*]}
EOF
else
  echo "Already running as non-root UID $(id -u)"
  echo "dar-backup: $(which dar-backup)"
  echo "manager:    $(which manager)"
  echo "Creating catalog databases if needed..."
  manager --create-db --log-stdout --config "$CONFIG_PATH"
  echo "Running dar-backup with args: ${ARGS[*]}"
  exec dar-backup "${ARGS[@]}"
fi

