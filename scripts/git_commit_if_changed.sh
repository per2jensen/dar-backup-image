#!/bin/bash
# Usage: scripts/git_commit_if_changed.sh <message> <path1> [path2] ...
MESSAGE="$1"
shift

git add "$@"
if ! git diff --cached --quiet; then
  git commit -m "$MESSAGE"
fi
