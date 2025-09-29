from django.core.management.base import BaseCommand
from core.models import Role, Department


class Command(BaseCommand):
    help = 'Set up initial roles and departments'

    def handle(self, *args, **options):
        # Create default roles
        roles_data = [
            {
                'name': 'SuperAdmin',
                'description': 'Full system access with all permissions',
                'permissions': [
                    'all',
                    'manage_users',
                    'manage_staff',
                    'manage_clients',
                    'manage_programs',
                    'manage_departments',
                    'view_reports',
                    'manage_roles',
                    'system_admin'
                ]
            },
            {
                'name': 'Staff',
                'description': 'Staff member with operational access',
                'permissions': [
                    'view_clients',
                    'edit_clients',
                    'view_programs',
                    'view_enrollments',
                    'view_reports',
                    'manage_own_profile'
                ]
            },
            {
                'name': 'User',
                'description': 'Basic user with limited access',
                'permissions': [
                    'view_own_profile',
                    'edit_own_profile'
                ]
            }
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
