#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
#
# save-docker-image.sh — check if the latest dar-backup Docker image has been
# archived locally, and if not, pull it from Docker Hub and save it as a
# compressed tar alongside the dar archives.
#
# Source of truth: build-history.json from the dar-backup-image GitHub repo.
# The latest entry (highest build_number) determines the expected image tag.
#
# Usage:
#   ./save-docker-image.sh
#   DOCKER_ARCHIVE_DIR=/mnt/nas/docker-images ./save-docker-image.sh

set -euo pipefail

DOCKER_ARCHIVE_DIR="${DOCKER_ARCHIVE_DIR:-/mnt/dar/docker-archives}"
IMAGE_BASE="per2jensen/dar-backup"
BUILD_HISTORY_URL="https://raw.githubusercontent.com/per2jensen/dar-backup-image/main/doc/build-history.json"

########################################
# Helpers
########################################
red()   { echo -e "\033[1;31m$*\033[0m"; }
green() { echo -e "\033[1;32m$*\033[0m"; }
info()  { echo -e "\033[1;34m$*\033[0m"; }

########################################
# Check required tools
########################################
for tool in docker curl jq; do
    if ! command -v "${tool}" &>/dev/null; then
        red "❌ Required tool not found: ${tool}"
        exit 1
    fi
done

########################################
# Fetch build-history.json from GitHub
########################################
info "Fetching build-history.json from GitHub..."
BUILD_HISTORY="$(curl -fsSL "${BUILD_HISTORY_URL}")" \
    || { red "❌ Failed to fetch build-history.json from ${BUILD_HISTORY_URL}"; exit 1; }

########################################
# Find latest entry by highest build_number
########################################
LATEST="$(echo "${BUILD_HISTORY}" | jq 'max_by(.build_number)')"
VERSION="$(echo "${LATEST}"      | jq -r '.tag')"
CREATED="$(echo "${LATEST}"      | jq -r '.created')"
BUILD_NUMBER="$(echo "${LATEST}" | jq -r '.build_number')"

info "Latest image: ${IMAGE_BASE}:${VERSION}  (build #${BUILD_NUMBER}, created ${CREATED})"

########################################
# Check if already archived
########################################
ARCHIVE="${DOCKER_ARCHIVE_DIR}/dar-backup-${VERSION}-docker-image.tar.gz"

if [[ -f "${ARCHIVE}" ]]; then
    green "✅ Already archived: ${ARCHIVE}"
    exit 0
fi

########################################
# Pull from Docker Hub
########################################
green "Pulling ${IMAGE_BASE}:${VERSION} from Docker Hub..."
docker pull "${IMAGE_BASE}:${VERSION}" \
    || { red "❌ Failed to pull ${IMAGE_BASE}:${VERSION}"; exit 1; }

########################################
# Save and compress
########################################
mkdir -p "${DOCKER_ARCHIVE_DIR}" \
    || { red "❌ Failed to create archive dir: ${DOCKER_ARCHIVE_DIR}"; exit 1; }

green "Saving and compressing to ${ARCHIVE}..."
docker save "${IMAGE_BASE}:${VERSION}" | gzip > "${ARCHIVE}" \
    || { red "❌ docker save/compress failed"; exit 1; }

green "✅ Saved: ${ARCHIVE} ($(du -h "${ARCHIVE}" | cut -f1))"
