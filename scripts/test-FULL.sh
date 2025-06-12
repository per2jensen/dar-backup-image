#! /bin/bash
set -euo pipefail

# Configuration
export DATA_DIR=/tmp/test-data
export BACKUP_DIR=/tmp/test-backups
export RESTORE_DIR=/tmp/test-restore
export BACKUP_D_DIR=/tmp/test-backup.d
export IMAGE=dar-backup:0.5.0-alpha

# Create required directories
mkdir -p "$DATA_DIR" "$BACKUP_DIR" "$RESTORE_DIR" "$BACKUP_D_DIR"

# Generate test file
echo "Sample file" > "$DATA_DIR"/hello.txt

# Crate a dar-backup `backup definition` (default)
cat <<EOF > "$BACKUP_D_DIR"/default
# Switch to ordered selection mode, which means that the following
# options will be considered top to bottom
-am

# Backup Root dir
# /data is mapped into the container at run time
-R /data

# Directories to backup below the Root dir


# Directories to exclude below the Root dir
# compression level
-z5

# no overwrite, if you rerun a backup, 'dar' halts and asks what to do
-n

# size of each slice in the archive
--slice 7G

# see https://github.com/per2jensen/dar-backup?tab=readme-ov-file#restore-test-exit-code-4
# run as root
#--comparison-field=ignore-owner

# bypass directores marked as cache directories
# http://dar.linux.free.fr/doc/Features.html
--cache-directory-tagging
EOF


# Ensure backup output is clear
echo "Running dar-backup FULL test..."
echo "Using image: $IMAGE"
echo


# Run the container
sudo docker run --rm \
  -e RUN_AS_UID=1000 \
  -v "$DATA_DIR":/data \
  -v "$BACKUP_DIR":/backup \
  -v "$RESTORE_DIR":/restore \
  -v "$BACKUP_D_DIR":/backup.d \
  "$IMAGE" \
  -F --log-stdout --config /etc/dar-backup/dar-backup.conf
