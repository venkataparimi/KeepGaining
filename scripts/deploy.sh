#!/bin/bash
# Deployment Script for KeepGaining Production

set -e

echo "==================================="
echo "KeepGaining Production Deployment"
echo "==================================="

# Check if .env file exists
if [ ! -f .env.prod ]; then
    echo "ERROR: .env.prod file not found"
    echo "Please create .env.prod with required environment variables"
    exit 1
fi

# Load environment variables
export $(cat .env.prod | grep -v '^#' | xargs)

# Validate required variables
required_vars=(
    "DB_PASSWORD"
    "SECRET_KEY"
    "FYERS_API_ID"
    "FYERS_SECRET_KEY"
    "UPSTOX_API_KEY"
    "UPSTOX_API_SECRET"
)

for var in "${required_vars[@]}"; do
    if [ -z "${!var}" ]; then
        echo "ERROR: Required environment variable $var is not set"
        exit 1
    fi
done

echo "✓ Environment variables validated"

# Pull latest code
echo "Pulling latest code..."
git pull origin main

# Build and deploy
echo "Building Docker images..."
docker-compose -f docker-compose.prod.yml build --no-cache

echo "Starting services..."
docker-compose -f docker-compose.prod.yml up -d

# Wait for services to be healthy
echo "Waiting for services to be healthy..."
sleep 10

# Check service health
echo "Checking service health..."
if docker-compose -f docker-compose.prod.yml ps | grep -q "unhealthy"; then
    echo "ERROR: Some services are unhealthy"
    docker-compose -f docker-compose.prod.yml ps
    exit 1
fi

# Run database migrations
echo "Running database migrations..."
docker-compose -f docker-compose.prod.yml exec -T backend alembic upgrade head

echo "==================================="
echo "✓ Deployment completed successfully"
echo "==================================="
echo ""
echo "Services running at:"
echo "  Frontend: http://localhost:3000"
echo "  Backend API: http://localhost:8000"
echo "  API Docs: http://localhost:8000/docs"
echo ""
echo "View logs with: docker-compose -f docker-compose.prod.yml logs -f"
