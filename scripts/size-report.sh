#!/usr/bin/env bash

# SPDX-FileCopyrightText: 2025-2026 Per Jensen
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This file is part of dar-backup-image:
# https://github.com/per2jensen/dar-backup-image
#
# License terms and warranty disclaimer:
# https://github.com/per2jensen/dar-backup-image/blob/main/LICENSE

# Show a formatted layer size breakdown in decimal MB.

set -euo pipefail

if [[ $# -ne 1 || -z "${1:-}" ]]; then
  >&2 echo "ERROR: exactly one non-empty image reference is required"
  exit 2
fi

IMAGE="$1"

docker history --no-trunc --format '{{json .}}' "$IMAGE" \
  | jq -sr '
      [
      .[] |
      select(.Size != "0B") |
      .Size as $s |
      ($s | capture("(?<num>[0-9.]+)(?<unit>[A-Za-z]+)")) as $parts |
      ($parts.num | tonumber) as $n |
      (if $parts.unit == "TB" then $n*1000000
       elif $parts.unit == "GB" then $n*1000
       elif $parts.unit == "MB" then $n
       elif $parts.unit == "kB" then $n/1000
       elif $parts.unit == "B"  then $n/1000000
       else 0 end) as $mb |
      select($mb >= 0.01) |
      {megabytes: $mb, command: .CreatedBy[0:80]}
      ] |
      sort_by(.megabytes) |
      reverse |
      .[:10][] |
      "\( (.megabytes*1000|round/1000) ) MB | \(.command)"' \
  | column -t -s '|'
