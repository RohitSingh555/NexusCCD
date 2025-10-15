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
echo "SuperAdmin: superadmin, superadmin2, superadmin3 / admin123"
echo "Admin: admin1, admin2, admin3 / admin123"
echo "Manager: manager1, manager2, manager3 / manager123"
echo "Staff: staff1, staff2, staff3 / staff123"
echo "Manager: progmanager1, progmanager2, progmanager3 / progmanager123"
echo "Viewer: viewer1, viewer2, viewer3 / viewer123"
echo "Coordinator: coordinator1, coordinator2, coordinator3 / coordinator123"
echo "Analyst: analyst1, analyst2, analyst3 / analyst123"
