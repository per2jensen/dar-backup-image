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


# Ensure required environment variables are set
: "${RUN_AS_UID:?RUN_AS_UID must be set}"

# === Helpers ===

pass() { echo -e "${GREEN}✔ $1${RESET}"; }
fail() { echo -e "${RED}✘ $1${RESET}"; exit 1; }

clean_dirs() {
  if [[ "${CLEAN_ALL:-1}" -eq 1 ]]; then
    rm -rf "$TEST_TMP"
  fi
  mkdir -p "$TEST_TMP"
}


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


run_test_case() {
  local name="$1"
  shift

  clean_dirs
  echo "Running test: $name"


  : "${WORKDIR:=$TEST_TMP/workdir}"
  export WORKDIR
  mkdir -p "$WORKDIR"


  _IMAGE=""
  _RUN_AS_UID=""
  _DAR_BACKUP_DIR=""
  _DAR_BACKUP_D_DIR=""
  _DAR_BACKUP_DATA_DIR=""
  _DAR_BACKUP_RESTORE_DIR=""
  CLEAN_ALL=1

  # Save original env state
  _IMAGE="$IMAGE"
  _RUN_AS_UID="$RUN_AS_UID"
  echo "🔒 Will run container with UID: ${RUN_AS_UID:-unknown}"
  _DAR_BACKUP_DIR="$DAR_BACKUP_DIR"
  _DAR_BACKUP_D_DIR="$DAR_BACKUP_D_DIR"
  _DAR_BACKUP_DATA_DIR="$DAR_BACKUP_DATA_DIR"
  _DAR_BACKUP_RESTORE_DIR="$DAR_BACKUP_RESTORE_DIR"

  mkdir -p "$DAR_BACKUP_DATA_DIR"

  # Optional pre-hook to manipulate data before test
  if declare -f PRE_HOOK >/dev/null; then
    PRE_HOOK
  fi

  # Ensure environment is restored and cleaned even if the script fails
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

  set +e
  "$SCRIPT" "$@"
  local exit_code=$?
  set -e



  # === Evaluate result ===
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



# === Test Cases ===

test_case_1() {
  EXPECT_FAIL=0
  run_test_case "Default env, FULL backup" -t FULL
}

test_case_2() {
  IMAGE_OVERRIDE="dar-backup:custom"
  EXPECT_FAIL=1
  run_test_case "Custom image, DIFF backup" -t DIFF
  unset IMAGE_OVERRIDE   # <== add this  
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








