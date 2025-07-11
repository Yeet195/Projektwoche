#!/bin/bash
# Docker build and run script

DETACHED=${1:-false}

echo "Building Docker image..."
docker compose build --no-cache

echo "Starting Docker containers..."
if [ "$DETACHED" = true ]; then
	docker compose up -d
else
	docker compose up
fi