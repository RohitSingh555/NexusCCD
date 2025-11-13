#!/bin/bash
set -e  # Exit on any error

# Production startup script
echo "Starting production Django application..."

# Wait for database to be ready
echo "Waiting for database to be ready..."
until python -c "import psycopg2; psycopg2.connect(
    host='${DB_HOST:-db}',
    port='${DB_PORT:-5432}',
    user='${DB_USER}',
    password='${DB_PASSWORD}',
    dbname='${DB_NAME}'
)" 2>/dev/null; do
    echo "Database is unavailable - sleeping"
    sleep 2
done
echo "Database is ready!"

# Run migrations
echo "Running database migrations..."
python manage.py migrate --noinput

# Setup initial data (roles, departments, and users) if not already done
echo "Setting up initial data..."
python manage.py setup_initial_data || echo "Warning: setup_initial_data failed, continuing..."

# Collect static files (in case they weren't collected during build)
echo "Collecting static files..."
python manage.py collectstatic --noinput

# Start Gunicorn
echo "Starting Gunicorn server..."
exec gunicorn ccd.wsgi:application --bind 0.0.0.0:8000 --workers 3 --timeout 0 --access-logfile - --error-logfile -
