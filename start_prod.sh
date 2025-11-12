#!/bin/bash

# Production startup script
echo "Starting production Django application..."

# Run migrations
echo "Running database migrations..."
python manage.py migrate

# Setup initial data (roles, departments, and users) if not already done
echo "Setting up initial data..."
python manage.py setup_initial_data

# Collect static files
echo "Collecting static files..."
python manage.py collectstatic --noinput

# Start Gunicorn
echo "Starting Gunicorn server..."
exec gunicorn ccd.wsgi:application --bind 0.0.0.0:8000 --timeout 0
