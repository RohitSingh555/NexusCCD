#!/bin/bash
set -e

echo "=========================================="
echo "Testing Production Deployment"
echo "=========================================="

# Check if docker-compose is available
if ! command -v docker-compose &> /dev/null; then
    echo "ERROR: docker-compose is not installed"
    exit 1
fi

echo ""
echo "1. Checking docker-compose.prod.yml syntax..."
docker-compose -f docker-compose.prod.yml config > /dev/null
echo "✓ docker-compose.prod.yml is valid"

echo ""
echo "2. Checking for .env.prod file..."
if [ -f .env.prod ]; then
    echo "✓ .env.prod file exists"
else
    echo "⚠ WARNING: .env.prod file not found (will use defaults)"
fi

echo ""
echo "3. Building production image..."
docker-compose -f docker-compose.prod.yml build web

echo ""
echo "4. Checking migration status..."
# Start database only
docker-compose -f docker-compose.prod.yml up -d db

# Wait for database
echo "Waiting for database to be ready..."
sleep 5

# Check if we can connect to database
docker-compose -f docker-compose.prod.yml run --rm web python -c "
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ccd.settings')
django.setup()
from django.db import connection
cursor = connection.cursor()
cursor.execute('SELECT version();')
print('✓ Database connection successful')
print(f'  PostgreSQL version: {cursor.fetchone()[0]}')
"

echo ""
echo "5. Testing migrations..."
docker-compose -f docker-compose.prod.yml run --rm web python manage.py migrate --plan

echo ""
echo "6. Checking for pending migrations..."
PENDING=$(docker-compose -f docker-compose.prod.yml run --rm web python manage.py showmigrations --plan | grep '\[ \]' | wc -l)
if [ "$PENDING" -gt 0 ]; then
    echo "⚠ WARNING: $PENDING pending migrations found"
    echo "   Run 'docker-compose -f docker-compose.prod.yml run --rm web python manage.py migrate' to apply them"
else
    echo "✓ No pending migrations"
fi

echo ""
echo "7. Testing static files collection..."
docker-compose -f docker-compose.prod.yml run --rm web python manage.py collectstatic --noinput --dry-run
echo "✓ Static files collection test passed"

echo ""
echo "8. Testing management commands..."
docker-compose -f docker-compose.prod.yml run --rm web python manage.py setup_initial_data --skip-users
echo "✓ setup_initial_data command works"

echo ""
echo "=========================================="
echo "Production Deployment Test Complete"
echo "=========================================="
echo ""
echo "To deploy to production, run:"
echo "  docker-compose -f docker-compose.prod.yml up -d"
echo ""
echo "To check logs:"
echo "  docker-compose -f docker-compose.prod.yml logs -f web"
echo ""
echo "To apply migrations manually:"
echo "  docker-compose -f docker-compose.prod.yml run --rm web python manage.py migrate"
echo ""

