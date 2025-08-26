#!/bin/bash

set -euo pipefail


# Dummy values for test
#FINAL_VERSION="0.9.9"
#DAR_BACKUP_VERSION="0.8.5"
#GIT_REV="deadbe"
#DOCKERHUB_REPO="per2jensen/dar-backup"
#DIGEST_ONLY="sha256-1234567890abcdef"

: "${FINAL_VERSION:?must be set}"
: "${DAR_BACKUP_VERSION:?must be set}"
: "${GIT_REV:?must be set}"
: "${DOCKERHUB_REPO:?must be set}"
: "${DIGEST_ONLY:?must be set}"


TMP_FILE="README.md.tmp"
TABLE_ANCHOR='<a name="dockerhub-builds">'

# Build new row
NEW_ROW="| $FINAL_VERSION| $DAR_BACKUP_VERSION| $DAR_VERSION| $GIT_REV|[tag:$FINAL_VERSION](https://hub.docker.com/layers/$DOCKERHUB_REPO/$FINAL_VERSION/images/$DIGEST_ONLY)| $NOTE|"

TABLE_HEADER="## Builds uploaded to Docker Hub"
TMP_FILE="README.md.tmp"

awk -v new_row="$NEW_ROW" -v anchor="$TABLE_ANCHOR" '
BEGIN {
    in_section = 0
    in_table = 0
    row_count = 0
}
{
    if ($0 ~ anchor) {
        print             # anchor
        getline; print    # header line (## Builds ...)
        next_line = ""
        getline next_line
        if (next_line != "") print ""  # blank line if not already there
        else print next_line
        in_section = 1
        next
    }

    if (in_section && !in_table && $0 ~ /^\|.*Tag.*\|/) {
        print $0         # column header
        getline
        print $0         # separator
        print new_row    # insert new row
        in_table = 1
        next
    }

    if (in_table && $0 ~ /^\|.*\[tag:/) {
        if (row_count < 4) {
            old_rows[row_count++] = $0
        }
        next
    }

    if (in_table) {
        for (i = 0; i < row_count; i++) print old_rows[i]
        in_table = 0
        in_section = 0
    }

    print
}
END {
    if (in_table) {
        for (i = 0; i < row_count; i++) print old_rows[i]
    }
}
' README.md > "$TMP_FILE"


mv "$TMP_FILE" README.md
echo "✅ README.md updated with build row"

