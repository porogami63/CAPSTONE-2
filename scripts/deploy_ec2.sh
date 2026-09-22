#!/usr/bin/env bash

# ==============================================================================
# HTC Core — Amazon EC2 Automated Production Deployment Script
# ==============================================================================
# Usage: ./scripts/deploy_ec2.sh
# Prerequisites: Git, Docker, and Docker Compose V2 installed on Ubuntu EC2 host.
# ==============================================================================

set -e

echo "[1/5] Pulling latest code changes from repository..."
git pull origin main

echo "[2/5] Building production Docker container images..."
docker compose build --no-cache

echo "[3/5] Starting Docker Compose stack..."
docker compose up -d

echo "[4/5] Executing database migrations..."
docker compose exec -T web python manage.py migrate --noinput

echo "[5/5] Collecting static assets..."
docker compose exec -T web python manage.py collectstatic --noinput

echo "=============================================================================="
echo " Deployment successful! HTC Core is live on Amazon EC2 host."
echo "=============================================================================="
docker compose ps
