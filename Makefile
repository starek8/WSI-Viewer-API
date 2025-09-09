# Project Makefile for WSI Viewer

SERVICE = wsi-viewer
COMPOSE = docker-compose

.PHONY: build up down logs

## Build the Docker image
build:
	$(COMPOSE) build --no-cache

## Start the app in background
up:
	$(COMPOSE) up -d

## Stop and remove containers
down:
	$(COMPOSE) down

## Show logs (follow mode)
logs:
	$(COMPOSE) logs -f $(SERVICE)


