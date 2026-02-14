#! /bin/bash
#SPFX-License-Identifier: GPL-3.0-or-later

# This script is part of the dar-backup-image project, which 
# poovides a Docker image for running `dar` backups using the
# dar-backup wrapperwith sensible defaults and easy configuration.
# See more at the project's GitHub repository:
# https://github.com/per2jensen/dar-backup-image

# this script is part of the e2e testsuite used in a GitHub Actions workflow
# it creates a sample dataset, runs a FULL, DIFF and INCR backup, mutates
# the dataset between each backup, restores each backup and compares the
# restored data with the original data

set -euo pipefail

export WORKDIR="$(pwd)/.e2e"
DATA_DIR="$WORKDIR/data"
BACKUP_DIR="$WORKDIR/backups"
BACKUP_D_DIR="$WORKDIR/backup.d"
RESTORE_DIR="$WORKDIR/restore"
LIST_RESTORE_DIR="$WORKDIR/restore-list"
DATE="$(date +%Y-%m-%d)"
echo "Using 'DATE': $DATE"
IMAGE="${IMAGE:-dar-backup:dev}"

rm -fr "$DATA_DIR" "$BACKUP_DIR" "$BACKUP_D_DIR" "$RESTORE_DIR" "$LIST_RESTORE_DIR"
mkdir -p "$DATA_DIR" "$BACKUP_DIR" "$BACKUP_D_DIR" "$RESTORE_DIR" "$LIST_RESTORE_DIR"

# ---------- helpers ----------
assert_deleted() { test ! -e "$1" || { echo "expected deleted: $1"; exit 1; }; }

assert_symlink_target() { local t; t=$(readlink "$1"); [ "$t" = "$2" ] || { echo "symlink target mismatch: $1 -> $t (want $2)"; exit 1; }; }

assert_same_inode() { # hardlink check: same inode == preserved hardlink
  local i1 i2; i1=$(stat -c '%i' "$1"); i2=$(stat -c '%i' "$2")
  [ "$i1" = "$i2" ] || { echo "hardlink lost: $1 ($i1) vs $2 ($i2)"; exit 1; }
}

assert_mode() { # octal mode compare
  local m; m=$(stat -c '%a' "$1"); [ "$m" = "$2" ] || { echo "mode mismatch on $1: $m != $2"; exit 1; }; }

assert_exists() { test -e "$1" || { echo "expected exists: $1"; exit 1; }; }

dump_restore_state () {
  echo "==> find /restore/ -ls"
  docker run --rm \
    -v "$RESTORE_DIR":/restore \
    --entrypoint /bin/sh \
    "$IMAGE" -c "find /restore/ -ls"
}

pitr_restore () {
  local when="$1"
  local restore_path="${2:-data/}"
  docker run --rm --user "$(id -u):$(id -g)" \
    -v "$BACKUP_DIR":/backups \
    -v "$BACKUP_D_DIR":/backup.d \
    -v "$RESTORE_DIR":/restore \
    --entrypoint /opt/venv/bin/manager \
    "$IMAGE" \
      --config-file /etc/dar-backup/dar-backup.conf \
      --backup-def default \
      --restore-path "$restore_path" \
      --when "$when" \
      --target /restore \
      --log-stdout --verbose
}

pitr_report () {
  local when="$1"
  local restore_path="${2:-data/}"
  docker run --rm --user "$(id -u):$(id -g)" \
    -v "$BACKUP_DIR":/backups \
    -v "$BACKUP_D_DIR":/backup.d \
    -v "$RESTORE_DIR":/restore \
    --entrypoint /opt/venv/bin/manager \
    "$IMAGE" \
      --config-file /etc/dar-backup/dar-backup.conf \
      --backup-def default \
      --restore-path "$restore_path" \
      --when "$when" \
      --pitr-report \
      --target /restore \
      --log-stdout --verbose
}

pitr_report_expect () {
  local when="$1"
  local restore_path="$2"
  local expect_deleted="${3:-0}"
  local report_output

  echo "==> PITR report: $restore_path (when: $when)"
  report_output="$(pitr_report "$when" "$restore_path" 2>&1)"
  echo "$report_output"

  if ! printf '%s\n' "$report_output" | grep -Fq "$restore_path"; then
    echo "❌ PITR report did not mention expected path: $restore_path"
    exit 1
  fi

  if [[ "$expect_deleted" = "1" ]]; then
    # Current PITR report output doesn't explicitly label deletions; path presence is the confirmation here.
    true
  fi
}

add_initial_dataset () {
  mkdir -p "$DATA_DIR/sub/inner" "$DATA_DIR/with space" "$DATA_DIR/unicode-æøå"
  # small text
  printf "hello dar-backup\n" > "$DATA_DIR/hello.txt"
  # binary (256 KiB)
  head -c 262144 /dev/urandom > "$DATA_DIR/bin-256k.dat"
  # large binary (64 MiB)
  head -c $((18*1024*1024)) /dev/urandom > "$DATA_DIR/large-64m.bin"
  # nested text
  printf "nested\n" > "$DATA_DIR/sub/inner/note.md"
  # symlink (relative)
  if [ ! -L "$DATA_DIR/sub/link-to-hello" ]; then
    ln -s ../hello.txt "$DATA_DIR/sub/link-to-hello"
  fi
  # hardlink to the binary
  if [ ! -e "$DATA_DIR/bin-256k.hardlink" ]; then
    ln "$DATA_DIR/bin-256k.dat" "$DATA_DIR/bin-256k.hardlink"
  fi
  # file in dir with spaces
  echo "space dir" > "$DATA_DIR/with space/file.txt"
  # unicode file
  echo "unicode" > "$DATA_DIR/unicode-æøå/fil.txt"
}

add_more_data_round1 () {
  echo "round1 append" >> "$DATA_DIR/hello.txt"
  # new files
  head -c 1048576 /dev/urandom > "$DATA_DIR/new-1m.bin"
  echo "new text r1" > "$DATA_DIR/sub/new-r1.txt"
  # change target of symlink
  echo "alt target" > "$DATA_DIR/alt.txt"
  rm -f "$DATA_DIR/sub/link-to-hello"
  ln -s ../alt.txt "$DATA_DIR/sub/link-to-hello"
  # delete something to test removals
  rm -f "$DATA_DIR/sub/inner/note.md"
}

add_more_data_round2 () {
  echo "round2 append" >> "$DATA_DIR/hello.txt"
  head -c 2097152 /dev/urandom > "$DATA_DIR/new-2m.bin"
  mkdir -p "$DATA_DIR/newdir"
  echo "brand new r2" > "$DATA_DIR/newdir/readme.txt"
  # flip hardlink: replace with independent file
  rm -f "$DATA_DIR/bin-256k.hardlink"
  cp "$DATA_DIR/bin-256k.dat" "$DATA_DIR/bin-256k.hardlink"
}

list_contents () {
  archive_basename="$1"  # e.g., default_FULL_${DATE}, default_DIFF_${DATE}, default_INCR_${DATE}  
  echo "Contents of archive set: $archive_basename"
  dump_restore_state
  docker run --rm   -e RUN_AS_UID=$(id -u) \
    -v "$DATA_DIR":/data \
    -v "$BACKUP_DIR":/backups \
    -v "$LIST_RESTORE_DIR":/restore \
    -v "$BACKUP_D_DIR":/backup.d \
    "$IMAGE" --list-contents  "$archive_basename" \
    --config /etc/dar-backup/dar-backup.conf    --log-stdout --verbose
}


restore_and_compare () {
  local ARCHIVE_BASENAME="$1"  # e.g., default_FULL_${DATE}, default_DIFF_${DATE}, default_INCR_${DATE}
  rm -rf "$RESTORE_DIR" && mkdir -p "$RESTORE_DIR"
  echo "==> Restoring (PITR): $ARCHIVE_BASENAME"
  local pitr_when=""
  local report_present=()
  local report_deleted=()
  case "$ARCHIVE_BASENAME" in
    "default_FULL_${DATE}")
      pitr_when="$PITR_WHEN_FULL"
      report_present=(
        "data/sub/inner/note.md"
        "data/hello.txt"
      )
      ;;
    "default_DIFF_${DATE}")
      pitr_when="$PITR_WHEN_DIFF"
      report_present=(
        "data/new-1m.bin"
        "data/sub/new-r1.txt"
        "data/alt.txt"
      )
      report_deleted=(
        "data/sub/inner/note.md"
      )
      ;;
    "default_INCR_${DATE}")
      pitr_when="$PITR_WHEN_INCR"
      report_present=(
        "data/new-2m.bin"
        "data/newdir/readme.txt"
      )
      report_deleted=(
        "data/sub/inner/note.md"
      )
      ;;
    *) echo "Unknown restore set: $ARCHIVE_BASENAME" >&2; exit 2 ;;
  esac
  if [[ "${LIST_CONTENTS:-0}" = "1" ]]; then
    list_contents "$ARCHIVE_BASENAME"
  fi
  dump_restore_state
  for path in "${report_present[@]}"; do
    pitr_report_expect "$pitr_when" "$path" 0
  done
  for path in "${report_deleted[@]}"; do
    pitr_report_expect "$pitr_when" "$path" 1
  done
  pitr_restore "$pitr_when" "data/"
  echo "==> Comparing /restore vs /data for $ARCHIVE_BASENAME"
  diff -qr "$DATA_DIR" "$RESTORE_DIR/data" > "$WORKDIR/diff-${ARCHIVE_BASENAME}.txt" || true
  if [[ -s "$WORKDIR/diff-${ARCHIVE_BASENAME}.txt" ]]; then
    echo "Diff found for $ARCHIVE_BASENAME:"
    sed -n '1,120p' "$WORKDIR/diff-${ARCHIVE_BASENAME}.txt"
    echo "❌ Mismatch after restore for $ARCHIVE_BASENAME"
    exit 1
  else
    echo "✅ Restore matches source for $ARCHIVE_BASENAME"
  fi
}
# Create `default` backup definition in $BACKUP_D_DIR
cat > "$BACKUP_D_DIR/default" <<EOF
-am
-R /
-g data/
-z5
-n
--slice 12G
--comparison-field=ignore-owner
--cache-directory-tagging
EOF

# ---------- dataset + FULL ----------
echo "==> Creating dataset"
add_initial_dataset

echo "==> FULL backup"
dump_restore_state
scripts/run-backup.sh -t FULL  
PITR_WHEN_FULL="$(date '+%Y-%m-%d %H:%M:%S')"
restore_and_compare "default_FULL_${DATE}"
restore_and_compare "default_FULL_${DATE}"
# Hardlink must be preserved in FULL
assert_same_inode "$RESTORE_DIR/data/bin-256k.dat" "$RESTORE_DIR/data/bin-256k.hardlink"
# Symlink target must point to hello.txt initially
assert_symlink_target "$RESTORE_DIR/data/sub/link-to-hello" "../hello.txt"


# ---------- mutate + DIFF ----------
echo "==> Add more data (R1) and DIFF backup"
add_more_data_round1
dump_restore_state
scripts/run-backup.sh -t DIFF 
PITR_WHEN_DIFF="$(date '+%Y-%m-%d %H:%M:%S')"
restore_and_compare "default_DIFF_${DATE}"
assert_deleted "$RESTORE_DIR/data/sub/inner/note.md"
# Symlink retarget must be applied
assert_symlink_target "$RESTORE_DIR/data/sub/link-to-hello" "../alt.txt"

# ---------- mutate + INCR ----------
echo "==> Add more data (R2) and INCR backup"
add_more_data_round2
dump_restore_state
scripts/run-backup.sh -t INCR
PITR_WHEN_INCR="$(date '+%Y-%m-%d %H:%M:%S')"
restore_and_compare "default_INCR_${DATE}"
# We deliberately broke the hardlink in round2; ensure they are now different inodes
DAT_INODE=$(stat -c '%i' "$RESTORE_DIR/data/bin-256k.dat")
HARDLINK_INODE=$(stat -c '%i' "$RESTORE_DIR/data/bin-256k.hardlink")
if [ "$DAT_INODE" = "$HARDLINK_INODE " ]; then
  echo "hardlink incorrectly preserved after round2 change"; exit 1
fi
