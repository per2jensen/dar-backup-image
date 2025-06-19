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

BASE_IMAGE_NAME = dar-backup-base
FINAL_IMAGE_NAME = dar-backup
DOCKERHUB_REPO = per2jensen/dar-backup
BASE_LATEST_TAG = $(BASE_IMAGE_NAME):24.04

# these LABELS are used in the final image
BASE_IMAGE_DATE := $(shell date -u +%Y-%m-%dT%H:%M:%SZ)
DAR_BACKUP_DATE := $(shell date -u +%Y-%m-%dT%H:%M:%SZ)

DOCKER ?= docker

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


base: check_version
	@echo "Building base image..."
	$(DOCKER) build --pull -f Dockerfile-base-image \
		--build-arg VERSION=$(DAR_BACKUP_IMAGE_VERSION) \
		-t $(BASE_IMAGE_NAME):24.04-$(DAR_BACKUP_IMAGE_VERSION) .
		$(DOCKER) tag $(BASE_IMAGE_NAME):24.04-$(DAR_BACKUP_IMAGE_VERSION) $(BASE_LATEST_TAG)


release: check_version final login push
	@echo "✅ Release complete for: $(DOCKERHUB_REPO):$(DAR_BACKUP_IMAGE_VERSION)"


final: check_version base
	$(eval FINAL_TAG := $(FINAL_IMAGE_NAME):$(DAR_BACKUP_IMAGE_VERSION))
	$(eval DOCKERHUB_TAG := $(DOCKERHUB_REPO):$(DAR_BACKUP_IMAGE_VERSION))
	@echo "Building final image: $(FINAL_TAG) and $(DOCKERHUB_TAG) ..."
	$(DOCKER) build -f Dockerfile-dar-backup \
		--build-arg VERSION=$(DAR_BACKUP_IMAGE_VERSION) \
		--label org.opencontainers.image.source=https://hub.docker.com/r/per2jensen/dar-backup \
		--label org.opencontainers.image.created="$(DAR_BACKUP_DATE)" \
		--label org.opencontainers.image.base.created="$(BASE_IMAGE_DATE)" \
		-t $(FINAL_TAG) \
		-t $(DOCKERHUB_TAG) .

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
	-$(DOCKER) rmi -f $(BASE_IMAGE_NAME):24.04-$(DAR_BACKUP_IMAGE_VERSION) || true
	-$(DOCKER) rmi -f $(BASE_LATEST_TAG) || true
	-$(DOCKER) rmi -f $(FINAL_IMAGE_NAME):$(DAR_BACKUP_IMAGE_VERSION) || true

push: check_version
	@echo "Push $(DOCKERHUB_REPO):$(DAR_BACKUP_IMAGE_VERSION) to Docker Hub..."
	$(DOCKER) push $(DOCKERHUB_REPO):$(DAR_BACKUP_IMAGE_VERSION)


# ================================
# Dev build
# ================================

all-dev:
	@$(MAKE) DAR_BACKUP_IMAGE_VERSION=dev base
	@$(MAKE) dev
dev:
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

labels:
	@if [ -z "$(DAR_BACKUP_IMAGE_VERSION)" ]; then \
		echo "❌ ERROR: DAR_BACKUP_IMAGE_VERSION is not set."; \
	else \
		docker inspect $(FINAL_IMAGE_NAME):$(DAR_BACKUP_IMAGE_VERSION) --format '{{json .Config.Labels}}' | jq; \
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
		echo "Base Image (versioned):  $(BASE_IMAGE_NAME):24.04-$(DAR_BACKUP_IMAGE_VERSION)"; \
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
