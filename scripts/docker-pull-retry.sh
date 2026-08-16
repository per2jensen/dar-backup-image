#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later

set -euo pipefail

MAX_DELAY_SECONDS=30

usage() {
  >&2 echo "Usage: $0 IMAGE [MAX_ATTEMPTS] [INITIAL_DELAY_SECONDS]"
}

validate_inputs() {
  local image="$1"
  local max_attempts="$2"
  local initial_delay_seconds="$3"

  if [[ -z "$image" || "$image" == -* || "$image" =~ [[:space:]] ]]; then
    >&2 echo "ERROR: IMAGE must be a non-empty container image reference without whitespace"
    return 2
  fi
  if ! [[ "$max_attempts" =~ ^[1-9][0-9]*$ ]] || (( max_attempts > 20 )); then
    >&2 echo "ERROR: MAX_ATTEMPTS must be an integer between 1 and 20"
    return 2
  fi
  if ! [[ "$initial_delay_seconds" =~ ^(0|[1-9][0-9]*)$ ]] \
    || (( initial_delay_seconds > MAX_DELAY_SECONDS )); then
    >&2 echo "ERROR: INITIAL_DELAY_SECONDS must be an integer between 0 and $MAX_DELAY_SECONDS"
    return 2
  fi
  if ! command -v docker >/dev/null 2>&1; then
    >&2 echo "ERROR: docker is required but was not found in PATH"
    return 127
  fi
}

pull_image_with_retry() {
  local image="$1"
  local max_attempts="$2"
  local delay_seconds="$3"
  local attempt=1

  while (( attempt <= max_attempts )); do
    >&2 echo "Pulling $image (attempt $attempt/$max_attempts)"
    if docker pull "$image"; then
      >&2 echo "Successfully pulled $image"
      return 0
    fi

    if (( attempt == max_attempts )); then
      break
    fi

    >&2 echo "WARNING: docker pull failed; retrying in ${delay_seconds} seconds"
    sleep "$delay_seconds"
    delay_seconds=$((delay_seconds * 2))
    if (( delay_seconds > MAX_DELAY_SECONDS )); then
      delay_seconds=$MAX_DELAY_SECONDS
    fi
    attempt=$((attempt + 1))
  done

  >&2 echo "ERROR: Failed to pull $image after $max_attempts attempts"
  return 1
}

main() {
  if (( $# < 1 || $# > 3 )); then
    usage
    return 2
  fi

  local image="$1"
  local max_attempts="${2:-5}"
  local initial_delay_seconds="${3:-5}"

  validate_inputs "$image" "$max_attempts" "$initial_delay_seconds"
  pull_image_with_retry "$image" "$max_attempts" "$initial_delay_seconds"
}

main "$@"
