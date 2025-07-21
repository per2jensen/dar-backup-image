#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later

set -euo pipefail

export RUN_AS_UID="${RUN_AS_UID:-$(id -u)}"
: "${DAR_BACKUP_DIR:=${TEST_TMP:-/tmp}/backups}"
: "${DAR_BACKUP_D_DIR:=${TEST_TMP:-/tmp}/backup.d}"
: "${DAR_BACKUP_DATA_DIR:=${TEST_TMP:-/tmp}/data}"
: "${DAR_BACKUP_RESTORE_DIR:=${TEST_TMP:-/tmp}/restore}"

SCRIPT="scripts/run-backup.sh"
IMAGE="${IMAGE:-dar-backup:dev}"
TEST_TMP="/tmp/dar-backup-test"
STATEFUL_BASE="/tmp/dar-backup-test-state"
TEST_FILE_NAME="test.txt"

mkdir -p "$STATEFUL_BASE"

# Colors
if [ -t 1 ] && command -v tput &>/dev/null && tput colors &>/dev/null; then
  RED=$(tput setaf 1); GREEN=$(tput setaf 2); RESET=$(tput sgr0)
else
  RED=""; GREEN=""; RESET=""
fi

: "${RUN_AS_UID:?RUN_AS_UID must be set}"

pass() { echo -e "${GREEN}✔ $1${RESET}"; }
fail() { echo -e "${RED}✘ $1${RESET}"; exit 1; }


clean_dirs() {
  # For stateless tests, always wipe *everything* so we start fresh.
  # For stateful tests (chain), CLEAN_ALL=0 lets us skip the wipe.
  if [[ "${CLEAN_ALL:-1}" -eq 1 ]]; then
    rm -rf "$TEST_TMP" "$STATEFUL_BASE"
  fi

  # Recreate the base test dirs (so prepare_dataset can populate them)
  mkdir -p "$TEST_TMP" "$STATEFUL_BASE"
}


print_sha256() {
  local label="$1"; shift
  echo "--- SHA256 hashes for $label ---"
  if [[ -d "$label" ]]; then
    find "$label" -type f -exec sha256sum {} +
  else
    echo "(missing)"
  fi
  echo "----------------------------------------"
}


prepare_dataset() {
    local mode="$1"

    mkdir -p "$DAR_BACKUP_DATA_DIR"

    if [ "$mode" = "stateless" ]; then
        echo "⚠️  Rebuilding dataset (stateless test)"
        rm -rf "$DAR_BACKUP_DATA_DIR"/*
        echo "Hello World, created at $(date)" > "$DAR_BACKUP_DATA_DIR/hello.txt"
        echo "Test file generated at $(date)" > "$DAR_BACKUP_DATA_DIR/test.txt"
        dd if=/dev/urandom of="$DAR_BACKUP_DATA_DIR/verify_test.bin" bs=1M count=2 status=none

    elif [ ! -f "$DAR_BACKUP_DATA_DIR/test.txt" ]; then
        # Bootstrap initial dataset for the first stateful run
        echo "🆕 Bootstrapping stateful dataset"
        echo "Hello World (stateful) at $(date)" > "$DAR_BACKUP_DATA_DIR/hello.txt"
        echo "Test file initialized at $(date)" > "$DAR_BACKUP_DATA_DIR/test.txt"
        dd if=/dev/urandom of="$DAR_BACKUP_DATA_DIR/verify_test.bin" bs=1M count=2 status=none

    else
        # Mutate test.txt to simulate change for DIFF/INCR runs
        echo "ℹ️  Preserving dataset for stateful chain (mutating only test.txt)"
        echo "Stateful change: $(date)" >> "$DAR_BACKUP_DATA_DIR/test.txt"
    fi

    rm -rf "$WORKDIR/originals"
    mkdir -p "$WORKDIR/originals"
    cp -a "$DAR_BACKUP_DATA_DIR"/* "$WORKDIR/originals/"
    echo "Backed up original source files to $WORKDIR/originals"
}



compare_to_originals() {
  echo "--- Comparing current files to originals ---"
  for file in "$WORKDIR/originals"/*; do
    local name=$(basename "$file")
    local orig_hash=$(sha256sum "$file" | awk '{print $1}')
    local cur="$DAR_BACKUP_DATA_DIR/$name"

    if [[ ! -f "$cur" ]]; then
      echo "⚠️ Missing in source: $name"
      continue
    fi

    local cur_hash=$(sha256sum "$cur" | awk '{print $1}')
    if [[ "$orig_hash" != "$cur_hash" ]]; then
      echo "❌ MISMATCH: $name (source:$cur_hash vs backup:$orig_hash)"
    fi
  done
  echo "--------------------------------------------"
}

run_test_case() {
  local name="$1"; shift
  local DATASET_MODE="${DATASET_MODE:-stateless}"  # default to stateless

  clean_dirs
  echo "Running test: $name"

  : "${WORKDIR:=$TEST_TMP/workdir}"
  export WORKDIR
  mkdir -p "$WORKDIR"

  _IMAGE="$IMAGE"; _RUN_AS_UID="$RUN_AS_UID"
  _DAR_BACKUP_DIR="$DAR_BACKUP_DIR"; _DAR_BACKUP_D_DIR="$DAR_BACKUP_D_DIR"
  _DAR_BACKUP_DATA_DIR="$DAR_BACKUP_DATA_DIR"; _DAR_BACKUP_RESTORE_DIR="$DAR_BACKUP_RESTORE_DIR"
  CLEAN_ALL=1

  trap '
    export IMAGE="$_IMAGE" RUN_AS_UID="$_RUN_AS_UID"
    export DAR_BACKUP_DIR="$_DAR_BACKUP_DIR" DAR_BACKUP_D_DIR="$_DAR_BACKUP_D_DIR"
    export DAR_BACKUP_DATA_DIR="$_DAR_BACKUP_DATA_DIR" DAR_BACKUP_RESTORE_DIR="$_DAR_BACKUP_RESTORE_DIR"
    unset IMAGE_OVERRIDE EXPECT_FAIL RUN_AS_UID_OVERRIDE \
          DAR_BACKUP_DIR_OVERRIDE DAR_BACKUP_D_DIR_OVERRIDE \
          DAR_BACKUP_DATA_DIR_OVERRIDE DAR_BACKUP_RESTORE_DIR_OVERRIDE CLEAN_ALL
  ' RETURN

  export RUN_AS_UID="${RUN_AS_UID_OVERRIDE:-$(id -u)}"
  export IMAGE="${IMAGE_OVERRIDE:-$IMAGE}"
  export DAR_BACKUP_DIR="${DAR_BACKUP_DIR_OVERRIDE:-$WORKDIR/backups}"
  export DAR_BACKUP_D_DIR="${DAR_BACKUP_D_DIR_OVERRIDE:-$WORKDIR/backup.d}"
  export DAR_BACKUP_DATA_DIR="${DAR_BACKUP_DATA_DIR_OVERRIDE:-$WORKDIR/data}"
  export DAR_BACKUP_RESTORE_DIR="${DAR_BACKUP_RESTORE_DIR_OVERRIDE:-$WORKDIR/restore}"

  # Prepare dataset (and originals)
  prepare_dataset "$DATASET_MODE"

  # Print SHA256 before backup
  print_sha256 "$DAR_BACKUP_DIR"
  print_sha256 "$DAR_BACKUP_D_DIR"
  print_sha256 "$DAR_BACKUP_DATA_DIR"
  print_sha256 "$DAR_BACKUP_RESTORE_DIR"
  print_sha256 "$WORKDIR/originals"

  set +e
  "$SCRIPT" "$@"
  local exit_code=$?
  set -e

  # After run, show new SHA256 and compare to originals
  print_sha256 "$DAR_BACKUP_DATA_DIR"
  compare_to_originals

  if [[ "${EXPECT_FAIL:-0}" -eq 1 ]]; then
    if [[ $exit_code -ne 0 ]]; then pass "$name failed as expected"
    else fail "$name should have failed but succeeded"; fi
    return
  fi

  if [[ $exit_code -ne 0 ]]; then fail "$name failed (exit code $exit_code)"; fi

  local dar_files
  dar_files=$(find "$DAR_BACKUP_DIR" -name "*.dar" -type f || true)
  if [[ -z "$dar_files" ]]; then fail "$name did not produce any .dar backup files"; fi

  pass "$name"
}

# === Stateful tests ===
test_case_stateful_full() { CLEAN_ALL=0; export WORKDIR="$STATEFUL_BASE"; EXPECT_FAIL=0;  DATASET_MODE=stateful; run_test_case "Initial FULL backup for stateful tests" -t FULL; }
test_case_diff()          { CLEAN_ALL=0; export WORKDIR="$STATEFUL_BASE"; EXPECT_FAIL=0;  DATASET_MODE=stateful; run_test_case "DIFF backup (requires FULL first)" -t DIFF; }
test_case_incr()          { CLEAN_ALL=0; export WORKDIR="$STATEFUL_BASE"; EXPECT_FAIL=0;  DATASET_MODE=stateful; run_test_case "INCR backup (requires DIFF first)" -t INCR; }

# === Original test cases ===
test_case_1() { EXPECT_FAIL=0; run_test_case "Default env, FULL backup" -t FULL; }
test_case_2() { IMAGE_OVERRIDE="dar-backup:custom"; EXPECT_FAIL=1; run_test_case "Custom image, DIFF backup" -t DIFF; unset IMAGE_OVERRIDE; }
test_case_3() { RUN_AS_UID_OVERRIDE=0; EXPECT_FAIL=1; run_test_case "Fails when run as root (simulated)" -t INCR; unset RUN_AS_UID_OVERRIDE; }
test_case_4() { BACKUP_TYPE="invalid"; EXPECT_FAIL=1; run_test_case "Fails with invalid backup type" -t "$BACKUP_TYPE"; }
test_case_5() { DAR_BACKUP_DIR_OVERRIDE="/tmp/custom_backups"; rm -rf "$DAR_BACKUP_DIR_OVERRIDE"; EXPECT_FAIL=0; run_test_case "Custom backup dir set" -t FULL; unset DAR_BACKUP_DIR_OVERRIDE; }

# === Utility tests ===
test_case_6() {
  EXPECT_FAIL=0; clean_dirs; echo "Running test: Container runs as daruser (UID 1000) by default"
  uid=$(docker run --rm --user 1000 --entrypoint /bin/sh "$IMAGE" -c "id -u")
  [[ "$uid" -eq 1000 ]] || fail "Expected UID 1000, got $uid"
  pass "Container runs as daruser (UID 1000) when no --user is provided"
}
test_case_7() {
  EXPECT_FAIL=0; clean_dirs; echo "Running test: Verify venv usage and no pip/setuptools/wheel"
  path=$(docker run --rm --entrypoint /bin/sh "$IMAGE" -c "which dar-backup")
  [[ "$path" == "/opt/venv/bin/dar-backup" ]] || fail "dar-backup not found in venv, found at $path"
  for pkg in pip setuptools wheel; do
    docker run --rm --entrypoint /bin/sh "$IMAGE" -c "python3 -m $pkg --version" >/dev/null 2>&1 && fail "$pkg still present"
  done
  pass "dar-backup runs from venv and no pip/setuptools/wheel installed"
}



test_case_8() {
  EXPECT_FAIL=0
  clean_dirs
  echo "Running test: Restore directory is usable and populated"

  # Define WORKDIR and environment (consistent with other tests)
  WORKDIR="${TEST_TMP}/workdir"
  export WORKDIR
  export DAR_BACKUP_DIR="$WORKDIR/backups"
  export DAR_BACKUP_D_DIR="$WORKDIR/backup.d"
  export DAR_BACKUP_DATA_DIR="$WORKDIR/data"
  export DAR_BACKUP_RESTORE_DIR="$WORKDIR/restore"

  mkdir -p "$DAR_BACKUP_DIR" "$DAR_BACKUP_D_DIR" "$DAR_BACKUP_DATA_DIR" "$DAR_BACKUP_RESTORE_DIR"

  # Create a simple backup.d/default definition (dar needs this)
  cat <<EOF > "$DAR_BACKUP_D_DIR/default"
-am
-R /data
-z5
-n
--slice 7G
--cache-directory-tagging
EOF

  # Create a small dataset to back up
  echo "Test file for restore check" > "$DAR_BACKUP_DATA_DIR/restore_test_src.txt"

  # Run a full backup so dar-backup sets everything up
  "$SCRIPT" -t FULL

  # Verify restore dir is writable inside the container
  docker run --rm \
     --user="$(id -u):$(id -g)" \
     -v "$WORKDIR":"$WORKDIR" \
     -e DAR_BACKUP_RESTORE_DIR="$DAR_BACKUP_RESTORE_DIR" \
     --entrypoint sh \
     "$IMAGE" -c 'mkdir -p "$DAR_BACKUP_RESTORE_DIR" && touch "$DAR_BACKUP_RESTORE_DIR/restore_test.txt"'



  if [[ ! -f "$DAR_BACKUP_RESTORE_DIR/restore_test.txt" ]]; then
    fail "Restore directory not created or writable"
  fi

  pass "Restore directory is writable and populated during verification"
}


test_case_9() {
  EXPECT_FAIL=0
  clean_dirs
  echo "Running test: Manager creates database files"

  # Define WORKDIR and env vars
  WORKDIR="${TEST_TMP}/workdir"
  export WORKDIR
  export DAR_BACKUP_DIR="$WORKDIR/backups"
  export DAR_BACKUP_D_DIR="$WORKDIR/backup.d"
  mkdir -p "$DAR_BACKUP_DIR" "$DAR_BACKUP_D_DIR"

  # Create a minimal backup definition so manager has something to register
  cat <<EOF > "$DAR_BACKUP_D_DIR/default"
# Minimal definition for testing manager DB creation
-R /data
-z5
-n
--slice 7G
EOF



# Run manager and mount both /backups and /backup.d
 docker run --rm \
  -v "$DAR_BACKUP_DIR":/backups \
  -v "$DAR_BACKUP_D_DIR":/backup.d \
  --entrypoint manager \
  "$IMAGE" --create-db --config /etc/dar-backup/dar-backup.conf



  # Verify .db files were created
  db_files=$(find "$DAR_BACKUP_DIR" -type f -name "*.db" 2>/dev/null || true)
  if [[ -z "$db_files" ]]; then
    fail "Manager did not create any database files"
  fi

  pass "Manager successfully created database files"
}


# === Run tests ===
test_case_1
test_case_2
test_case_3
test_case_4
test_case_5
rm -f "$STATEFUL_BASE/backups"/*.dar "$STATEFUL_BASE/backups"/*.par2
test_case_stateful_full
test_case_diff
test_case_incr
test_case_6
test_case_7
test_case_8
test_case_9 

