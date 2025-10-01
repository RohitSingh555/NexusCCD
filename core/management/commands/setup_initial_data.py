from django.core.management.base import BaseCommand
from core.models import Role, Department, Staff, StaffRole
from django.contrib.auth import get_user_model

User = get_user_model()

class Command(BaseCommand):
    help = 'Set up initial roles and departments'

    def handle(self, *args, **options):
        # Create default roles
        
        roles_data = [
            {'name': 'SuperAdmin', 'description': 'Full system access', 'permissions': ['all']},
            {'name': 'Staff', 'description': 'Basic staff access', 'permissions': ['read', 'write']},
            {'name': 'Program Manager', 'description': 'Program management access', 'permissions': ['program_management']},
        ]

        for role_data in roles_data:
            role, created = Role.objects.get_or_create(
                name=role_data['name'],
                defaults=role_data
            )
            if created:
                self.stdout.write(f'Created role: {role.name}')
            else:
                self.stdout.write(f'Role already exists: {role.name}')

        # Create default departments
        departments_data = [
            {'name': 'Administration', 'owner': 'System Administrator'},
            {'name': 'Social Services', 'owner': 'Department Head'},
            {'name': 'Healthcare', 'owner': 'Medical Director'},
            {'name': 'Housing', 'owner': 'Housing Coordinator'},
            {'name': 'Employment', 'owner': 'Employment Specialist'},
            {'name': 'NA', 'owner': 'System'},  # Add NA department
        ]

        for dept_data in departments_data:
            dept, created = Department.objects.get_or_create(
                name=dept_data['name'],
                defaults=dept_data
            )
            if created:
                self.stdout.write(f'Created department: {dept.name}')
            else:
                self.stdout.write(f'Department already exists: {dept.name}')

        self.stdout.write(self.style.SUCCESS('Initial data setup completed!'))
