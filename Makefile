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
# Usage examples:
# ---------------
# make dev-nuke
# make IMAGE=dar-backup:dev test-nobuild
# make FINAL_VERSION=0.9.9-rc1 final



# ================================
# Configuration
# ================================

SHELL := /bin/bash

# Default values
DOCKER ?= docker
FINAL_VERSION ?= dev
IMAGE_VERSION_FILE ?= IMAGE_VERSION

UBUNTU_VERSION ?= 24.04
UBUNTU_DIGEST ?=
UBUNTU_DIGEST_FILE ?= build/ubuntu-digest
IMAGE_LICENSE_SHA256 ?= 3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986


DAR_BACKUP_VERSION ?= $(shell cat DAR_BACKUP_VERSION)
DAR_VERSION ?= $(shell cat DAR_VERSION)
DAR_BACKUP_INSTALL_SOURCE ?= pypi
DAR_BACKUP_LOCAL_DIST ?=
DAR_BACKUP_LOCAL_WHEEL ?= dar_backup-$(DAR_BACKUP_VERSION)-py3-none-any.whl

ifeq ($(DAR_BACKUP_INSTALL_SOURCE),local)
DAR_BACKUP_CONTEXT_ARGS = --build-context dar_backup_dist="$(DAR_BACKUP_LOCAL_DIST)"
else
DAR_BACKUP_CONTEXT_ARGS =
endif

FINAL_IMAGE_NAME = dar-backup
DOCKERHUB_REPO = per2jensen/dar-backup


IMAGE_REF        ?= $(FINAL_IMAGE_NAME):$(FINAL_VERSION)
IMAGE            ?= dar-backup:dev
GRYPE_FAIL_ON    ?= High
GRYPE_DB_AUTO_UPDATE ?= false
GRYPE_CACHE_DIR  ?= $(HOME)/.cache/grype
ANCHORE_TOOL_VERSIONS_FILE ?= config/anchore-tool-versions.env
ANCHORE_TOOLS_BIN_DIR ?= $(HOME)/.local/bin

-include $(ANCHORE_TOOL_VERSIONS_FILE)
export PATH := $(ANCHORE_TOOLS_BIN_DIR):$(PATH)

SBOM_FILE := sbom-$(FINAL_IMAGE_NAME)-$(FINAL_VERSION).cyclonedx.json
GRYPE_TXT := grype-report-$(FINAL_IMAGE_NAME)-$(FINAL_VERSION).txt
GRYPE_SARIF := grype-$(FINAL_IMAGE_NAME)-$(FINAL_VERSION).sarif


# === Build log configuration ===
BUILD_LOG_DIR ?= doc
BUILD_LOG_FILE ?= build-history.json
BUILD_LOG_PATH := $(BUILD_LOG_DIR)/$(BUILD_LOG_FILE)

# near the top of your Makefile, right after you define UBUNTU_VERSION, etc.
LABEL_ARGS = \
  --label org.opencontainers.image.base.name=ubuntu \
  --label org.opencontainers.image.base.version="$(UBUNTU_VERSION)" \
  --label org.opencontainers.image.source="https://github.com/per2jensen/dar-backup-image" \
  --label org.opencontainers.image.created="$(shell date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --label org.opencontainers.image.revision="$(shell git rev-parse HEAD)" \
  --label org.opencontainers.image.title="dar-backup" \
  --label org.opencontainers.image.version="$(FINAL_VERSION)" \
  --label org.opencontainers.image.description="Container for DAR-based backups using \`dar-backup\`" \
  --label org.opencontainers.image.documentation="https://github.com/per2jensen/dar-backup-image/blob/main/README.md" \
  --label org.opencontainers.image.url="https://hub.docker.com/r/per2jensen/dar-backup" \
  --label org.opencontainers.image.licenses="GPL-3.0-or-later" \
  --label org.opencontainers.image.authors="Per Jensen <dar-backup@pm.me>" \
  --label org.opencontainers.image.ref.name="$(DOCKERHUB_REPO):$(FINAL_VERSION)" \
  --label org.dar-backup.documentation.command="docs" \
  --label org.dar-backup.documentation.path="/usr/share/doc/dar-backup" \
  --label org.dar-backup.install-source="$(DAR_BACKUP_INSTALL_SOURCE)" \
  --label org.dar-backup.version="$(DAR_BACKUP_VERSION)" \
  --label org.dar.version="$(DAR_VERSION)"



# ================================
# Targets
# ================================

.PHONY: all all-dev dev-rebuild final final-noscan refresh-final-noscan _finalize-image release clean clean-all push tag login dev dev-clean labels help \
	check_version check-release-image-version check-refresh-image-version test test-integration all-dev \
	check-docker-creds test-log-pushed-build-json sbom-sarif sbom-sarif-docker install-tools \
	grype-db-status grype-db-update scan-final verify-labels validate-dar-backup-install \
	check-publish-install-source check-anchore-tool-versions verify-dev-image


check_version:
	@if [ -z "$(FINAL_VERSION)" ]; then \
		echo "❌ ERROR: You must set FINAL_VERSION explicitly."; \
		echo "   Example: make FINAL_VERSION=1.0.0 final"; \
		exit 1; \
	fi
	@if [ -z "$(DAR_BACKUP_VERSION)" ]; then \
		echo "❌ ERROR: You must set DAR_BACKUP_VERSION explicitly."; \
		echo "   Example: make DAR_BACKUP_VERSION=1.0.0 final"; \
		exit 1; \
	fi
	@if [ -z "$(DAR_VERSION)" ]; then \
		echo "❌ ERROR: You must set DAR_VERSION explicitly."; \
		echo "   Example: make DAR_VERSION=2.7.19 final"; \
		exit 1; \
	fi


# Release outputs must use the exact canonical version committed in source.
# FINAL_VERSION=dev remains convenient for development targets but cannot pass
# this publication guard.
check-release-image-version: check_version
	@python3 scripts/validate_image_version.py release \
		--image-version-file "$(IMAGE_VERSION_FILE)" \
		--final-version "$(FINAL_VERSION)"


# Weekly refreshes derive their base from the latest build-history entry, not
# IMAGE_VERSION. The selected stable x.y.z base may produce x.y.z-N.
check-refresh-image-version: check_version
	@python3 scripts/validate_image_version.py refresh \
		--base-version "$(BASE_VERSION)" \
		--final-version "$(FINAL_VERSION)"


validate-dar-backup-install:
	@set -euo pipefail; \
	case "$(DAR_BACKUP_INSTALL_SOURCE)" in \
	  pypi) \
	    if [ -n "$(DAR_BACKUP_LOCAL_DIST)" ]; then \
	      echo "❌ DAR_BACKUP_LOCAL_DIST is only valid when DAR_BACKUP_INSTALL_SOURCE=local" >&2; \
	      exit 2; \
	    fi; \
	    ;; \
	  local) \
	    if [ -z "$(DAR_BACKUP_LOCAL_DIST)" ]; then \
	      echo "❌ DAR_BACKUP_LOCAL_DIST is required for a local build" >&2; \
	      exit 2; \
	    fi; \
	    if [ ! -d "$(DAR_BACKUP_LOCAL_DIST)" ]; then \
	      echo "❌ Local distribution directory does not exist: $(DAR_BACKUP_LOCAL_DIST)" >&2; \
	      exit 2; \
	    fi; \
	    case "$(DAR_BACKUP_LOCAL_WHEEL)" in \
	      ''|*[!A-Za-z0-9._+-]*) \
	        echo "❌ DAR_BACKUP_LOCAL_WHEEL must be a safe wheel basename" >&2; \
	        exit 2; \
	        ;; \
	    esac; \
	    python3 scripts/validate_dar_backup_wheel.py \
	      --wheel "$(DAR_BACKUP_LOCAL_DIST)/$(DAR_BACKUP_LOCAL_WHEEL)" \
	      --expected-version "$(DAR_BACKUP_VERSION)" >/dev/null; \
	    ;; \
	  *) \
	    echo "❌ DAR_BACKUP_INSTALL_SOURCE must be 'pypi' or 'local'" >&2; \
	    exit 2; \
	    ;; \
	esac
sbom-sarif: install-tools
	@echo "🔍 SBOM + scan for $(IMAGE_REF)"
	@mkdir -p "$(GRYPE_CACHE_DIR)"
	@set -e; \
	# Check DB status and force update if missing/invalid/expired
	DBSTAT="$$( GRYPE_CHECK_FOR_APP_UPDATE=false GRYPE_DB_CACHE_DIR="$(GRYPE_CACHE_DIR)" grype db status 2>&1 || true )"; \
	echo "$$DBSTAT"; \
	if [ "$(GRYPE_DB_AUTO_UPDATE)" = "true" ] || echo "$$DBSTAT" | grep -Eq 'Status:\s*invalid|does not exist|no vulnerability database|failed to load|max allowed age'; then \
	  echo "🔄 Updating Grype DB…"; \
	  GRYPE_CHECK_FOR_APP_UPDATE=false GRYPE_DB_CACHE_DIR="$(GRYPE_CACHE_DIR)" grype db update; \
	fi; \
	GRYPE_CHECK_FOR_APP_UPDATE=false GRYPE_DB_CACHE_DIR="$(GRYPE_CACHE_DIR)" grype db status || true

	# Generate SBOM (CycloneDX JSON)
	@SYFT_CHECK_FOR_APP_UPDATE=false syft "docker:$(IMAGE_REF)" -o cyclonedx-json > "$(SBOM_FILE)"

	# Sanity checks on SBOM
	@test -s "$(SBOM_FILE)"
	@wc -c "$(SBOM_FILE)"
	@grep -q '"components"' "$(SBOM_FILE)" || { echo 'SBOM missing "components"'; exit 1; }

	# Grype scan from SBOM: table (fail on High/Critical) + SARIF, retry once if DB error
	@set -euo pipefail; \
	export GRYPE_CHECK_FOR_APP_UPDATE=false; \
	export GRYPE_DB_AUTO_UPDATE=$(GRYPE_DB_AUTO_UPDATE); \
	export GRYPE_DB_CACHE_DIR="$(GRYPE_CACHE_DIR)"; \
	grype "sbom:$(SBOM_FILE)" -o table --fail-on "$(GRYPE_FAIL_ON)" | tee "$(GRYPE_TXT)" || { \
	  echo "⚠️  Grype scan failed. Forcing DB update and retrying once…"; \
	  grype db update; \
	  grype "sbom:$(SBOM_FILE)" -o table --fail-on "$(GRYPE_FAIL_ON)" | tee "$(GRYPE_TXT)"; \
	}; \
	grype "sbom:$(SBOM_FILE)" -o sarif > "$(GRYPE_SARIF)"

	@echo "✅ Outputs:"
	@ls -lh "$(SBOM_FILE)" "$(GRYPE_TXT)" "$(GRYPE_SARIF)"




# Docker-based SBOM + SARIF scan (alternative to the native sbom-sarif target).
# Uses GRYPE_CACHE_DIR (defined at the top of this Makefile) for the Grype DB
# volume mount — consistent with sbom-sarif and scan-final.
sbom-sarif-docker: check_version
	@echo "🔍 Generating SBOM and SARIF for $(FINAL_IMAGE_NAME):$(FINAL_VERSION)"
	@mkdir -p "$(GRYPE_CACHE_DIR)"

	# SBOM via Syft (no network version-check)
	@$(DOCKER) run --rm \
	  -e SYFT_CHECK_FOR_APP_UPDATE=false \
	  -v /var/run/docker.sock:/var/run/docker.sock \
	  anchore/syft:$(SYFT_VERSION) \
	  $(FINAL_IMAGE_NAME):$(FINAL_VERSION) -o cyclonedx-json > $(SBOM)

	# Vulnerability scan via Grype
	# - Disable app-update ping; persist DB cache to avoid re-downloads
	@$(DOCKER) run --rm \
	  -e GRYPE_CHECK_FOR_APP_UPDATE=false \
	  -v /var/run/docker.sock:/var/run/docker.sock \
	  -v $(PWD)/$(GRYPE_CACHE_DIR):/home/anchore/.cache \
	  anchore/grype:$(GRYPE_VERSION) \
	  $(FINAL_IMAGE_NAME):$(FINAL_VERSION) -o sarif > $(SARIF)

	@echo "✅ Generated files:"
	@ls -lh $(SBOM) $(SARIF)



install-tools:
	@python3 scripts/anchore_tools.py \
	  --versions-file "$(ANCHORE_TOOL_VERSIONS_FILE)" \
	  install --bin-dir "$(ANCHORE_TOOLS_BIN_DIR)"

check-anchore-tool-versions:
	@python3 scripts/anchore_tools.py \
	  --versions-file "$(ANCHORE_TOOL_VERSIONS_FILE)" \
	  check-latest

grype-db-status:
	@GRYPE_CHECK_FOR_APP_UPDATE=false grype db status

grype-db-update:
	@GRYPE_CHECK_FOR_APP_UPDATE=false grype db update







# Base image target is now a no-op (we only have one Dockerfile now)
base:
	@echo "Skipping separate base image build (single Dockerfile in use)"


release:
	@echo "ERROR: remote releases must be published through the Manual Docker Release workflow" >&2
	@echo "Optional local finalization and scanning remain available through 'make final'." >&2
	@exit 2

# ================================
# Dev build
# ================================

all-dev: dev

# Default clean: keeps Ubuntu/base layers for faster rebuilds
dev-clean: check_version
	@echo "⚡ Fast clean:  Removing local $(FINAL_VERSION) image and old dangling layers..."
	-$(DOCKER) rmi -f dar-backup:$(FINAL_VERSION) || true
	-$(DOCKER) image prune -f
	@echo "Tip: Use 'make dev-nuke' for a full rebuild without cache."
	@echo "Rebuilding image (via 'make dev' to preserve labels)..."
	$(MAKE) dev

# Full nuke: deletes *all* caches and forces a completely fresh build.
# Note: passes DAR_BACKUP_VERSION (not VERSION) to match the Dockerfile ARG name,
# and includes LABEL_ARGS so the nuked image is labeled consistently with 'make dev'.
dev-nuke: validate-dar-backup-install
	@echo "🧨 Full nuke: Pruning ALL Docker build caches and images (this may take a while)..."
	@if ! $(DOCKER) builder prune -a -f; then \
	  echo "ERROR: unable to prune Docker build cache; refusing to claim a clean build" >&2; \
	  exit 2; \
	fi
	@if ! $(DOCKER) image prune -a -f; then \
	  echo "ERROR: unable to prune unused Docker images; refusing to claim a clean build" >&2; \
	  exit 2; \
	fi
	@echo "Rebuilding image from scratch..."
	@set -euo pipefail; \
	mkdir -p "$(dir $(UBUNTU_DIGEST_FILE))"; \
	rm -f "$(UBUNTU_DIGEST_FILE)"; \
	ubuntu_digest="$$(scripts/resolve_ubuntu_digest.sh \
	  "$(DOCKER)" "ubuntu:$(UBUNTU_VERSION)" "$(UBUNTU_DIGEST)")"; \
	package_sha="not-applicable"; \
	if [ "$(DAR_BACKUP_INSTALL_SOURCE)" = "local" ]; then \
	  package_sha="$$(python3 scripts/validate_dar_backup_wheel.py \
	    --wheel "$(DAR_BACKUP_LOCAL_DIST)/$(DAR_BACKUP_LOCAL_WHEEL)" \
	    --expected-version "$(DAR_BACKUP_VERSION)")"; \
	fi; \
	$(DOCKER) build --no-cache -f Dockerfile \
	  $(DAR_BACKUP_CONTEXT_ARGS) \
	  --build-arg DAR_BACKUP_VERSION="$(DAR_BACKUP_VERSION)" \
	  --build-arg DAR_BACKUP_INSTALL_SOURCE="$(DAR_BACKUP_INSTALL_SOURCE)" \
	  --build-arg DAR_BACKUP_LOCAL_WHEEL="$(DAR_BACKUP_LOCAL_WHEEL)" \
	  --build-arg DAR_BACKUP_LOCAL_WHEEL_SHA256="$$package_sha" \
	  --build-arg DAR_VERSION="$(DAR_VERSION)" \
	  --build-arg UBUNTU_DIGEST="$$ubuntu_digest" \
	  $(LABEL_ARGS) \
	  --label org.opencontainers.image.base.digest="$$ubuntu_digest" \
	  --label org.dar-backup.wheel.sha256="$$package_sha" \
	  -t dar-backup:$(FINAL_VERSION) .; \
	printf '%s\n' "$$ubuntu_digest" > "$(UBUNTU_DIGEST_FILE)"


dev-rebuild:
	@$(MAKE) --no-print-directory dev-nuke


# Dev image build (always produce a fully labeled dar-backup:dev)
dev: validate validate-dar-backup-install
	@echo "Building development image (cached & labeled): $(FINAL_VERSION)"
	@set -euo pipefail; \
	mkdir -p "$(dir $(UBUNTU_DIGEST_FILE))"; \
	rm -f "$(UBUNTU_DIGEST_FILE)"; \
	ubuntu_digest="$$(scripts/resolve_ubuntu_digest.sh \
	  "$(DOCKER)" "ubuntu:$(UBUNTU_VERSION)" "$(UBUNTU_DIGEST)")"; \
	package_sha="not-applicable"; \
	if [ "$(DAR_BACKUP_INSTALL_SOURCE)" = "local" ]; then \
	  package_sha="$$(python3 scripts/validate_dar_backup_wheel.py \
	    --wheel "$(DAR_BACKUP_LOCAL_DIST)/$(DAR_BACKUP_LOCAL_WHEEL)" \
	    --expected-version "$(DAR_BACKUP_VERSION)")"; \
	fi; \
	$(DOCKER) build -f Dockerfile \
	  $(DAR_BACKUP_CONTEXT_ARGS) \
	  --build-arg VERSION="$(FINAL_VERSION)" \
	  --build-arg DAR_VERSION="$(DAR_VERSION)" \
	  --build-arg DAR_BACKUP_VERSION="$(DAR_BACKUP_VERSION)" \
	  --build-arg DAR_BACKUP_INSTALL_SOURCE="$(DAR_BACKUP_INSTALL_SOURCE)" \
	  --build-arg DAR_BACKUP_LOCAL_WHEEL="$(DAR_BACKUP_LOCAL_WHEEL)" \
	  --build-arg DAR_BACKUP_LOCAL_WHEEL_SHA256="$$package_sha" \
	  --build-arg UBUNTU_DIGEST="$$ubuntu_digest" \
	  $(LABEL_ARGS) \
	  --label org.opencontainers.image.base.digest="$$ubuntu_digest" \
	  --label org.dar-backup.wheel.sha256="$$package_sha" \
	  -t dar-backup:dev \
	  .; \
	printf '%s\n' "$$ubuntu_digest" > "$(UBUNTU_DIGEST_FILE)"



final: check-release-image-version
	@$(MAKE) --no-print-directory _finalize-image

	@echo
	@echo "🔍 Running scans…"
	@$(MAKE) scan-final

	@echo
	@echo "📊 Image layer size report (for audit):"
	@$(MAKE) FINAL_VERSION=$(FINAL_VERSION) size-report


final-noscan: check-release-image-version
	@$(MAKE) --no-print-directory _finalize-image

	@echo
	@echo "📊 Image layer size report (for audit):"
	@$(MAKE) FINAL_VERSION=$(FINAL_VERSION) size-report
	@echo "ℹ️  Scan skipped — SBOM and Grype will run as dedicated workflow steps."


refresh-final-noscan: check-refresh-image-version
	@$(MAKE) --no-print-directory _finalize-image

	@echo
	@echo "📊 Image layer size report (for audit):"
	@$(MAKE) FINAL_VERSION=$(FINAL_VERSION) size-report
	@echo "ℹ️  Scan skipped — SBOM and Grype will run as dedicated workflow steps."


# Internal shared implementation. Publication entry points above must complete
# their policy guard before invoking this target.
_finalize-image: $(if $(strip $(BASE_VERSION)),check-refresh-image-version,check-release-image-version)
	@echo "🔎 Verifying dar-backup:dev provenance and component versions…"
	@if ! $(DOCKER) image inspect dar-backup:dev >/dev/null 2>&1; then \
	  echo "❌ dar-backup:dev not found — run 'make dev' first"; exit 1; \
	fi
	@$(MAKE) --no-print-directory verify-dev-image

	@echo "🧩 Creating release image with corrected labels (no rebuild)…"
	@set -euo pipefail; \
	CID=""; \
	cleanup_container() { \
	  if [ -n "$$CID" ]; then \
	    $(DOCKER) rm -f "$$CID" >/dev/null 2>&1 \
	      || echo "WARNING: unable to remove temporary container $$CID" >&2; \
	  fi; \
	}; \
	trap cleanup_container EXIT; \
	CID="$$( $(DOCKER) create dar-backup:dev )"; \
	$(DOCKER) commit \
	  --change 'LABEL org.opencontainers.image.version=$(FINAL_VERSION)' \
	  --change 'LABEL org.opencontainers.image.ref.name=$(DOCKERHUB_REPO):$(FINAL_VERSION)' \
	  "$$CID" dar-backup:$(FINAL_VERSION) >/dev/null; \
	$(DOCKER) rm "$$CID" >/dev/null; \
	CID=""; \
	trap - EXIT

	@$(DOCKER) tag dar-backup:$(FINAL_VERSION) $(DOCKERHUB_REPO):$(FINAL_VERSION)

	@echo
	@echo "🔎 Verifying CLI version…"
	@$(MAKE) verify-cli-version

	@echo
	@echo "🔍 Verifying OCI image labels…"
	@$(MAKE) verify-labels

verify-dev-image:
	@set -euo pipefail; \
	if [ ! -s "$(UBUNTU_DIGEST_FILE)" ]; then \
	  echo "ERROR: Ubuntu digest record is missing: $(UBUNTU_DIGEST_FILE); rebuild dar-backup:dev" >&2; \
	  exit 2; \
	fi; \
	ubuntu_digest="$$(cat "$(UBUNTU_DIGEST_FILE)")"; \
	revision="$$(git rev-parse HEAD)"; \
	wheel_sha="not-applicable"; \
	if [ "$(DAR_BACKUP_INSTALL_SOURCE)" = "local" ]; then \
	  wheel_sha="$$(python3 scripts/validate_dar_backup_wheel.py \
	    --wheel "$(DAR_BACKUP_LOCAL_DIST)/$(DAR_BACKUP_LOCAL_WHEEL)" \
	    --expected-version "$(DAR_BACKUP_VERSION)")"; \
	fi; \
	DOCKER="$(DOCKER)" scripts/verify_image_metadata.sh \
	  dar-backup:dev "$$revision" dev "$(DAR_BACKUP_VERSION)" \
	  "$(DAR_VERSION)" "$$ubuntu_digest" "$(DAR_BACKUP_INSTALL_SOURCE)" "$$wheel_sha"

verify-labels:
	@echo "🔍 Verifying exact OCI image metadata on $(FINAL_IMAGE_NAME):$(FINAL_VERSION)"
	@set -euo pipefail; \
	if [ ! -s "$(UBUNTU_DIGEST_FILE)" ]; then \
	  echo "ERROR: Ubuntu digest record is missing: $(UBUNTU_DIGEST_FILE); rebuild dar-backup:dev" >&2; \
	  exit 2; \
	fi; \
	ubuntu_digest="$$(cat "$(UBUNTU_DIGEST_FILE)")"; \
	revision="$$(git rev-parse HEAD)"; \
	wheel_sha="not-applicable"; \
	if [ "$(DAR_BACKUP_INSTALL_SOURCE)" = "local" ]; then \
	  wheel_sha="$$(python3 scripts/validate_dar_backup_wheel.py \
	    --wheel "$(DAR_BACKUP_LOCAL_DIST)/$(DAR_BACKUP_LOCAL_WHEEL)" \
	    --expected-version "$(DAR_BACKUP_VERSION)")"; \
	fi; \
	DOCKER="$(DOCKER)" scripts/verify_image_metadata.sh \
	  "$(FINAL_IMAGE_NAME):$(FINAL_VERSION)" "$$revision" "$(FINAL_VERSION)" \
	  "$(DAR_BACKUP_VERSION)" "$(DAR_VERSION)" "$$ubuntu_digest" \
	  "$(DAR_BACKUP_INSTALL_SOURCE)" "$$wheel_sha"; \
	DOCKER="$(DOCKER)" scripts/verify_image_license.sh \
	  "$(FINAL_IMAGE_NAME):$(FINAL_VERSION)" "$(IMAGE_LICENSE_SHA256)"




# SBOM (Syft) + SARIF (Grype)
SBOM := $(FINAL_IMAGE_NAME)-$(FINAL_VERSION)-sbom.cyclonedx.json
SARIF := $(FINAL_IMAGE_NAME)-$(FINAL_VERSION)-grype.sarif
# Note: Grype DB cache is GRYPE_CACHE_DIR, defined at the top of this Makefile.


# ================================
# SBOM + Grype scan for FINAL image (pre-push gate)
# ================================
scan-final: install-tools
	@if [ -z "$(FINAL_VERSION)" ]; then echo "❌ FINAL_VERSION not set"; exit 1; fi
	@if [ -z "$(FINAL_IMAGE_NAME)" ]; then echo "❌ FINAL_IMAGE_NAME not set"; exit 1; fi
	@if ! $(DOCKER) image inspect $(FINAL_IMAGE_NAME):$(FINAL_VERSION) >/dev/null 2>&1; then \
	  echo "❌ Image $(FINAL_IMAGE_NAME):$(FINAL_VERSION) not found. Run 'make final' first."; exit 1; \
	fi
	@echo "🔍 SBOM + scan for $(FINAL_IMAGE_NAME):$(FINAL_VERSION)"
	@mkdir -p "$(GRYPE_CACHE_DIR)"
	@{ \
	  set -e; \
	  export GRYPE_CHECK_FOR_APP_UPDATE=false; \
	  export GRYPE_DB_CACHE_DIR="$(GRYPE_CACHE_DIR)"; \
	  DBSTAT="$$( grype db status 2>&1 || true )"; \
	  echo "$$DBSTAT"; \
	  if [ "$(GRYPE_DB_AUTO_UPDATE)" = "true" ] || echo "$$DBSTAT" | grep -Eq 'Status:\s*invalid|does not exist|no vulnerability database|failed to load|max allowed age'; then \
	    echo "🔄 Updating Grype DB…"; \
	    grype db update; \
	  fi; \
	  grype db status || true; \
	}



	# Generate SBOM (CycloneDX JSON) against the *local* final image
	@SYFT_CHECK_FOR_APP_UPDATE=false syft "docker:$(FINAL_IMAGE_NAME):$(FINAL_VERSION)" -o cyclonedx-json > "$(SBOM_FILE)"

	# Sanity checks on SBOM
	@test -s "$(SBOM_FILE)"
	@wc -c "$(SBOM_FILE)"
	@grep -q '"components"' "$(SBOM_FILE)" || { echo 'SBOM missing "components"'; exit 1; }

	# Grype scan from SBOM: table (fail on High/Critical) + SARIF artifact
	@set -euo pipefail; \
	export GRYPE_CHECK_FOR_APP_UPDATE=false; \
	export GRYPE_DB_AUTO_UPDATE=$(GRYPE_DB_AUTO_UPDATE); \
	export GRYPE_DB_CACHE_DIR="$(GRYPE_CACHE_DIR)"; \
	grype "sbom:$(SBOM_FILE)" -o table --fail-on "$(GRYPE_FAIL_ON)" | tee "$(GRYPE_TXT)" || { \
	  echo "⚠️  Grype scan failed. Forcing DB update and retrying once…"; \
	  grype db update; \
	  grype "sbom:$(SBOM_FILE)" -o table --fail-on "$(GRYPE_FAIL_ON)" | tee "$(GRYPE_TXT)"; \
	}; \
	grype "sbom:$(SBOM_FILE)" -o sarif > "$(GRYPE_SARIF)"


	@echo "✅ Outputs:"
	@ls -lh "$(SBOM_FILE)" "$(GRYPE_TXT)" "$(GRYPE_SARIF)"

	@echo "🛡️  Vulnerability gate passed for $(FINAL_IMAGE_NAME):$(FINAL_VERSION)"




verify-cli-version:
	@echo "🔎 Verifying 'dar-backup --version' matches DAR_BACKUP_VERSION ($(DAR_BACKUP_VERSION))"
	@set -euo pipefail; \
	if ! version_output="$$( $(DOCKER) run --rm --entrypoint dar-backup \
	  "$(FINAL_IMAGE_NAME):$(FINAL_VERSION)" --version 2>&1 )"; then \
	  echo "ERROR: unable to run dar-backup --version in $(FINAL_IMAGE_NAME):$(FINAL_VERSION): $$version_output" >&2; \
	  exit 2; \
	fi; \
	actual_version="$$(printf '%s\n' "$$version_output" | awk 'NR == 1 { print $$2; exit }')"; \
	if [ "$$actual_version" != "$(DAR_BACKUP_VERSION)" ]; then \
	  echo "ERROR: CLI version mismatch on $(FINAL_IMAGE_NAME):$(FINAL_VERSION)" >&2; \
	  echo "       expected: '$(DAR_BACKUP_VERSION)'" >&2; \
	  echo "       actual:   '$${actual_version:-missing}'" >&2; \
	  echo "       output:   '$$version_output'" >&2; \
	  exit 2; \
	fi; \
	echo "✅ dar-backup --version is correct: $(DAR_BACKUP_VERSION)"


log-pushed-build-json:
	@echo "ERROR: release metadata is written only by the Manual Docker Release workflow" >&2
	@exit 2



update-readme-version:
	@echo "🔄 Updating version examples in README.md to VERSION=$(FINAL_VERSION)"
	@if sed -i -E "s/VERSION=[0-9]+\.[0-9]+\.[0-9]+(-[a-zA-Z0-9]+)?;/VERSION=$(FINAL_VERSION);/" README.md; then \
	  if ! git diff --quiet README.md; then \
	    git add README.md; \
	    git commit -m "examples updated to VERSION=$(FINAL_VERSION)"; \
	    echo "✅ README.md updated and committed"; \
	  else \
	    echo "ℹ️ No changes to commit — README.md already up to date"; \
	  fi; \
	else \
	  echo "❌ sed command failed — README.md not updated"; \
	  exit 1; \
	fi


test-log-pushed-build-json:
	@echo "🧪 Testing log-pushed-build-json with mock values..."
	@mkdir -p ./logs
	@test -f ./logs/build-history.json || echo "[]" > ./logs/build-history.json
	$(eval FINAL_VERSION     := test-tag)
	$(eval DAR_BACKUP_VERSION := 0.99.0-test)
	$(eval DAR_VERSION        := 2.7.21-test)
	$(eval GIT_REV           := mockrev123)
	$(eval DAR_BACKUP_DATE   := 2025-07-13T00:00:00Z)
	$(eval DIGEST_ONLY       := sha256:deadbeef1234567890)
	$(eval IMAGE_ID          := sha256:cafebabef00d1234567890)
	$(eval MOCK_UBUNTU_DIGEST := sha256:mockubuntudigest1234567890)
	$(eval BUILD_LOG_PATH    := ./logs/build-history.json)
	$(eval BUILD_NUMBER      := $(shell jq length ./logs/build-history.json 2>/dev/null || echo 0))
	@export PYTHONPATH="$$PYTHONPATH:scripts"; \
	python3 scripts/update_build_log.py \
	  --log              ./logs/build-history.json \
	  --build-number     $(BUILD_NUMBER) \
	  --version          $(FINAL_VERSION) \
	  --base             "ubuntu:24.04" \
	  --base-image-digest "$(MOCK_UBUNTU_DIGEST)" \
	  --git-rev          $(GIT_REV) \
	  --created          "$(DAR_BACKUP_DATE)" \
	  --url              "https://hub.docker.com/layers/per2jensen/dar-backup/$(FINAL_VERSION)/images/$(DIGEST_ONLY)" \
	  --digest           "$(DIGEST_ONLY)" \
	  --image-id         "$(IMAGE_ID)" \
	  --dar-backup-version "$(DAR_BACKUP_VERSION)" \
	  --dar-version      "$(DAR_VERSION)"
	@echo "✅ Test entry added:"
	@jq '.[-1]' ./logs/build-history.json


commit-log:
	@if [ ! -f $(BUILD_LOG_PATH) ]; then \
		echo "❌ Refusing to commit: $(BUILD_LOG_PATH) does not exist."; \
		exit 1; \
	fi
	@git add -f $(BUILD_LOG_PATH)  # Force re-adding if previously deleted
	@CHANGES=$$(git status --porcelain $(BUILD_LOG_PATH)); \
	if [ -n "$$CHANGES" ]; then \
		git commit -m "📦 Add build log entry for v$(FINAL_VERSION) (dar-backup v$(DAR_BACKUP_VERSION))"; \
	else \
		echo "ℹ️  No changes to $(BUILD_LOG_PATH) to commit."; \
	fi


test: all-dev
	@echo "Running pytest (full suite)..."
	@FINAL_VERSION=$${FINAL_VERSION:-dev}; \
	IMAGE=dar-backup:$${FINAL_VERSION} \
	pytest -s -v $(PYTEST_ARGS) tests/


test-nobuild:
	@echo "Running pytest (full suite)..."
	@if [ -z "$(IMAGE)" ]; then \
	  echo "ERROR: IMAGE must be a non-empty image reference" >&2; \
	  exit 2; \
	fi
	@echo "Testing image: $(IMAGE)"
	@$(DOCKER) image inspect "$(IMAGE)" \
	  --format 'Image ID: {{.Id}} | Repo digests: {{json .RepoDigests}} | Revision: {{index .Config.Labels "org.opencontainers.image.revision"}} | Version: {{index .Config.Labels "org.opencontainers.image.version"}}'
	@set -euo pipefail; \
	if ! pytest_help="$$(pytest --help 2>&1)"; then \
	  echo "ERROR: pytest is unavailable or failed while loading its plugins: $$pytest_help" >&2; \
	  exit 2; \
	fi; \
	report_args=(); \
	if [[ "$$pytest_help" == *"--json-report"* ]]; then \
	  report_args=(--json-report --json-report-file=pytest-report.json); \
	else \
	  echo "INFO: pytest-json-report is not installed; continuing without pytest-report.json"; \
	fi; \
	IMAGE="$(IMAGE)" pytest "$${report_args[@]}" $(PYTEST_ARGS) tests/

# Test using a pulled image (skips local build)
test-pulled:
	@if [ -z "$(IMAGE)" ]; then \
		echo "❌ IMAGE must be specified, e.g. 'make IMAGE=per2jensen/dar-backup:0.5.13 test-pulled'"; \
		exit 1; \
	fi
	@echo "🔄 Pulling latest image from Docker Hub: $(IMAGE)"
	@$(DOCKER) pull $(IMAGE)
	@echo "▶ Running tests using $(IMAGE) (no local build)"
	@IMAGE=$(IMAGE) pytest -s -v $(PYTEST_ARGS) tests/


test-integration: all-dev test
	@echo "✅ Integration (pytest) passed"



clean:
	@if [ -z "$(FINAL_VERSION)" ]; then \
		echo "❌ FINAL_VERSION not set"; exit 1; \
	fi
	-$(DOCKER) rmi -f $(BASE_IMAGE_NAME):$(UBUNTU_VERSION)-$(FINAL_VERSION) || true
	-$(DOCKER) rmi -f $(BASE_LATEST_TAG) || true
	-$(DOCKER) rmi -f $(FINAL_IMAGE_NAME):$(FINAL_VERSION) || true



# Remove all images related to dar-backup
clean-all:
	@echo "Cleaning all dangling images..."
	-$(DOCKER) images -f "dangling=true"
	-$(DOCKER) image prune -f
	@echo "Cleaning all dar-backup images..."
	-$(DOCKER) images --format "{{.Repository}}:{{.Tag}} {{.ID}}" | grep '^dar-backup' | awk '{print $2}' | xargs -r docker rmi -f


check-docker-creds:
	@missing=0; \
	if [ -z "$(DOCKER_USER)" ]; then \
	  echo "❌ Missing environment variable: DOCKER_USER"; \
	  missing=1; \
	fi; \
	if [ -z "$(DOCKER_TOKEN)" ]; then \
	  echo "❌ Missing environment variable: DOCKER_TOKEN"; \
	  missing=1; \
	fi; \
	if [ "$$missing" -eq 1 ]; then \
	  echo "💡 Please export both DOCKER_USER and DOCKER_TOKEN"; \
	  exit 1; \
	fi; \
	echo "🔐 Docker credentials are present."


check-publish-install-source:
	@install_source="$$($(DOCKER) inspect -f '{{ index .Config.Labels "org.dar-backup.install-source" }}' \
	  $(DOCKERHUB_REPO):$(FINAL_VERSION) 2>/dev/null)"; \
	if [ "$$install_source" != "pypi" ]; then \
	  echo "❌ Refusing to publish $(DOCKERHUB_REPO):$(FINAL_VERSION): installation source is '$${install_source:-missing}', not 'pypi'." >&2; \
	  exit 2; \
	fi


push:
	@echo "ERROR: remote images are published only by the Manual Docker Release workflow" >&2
	@exit 2



# Show image version, Git revision, and build timestamp
print-version:
	@echo "🔖 dar-backup image metadata"
	@echo "────────────────────────────────────────────"
	@echo " Ubuntu Base   : $(UBUNTU_VERSION)"
	@echo " Image Version : $(FINAL_VERSION)"
	@echo " Git Revision  : $(GIT_REV)"
	@echo " Build Time    : $(DAR_BACKUP_DATE)"


# check for docker and jq installation
validate:
	@command -v jq >/dev/null || { echo "❌ jq not found"; exit 1; }
	@command -v docker >/dev/null || { echo "❌ docker not found"; exit 1; }



size-report:
	@echo "🔍 Image size report for dar-backup:$(FINAL_VERSION)"
	@echo "───────────────────────────────────────────────"
	@$(DOCKER) images dar-backup:$(FINAL_VERSION) --format "Total Size: {{.Size}} (ID: {{.ID}})"
	@echo
	@echo "Largest layers (all sizes in MB):"
	@scripts/size-report.sh dar-backup:$(FINAL_VERSION)
	@echo
	@echo "Tip: Use 'make dev-nuke' for a fully fresh rebuild if something looks off."



# ================================
# Labels
# ================================

# Show all OCI image labels in aligned key=value format
show-labels:
	@if [ -z "$(FINAL_VERSION)" ]; then \
		echo "❌ ERROR: FINAL_VERSION is not set."; \
	else \
		echo "🔖 OCI image labels for $(DOCKERHUB_REPO):$(FINAL_VERSION)"; \
		docker inspect $(DOCKERHUB_REPO):$(FINAL_VERSION) \
		--format '{{ range $$k, $$v := .Config.Labels }}{{ printf "%-40s %s\n" $$k $$v }}{{ end }}'; \
	fi


# ================================
# Docker Login
# ================================
login:
	@echo "ERROR: release registry login is managed only by the Manual Docker Release workflow" >&2
	@exit 2


# ================================
# Tag preview
# ================================
tag:
	@if [ -z "$(FINAL_VERSION)" ]; then \
		echo "❌ FINAL_VERSION is not set"; \
	else \
		echo "Base Image (versioned):  $(BASE_IMAGE_NAME):$(UBUNTU_VERSION)-$(FINAL_VERSION)"; \
		echo "Base Image (latest):     $(BASE_LATEST_TAG)"; \
		echo "Final Image (local):     $(FINAL_IMAGE_NAME):$(FINAL_VERSION)"; \
		echo "Docker Hub Image:        $(DOCKERHUB_REPO):$(FINAL_VERSION)"; \
	fi

# ================================
# Help
# ================================

help:
	@echo "Available targets:"
	@grep -E '^[a-zA-Z0-9_-]+:' Makefile | grep -v '^.PHONY' | cut -d: -f1 | xargs -n1 echo " -"
