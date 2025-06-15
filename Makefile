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
GHCR_REPO = ghcr.io/per2jensen/dar-backup
BASE_LATEST_TAG = $(BASE_IMAGE_NAME):24.04

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

final: check_version base
	$(eval FINAL_TAG := $(FINAL_IMAGE_NAME):$(DAR_BACKUP_IMAGE_VERSION))
	$(eval GHCR_TAG := $(GHCR_REPO):$(DAR_BACKUP_IMAGE_VERSION))
	@echo "Building final image: $(FINAL_TAG) and $(GHCR_TAG) ..."
	$(DOCKER) build -f Dockerfile-dar-backup \
		--build-arg VERSION=$(DAR_BACKUP_IMAGE_VERSION) \
		-t $(FINAL_TAG) \
		-t $(GHCR_TAG) .

release: check_version final login push
	@echo "✅ Release complete for: ghcr.io/per2jensen/dar-backup:$(DAR_BACKUP_IMAGE_VERSION)"



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
	-$(DOCKER) rmi -f $(GHCR_REPO):$(DAR_BACKUP_IMAGE_VERSION) || true

push: check_version
	@echo "Push ghcr.io/per2jensen/dar-backup:$(DAR_BACKUP_IMAGE_VERSION) to GHCR..."
	$(DOCKER) push ghcr.io/per2jensen/dar-backup:$(DAR_BACKUP_IMAGE_VERSION)




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
# GHCR Login
# ================================

login:
	@echo "Logging in to GitHub Container Registry (GHCR.io)..."
	@if [ -z "$$CR_PAT" ]; then \
		echo "❌ ERROR: Please export your personal access token as CR_PAT in your shell:"; \
		echo "   export CR_PAT=your_token"; \
		exit 1; \
	fi
	echo "$$CR_PAT" | $(DOCKER) login ghcr.io -u per2jensen --password-stdin

# ================================
# GHCR Tags Listing
# ================================

ghcr-tags:
	@if [ -z "$$CR_PAT" ]; then \
		echo "❌ ERROR: Please export your GitHub token as CR_PAT"; \
		exit 1; \
	fi
	curl -s -H "Authorization: Bearer $$CR_PAT" \
	     -H "Accept: application/vnd.github+json" \
	     "https://api.github.com/users/per2jensen/packages/container/dar-backup/versions" | jq

ghcr-list-ids:
	@if [ -z "$$CR_PAT" ]; then \
		echo "❌ ERROR: Please export your GitHub token as CR_PAT"; \
		exit 1; \
	fi
	curl -s -H "Authorization: Bearer $$CR_PAT" \
	     -H "Accept: application/vnd.github+json" \
	     "https://api.github.com/users/per2jensen/packages/container/dar-backup/versions" | \
	     jq -r '.[] | "ID: \(.id)  Tags: \(.metadata.container.tags)"'

ghcr-delete-id:
	@if [ -z "$$ID" ]; then \
		echo "❌ ERROR: Please provide ID. Usage: make ghcr-delete-id ID=12345678"; \
		exit 1; \
	fi
	@if [ -z "$$CR_PAT" ]; then \
		echo "❌ ERROR: Please export your GitHub token as CR_PAT"; \
		exit 1; \
	fi
	curl -s -X DELETE -H "Authorization: Bearer $$CR_PAT" \
	     -H "Accept: application/vnd.github+json" \
	     "https://api.github.com/users/per2jensen/packages/container/dar-backup/versions/$$ID"

# ================================
# Tag preview
# ================================

tag:
	@if [ -z "$(DAR_BACKUP_IMAGE_VERSION)" ]; then \
		echo "❌ DAR_BACKUP_IMAGE_VERSION is not set"; \
	else \
		echo "Base Image (versioned):  $(BASE_IMAGE_NAME):24.04-$(DAR_BACKUP_IMAGE_VERSION)"; \
		echo "Base Image (latest):     $(BASE_LATEST_TAG)"; \
		echo "Final Image:             $(FINAL_IMAGE_NAME):$(DAR_BACKUP_IMAGE_VERSION)"; \
		echo "GHCR Image:              $(GHCR_REPO):$(DAR_BACKUP_IMAGE_VERSION)"; \
	fi

# ================================
# Help
# ================================

help:
	@echo "Available targets:"
	@grep -E '^[a-zA-Z0-9_-]+:' Makefile | grep -v '^.PHONY' | cut -d: -f1 | xargs -n1 echo " -"
