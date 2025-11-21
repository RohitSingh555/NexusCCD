#!/bin/bash

# Start the Django application with debugpy for VS Code remote debugging
echo "Starting Django application with debugpy..."

# Run migrations
echo "Running database migrations..."
python manage.py migrate

# Setup initial data (roles, departments, and users) if not already done
echo "Setting up initial data..."
python manage.py setup_initial_data

# Start the development server with debugpy
echo "Starting development server with debugpy on port 5678..."
echo "Waiting for debugger to attach..."
echo "Note: VS Code should connect to localhost:5679 (mapped from container port 5678)"
python -m debugpy --listen 0.0.0.0:5678 manage.py runserver 0.0.0.0:8000

