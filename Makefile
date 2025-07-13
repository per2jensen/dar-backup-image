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
UBUNTU_VERSION ?= 24.04
DAR_BACKUP_VERSION ?=


BASE_IMAGE_NAME = dar-backup-base
FINAL_IMAGE_NAME = dar-backup
DOCKERHUB_REPO = per2jensen/dar-backup
BASE_LATEST_TAG = $(BASE_IMAGE_NAME):$(UBUNTU_VERSION)

# === Build log configuration ===
BUILD_LOG_DIR ?= doc
BUILD_LOG_FILE ?= build-history.json
BUILD_LOG_PATH := $(BUILD_LOG_DIR)/$(BUILD_LOG_FILE)


# ================================
# Targets
# ================================

.PHONY: all all-dev base final release clean clean-all push tag login dev dev-clean labels help \
	check_version test test-integration all-dev dry-run-release-internal

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


base: check_version validate
	@echo "Building base image..."
	$(DOCKER) build --pull -f Dockerfile-base-image \
		--build-arg VERSION=$(FINAL_VERSION) \
		--label org.opencontainers.image.base.name="ubuntu" \
		--label org.opencontainers.image.base.version="$(UBUNTU_VERSION)" \
		--label org.opencontainers.image.base.created="$(BASE_IMAGE_DATE)" \
		--label org.opencontainers.image.version="$(FINAL_VERSION)-base" \
		--label org.opencontainers.image.authors="Per Jensen <per2jensen@gmail.com>" \
		-t $(BASE_IMAGE_NAME):$(UBUNTU_VERSION)-$(FINAL_VERSION) .
	$(DOCKER) tag $(BASE_IMAGE_NAME):$(UBUNTU_VERSION)-$(FINAL_VERSION) $(BASE_LATEST_TAG)



release: check_version final verify-labels verify-cli-version  login push log-pushed-build-json
	@echo "✅ Release complete for: $(DOCKERHUB_REPO):$(FINAL_VERSION)"


final: check_version validate base
	@if [ "$(DAR_BACKUP_VERSION)" = "latest" ]; then \
		echo "❌ ERROR: DAR_BACKUP_VERSION must not be 'latest' for final builds."; \
		echo "   Set a specific version (e.g., DAR_BACKUP_VERSION=0.8.0)"; \
		exit 1; \
	fi
	$(eval BASE_IMAGE_DATE := $(shell date -u +%Y-%m-%dT%H:%M:%SZ))
	$(eval DAR_BACKUP_DATE := $(shell date -u +%Y-%m-%dT%H:%M:%SZ))
	$(eval GIT_REV := $(shell git rev-parse --short HEAD))
	$(eval FINAL_TAG := $(FINAL_IMAGE_NAME):$(FINAL_VERSION))
	$(eval DOCKERHUB_TAG := $(DOCKERHUB_REPO):$(FINAL_VERSION))
	@echo "Building final image: $(FINAL_TAG) and $(DOCKERHUB_TAG) ..."
	$(DOCKER) build -f Dockerfile-dar-backup \
	    --build-arg base="$(BASE_IMAGE_NAME):$(UBUNTU_VERSION)-$(FINAL_VERSION)" \
		--build-arg VERSION=$(FINAL_VERSION) \
		--build-arg DAR_BACKUP_VERSION=$(DAR_BACKUP_VERSION) \
		--label org.opencontainers.image.source="https://github.com/per2jensen/dar-backup-image" \
		--label org.opencontainers.image.created="$(DAR_BACKUP_DATE)" \
		--label org.opencontainers.image.revision="$(GIT_REV)" \
		--label org.opencontainers.image.title="dar-backup" \
		--label org.opencontainers.image.version="$(FINAL_VERSION)" \
		--label org.opencontainers.image.description="Container for DAR-based backups using `dar-backup`" \
		--label org.opencontainers.image.source="https://github.com/per2jensen/dar-backup-image" \
		--label org.opencontainers.image.url="https://hub.docker.com/r/per2jensen/dar-backup" \
		--label org.opencontainers.image.licenses="GPL-3.0-or-later" \
		--label org.opencontainers.image.authors="Per Jensen <dar-backup@pm.me>" \
		--label org.opencontainers.image.ref.name="$(DOCKERHUB_REPO):$(FINAL_VERSION)" \
		--label org.dar-backup.version="$(DAR_BACKUP_VERSION)" \
		-t $(FINAL_TAG) \
		-t $(DOCKERHUB_TAG) .



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
	                  org.opencontainers.image.version)

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

	$(eval GIT_REV := $(shell git rev-parse --short HEAD))
	$(eval DAR_BACKUP_DATE := $(shell date -u +%Y-%m-%dT%H:%M:%SZ))
	$(eval BASE_TAG := $(BASE_IMAGE_NAME):$(UBUNTU_VERSION)-$(FINAL_VERSION))
	$(eval DIGEST := $(shell docker inspect --format '{{ index .RepoDigests 0 }}' $(DOCKERHUB_REPO):$(FINAL_VERSION) 2>/dev/null || echo ""))
	$(eval IMAGE_ID := $(shell docker inspect --format '{{ .Id }}' $(FINAL_IMAGE_NAME):$(FINAL_VERSION)))

	@if [ -z "$(DIGEST)" ]; then \
		echo "❌ Digest not found. Make sure the image has been pushed."; \
		exit 1; \
	fi

	$(eval DIGEST_ONLY := $(shell echo "$(DIGEST)" | cut -d'@' -f2))
	$(eval BUILD_NUMBER := $(shell test -f $(BUILD_LOG_PATH) && jq length $(BUILD_LOG_PATH) || echo 0))

	@jq --arg tag "$(FINAL_VERSION)" \
	    --arg dar_backup_version "$(DAR_BACKUP_VERSION)" \
	    --arg base "$(BASE_TAG)" \
	    --arg rev "$(GIT_REV)" \
	    --arg created "$(DAR_BACKUP_DATE)" \
	    --arg url "https://hub.docker.com/r/$(DOCKERHUB_REPO)/tags/$(FINAL_VERSION)" \
	    --arg digest "$(DIGEST_ONLY)" \
	    --arg image_id "$(IMAGE_ID)" \
	    --argjson build_number $(BUILD_NUMBER) \
	    '. += [{"build_number": $$build_number, "tag": $$tag, "dar_backup_version": $$version, "base_image": $$base, "git_revision": $$rev, "created": $$created, "dockerhub_tag_url": $$url, "digest": $$digest, "image_id": $$image_id}]' \
	    $(BUILD_LOG_PATH) > $(BUILD_LOG_PATH).tmp && mv $(BUILD_LOG_PATH).tmp $(BUILD_LOG_PATH)

	@if [ "$(COMMIT_LOG)" = "yes" ]; then \
		$(MAKE) commit-log; \
	fi



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


# The used script defaults to IMAGE="dar-backup:dev" if IMAGE is not set.
test:
	@echo "Running dar-backup FULL + DIFF + INCR test in a temp directory..."
	@TMPDIR=$$(mktemp -d /tmp/dar-backup-test-XXXXXX) && \
	TEST_SCRIPT=$${TEST_SCRIPT:-scripts/run-backup.sh} && \
	SCRIPT_NAME=$$(basename $$TEST_SCRIPT) && \
	cp $$TEST_SCRIPT $$TMPDIR/$$SCRIPT_NAME && \
	chmod +x $$TMPDIR/$$SCRIPT_NAME && \
	cd $$TMPDIR && \
	WORKDIR=$$TMPDIR ./$$SCRIPT_NAME -t FULL  || { echo "❌ FULL backup failed"; exit 1; }  && \
	echo "first_diff_file" > $$TMPDIR/data/diff.txt && \
	WORKDIR=$$TMPDIR ./$$SCRIPT_NAME -t DIFF  || { echo "❌ DIFF backup failed"; exit 1; }  && \
	echo "incr_file" > $$TMPDIR/data/incr.txt && \
	WORKDIR=$$TMPDIR ./$$SCRIPT_NAME -t INCR  || { echo "❌ INCR backup failed"; exit 1; } && \
	echo "✅ FULL + DIFF + INCR test completed in $$TMPDIR"



# Run integration tests
test-integration: all-dev
	bash tests/test_run_backup.sh


clean:
	@if [ -z "$(FINAL_VERSION)" ]; then \
		echo "❌ FINAL_VERSION not set"; exit 1; \
	fi
	-$(DOCKER) rmi -f $(BASE_IMAGE_NAME):$(UBUNTU_VERSION)-$(FINAL_VERSION) || true
	-$(DOCKER) rmi -f $(BASE_LATEST_TAG) || true
	-$(DOCKER) rmi -f $(FINAL_IMAGE_NAME):$(FINAL_VERSION) || true



# Remove all images related to dar-backup
clean-all:
	-docker images -q 'dar-backup*' | xargs -r docker rmi -f


push: check_version
	@echo "Push $(DOCKERHUB_REPO):$(FINAL_VERSION) to Docker Hub..."
	$(DOCKER) push $(DOCKERHUB_REPO):$(FINAL_VERSION)


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




dry-run-release-internal: check_version
	@$(eval FINAL_VERSION := $($(FINAL_VERSION)))
	@echo "🔧 Building image $(FINAL_IMAGE_NAME):$(FINAL_VERSION) (dry-run, no push to Docker Hub)"
	$(MAKE) FINAL_VERSION=$(FINAL_VERSION) final verify-labels verify-cli-version
	@IMAGE=$(FINAL_IMAGE_NAME):$(FINAL_VERSION) bash tests/test_run_backup.sh



# ================================
# Dev build
# ================================

all-dev: validate
	@$(MAKE) FINAL_VERSION=dev base
	@$(MAKE) dev


dev: validate
	@echo "Building development image: dar-backup:dev ..."
	$(DOCKER) build -f Dockerfile-dar-backup \
		--build-arg VERSION=dev \
		-t dar-backup:dev .

dev-clean:
	@echo "Removing dev image..."
	-$(DOCKER) rmi -f dar-backup:dev || true



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
