#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later

set -e

# === Default UID fallback ===
DEFAULT_UID=1000

# === Drop privileges if running as root ===
if [ "$(id -u)" -eq 0 ]; then
  echo "Running as root — will drop to UID ${RUN_AS_UID:-$DEFAULT_UID}"
  export RUN_AS_UID="${RUN_AS_UID:-$DEFAULT_UID}"
else
  echo "Already running as non-root UID $(id -u)"
fi

# === Resolve config path from ENV or fallback ===
DEFAULT_CONFIG="/etc/dar-backup/dar-backup.conf"
CONFIG_PATH="${DAR_BACKUP_CONFIG:-$DEFAULT_CONFIG}"

# === Validate config file ===
if [[ ! -f "$CONFIG_PATH" ]]; then
  echo "ERROR: Configuration file not found at '$CONFIG_PATH'" >&2
  exit 1
fi

# === Create and secure required directories ===
mkdir -p "$DAR_BACKUP_DIR" "$DAR_BACKUP_D_DIR" "$DAR_BACKUP_DATA_DIR" "$DAR_BACKUP_RESTORE_DIR" || {
  echo "❌ Failed to create required directories"
  exit 1
}

chmod -R 0770 "$DAR_BACKUP_DIR" "$DAR_BACKUP_D_DIR" "$DAR_BACKUP_DATA_DIR" "$DAR_BACKUP_RESTORE_DIR" || {
  echo "❌ Failed to set permissions on directories"
  exit 1
}

chown -R "$RUN_AS_UID:$RUN_AS_UID" "$DAR_BACKUP_DIR" "$DAR_BACKUP_D_DIR" "$DAR_BACKUP_DATA_DIR" "$DAR_BACKUP_RESTORE_DIR" || {
  echo "❌ Failed to set ownership on directories"
  exit 1
}

# === Setup log file ===
LOG_FILE="/tmp/dar_backup_completer.log"
touch "$LOG_FILE"
chown "$RUN_AS_UID:$RUN_AS_UID" "$LOG_FILE"
chmod 644 "$LOG_FILE"

# === Validate required mount points ===
[ -d "$DAR_BACKUP_DIR" ]        || { echo "❌ Missing mount: $DAR_BACKUP_DIR"; exit 1; }
[ -d "$DAR_BACKUP_D_DIR" ]      || { echo "❌ Missing mount: $DAR_BACKUP_D_DIR"; exit 1; }
[ -d "$DAR_BACKUP_DATA_DIR" ]   || { echo "❌ Missing mount: $DAR_BACKUP_DATA_DIR"; exit 1; }
[ -d "$DAR_BACKUP_RESTORE_DIR" ]|| { echo "❌ Missing mount: $DAR_BACKUP_RESTORE_DIR"; exit 1; }

# === Ensure /tmp is usable ===
chmod 1777 /tmp
touch "$LOG_FILE"
chown "$RUN_AS_UID:$RUN_AS_UID" "$LOG_FILE"
chmod 644 "$LOG_FILE"


# === Ensure config file exists ===
if [[ ! -f "$CONFIG_PATH" ]]; then
  echo "ERROR: Configuration file not found at '$CONFIG_PATH'" >&2
  exit 1
fi

# === Build arg list ===
ARGS=()

# Only append --config if user didn't explicitly give one
if [[ ! " $* " =~ " --config " ]]; then
  ARGS+=(--config "$CONFIG_PATH")
fi

ARGS+=("$@")

echo "Executing as UID $RUN_AS_UID"
exec gosu "$RUN_AS_UID" /bin/bash -s <<EOF
  echo "dar-backup: \$(which dar-backup)"
  echo "manager:    \$(which manager)"
  echo "Creating catalog databases if needed..."
  manager --create-db --log-stdout --config "$CONFIG_PATH"
  echo "Running dar-backup with args: ${ARGS[*]}"
  exec dar-backup ${ARGS[*]}
EOF

