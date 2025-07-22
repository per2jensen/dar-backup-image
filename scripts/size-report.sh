#!/usr/bin/env bash
# Show a formatted layer size breakdown (all sizes in MB, readable table)

IMAGE="$1"

docker history --no-trunc --format '{{json .}}' "$IMAGE" \
  | jq -r '
      select(.Size != "0B") |
      .Size as $s |
      ($s | capture("(?<num>[0-9.]+)(?<unit>[A-Za-z]+)")) as $parts |
      ($parts.num | tonumber) as $n |
      (if $parts.unit == "GB" then $n*1024
       elif $parts.unit == "MB" then $n
       elif $parts.unit == "kB" then $n/1024
       elif $parts.unit == "B"  then $n/1048576
       else 0 end) as $mb |
      select($mb >= 0.01) |  # Skip layers under ~10kB
      "\( ($mb*1000|round/1000) ) MB | \(.CreatedBy[0:80])"' \
  | column -t -s '|' | sort -hrk1 | head -n 10
