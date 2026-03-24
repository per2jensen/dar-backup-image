# SPDX-License-Identifier: GPL-3.0-or-later
#
# Usage examples:
# ---------------
# make dev-clean dev
# make FINAL_VERSION=0.9.9-rc1 final
# make FINAL_VERSION=0.9.9-rc1 dry-run-release
# make FINAL_VERSION=0.9.9-rc1 release



# ================================
# Configuration
# ================================

SHELL := /bin/bash

# Default values
DOCKER ?= docker
FINAL_VERSION ?= dev

UBUNTU_VERSION ?= 24.04
DAR_BACKUP_VERSION ?= $(shell cat DAR_BACKUP_VERSION)
DAR_VERSION ?= $(shell cat DAR_VERSION)

FINAL_IMAGE_NAME = dar-backup
DOCKERHUB_REPO = per2jensen/dar-backup


IMAGE_REF        ?= $(FINAL_IMAGE_NAME):$(FINAL_VERSION)
GRYPE_FAIL_ON    ?= High
GRYPE_DB_AUTO_UPDATE ?= false
GRYPE_CACHE_DIR  ?= $(HOME)/.cache/grype

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
  --label org.opencontainers.image.revision="$(shell git rev-parse --short HEAD)" \
  --label org.opencontainers.image.title="dar-backup" \
  --label org.opencontainers.image.version="$(FINAL_VERSION)" \
  --label org.opencontainers.image.description="Container for DAR-based backups using \`dar-backup\`" \
  --label org.opencontainers.image.url="https://hub.docker.com/r/per2jensen/dar-backup" \
  --label org.opencontainers.image.licenses="GPL-3.0-or-later" \
  --label org.opencontainers.image.authors="Per Jensen <dar-backup@pm.me>" \
  --label org.opencontainers.image.ref.name="$(DOCKERHUB_REPO):$(FINAL_VERSION)" \
  --label org.dar-backup.version="$(DAR_BACKUP_VERSION)" \
  --label org.dar.version="$(DAR_VERSION)"



# ================================
# Targets
# ================================

.PHONY: all all-dev dev-rebuild final release clean clean-all push tag login dev dev-clean labels help \
	check_version test test-integration all-dev dry-run-release dry-run-release-internal dry-run-cleanup \
	check-docker-creds test-log-pushed-build-json sbom-sarif sbom-sarif-docker install-tools \
	grype-db-status grype-db-update scan-final verify-labels


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
	  anchore/syft:latest \
	  $(FINAL_IMAGE_NAME):$(FINAL_VERSION) -o cyclonedx-json > $(SBOM)

	# Vulnerability scan via Grype
	# - Disable app-update ping; persist DB cache to avoid re-downloads
	@$(DOCKER) run --rm \
	  -e GRYPE_CHECK_FOR_APP_UPDATE=false \
	  -v /var/run/docker.sock:/var/run/docker.sock \
	  -v $(PWD)/$(GRYPE_CACHE_DIR):/home/anchore/.cache \
	  anchore/grype:latest \
	  $(FINAL_IMAGE_NAME):$(FINAL_VERSION) -o sarif > $(SARIF)

	@echo "✅ Generated files:"
	@ls -lh $(SBOM) $(SARIF)



install-tools:
	@command mkdir -p "$(HOME)"/.local/bin
	@command -v syft >/dev/null 2>&1 || { echo "Installing syft"; \
	  curl -sSfL https://raw.githubusercontent.com/anchore/syft/main/install.sh | sh -s -- -b  "$(HOME)"/.local/bin; }
	@command -v grype >/dev/null 2>&1 || { echo "Installing grype"; \
	  curl -sSfL https://raw.githubusercontent.com/anchore/grype/main/install.sh | sh -s -- -b "$(HOME)"/.local/bin; }

grype-db-status:
	@GRYPE_CHECK_FOR_APP_UPDATE=false grype db status

grype-db-update:
	@GRYPE_CHECK_FOR_APP_UPDATE=false grype db update







# Base image target is now a no-op (we only have one Dockerfile now)
base:
	@echo "Skipping separate base image build (single Dockerfile in use)"


release: check_version check-docker-creds final verify-labels verify-cli-version login push log-pushed-build-json
	@echo "✅ Release complete for: $(DOCKERHUB_REPO):$(FINAL_VERSION)"
	@echo "🏷️ Tagging release as v$(FINAL_VERSION)..."
	@if git rev-parse "v$(FINAL_VERSION)" >/dev/null 2>&1; then \
		echo "🔁 Git tag 'v$(FINAL_VERSION)' already exists — skipping tag creation."; \
	else \
		git tag -a "v$(FINAL_VERSION)" -m "Release version v$(FINAL_VERSION)"; \
		git push origin "v$(FINAL_VERSION)"; \
		echo "✅ Git tag 'v$(FINAL_VERSION)' created and pushed."; \
	fi


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
	$(MAKE) dev \
		FINAL_VERSION=$(FINAL_VERSION) \
		DAR_BACKUP_VERSION=$(DAR_BACKUP_VERSION) \
		DAR_VERSION=$(DAR_VERSION) 

# Full nuke: deletes *all* caches and forces a completely fresh build.
# Note: passes DAR_BACKUP_VERSION (not VERSION) to match the Dockerfile ARG name,
# and includes LABEL_ARGS so the nuked image is labeled consistently with 'make dev'.
dev-nuke:
	@echo "🧨 Full nuke: Pruning ALL Docker build caches and images (this may take a while)..."
	-$(DOCKER) builder prune -a -f
	-$(DOCKER) image prune -a -f
	@echo "Rebuilding image from scratch..."
	$(DOCKER) build --no-cache -f Dockerfile \
		--build-arg DAR_BACKUP_VERSION=$(DAR_BACKUP_VERSION) \
		--build-arg DAR_VERSION=$(DAR_VERSION) \
		$(LABEL_ARGS) \
		-t dar-backup:$(FINAL_VERSION) .


dev-rebuild: dev-nuke dev


# Dev image build (always produce a fully labeled dar-backup:dev)
dev: validate
	@echo "Building development image (cached & labeled): $(FINAL_VERSION)"
	$(DOCKER) build -f Dockerfile \
	  --build-arg VERSION=$(FINAL_VERSION) \
	  --build-arg DAR_VERSION=$(DAR_VERSION) \
	  --build-arg DAR_BACKUP_VERSION=$(DAR_BACKUP_VERSION) \
	  $(LABEL_ARGS) \
	  -t dar-backup:dev \
	  .



final: check_version
	@echo "🔎 Ensuring dar-backup:dev exists and is fresh…"
	@if ! $(DOCKER) image inspect dar-backup:dev >/dev/null 2>&1; then \
	  echo "❌ dar-backup:dev not found — run 'make dev' first"; exit 1; \
	fi

	@echo "🧩 Creating release image with corrected labels (no rebuild)…"
	@set -e; \
	CID="$$( $(DOCKER) create dar-backup:dev )"; \
	$(DOCKER) commit \
	  --change 'LABEL org.opencontainers.image.version=$(FINAL_VERSION)' \
	  --change 'LABEL org.opencontainers.image.ref.name=$(DOCKERHUB_REPO):$(FINAL_VERSION)' \
	  $$CID dar-backup:$(FINAL_VERSION) >/dev/null; \
	$(DOCKER) rm $$CID >/dev/null

	@$(DOCKER) tag dar-backup:$(FINAL_VERSION) $(DOCKERHUB_REPO):$(FINAL_VERSION)

	@echo
	@echo "🔎 Verifying CLI version…"
	@$(MAKE) verify-cli-version

	@echo
	@echo "🔍 Verifying OCI image labels…"
	@$(MAKE) verify-labels

	@echo
	@echo "🔍 Running scans…"
	@$(MAKE) scan-final

	@echo
	@echo "📊 Image layer size report (for audit):"
	@$(MAKE) FINAL_VERSION=$(FINAL_VERSION) size-report


verify-labels:
	@$(eval FINAL_VERSION := $(or $(FINAL_VERSION)))
	@echo "🔍 Verifying OCI image labels on $(FINAL_IMAGE_NAME):$(FINAL_VERSION)"
	@$(eval LABELS := org.opencontainers.image.authors \
	                  org.opencontainers.image.base.name \
	                  org.opencontainers.image.base.version \
	                  org.opencontainers.image.created \
	                  org.opencontainers.image.description \
	                  org.opencontainers.image.licenses \
	                  org.opencontainers.image.ref.name \
	                  org.opencontainers.image.revision \
	                  org.opencontainers.image.source \
	                  org.opencontainers.image.title \
	                  org.opencontainers.image.url \
	                  org.opencontainers.image.version \
	                  org.dar-backup.version \
	                  org.dar.version)

	@for label in $(LABELS); do \
	  value=$$($(DOCKER) inspect -f "$$${label}={{ index .Config.Labels \"$$label\" }}" $(FINAL_IMAGE_NAME):$(FINAL_VERSION) 2>/dev/null | cut -d= -f2-); \
	  if [ -z "$$value" ]; then \
	    echo "❌ Missing or empty label: $$label"; \
	    exit 1; \
	  else \
	    echo "✅ $$label: $$value"; \
	  fi; \
	done

	@echo "🔎 Checking exact matches for version and ref.name…"
	@set -e; \
	exp_version="$(FINAL_VERSION)"; \
	act_version="$$($(DOCKER) inspect -f '{{ index .Config.Labels "org.opencontainers.image.version" }}' $(FINAL_IMAGE_NAME):$(FINAL_VERSION))"; \
	if [ "$$act_version" != "$$exp_version" ]; then \
	  echo "❌ org.opencontainers.image.version mismatch"; \
	  echo "   expected: '$$exp_version'"; \
	  echo "   actual:   '$$act_version'"; \
	  exit 1; \
	fi; \
	exp_ref="$(DOCKERHUB_REPO):$(FINAL_VERSION)"; \
	act_ref="$$($(DOCKER) inspect -f '{{ index .Config.Labels "org.opencontainers.image.ref.name" }}' $(FINAL_IMAGE_NAME):$(FINAL_VERSION))"; \
	if [ "$$act_ref" != "$$exp_ref" ]; then \
	  echo "❌ org.opencontainers.image.ref.name mismatch"; \
	  echo "   expected: '$$exp_ref'"; \
	  echo "   actual:   '$$act_ref'"; \
	  exit 1; \
	fi; \
	echo "✅ Labels match expected values."

	@echo "🎉 All required OCI labels are present and correct."




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
	@echo "🔎 Verifying 'dar-backup --version' matches DAR_BACKUP_VERSION ($(DAR_BACKUP_VERSION) )"
	@actual_version="$$($(DOCKER) run  --rm --entrypoint dar-backup $(FINAL_IMAGE_NAME):$(FINAL_VERSION) --version | head -n1 | awk '{print $$2}')" && \
	if [ "$$actual_version" != "$(DAR_BACKUP_VERSION)" ]; then \
	  echo "❌ Version mismatch: CLI reports '$$actual_version', expected '$(DAR_BACKUP_VERSION)'"; \
	  exit 1; \
	else \
	  echo "✅ dar-backup --version is correct: $(DAR_BACKUP_VERSION)"; \
	fi


# ================================
# Log build metadata to JSON file
# ================================
log-pushed-build-json: check_version
	@mkdir -p $(BUILD_LOG_DIR)
	@test -f $(BUILD_LOG_PATH) || echo "[]" > $(BUILD_LOG_PATH)

	$(eval DATE := $(shell date -u +%Y-%m-%dT%H:%M:%SZ))
	$(eval GIT_REV := $(shell git rev-parse --short HEAD))

	$(eval DIGEST := $(shell docker inspect --format '{{ index .RepoDigests 0 }}' $(DOCKERHUB_REPO):$(FINAL_VERSION) 2>/dev/null || echo ""))
	@if [ -z "$(DIGEST)" ]; then \
		echo "❌ Digest not found. Make sure the image has been pushed."; \
		exit 1; \
	fi

	$(eval IMAGE_ID := $(shell docker inspect --format '{{ .Id }}' $(FINAL_IMAGE_NAME):$(FINAL_VERSION)))
	@if [ -z "$(IMAGE_ID)" ]; then \
		echo "❌ Image ID not found. Did you build the final image?"; \
		exit 1; \
	fi

	$(eval DIGEST_ONLY := $(shell echo "$(DIGEST)" | cut -d'@' -f2))
	$(eval BUILD_NUMBER := $(shell test -f $(BUILD_LOG_PATH) && jq length $(BUILD_LOG_PATH) || echo 0))

	@jq --arg tag "$(FINAL_VERSION)" \
		--arg dar_backup_version "$(DAR_BACKUP_VERSION)" \
		--arg base "$(BASE_IMAGE_NAME):$(UBUNTU_VERSION)-$(FINAL_VERSION)" \
		--arg rev "$(GIT_REV)" \
		--arg created "$(DATE)" \
		--arg url "https://hub.docker.com/layers/$(DOCKERHUB_REPO)/$(FINAL_VERSION)/images/$(DIGEST_ONLY)" \
		--arg digest "$(DIGEST_ONLY)" \
		--arg image_id "$(IMAGE_ID)" \
		--arg full_tag "$(DOCKERHUB_REPO):$(FINAL_VERSION)" \
		--argjson build_number $(BUILD_NUMBER) \
		'. += [{"build_number": $$build_number, "tag": $$tag, "dar_backup_version": $$dar_backup_version, "base_image": $$base, "full_image_tag": $$full_tag, "git_revision": $$rev, "created": $$created, "dockerhub_tag_url": $$url, "digest": $$digest, "image_id": $$image_id}]' \
		$(BUILD_LOG_PATH) > $(BUILD_LOG_PATH).tmp && mv $(BUILD_LOG_PATH).tmp $(BUILD_LOG_PATH)


	@echo "✅ Log entry added. Total builds: $$(jq length $(BUILD_LOG_PATH))"
	@jq '.[-1]' $(BUILD_LOG_PATH)


	@echo "🔄 Checking if $(BUILD_LOG_PATH) changed"
	@if ! git diff --quiet $(BUILD_LOG_PATH); then \
		git add $(BUILD_LOG_PATH); \
		git commit -m "build-history: add $(FINAL_VERSION) metadata"; \
		echo "✅ $(BUILD_LOG_PATH) updated and committed"; \
	else \
		echo "ℹ️ No changes to commit — build history already up to date"; \
	fi


	@echo "📘 Updating README.md with latest build row..."
	@FINAL_VERSION="$(FINAL_VERSION)" \
	 DAR_BACKUP_VERSION="$(DAR_BACKUP_VERSION)" \
	 DAR_VERSION="$(DAR_VERSION)" \
	 GIT_REV="$(GIT_REV)" \
	 DOCKERHUB_REPO="$(DOCKERHUB_REPO)" \
	 DIGEST_ONLY="$(DIGEST_ONLY)" \
	 NOTE=" - " \
	 ./scripts/patch-readme-build.sh

	@echo "🔄 Updating version examples in README.md to VERSION=$(FINAL_VERSION)"
	@sed -i -E "s/VERSION=[0-9]+\.[0-9]+\.[0-9]+(-[a-zA-Z0-9]+)?;/VERSION=$(FINAL_VERSION);/" README.md

	@echo "🔄 Checking if README.md changed"
	@if ! git diff --quiet README.md; then \
		git add README.md; \
		git commit -m "Release: add tag $(FINAL_VERSION)"; \
		echo "✅ README.md updated and committed"; \
	else \
		echo "ℹ️ No changes to commit — README.md already up to date"; \
	fi



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

	$(eval FINAL_VERSION := test-tag)
	$(eval DAR_BACKUP_VERSION := 0.99.0-test)
	$(eval BASE_TAG := dar-backup-base:24.04-test-tag)
	$(eval GIT_REV := mockrev123)
	$(eval DAR_BACKUP_DATE := 2025-07-13T00:00:00Z)
	$(eval DOCKERHUB_REPO := per2jensen/dar-backup)
	$(eval DIGEST_ONLY := sha256:deadbeef1234567890)
	$(eval IMAGE_ID := sha256:cafebabef00d1234567890)
	$(eval BUILD_LOG_PATH := ./logs/build-history.json)
	$(eval BUILD_NUMBER := $(shell test -f ./logs/build-history.json && jq length ./logs/build-history.json || echo 0))

	@jq --arg tag "$(FINAL_VERSION)" \
		--arg dar_backup_version "$(DAR_BACKUP_VERSION)" \
		--arg base "$(BASE_TAG)" \
		--arg rev "$(GIT_REV)" \
		--arg created "$(DAR_BACKUP_DATE)" \
		--arg url "https://hub.docker.com/layers/$(DOCKERHUB_REPO)/$(FINAL_VERSION)/images/$(DIGEST_ONLY)" \
		--arg digest "$(DIGEST_ONLY)" \
		--arg image_id "$(IMAGE_ID)" \
		--argjson build_number $(BUILD_NUMBER) \
		'. += [{"build_number": $$build_number, "tag": $$tag, "dar_backup_version": $$dar_backup_version, "base_image": $$base, "git_revision": $$rev, "created": $$created, "dockerhub_tag_url": $$url, "digest": $$digest, "image_id": $$image_id}]' \
		$(BUILD_LOG_PATH) > $(BUILD_LOG_PATH).tmp && mv $(BUILD_LOG_PATH).tmp $(BUILD_LOG_PATH) && \
		echo "✅ Test entry added:" && jq '.[-1]' $(BUILD_LOG_PATH)



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
	@FINAL_VERSION=$${FINAL_VERSION:-dev}; \
	IMAGE=$${IMAGE:-dar-backup:$${FINAL_VERSION}}; \
#	pytest -s -v $(PYTEST_ARGS) tests/
	pytest --json-report --json-report-file=pytest-report.json

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


push: check_version check-docker-creds
	@if $(DOCKER) manifest inspect $(DOCKERHUB_REPO):$(FINAL_VERSION) >/dev/null 2>&1; then \
	  echo "🛑 Tag $(FINAL_VERSION) already exists on Docker Hub — skipping push."; \
	else \
	  echo "🚀 Pushing image $(DOCKERHUB_REPO):$(FINAL_VERSION)"; \
	  $(DOCKER) push $(DOCKERHUB_REPO):$(FINAL_VERSION); \
	  echo "🔎 Resolving published digest…"; \
	  DIGEST="$$( $(DOCKER) inspect --format '{{index .RepoDigests 0}}' $(DOCKERHUB_REPO):$(FINAL_VERSION) 2>/dev/null )"; \
	  if [ -n "$$DIGEST" ]; then \
	    echo "📦 Published digest: $$DIGEST"; \
	    echo "$$DIGEST" > .last_digest; \
	    echo "🔗 Docker Hub URL: https://hub.docker.com/layers/$(DOCKERHUB_REPO)/$(FINAL_VERSION)/images/$${DIGEST#*@}"; \
	  else \
	    echo "⚠️  Could not determine digest locally. You can query later with:"; \
	    echo "    $(DOCKER) inspect --format '{{index .RepoDigests 0}}' $(DOCKERHUB_REPO):$(FINAL_VERSION)"; \
	  fi; \
	fi



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



# Always-run cleanup target for the dry-run worktree.
# Called explicitly at the end of dry-run-release AND as an error recovery step,
# since Make's per-line @-prefixed commands don't support shell trap directly.
dry-run-cleanup:
	@if [ -d .dryrun ]; then \
		echo "🧹 Removing .dryrun worktree..."; \
		git worktree remove --force .dryrun || true; \
	fi


dry-run-release: check_version install-tools
	@echo "🔍 Creating temporary dry-run environment..."
	@$(MAKE) dry-run-cleanup
	@git worktree add -f .dryrun HEAD
	@echo "🚧 Running release steps in .dryrun..."
	@cd .dryrun && \
		$(MAKE) dry-run-release-internal \
			FINAL_VERSION=$(FINAL_VERSION) \
			DAR_BACKUP_VERSION=$(DAR_BACKUP_VERSION) \
			DAR_VERSION=$(DAR_VERSION) \
		|| { cd $(CURDIR) && $(MAKE) dry-run-cleanup && exit 1; }
	@$(MAKE) dry-run-cleanup
	@echo "✅ Dry-run build complete — no push performed."
	@echo "▶ Running tests against the locally built image $(FINAL_IMAGE_NAME):$(FINAL_VERSION)..."
	@IMAGE=$(FINAL_IMAGE_NAME):$(FINAL_VERSION) $(MAKE) test
	@echo "✅ Dry-run complete — working directory unchanged."


# Internal target: runs inside the .dryrun worktree.
# DRY_RUN is intentionally not set here — nothing downstream checks it,
# and 'final' already excludes push by design. If push-guarding via DRY_RUN
# is added in future, set it here.
dry-run-release-internal: check_version install-tools
	@echo "🔧 Building image $(FINAL_IMAGE_NAME):$(FINAL_VERSION) (dry-run, no push to Docker Hub)"
	@$(MAKE) FINAL_VERSION=$(FINAL_VERSION) \
		DAR_BACKUP_VERSION=$(DAR_BACKUP_VERSION) \
		DAR_VERSION=$(DAR_VERSION) \
		final verify-labels verify-cli-version
	


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
	@echo "🔐 Logging in to Docker Hub (2FA enabled)..."
	@if [ -z "$$DOCKER_USER" ] || [ -z "$$DOCKER_TOKEN" ]; then \
		echo "❌ ERROR: You must export DOCKER_USER and DOCKER_TOKEN."; \
		echo "   Example: export DOCKER_USER=per2jensen && export DOCKER_TOKEN=your_token"; \
		exit 1; \
	fi
	echo "$$DOCKER_TOKEN" | $(DOCKER) login -u "$$DOCKER_USER" --password-stdin


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