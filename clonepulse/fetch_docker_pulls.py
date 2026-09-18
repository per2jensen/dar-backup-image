#!/usr/bin/env python3

# SPDX-FileCopyrightText: 2025 Per Jensen
#
# SPDX-License-Identifier: MIT
#
# This file is part of dar-backup-image:
# https://github.com/per2jensen/dar-backup-image
#
# License terms and warranty disclaimer:
# https://github.com/per2jensen/dar-backup-image/blob/main/LICENSES/MIT.txt
"""
Fetch total pull count for the dar-backup image from Docker Hub and
append/update a small history JSON under clonepulse/docker_pulls.json.

Uses the public Docker Hub v2 API, no auth needed for a public repo.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


NAMESPACE = "per2jensen"
REPOSITORY = "dar-backup"
API_URL = f"https://hub.docker.com/v2/repositories/{NAMESPACE}/{REPOSITORY}/"
REQUEST_TIMEOUT_SECONDS = 30


def fetch_pull_count() -> int:
    """Fetch and validate the current Docker Hub pull count.

    Returns:
        Non-negative Docker Hub pull count.

    Raises:
        RuntimeError: If Docker Hub returns a missing or invalid pull count.
        HTTPError: If Docker Hub returns an unsuccessful HTTP response.
        URLError: If the request cannot be completed.
        TimeoutError: If the request exceeds the configured timeout.
    """
    with urlopen(API_URL, timeout=REQUEST_TIMEOUT_SECONDS) as resp:
        data = json.load(resp)
    pulls = data.get("pull_count")
    if pulls is None:
        raise RuntimeError(f"No pull_count in Docker Hub response: {data}")
    parsed_pulls = int(pulls)
    if parsed_pulls < 0:
        raise RuntimeError(f"Docker Hub returned a negative pull_count: {parsed_pulls}")
    return parsed_pulls


def main() -> int:
    """Fetch Docker Hub statistics and update the local history.

    Returns:
        Zero on success and one on network, input, or filesystem failure.
    """
    try:
        pulls = fetch_pull_count()
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, RuntimeError, ValueError) as error:
        print(f"ERROR: unable to fetch Docker Hub pull count: {error}", file=sys.stderr)
        return 1
    today = date.today().isoformat()

    out_path = Path(__file__).with_name("docker_pulls.json")

    try:
        if out_path.exists():
            blob = json.loads(out_path.read_text(encoding="utf-8"))
        else:
            blob = {}
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        print(f"ERROR: unable to read Docker pull history {out_path}: {error}", file=sys.stderr)
        return 1
    if not isinstance(blob, dict):
        print(f"ERROR: Docker pull history root must be an object: {out_path}", file=sys.stderr)
        return 1

    history = blob.setdefault("history", [])
    if not isinstance(history, list) or any(not isinstance(entry, dict) for entry in history):
        print(f"ERROR: Docker pull history must contain a list of objects: {out_path}", file=sys.stderr)
        return 1
    # Update or append today’s entry
    for entry in history:
        if entry.get("date") == today:
            entry["pulls"] = pulls
            break
    else:
        history.append({"date": today, "pulls": pulls})

    blob["latest"] = {"date": today, "pulls": pulls}

    try:
        out_path.write_text(
            json.dumps(blob, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except (OSError, TypeError, ValueError) as error:
        print(f"ERROR: unable to write Docker pull history {out_path}: {error}", file=sys.stderr)
        return 1
    print(f"{today}: Docker Hub pulls = {pulls}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
