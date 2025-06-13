#  Usage examples:
#  ---------------
#
#  make final
#   or
#  export DAR_BACKUP_IMAGE_VERSION=0.9.9-rc1; make final
#   or
#  make DAR_BACKUP_IMAGE_VERSION=0.9.9-rc1 final
#
# ================================
# Configuration
# ================================

DAR_BACKUP_IMAGE_VERSION ?= 0.5.1-alpha
BASE_IMAGE_NAME = dar-backup-base
FINAL_IMAGE_NAME = dar-backup
BASE_TAG = $(BASE_IMAGE_NAME):24.04-$(DAR_BACKUP_IMAGE_VERSION)
FINAL_TAG = $(FINAL_IMAGE_NAME):$(DAR_BACKUP_IMAGE_VERSION)
GHCR_REPO = ghcr.io/per2jensen/dar-backup
GHCR_TAG = $(GHCR_REPO):$(DAR_BACKUP_IMAGE_VERSION)
BASE_LATEST_TAG = $(BASE_IMAGE_NAME):24.04

DOCKER ?= docker

# ================================
# Targets
# ================================

.PHONY: all base final clean push tag login

all: base final

base:
	@echo "Building base image: $(BASE_TAG) ..."
	$(DOCKER) build -f Dockerfile-base-image --build-arg VERSION=$(DAR_BACKUP_IMAGE_VERSION) -t $(BASE_TAG) .
	$(DOCKER) tag $(BASE_TAG) $(BASE_LATEST_TAG)

final:
	@echo "Building final image: $(FINAL_TAG) and $(GHCR_TAG) ..."
	$(DOCKER) build -f Dockerfile-dar-backup --build-arg VERSION=$(DAR_BACKUP_IMAGE_VERSION) \
		-t $(FINAL_TAG) \
		-t $(GHCR_TAG) .

clean:
	-$(DOCKER) rmi -f $(BASE_TAG) || true
	-$(DOCKER) rmi -f $(BASE_LATEST_TAG) || true
	-$(DOCKER) rmi -f $(FINAL_TAG) || true
	-$(DOCKER) rmi -f $(GHCR_TAG) || true

push:
# Not uploading to Docker Hub yet
#	$(DOCKER) push $(FINAL_TAG)
	@echo "Push $(GHCR_TAG) to GitHub Container Registry (GHCR.io)..."
	$(DOCKER) push $(GHCR_TAG)


# ================================
# Labels (pretty-print)
# ================================

labels:
	@echo "Labels for $(FINAL_TAG):"
	@docker inspect $(FINAL_TAG) --format '{{json .Config.Labels}}' | jq


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
		echo "   export CR_PAT=your_token"; \
		exit 1; \
	fi
	curl -s -H "Authorization: Bearer $$CR_PAT" \
	     -H "Accept: application/vnd.github+json" \
	     "https://api.github.com/users/per2jensen/packages/container/dar-backup/versions" | jq


# ================================
# List GHCR version IDs and tags
# ================================
ghcr-list-ids:
	@if [ -z "$$CR_PAT" ]; then \
		echo "❌ ERROR: Please export your GitHub token as CR_PAT"; \
		echo "   export CR_PAT=your_token"; \
		exit 1; \
	fi
	curl -s -H "Authorization: Bearer $$CR_PAT" \
	     -H "Accept: application/vnd.github+json" \
	     "https://api.github.com/users/per2jensen/packages/container/dar-backup/versions" | \
	     jq -r '.[] | "ID: \(.id)  Tags: \(.metadata.container.tags)"'


# ================================
# Delete GHCR version by ID
# ================================
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
# Convenience
# ================================

tag:
	@echo "Base Image (versioned):  $(BASE_TAG)"
	@echo "Base Image (latest):     $(BASE_LATEST_TAG)"
	@echo "Final Image:             $(FINAL_TAG)"
	@echo "GHCR Image:              $(GHCR_TAG)"


# ================================
# Help
# ================================

help:
	@echo "Available targets:"
	@grep -E '^[a-zA-Z0-9_-]+:' Makefile | grep -v '^.PHONY' | cut -d: -f1 | xargs -n1 echo " -"
