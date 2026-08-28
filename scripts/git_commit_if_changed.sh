#!/bin/bash

# SPDX-FileCopyrightText: 2025-2026 Per Jensen
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This file is part of dar-backup-image:
# https://github.com/per2jensen/dar-backup-image
#
# License terms and warranty disclaimer:
# https://github.com/per2jensen/dar-backup-image/blob/main/LICENSE

# Usage: scripts/git_commit_if_changed.sh <message> <path1> [path2] ...
MESSAGE="$1"
shift

git add "$@"
if ! git diff --cached --quiet; then
  git commit -m "$MESSAGE"
fi
