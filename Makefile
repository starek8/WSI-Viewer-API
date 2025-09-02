# Project Makefile for WSI Viewer

SERVICE = wsi-viewer
COMPOSE = docker-compose

.PHONY: build up down logs bash shell prune restart

## Build the Docker image
build:
	$(COMPOSE) build --no-cache

## Start the app in background
up:
	$(COMPOSE) up -d

## Stop and remove containers
down:
	$(COMPOSE) down

## Restart the app
restart: down up

## Show logs (follow mode)
logs:
	$(COMPOSE) logs -f $(SERVICE)

## Open a bash shell inside the running container
bash:
	docker exec -it $$(docker ps --filter "name=$(SERVICE)" -q) /bin/bash

## Run a one-off shell in a new container
shell:
	$(COMPOSE) run --rm $(SERVICE) /bin/bash

## Remove orphaned containers
prune:
	$(COMPOSE) down --remove-orphans
	docker system prune -f
