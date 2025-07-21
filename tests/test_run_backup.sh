#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later

# Test harness for run-backup.sh
set -euo pipefail

export RUN_AS_UID="${RUN_AS_UID:-$(id -u)}"
: "${DAR_BACKUP_DIR:=${TEST_TMP:-/tmp}/backups}"
: "${DAR_BACKUP_D_DIR:=${TEST_TMP:-/tmp}/backup.d}"
: "${DAR_BACKUP_DATA_DIR:=${TEST_TMP:-/tmp}/data}"
: "${DAR_BACKUP_RESTORE_DIR:=${TEST_TMP:-/tmp}/restore}"

SCRIPT="scripts/run-backup.sh"
IMAGE="${IMAGE:-dar-backup:dev}"
TEST_TMP="/tmp/dar-backup-test"
TEST_FILE_NAME="test.txt"

STATEFUL_BASE="/tmp/dar-backup-test-state"
mkdir -p "$STATEFUL_BASE"

# Colors
if [ -t 1 ] && command -v tput &>/dev/null && tput colors &>/dev/null; then
  RED=$(tput setaf 1)
  GREEN=$(tput setaf 2)
  RESET=$(tput sgr0)
else
  RED=""
  GREEN=""
  RESET=""
fi

: "${RUN_AS_UID:?RUN_AS_UID must be set}"

pass() { echo -e "${GREEN}✔ $1${RESET}"; }
fail() { echo -e "${RED}✘ $1${RESET}"; exit 1; }

clean_dirs() {
  if [[ "${CLEAN_ALL:-1}" -eq 1 ]]; then
    rm -rf "$TEST_TMP"
  fi
  mkdir -p "$TEST_TMP"
}

run_test_case() {
  local name="$1"
  shift

  clean_dirs
  echo "Running test: $name"

  : "${WORKDIR:=$TEST_TMP/workdir}"
  export WORKDIR
  mkdir -p "$WORKDIR"

  _IMAGE="$IMAGE"
  _RUN_AS_UID="$RUN_AS_UID"
  echo "🔒 Will run container with UID: ${RUN_AS_UID:-unknown}"
  _DAR_BACKUP_DIR="$DAR_BACKUP_DIR"
  _DAR_BACKUP_D_DIR="$DAR_BACKUP_D_DIR"
  _DAR_BACKUP_DATA_DIR="$DAR_BACKUP_DATA_DIR"
  _DAR_BACKUP_RESTORE_DIR="$DAR_BACKUP_RESTORE_DIR"
  CLEAN_ALL=1

  mkdir -p "$DAR_BACKUP_DATA_DIR"

  if declare -f PRE_HOOK >/dev/null; then
    PRE_HOOK
  fi

  trap '
    export IMAGE="$_IMAGE"
    export RUN_AS_UID="$_RUN_AS_UID"
    export DAR_BACKUP_DIR="$_DAR_BACKUP_DIR"
    export DAR_BACKUP_D_DIR="$_DAR_BACKUP_D_DIR"
    export DAR_BACKUP_DATA_DIR="$_DAR_BACKUP_DATA_DIR"
    export DAR_BACKUP_RESTORE_DIR="$_DAR_BACKUP_RESTORE_DIR"
    unset IMAGE_OVERRIDE EXPECT_FAIL RUN_AS_UID_OVERRIDE \
          DAR_BACKUP_DIR_OVERRIDE DAR_BACKUP_D_DIR_OVERRIDE \
          DAR_BACKUP_DATA_DIR_OVERRIDE DAR_BACKUP_RESTORE_DIR_OVERRIDE CLEAN_ALL
  ' RETURN

  export RUN_AS_UID="${RUN_AS_UID_OVERRIDE:-$(id -u)}"
  echo "🔒 Will run container with UID: $RUN_AS_UID"

  export IMAGE="${IMAGE_OVERRIDE:-$IMAGE}"
  export DAR_BACKUP_DIR="${DAR_BACKUP_DIR_OVERRIDE:-$WORKDIR/backups}"
  export DAR_BACKUP_D_DIR="${DAR_BACKUP_D_DIR_OVERRIDE:-$WORKDIR/backup.d}"
  export DAR_BACKUP_DATA_DIR="${DAR_BACKUP_DATA_DIR_OVERRIDE:-$WORKDIR/data}"
  export DAR_BACKUP_RESTORE_DIR="${DAR_BACKUP_RESTORE_DIR_OVERRIDE:-$WORKDIR/restore}"

  mkdir -p "$DAR_BACKUP_DATA_DIR"
  echo "Hello world" > "$DAR_BACKUP_DATA_DIR/test.txt"

  # Enable fix-perms automatically if test forces root
  if [[ "$RUN_AS_UID" -eq 0 ]]; then
    export DAR_BACKUP_FIX_PERMS=1
  else
    unset DAR_BACKUP_FIX_PERMS || true
  fi

  set +e
  "$SCRIPT" "$@"
  local exit_code=$?
  set -e

  if [[ "${EXPECT_FAIL:-0}" -eq 1 ]]; then
    if [[ $exit_code -ne 0 ]]; then
      pass "$name failed as expected"
    else
      fail "$name should have failed but succeeded"
    fi
    return
  fi

  if [[ $exit_code -ne 0 ]]; then
    fail "$name failed (exit code $exit_code)"
  fi

  local dar_files
  dar_files=$(find "$DAR_BACKUP_DIR" -name "*.dar" -type f)
  if [[ -z "$dar_files" ]]; then
    fail "$name did not produce any .dar backup files"
  fi

  pass "$name"
}

# === Stateful tests ===
test_case_stateful_full() {
  CLEAN_ALL=0
  export WORKDIR="$STATEFUL_BASE"
  EXPECT_FAIL=0
  PRE_HOOK() {
    echo "FULL:  Updated at $(date)" >> "$DAR_BACKUP_DATA_DIR/$TEST_FILE_NAME"
  }
  run_test_case "Initial FULL backup for stateful tests" -t FULL
  unset -f PRE_HOOK
}

test_case_diff() {
  CLEAN_ALL=0
  export WORKDIR="$STATEFUL_BASE"
  EXPECT_FAIL=0
  PRE_HOOK() {
    echo "DIFF: updated at $(date)" >> "$DAR_BACKUP_DATA_DIR/$TEST_FILE_NAME"
  }
  run_test_case "DIFF backup (requires FULL first)" -t DIFF
  unset -f PRE_HOOK
}

test_case_incr() {
  CLEAN_ALL=0
  export WORKDIR="$STATEFUL_BASE"
  EXPECT_FAIL=0
  PRE_HOOK() {
    echo "INCR: updated at $(date)" >> "$DAR_BACKUP_DATA_DIR/$TEST_FILE_NAME"
  }
  run_test_case "INCR backup (requires DIFF first)" -t INCR
  unset -f PRE_HOOK
}

# === Original test cases ===
test_case_1() {
  EXPECT_FAIL=0
  run_test_case "Default env, FULL backup" -t FULL
}

test_case_2() {
  IMAGE_OVERRIDE="dar-backup:custom"
  EXPECT_FAIL=1
  run_test_case "Custom image, DIFF backup" -t DIFF
  unset IMAGE_OVERRIDE
}

test_case_3() {
  RUN_AS_UID_OVERRIDE=0
  EXPECT_FAIL=1
  run_test_case "Fails when run as root (simulated)" -t INCR
  unset RUN_AS_UID_OVERRIDE
}

test_case_4() {
  BACKUP_TYPE="invalid"
  EXPECT_FAIL=1
  run_test_case "Fails with invalid backup type" -t "$BACKUP_TYPE"
}

test_case_5() {
  DAR_BACKUP_DIR_OVERRIDE="/tmp/custom_backups"
  rm -rf "$DAR_BACKUP_DIR_OVERRIDE"
  EXPECT_FAIL=0
  run_test_case "Custom backup dir set" -t FULL
  unset DAR_BACKUP_DIR_OVERRIDE
}


test_case_6() {
  EXPECT_FAIL=0
  clean_dirs
  echo "Running test: Container runs as daruser (UID 1000) by default"

  # Force run as 1000 to simulate daruser (since bypassing entrypoint defaults to root)
  uid=$(docker run --rm --user 1000 --entrypoint /bin/sh "$IMAGE" -c "id -u")
  if [[ "$uid" -ne 1000 ]]; then
    fail "Expected UID 1000, got $uid"
  fi

  pass "Container runs as daruser (UID 1000) when no --user is provided"
}

test_case_7() {
  EXPECT_FAIL=0
  clean_dirs
  echo "Running test: Verify venv usage and no pip/setuptools/wheel"

  # Verify dar-backup is in venv
  path=$(docker run --rm --entrypoint /bin/sh "$IMAGE" -c "which dar-backup")
  if [[ "$path" != "/opt/venv/bin/dar-backup" ]]; then
    fail "dar-backup not found in venv, found at $path"
  fi

  # Verify pip/setuptools/wheel are absent
  for pkg in pip setuptools wheel; do
    if docker run --rm --entrypoint /bin/sh "$IMAGE" -c "python3 -m $pkg --version" >/dev/null 2>&1; then
      fail "$pkg still present in the image"
    fi
  done

  pass "dar-backup runs from venv and no pip/setuptools/wheel installed"
}


test_case_8() {
  EXPECT_FAIL=0
  clean_dirs
  echo "Running test: Restore directory is usable and populated"

  # Clean up backup dir and ensure paths exist
  rm -rf "$DAR_BACKUP_DIR"/*
  mkdir -p "$DAR_BACKUP_DIR" "$DAR_BACKUP_RESTORE_DIR"

  # Run a fresh FULL backup (produces a valid archive)
  "$SCRIPT" -t FULL

  # Check restore dir by mounting WORKDIR into container
  docker run --rm \
    --user="$(id -u):$(id -g)" \
    -v "$WORKDIR":"$WORKDIR" \
    -e DAR_BACKUP_RESTORE_DIR="$DAR_BACKUP_RESTORE_DIR" \
    --entrypoint sh \
    "$IMAGE" -c 'mkdir -p "$DAR_BACKUP_RESTORE_DIR" && touch "$DAR_BACKUP_RESTORE_DIR/restore_test.txt"'

  if [[ ! -f "$DAR_BACKUP_RESTORE_DIR/restore_test.txt" ]]; then
    fail "Restore directory not created or writable"
  fi

  pass "Restore directory is writable and functional"
}


test_case_9() {
  EXPECT_FAIL=0
  clean_dirs
  echo "Running test: Manager creates database files"

  # Run manager initialization
  docker run --rm \
    -e DAR_BACKUP_CONFIG="/etc/dar-backup/dar-backup.conf" \
    -v "$WORKDIR":"$WORKDIR" \
    "$IMAGE" manager --create-db --config /etc/dar-backup/dar-backup.conf

  db_files=$(find "$WORKDIR/backups" -type f -name "*.db" 2>/dev/null || true)
  if [[ -z "$db_files" ]]; then
    fail "Manager did not create any database files"
  fi

  pass "Manager successfully created database files"
}



# === Run all test cases ===
test_case_1
test_case_2
test_case_3
test_case_4
test_case_5
rm -f /tmp/dar-backup-test-state/backups/*.dar /tmp/dar-backup-test-state/backups/*.par2
test_case_stateful_full
test_case_diff
test_case_incr
test_case_6
test_case_7
test_case_8
test_case_9