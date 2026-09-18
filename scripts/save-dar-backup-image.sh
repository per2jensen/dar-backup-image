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
#
# save-dar-backup-image.sh — check if the latest dar-backup Docker image has been
# archived locally, and if not, pull it from Docker Hub and save it as a
# compressed tar alongside the dar archives.
#
# Source of truth: build-history.json from the dar-backup-image GitHub repo.
# The latest entry (highest build_number) determines the expected image tag.
#
# This helper preserves image availability and records a SHA-256 checksum for
# local corruption detection. It does not verify the recorded registry digest
# or Cosign identity, or archive registry-hosted provenance material. See
# README.md before relying on it for long-term recovery.
#
# Usage:
#   ./save-dar-backup-image.sh
#   DOCKER_ARCHIVE_DIR=/mnt/nas/docker-images ./save-dar-backup-image.sh

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
for tool in docker curl jq gzip sha256sum mktemp; do
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
if ! LATEST="$(jq -e '
    if type == "array" and length > 0 then
        max_by(.build_number)
    else
        error("build history must be a non-empty array")
    end
' <<< "${BUILD_HISTORY}")"; then
    red "❌ Invalid build-history.json; unable to select the latest build"
    exit 1
fi
if ! VERSION="$(jq -er '.tag | select(type == "string" and length > 0)' \
        <<< "${LATEST}")" \
    || ! CREATED="$(jq -er '.created | select(type == "string" and length > 0)' \
        <<< "${LATEST}")" \
    || ! BUILD_NUMBER="$(jq -er '.build_number | select(type == "number")' \
        <<< "${LATEST}")"; then
    red "❌ Latest build-history entry lacks a valid tag, creation time, or build number"
    exit 1
fi
if [[ ! "${VERSION}" =~ ^[0-9]+\.[0-9]+\.[0-9]+(\.[0-9]+)?(-[0-9A-Za-z]+([.-][0-9A-Za-z]+)*)?$ ]]; then
    red "❌ Latest build-history entry has an unsafe image tag: ${VERSION}"
    exit 1
fi

info "Latest image: ${IMAGE_BASE}:${VERSION}  (build #${BUILD_NUMBER}, created ${CREATED})"

########################################
# Check if already archived
########################################
ARCHIVE="${DOCKER_ARCHIVE_DIR}/dar-backup-${VERSION}-docker-image.tar.gz"
CHECKSUM_FILE="${ARCHIVE}.sha256"

mkdir -p "${DOCKER_ARCHIVE_DIR}" \
    || { red "❌ Failed to create archive dir: ${DOCKER_ARCHIVE_DIR}"; exit 1; }

if [[ -f "${ARCHIVE}" ]]; then
    if ! gzip -t -- "${ARCHIVE}"; then
        red "❌ Existing Docker archive is corrupt: ${ARCHIVE}"
        exit 1
    fi
    if [[ -f "${CHECKSUM_FILE}" ]]; then
        checksum_line_count="$(wc -l < "${CHECKSUM_FILE}")"
        read -r expected_sha256 checksum_name checksum_extra < "${CHECKSUM_FILE}" || true
        if [[ "${checksum_line_count}" -ne 1 \
            || ! "${expected_sha256:-}" =~ ^[0-9a-f]{64}$ \
            || "${checksum_name:-}" != "$(basename "${ARCHIVE}")" \
            || -n "${checksum_extra:-}" ]]; then
            red "❌ Existing checksum file has invalid contents: ${CHECKSUM_FILE}"
            exit 1
        fi
        actual_sha256="$(sha256sum "${ARCHIVE}")"
        actual_sha256="${actual_sha256%% *}"
        if [[ "${actual_sha256}" != "${expected_sha256}" ]]; then
            red "❌ Existing Docker archive checksum does not match: ${ARCHIVE}"
            exit 1
        fi
    else
        archive_sha256="$(sha256sum "${ARCHIVE}")"
        archive_sha256="${archive_sha256%% *}"
        printf '%s  %s\n' "${archive_sha256}" "$(basename "${ARCHIVE}")" \
            > "${CHECKSUM_FILE}"
        info "Created missing checksum for existing archive: ${CHECKSUM_FILE}"
    fi
    green "✅ Existing archive verified: ${ARCHIVE}"
    exit 0
fi

########################################
# Pull from Docker Hub
########################################
green "Pulling ${IMAGE_BASE}:${VERSION} from Docker Hub..."
docker pull "${IMAGE_BASE}:${VERSION}" \
    || { red "❌ Failed to pull ${IMAGE_BASE}:${VERSION}"; exit 1; }

########################################
# Save and compress atomically
########################################
TEMP_ARCHIVE=""
TEMP_CHECKSUM=""
cleanup() {
    [[ -z "${TEMP_ARCHIVE}" ]] || rm -f -- "${TEMP_ARCHIVE}"
    [[ -z "${TEMP_CHECKSUM}" ]] || rm -f -- "${TEMP_CHECKSUM}"
}
trap cleanup EXIT

TEMP_ARCHIVE="$(mktemp "${DOCKER_ARCHIVE_DIR}/.dar-backup-${VERSION}.XXXXXX.tar.gz")"
TEMP_CHECKSUM="$(mktemp "${DOCKER_ARCHIVE_DIR}/.dar-backup-${VERSION}.XXXXXX.sha256")"

green "Saving and compressing to ${ARCHIVE}..."
if ! docker save "${IMAGE_BASE}:${VERSION}" | gzip > "${TEMP_ARCHIVE}"; then
    red "❌ Failed to save and compress ${IMAGE_BASE}:${VERSION}; no archive was published"
    exit 1
fi
if [[ ! -s "${TEMP_ARCHIVE}" ]]; then
    red "❌ Compressed Docker archive is empty; no archive was published"
    exit 1
fi
if ! gzip -t -- "${TEMP_ARCHIVE}"; then
    red "❌ Compressed Docker archive failed gzip validation; no archive was published"
    exit 1
fi

archive_sha256="$(sha256sum "${TEMP_ARCHIVE}")"
archive_sha256="${archive_sha256%% *}"
printf '%s  %s\n' "${archive_sha256}" "$(basename "${ARCHIVE}")" \
    > "${TEMP_CHECKSUM}"
mv -- "${TEMP_ARCHIVE}" "${ARCHIVE}"
TEMP_ARCHIVE=""
mv -- "${TEMP_CHECKSUM}" "${CHECKSUM_FILE}"
TEMP_CHECKSUM=""

green "✅ Saved and verified: ${ARCHIVE} ($(du -h "${ARCHIVE}" | cut -f1))"
green "✅ SHA-256: ${archive_sha256}"
