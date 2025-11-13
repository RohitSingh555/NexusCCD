#!/bin/bash
set -e

echo "=========================================="
echo "Production Deployment Script"
echo "=========================================="

# Check if docker-compose is available
if ! command -v docker-compose &> /dev/null; then
    echo "ERROR: docker-compose is not installed"
    exit 1
fi

echo ""
echo "Step 1: Stopping existing containers..."
docker-compose -f docker-compose.prod.yml down

echo ""
echo "Step 2: Building production image..."
docker-compose -f docker-compose.prod.yml build web

echo ""
echo "Step 3: Starting database..."
docker-compose -f docker-compose.prod.yml up -d db

echo ""
echo "Step 4: Waiting for database to be ready..."
sleep 10
until docker-compose -f docker-compose.prod.yml exec -T db pg_isready -U ccd -d ccd_prod > /dev/null 2>&1; do
    echo "  Waiting for database..."
    sleep 2
done
echo "✓ Database is ready"

echo ""
echo "Step 5: Running migrations..."
docker-compose -f docker-compose.prod.yml run --rm web python manage.py migrate --noinput
echo "✓ Migrations applied"

echo ""
echo "Step 6: Setting up initial data..."
docker-compose -f docker-compose.prod.yml run --rm web python manage.py setup_initial_data || echo "⚠ Warning: setup_initial_data had issues (may already be set up)"

echo ""
echo "Step 7: Collecting static files..."
docker-compose -f docker-compose.prod.yml run --rm web python manage.py collectstatic --noinput
echo "✓ Static files collected"

echo ""
echo "Step 8: Starting all services..."
docker-compose -f docker-compose.prod.yml up -d

echo ""
echo "Step 9: Checking service status..."
sleep 5
docker-compose -f docker-compose.prod.yml ps

echo ""
echo "=========================================="
echo "Deployment Complete!"
echo "=========================================="
echo ""
echo "To view logs:"
echo "  docker-compose -f docker-compose.prod.yml logs -f web"
echo ""
echo "To check migration status:"
echo "  docker-compose -f docker-compose.prod.yml run --rm web python manage.py showmigrations"
echo ""
echo "To access the application, check nginx configuration for the domain."
echo ""

