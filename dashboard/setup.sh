#!/bin/bash

# Bioforklift Monitoring Dashboard Setup Script

set -e

echo "🚀 Setting up Bioforklift Monitoring Dashboard..."

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install Docker first."
    exit 1
fi

# Check if Docker Compose is installed
if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose is not installed. Please install Docker Compose first."
    exit 1
fi

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo "📝 Creating .env file from template..."
    cp .env.example .env
    echo "⚠️  Please edit .env file with your configuration before continuing."
    echo "   Required variables:"
    echo "   - BIGQUERY_PROJECT_ID"
    echo "   - BIGQUERY_DATASET_ID"
    echo "   - GOOGLE_APPLICATION_CREDENTIALS"
    echo ""
    read -p "Press Enter when you've configured .env file..."
fi

# Validate required environment variables
source .env

# Check if using mock data
if [ "${MOCK_DATA:-false}" = "true" ]; then
    echo "✅ Using mock data for local testing"
else
    echo "🔍 Validating BigQuery configuration..."
    
    if [ -z "$BIGQUERY_PROJECT_ID" ]; then
        echo "❌ BIGQUERY_PROJECT_ID is not set in .env file"
        exit 1
    fi

    if [ -z "$BIGQUERY_DATASET_ID" ]; then
        echo "❌ BIGQUERY_DATASET_ID is not set in .env file"
        exit 1
    fi

    if [ -z "$GOOGLE_APPLICATION_CREDENTIALS" ]; then
        echo "❌ GOOGLE_APPLICATION_CREDENTIALS is not set in .env file"
        exit 1
    fi

    if [ ! -f "$GOOGLE_APPLICATION_CREDENTIALS" ]; then
        echo "❌ Google Cloud credentials file not found: $GOOGLE_APPLICATION_CREDENTIALS"
        exit 1
    fi
    
    echo "✅ BigQuery configuration validated"
fi

# Build and start services
echo "🏗️  Building Docker images..."
docker-compose build

echo "🚀 Starting services..."
docker-compose up -d

# Wait for services to be healthy
echo "⏳ Waiting for services to start..."
sleep 10

# Check backend health
echo "🔍 Checking backend health..."
if curl -f http://localhost:8000/health &> /dev/null; then
    echo "✅ Backend is healthy"
else
    echo "❌ Backend health check failed"
    echo "📋 Backend logs:"
    docker-compose logs backend
    exit 1
fi

# Check frontend
echo "🔍 Checking frontend..."
if curl -f http://localhost:3000 &> /dev/null; then
    echo "✅ Frontend is accessible"
else
    echo "❌ Frontend accessibility check failed"
    echo "📋 Frontend logs:"
    docker-compose logs frontend
    exit 1
fi

echo ""
echo "🎉 Dashboard setup complete!"
echo ""
echo "📊 Dashboard URL: http://localhost:3000"
echo "🔧 API Documentation: http://localhost:8000/docs"
echo "📋 View logs: docker-compose logs -f"
echo "🛑 Stop services: docker-compose down"
echo ""
echo "For development mode with hot reload:"
echo "docker-compose --profile dev up -d"
echo "Frontend (dev): http://localhost:5173"