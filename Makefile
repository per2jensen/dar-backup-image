# SPDX-License-Identifier: GPL-3.0-or-later
#
# Usage examples:
# ---------------
# make dev-clean dev
# make FINAL_VERSION=0.9.9-rc1 final
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
	check_version test test-integration all-dev dry-run-release-internal check-docker-creds test-log-pushed-build-json

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

# Full nuke: deletes *all* caches and forces a completely fresh build
dev-nuke:
	@echo "🧨 Full nuke: Pruning ALL Docker build caches and images (this may take a while)..."
	-$(DOCKER) builder prune -a -f
	-$(DOCKER) image prune -a -f
	@echo "Rebuilding image from scratch..."
	$(DOCKER) build --no-cache -f Dockerfile \
		--build-arg VERSION=$(FINAL_VERSION) \
		--build-arg DAR_BACKUP_VERSION=$(DAR_BACKUP_VERSION) \
		--build-arg DAR_VERSION=$(DAR_VERSION) \
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


# Final simply retags the freshest :dev, then runs your checks
final: check_version
	@echo "🔎 Ensuring dar-backup:dev exists and is fresh…"
	@if ! docker image inspect dar-backup:dev >/dev/null 2>&1; then \
	  echo "❌ dar-backup:dev not found — please run 'make dev' first"; exit 1; \
	fi

	@echo "🛠️  Tagging final image as $(FINAL_VERSION)…"
	@docker tag dar-backup:dev dar-backup:$(FINAL_VERSION)
	@docker tag dar-backup:dev $(DOCKERHUB_REPO):$(FINAL_VERSION)

	@echo
	@echo "🔎 Verifying CLI version…"
	@$(MAKE) verify-cli-version

	@echo
	@echo "🔍 Verifying OCI image labels…"
	@$(MAKE) verify-labels

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
	  value=$$(docker inspect -f "$$${label}={{ index .Config.Labels \"$$label\" }}" $(FINAL_IMAGE_NAME):$(FINAL_VERSION) 2>/dev/null | cut -d= -f2-); \
	  if [ -z "$$value" ]; then \
	    echo "❌ Missing or empty label: $$label"; \
	    exit 1; \
	  else \
	    echo "✅ $$label: $$value"; \
	  fi; \
	done

	@echo "🎉 All required OCI labels are present."


verify-cli-version:
	@echo "🔎 Verifying 'dar-backup --version' matches DAR_BACKUP_VERSION ($(DAR_BACKUP_VERSION) )"
	@actual_version="$$(docker run  --rm --entrypoint dar-backup $(FINAL_IMAGE_NAME):$(FINAL_VERSION) --version | head -n1 | awk '{print $$2}')" && \
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
	pytest -s -v $(PYTEST_ARGS) tests/


# Test using a pulled image (skips local build)
test-pulled:
	@if [ -z "$(IMAGE)" ]; then \
		echo "❌ IMAGE must be specified, e.g. 'make IMAGE=per2jensen/dar-backup:0.5.13 test-pulled'"; \
		exit 1; \
	fi
	@echo "🔄 Pulling latest image from Docker Hub: $(IMAGE)"
	@docker pull $(IMAGE)
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
	@if docker manifest inspect $(DOCKERHUB_REPO):$(FINAL_VERSION) >/dev/null 2>&1; then \
	  echo "🛑 Tag $(FINAL_VERSION) already exists on Docker Hub — skipping push."; \
	else \
	  echo "🚀 Pushing image $(DOCKERHUB_REPO):$(FINAL_VERSION)"; \
	  docker push $(DOCKERHUB_REPO):$(FINAL_VERSION); \
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



dry-run-release:
	@echo "🔍 Creating temporary dry-run environment..."
	@if [ -d .dryrun ]; then \
		echo "🧹 Removing stale .dryrun worktree..."; \
		git worktree remove --force .dryrun; \
	fi
	@git worktree add -f .dryrun HEAD
	@cd .dryrun && \
		echo "🚧 Running release steps in .dryrun..." && \
		DRY_RUN=1 FINAL_VERSION=$(FINAL_VERSION) make  dry-run-release-internal
	@git worktree remove .dryrun
	@echo "✅ Dry-run complete — no changes made to working directory"
	@IMAGE=$(FINAL_IMAGE_NAME):$(FINAL_VERSION) $(MAKE) test




dry-run-release-internal: check_version
	@$(eval FINAL_VERSION := $($(FINAL_VERSION)))
	@echo "🔧 Building image $(FINAL_IMAGE_NAME):$(FINAL_VERSION) (dry-run, no push to Docker Hub)"
	$(MAKE) FINAL_VERSION=$(FINAL_VERSION) final verify-labels verify-cli-version
	


size-report:
	@echo "🔍 Image size report for dar-backup:$(FINAL_VERSION)"
	@echo "───────────────────────────────────────────────"
	@docker images dar-backup:$(FINAL_VERSION) --format "Total Size: {{.Size}} (ID: {{.ID}})"
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
		docker inspect $(FINAL_IMAGE_NAME):$(FINAL_VERSION) \
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
