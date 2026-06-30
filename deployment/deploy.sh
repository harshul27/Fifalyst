#!/bin/bash

# FIFA World Cup 2026 - Production Deployment Script
# Usage: bash deployment/deploy.sh

set -e

echo "Starting FIFA World Cup 2026 Production Deployment..."

# Load environment variables
if [ -f ".env.prod" ]; then
    export $(cat .env.prod | xargs)
else
    echo "ERROR: .env.prod file not found!"
    exit 1
fi

# Create necessary directories
mkdir -p deployment/backups
mkdir -p deployment/grafana-dashboards
mkdir -p data/{models,embeddings,backups}

# Build Docker images
echo "Building Docker images..."
docker-compose -f docker-compose.prod.yml build

# Start all services
echo "Starting services..."
docker-compose -f docker-compose.prod.yml up -d

# Wait for services to be healthy
echo "Waiting for services to become healthy..."
sleep 30

# Check service health
echo "Checking service health..."
services=("postgres" "redis" "weaviate" "prometheus" "grafana" "streamlit")

for service in ${services[@]}; do
    if docker ps | grep -q "fifa-${service}-prod"; then
        echo "✓ ${service} is running"
    else
        echo "✗ ${service} failed to start"
        exit 1
    fi
done

# Initialize PostgreSQL schema
echo "Initializing PostgreSQL..."
docker exec fifa-postgres-prod psql -U fifa -d fifa_wc_2026 -f /backups/init_schema.sql || true

# Upload initial data to Weaviate
echo "Initializing Weaviate schema..."
python scripts/init_weaviate.py

# Initialize MinIO buckets
echo "Initializing MinIO buckets..."
docker exec fifa-minio mc alias set minio http://localhost:9000 ${MINIO_USER} ${MINIO_PASSWORD}
docker exec fifa-minio mc mb minio/models minio/embeddings minio/backups || true

echo ""
echo "=========================================="
echo "Deployment Complete!"
echo "=========================================="
echo ""
echo "Dashboard: http://localhost:8501"
echo "Prometheus: http://localhost:9090"
echo "Grafana: http://localhost:3000"
echo "MinIO: http://localhost:9001"
echo ""
