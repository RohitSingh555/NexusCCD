#!/bin/bash

# Start the Django application with database initialization
echo "Starting Django application..."

# Run migrations
echo "Running database migrations..."
python manage.py migrate

# Setup initial data (roles, departments, and users) if not already done
echo "Setting up initial data..."
python manage.py setup_initial_data

# Start the development server
echo "Starting development server..."
python manage.py runserver 0.0.0.0:8000
