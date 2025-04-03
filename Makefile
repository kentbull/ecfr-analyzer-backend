# Phony targets don't represent files, only actions.
.PHONY: all build push

VERSION=1.0.0
REGISTRY=kentbull
IMAGE=ecfr-api
IMAGE_TAG=$(REGISTRY)/$(IMAGE):latest
VERSIONED_TAG=$(REGISTRY)/$(IMAGE):$(VERSION)

all: build push

build:
	@docker build \
		--platform=linux/amd64,linux/arm64 \
		--label "version=$(VERSION)" \
		--label "build_date=$(shell date -u +'%Y-%m-%dT%H:%M:%SZ')" \
		--tag $(IMAGE_TAG) \
		--tag $(VERSIONED_TAG) \
		-f Dockerfile . || { echo "Build failed"; exit 1; }

# Requires the .env.docker file to be populated with correct environment variables
run:
	@docker run --name ecfr-api -p 3001:80 --rm --env-file .env.docker \
		$(IMAGE_TAG)


push:
	@echo "pushing image $(IMAGE_TAG) and $(VERSIONED_TAG)"
	@docker push $(IMAGE_TAG)
	@docker push $(VERSIONED_TAG)
