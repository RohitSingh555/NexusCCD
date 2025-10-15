from django.core.management.base import BaseCommand
from django.core.management import call_command
from core.models import Role, Department, Staff, StaffRole
from django.contrib.auth import get_user_model

User = get_user_model()

class Command(BaseCommand):
    help = 'Set up initial roles, departments, and default users'

    def add_arguments(self, parser):
        parser.add_argument(
            '--skip-users',
            action='store_true',
            help='Skip creating default users',
        )

    def handle(self, *args, **options):
        # Create default roles - ensuring all roles are created first
        
        roles_data = [
            {'name': 'SuperAdmin', 'description': 'Full system access', 'permissions': ['all']},
            {'name': 'Admin', 'description': 'Administrative access', 'permissions': ['admin']},
            {'name': 'Manager', 'description': 'Program management access', 'permissions': ['program_management']},
            {'name': 'Staff', 'description': 'Basic staff access', 'permissions': ['read', 'write']},
            {'name': 'Viewer', 'description': 'Read-only access', 'permissions': ['read']},
            {'name': 'Coordinator', 'description': 'Data coordination access', 'permissions': ['coordinate']},
            {'name': 'Analyst', 'description': 'Analytical access', 'permissions': ['analyze']},
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
        
        # Create default users for each role
        if not options['skip_users']:
            self.stdout.write('\nCreating default users...')
            try:
                call_command('create_default_users')
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Error creating default users: {e}'))
