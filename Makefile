# ================================
# Configuration
# ================================

VERSION ?= 0.5.0-alpha
BASE_IMAGE_NAME = dar-backup-base
FINAL_IMAGE_NAME = dar-backup
BASE_TAG = $(BASE_IMAGE_NAME):24.04-$(VERSION)
FINAL_TAG = $(FINAL_IMAGE_NAME):$(VERSION)

DOCKER ?= sudo docker

# ================================
# Targets
# ================================

.PHONY: all base final clean push

all: base final

base:
	$(DOCKER) build -f Dockerfile-base-image --build-arg VERSION=$(VERSION) -t $(BASE_TAG) .

final:
	$(DOCKER) build -f Dockerfile-dar-backup --build-arg VERSION=$(VERSION) -t $(FINAL_TAG) .

clean:
	$(DOCKER) rmi -f $(BASE_TAG) || true
	$(DOCKER) rmi -f $(FINAL_TAG) || true

push:
	$(DOCKER) push $(BASE_TAG)
	$(DOCKER) push $(FINAL_TAG)

# ================================
# Convenience
# ================================

tag:
	@echo "Base Image:  $(BASE_TAG)"
	@echo "Final Image: $(FINAL_TAG)"


