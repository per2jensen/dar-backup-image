#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later

# Test harness for run-backup.sh
set -euo pipefail

SCRIPT="scripts/run-backup.sh"
IMAGE="dar-backup:dev"
TEST_TMP="/tmp/dar-backup-test"

# Colors
RED=$(tput setaf 1)
GREEN=$(tput setaf 2)
RESET=$(tput sgr0)

# === Helpers ===

pass() { echo -e "${GREEN}✔ $1${RESET}"; }
fail() { echo -e "${RED}✘ $1${RESET}"; exit 1; }

clean_dirs() {
  rm -rf "$TEST_TMP"
  mkdir -p "$TEST_TMP"
}

run_test_case() {
  local name="$1"
  shift
  clean_dirs

  echo "Running test: $name"

  # Prepare fresh WORKDIR
  local WORKDIR="$TEST_TMP/workdir"
  mkdir -p "$WORKDIR"

  # Override directories (can be replaced per test)
  export WORKDIR="$WORKDIR"
  export RUN_AS_UID="${RUN_AS_UID_OVERRIDE:-1000}"
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

  # Check backup was created
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
}


# === Run all test cases ===
test_case_1
test_case_2
test_case_3
test_case_4
test_case_5
