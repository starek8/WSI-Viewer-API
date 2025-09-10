SERVICE = wsi-viewer
COMPOSE = docker-compose

.PHONY: build up down logs

build:
	$(COMPOSE) build --no-cache

up:
	$(COMPOSE) up -d

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f $(SERVICE)


