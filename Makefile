# SPDX-License-Identifier: GPL-3.0-or-later
#
# Usage examples:
# ---------------
# make dev-clean dev
# make DAR_BACKUP_IMAGE_VERSION=0.9.9-rc1 final
# make DAR_BACKUP_IMAGE_VERSION=0.9.9-rc1 release

# ================================
# Configuration
# ================================

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

.PHONY: all all-dev base final release clean push tag login dev dev-clean labels help \
	check_version ghcr-tags ghcr-list-ids ghcr-delete-id test


check_version:
	@if [ -z "$(DAR_BACKUP_IMAGE_VERSION)" ]; then \
		echo "❌ ERROR: You must set DAR_BACKUP_IMAGE_VERSION explicitly."; \
		echo "   Example: make DAR_BACKUP_IMAGE_VERSION=1.0.0 final"; \
		exit 1; \
	fi


base: check_version validate
	@echo "Building base image..."
	$(DOCKER) build --pull -f Dockerfile-base-image \
		--build-arg VERSION=$(DAR_BACKUP_IMAGE_VERSION) \
		-t $(BASE_IMAGE_NAME):$(UBUNTU_VERSION)-$(DAR_BACKUP_IMAGE_VERSION) .
	$(DOCKER) tag $(BASE_IMAGE_NAME):$(UBUNTU_VERSION)-$(DAR_BACKUP_IMAGE_VERSION) $(BASE_LATEST_TAG)



release: check_version final log-build-json  login push
	@echo "✅ Release complete for: $(DOCKERHUB_REPO):$(DAR_BACKUP_IMAGE_VERSION)"


final: check_version validate base
	@if [ -z "$(DAR_BACKUP_VERSION)" ] || [ "$(DAR_BACKUP_VERSION)" = "latest" ]; then \
		echo "❌ ERROR: DAR_BACKUP_VERSION must not be 'latest' for final builds."; \
		echo "   Set a specific version (e.g., DAR_BACKUP_VERSION=0.8.0)"; \
		exit 1; \
	fi
	$(eval BASE_IMAGE_DATE := $(shell date -u +%Y-%m-%dT%H:%M:%SZ))
	$(eval DAR_BACKUP_DATE := $(shell date -u +%Y-%m-%dT%H:%M:%SZ))
	$(eval GIT_REV := $(shell git rev-parse --short HEAD))
	$(eval FINAL_TAG := $(FINAL_IMAGE_NAME):$(DAR_BACKUP_IMAGE_VERSION))
	$(eval DOCKERHUB_TAG := $(DOCKERHUB_REPO):$(DAR_BACKUP_IMAGE_VERSION))
	@echo "Building final image: $(FINAL_TAG) and $(DOCKERHUB_TAG) ..."
	$(DOCKER) build -f Dockerfile-dar-backup \
	    --build-arg base="$(BASE_IMAGE_NAME):$(UBUNTU_VERSION)-$(DAR_BACKUP_IMAGE_VERSION)" \
		--build-arg VERSION=$(DAR_BACKUP_IMAGE_VERSION) \
		--label org.opencontainers.image.source=https://hub.docker.com/r/per2jensen/dar-backup \
		--build-arg DAR_BACKUP_VERSION=$(DAR_BACKUP_VERSION) \
		--label org.opencontainers.image.created="$(DAR_BACKUP_DATE)" \
		--label org.opencontainers.image.base.created="$(BASE_IMAGE_DATE)" \
		--label org.opencontainers.image.revision="$(GIT_REV)" \
		--label org.opencontainers.image.title="dar-backup" \
		--label org.opencontainers.image.version="$(DAR_BACKUP_IMAGE_VERSION)" \
		--label org.opencontainers.image.description="Container for DAR-based backups using dar-backup" \
		--label org.opencontainers.image.source="https://github.com/per2jensen/dar-backup-image" \
		--label org.opencontainers.image.url="https://github.com/per2jensen/dar-backup-image" \
		--label org.opencontainers.image.licenses="GPL-3.0-or-later" \
		--label org.opencontainers.image.authors="Per Jensen <dar-backup@pm.me>" \
		--label org.dar-backup.version="$(DAR_BACKUP_VERSION)" \
		-t $(FINAL_TAG) \
		-t $(DOCKERHUB_TAG) .



# ================================
# Log build metadata to JSON file
# ================================
log-pushed-build-json: check_version
	@mkdir -p $(BUILD_LOG_DIR)
	@test -f $(BUILD_LOG_PATH) || echo "[]" > $(BUILD_LOG_PATH)

	$(eval GIT_REV := $(shell git rev-parse --short HEAD))
	$(eval DAR_BACKUP_DATE := $(shell date -u +%Y-%m-%dT%H:%M:%SZ))
	$(eval BASE_TAG := $(BASE_IMAGE_NAME):$(UBUNTU_VERSION)-$(DAR_BACKUP_IMAGE_VERSION))
	$(eval DIGEST := $(shell docker inspect --format '{{ index .RepoDigests 0 }}' $(DOCKERHUB_REPO):$(DAR_BACKUP_IMAGE_VERSION) 2>/dev/null || echo ""))
	$(eval IMAGE_ID := $(shell docker inspect --format '{{ .Id }}' $(FINAL_IMAGE_NAME):$(DAR_BACKUP_IMAGE_VERSION)))

	@if [ -z "$(DIGEST)" ]; then \
		echo "❌ Digest not found. Make sure the image has been pushed."; \
		exit 1; \
	fi

	$(eval DIGEST_ONLY := $(shell echo "$(DIGEST)" | cut -d'@' -f2))
	$(eval BUILD_NUMBER := $(shell test -f $(BUILD_LOG_PATH) && jq length $(BUILD_LOG_PATH) || echo 0))

	@jq --arg tag "$(DAR_BACKUP_IMAGE_VERSION)" \
	    --arg version "$(DAR_BACKUP_VERSION)" \
	    --arg base "$(BASE_TAG)" \
	    --arg rev "$(GIT_REV)" \
	    --arg created "$(DAR_BACKUP_DATE)" \
	    --arg url "https://hub.docker.com/r/$(DOCKERHUB_REPO)/tags/$(DAR_BACKUP_IMAGE_VERSION)" \
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
		git commit -m "📦 Add build log entry for v$(DAR_BACKUP_IMAGE_VERSION) (dar-backup v$(DAR_BACKUP_VERSION))"; \
	else \
		echo "ℹ️  No changes to $(BUILD_LOG_PATH) to commit."; \
	fi



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

clean:
	-$(DOCKER) rmi -f $(BASE_IMAGE_NAME):$(UBUNTU_VERSION)-$(DAR_BACKUP_IMAGE_VERSION) || true
	-$(DOCKER) rmi -f $(BASE_LATEST_TAG) || true
	-$(DOCKER) rmi -f $(FINAL_IMAGE_NAME):$(DAR_BACKUP_IMAGE_VERSION) || true

push: check_version
	@echo "Push $(DOCKERHUB_REPO):$(DAR_BACKUP_IMAGE_VERSION) to Docker Hub..."
	$(DOCKER) push $(DOCKERHUB_REPO):$(DAR_BACKUP_IMAGE_VERSION)


# Show image version, Git revision, and build timestamp
print-version:
	@echo "🔖 dar-backup image metadata"
	@echo "────────────────────────────────────────────"
	@echo " Ubuntu Base   : $(UBUNTU_VERSION)"
	@echo " Image Version : $(DAR_BACKUP_IMAGE_VERSION)"
	@echo " Git Revision  : $(GIT_REV)"
	@echo " Build Time    : $(DAR_BACKUP_DATE)"


# check for docker and jq installation
validate:
	@command -v jq >/dev/null || { echo "❌ jq not found"; exit 1; }
	@command -v docker >/dev/null || { echo "❌ docker not found"; exit 1; }

# ================================
# Dev build
# ================================

all-dev: validate
	@$(MAKE) DAR_BACKUP_IMAGE_VERSION=dev base
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
	@if [ -z "$(DAR_BACKUP_IMAGE_VERSION)" ]; then \
		echo "❌ ERROR: DAR_BACKUP_IMAGE_VERSION is not set."; \
	else \
		docker inspect $(FINAL_IMAGE_NAME):$(DAR_BACKUP_IMAGE_VERSION) \
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
	@if [ -z "$(DAR_BACKUP_IMAGE_VERSION)" ]; then \
		echo "❌ DAR_BACKUP_IMAGE_VERSION is not set"; \
	else \
		echo "Base Image (versioned):  $(BASE_IMAGE_NAME):$(UBUNTU_VERSION)-$(DAR_BACKUP_IMAGE_VERSION)"; \
		echo "Base Image (latest):     $(BASE_LATEST_TAG)"; \
		echo "Final Image (local):     $(FINAL_IMAGE_NAME):$(DAR_BACKUP_IMAGE_VERSION)"; \
		echo "Docker Hub Image:        $(DOCKERHUB_REPO):$(DAR_BACKUP_IMAGE_VERSION)"; \
	fi

# ================================
# Help
# ================================

help:
	@echo "Available targets:"
	@grep -E '^[a-zA-Z0-9_-]+:' Makefile | grep -v '^.PHONY' | cut -d: -f1 | xargs -n1 echo " -"
