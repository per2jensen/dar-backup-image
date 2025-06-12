#!/bin/bash
set -e

# Default UID fallback
DEFAULT_UID=1000

# Ensure RUN_AS_UID is set properly
if [ "$(id -u)" -eq 0 ]; then
  echo "Running as root — will drop to UID ${RUN_AS_UID:-$DEFAULT_UID}"
  export RUN_AS_UID="${RUN_AS_UID:-$DEFAULT_UID}"
else
  echo "Already running as non-root UID $(id -u)"
fi

# Create and secure required directories
mkdir -p /backups /backup.d /data /restore || { echo "❌ Failed to create required directories"; exit 1; }
chmod -R 0770 /backups /backup.d /data /restore || { echo "❌ Failed to set permissions on directories"; exit 1; }
chown -R "$RUN_AS_UID:$RUN_AS_UID" /backups /backup.d /data /restore || { echo "❌ Failed to set ownership on directories"; exit 1; }

touch /tmp/dar_backup_completer.log
chown "$RUN_AS_UID:$RUN_AS_UID" /tmp/dar_backup_completer.log
chmod 644 /tmp/dar_backup_completer.log


# Validate mount points
[ -d /backups ]  || { echo "❌ Missing /backup mount"; exit 1; }
[ -d /backup.d ] || { echo "❌ Missing /backup.d"; exit 1; }
[ -d /data ]     || { echo "❌ Missing /data mount"; exit 1; }
[ -d /restore ]  || { echo "❌ Missing /restore mount"; exit 1; }


# Ensure /tmp is writable and log file is available
chmod 1777 /tmp
touch /tmp/dar_backup_completer.log
chown "$RUN_AS_UID:$RUN_AS_UID" /tmp/dar_backup_completer.log
chmod 644 /tmp/dar_backup_completer.log

# Drop privileges and run everything from here
echo "Executing as UID $RUN_AS_UID"
exec gosu "$RUN_AS_UID" /bin/bash -c "
  echo 'dar-backup: \$(which dar-backup)'
  echo 'manager:    \$(which manager)'
  echo 'Creating catalog databases if needed...'
  manager --create-db --log-stdout --verbose --config /etc/dar-backup/dar-backup.conf
  echo 'Running dar-backup with args: $*'
  exec dar-backup $*
"