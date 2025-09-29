from django.core.management.base import BaseCommand
from django.core.exceptions import ValidationError
from core.models import User, Staff, Role, Department
import getpass


class Command(BaseCommand):
    help = 'Create the first superadmin user with proper role assignment'

    def add_arguments(self, parser):
        parser.add_argument(
            '--email',
            type=str,
            help='Email for the superadmin user',
            default='admin@nexusccd.com'
        )
        parser.add_argument(
            '--username',
            type=str,
            help='Username for the superadmin user',
            default='superadmin'
        )
        parser.add_argument(
            '--first-name',
            type=str,
            help='First name for the superadmin user',
            default='Super'
        )
        parser.add_argument(
            '--last-name',
            type=str,
            help='Last name for the superadmin user',
            default='Admin'
        )
        parser.add_argument(
            '--password',
            type=str,
            help='Password for the superadmin user (if not provided, will prompt)',
            default=None
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force creation even if superadmin already exists',
            default=False
        )

    def handle(self, *args, **options):
        email = options['email']
        username = options['username']
        first_name = options['first_name']
        last_name = options['last_name']
        password = options['password']
        force = options['force']

        # Check if superadmin already exists
        if not force and User.objects.filter(is_superuser=True).exists():
            self.stdout.write(
                self.style.WARNING('Superadmin already exists! Use --force to override.')
            )
            return

        # Get password if not provided
        if not password:
            while True:
                password = getpass.getpass('Enter password for superadmin: ')
                password_confirm = getpass.getpass('Confirm password: ')
                if password == password_confirm:
                    break
                self.stdout.write(self.style.ERROR('Passwords do not match. Try again.'))

        try:
            # Create or update superadmin user
            if force and User.objects.filter(is_superuser=True).exists():
                user = User.objects.filter(is_superuser=True).first()
                user.email = email
                user.username = username
                user.first_name = first_name
                user.last_name = last_name
                user.set_password(password)
                user.save()
                self.stdout.write(self.style.SUCCESS(f'Updated existing superadmin: {user.email}'))
            else:
                user = User.objects.create_superuser(
                    email=email,
                    username=username,
                    first_name=first_name,
                    last_name=last_name,
                    password=password
                )
                self.stdout.write(self.style.SUCCESS(f'Created superadmin user: {user.email}'))

            # Create or update staff profile
            staff, created = Staff.objects.get_or_create(
                user=user,
                defaults={
                    'first_name': first_name,
                    'last_name': last_name,
                    'email': email,
                    'active': True
                }
            )
            
            if not created:
                # Update existing staff profile
                staff.first_name = first_name
                staff.last_name = last_name
                staff.email = email
                staff.active = True
                staff.save()
                self.stdout.write(self.style.SUCCESS(f'Updated staff profile for: {user.email}'))
            else:
                self.stdout.write(self.style.SUCCESS(f'Created staff profile for: {user.email}'))

            # Create SuperAdmin role if it doesn't exist
            superadmin_role, role_created = Role.objects.get_or_create(
                name='SuperAdmin',
                defaults={
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
                }
            )
            
            if role_created:
                self.stdout.write(self.style.SUCCESS(f'Created SuperAdmin role'))
            else:
                self.stdout.write(f'SuperAdmin role already exists')

            # Assign SuperAdmin role to staff
            staff_role, staff_role_created = staff.staffrole_set.get_or_create(
                role=superadmin_role,
                defaults={}
            )
            
            if staff_role_created:
                self.stdout.write(self.style.SUCCESS(f'Assigned SuperAdmin role to {user.email}'))
            else:
                self.stdout.write(f'SuperAdmin role already assigned to {user.email}')

            # Create default roles if they don't exist
            self.create_default_roles()

            # Create default department if it doesn't exist
            admin_dept, dept_created = Department.objects.get_or_create(
                name='Administration',
                defaults={'owner': 'System Administrator'}
            )
            
            if dept_created:
                self.stdout.write(self.style.SUCCESS('Created Administration department'))

            self.stdout.write(
                self.style.SUCCESS(
                    f'\n✅ Superadmin setup completed successfully!\n'
                    f'📧 Email: {email}\n'
                    f'👤 Username: {username}\n'
                    f'🔑 Password: {"*" * len(password)}\n'
                    f'🎯 Role: SuperAdmin\n'
                    f'📋 Staff Profile: Created\n\n'
                    f'You can now login and manage the system!'
                )
            )

        except ValidationError as e:
            self.stdout.write(self.style.ERROR(f'Validation error: {e}'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error creating superadmin: {e}'))

    def create_default_roles(self):
        """Create default roles for the system"""
        roles_data = [
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