#!/bin/bash

# Initialize the database with roles, departments, and default users
echo "Initializing database with roles and default users..."

# Run Django migrations first
python manage.py migrate

# Setup initial data (roles, departments, and users)
python manage.py setup_initial_data

echo "Database initialization completed!"
echo ""
echo "Available login credentials:"
echo "SuperAdmin: superadmin / SuperAdmin@2024"
echo "Admin: admin / Admin@2024"
echo "Manager: manager / Manager@2024"
echo "Leader: leader / Leader@2024"
echo "Staff: staff / Staff@2024"
echo "User: user / User@2024"
echo "Analyst: analyst / Analyst@2024"
