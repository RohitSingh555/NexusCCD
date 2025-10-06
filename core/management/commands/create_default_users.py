from django.core.management.base import BaseCommand
from core.models import Role, Staff, StaffRole
from django.contrib.auth import get_user_model
import uuid

User = get_user_model()

class Command(BaseCommand):
    help = 'Create default users for each role'

    def handle(self, *args, **options):
        # Default users for each role
        default_users = [
            {
                'role_name': 'SuperAdmin',
                'users': [
                    {'username': 'superadmin', 'email': 'admin@admin.com', 'password': 'admin123'},
                    {'username': 'superadmin2', 'email': 'superadmin2@admin.com', 'password': 'admin123'},
                    {'username': 'superadmin3', 'email': 'superadmin3@admin.com', 'password': 'admin123'},
                ]
            },
            {
                'role_name': 'Admin',
                'users': [
                    {'username': 'admin1', 'email': 'admin1@admin.com', 'password': 'admin123'},
                    {'username': 'admin2', 'email': 'admin2@admin.com', 'password': 'admin123'},
                    {'username': 'admin3', 'email': 'admin3@admin.com', 'password': 'admin123'},
                ]
            },
            {
                'role_name': 'Manager',
                'users': [
                    {'username': 'manager1', 'email': 'manager1@example.com', 'password': 'manager123'},
                    {'username': 'manager2', 'email': 'manager2@example.com', 'password': 'manager123'},
                    {'username': 'manager3', 'email': 'manager3@example.com', 'password': 'manager123'},
                ]
            },
            {
                'role_name': 'Staff',
                'users': [
                    {'username': 'staff1', 'email': 'staff1@example.com', 'password': 'staff123'},
                    {'username': 'staff2', 'email': 'staff2@example.com', 'password': 'staff123'},
                    {'username': 'staff3', 'email': 'staff3@example.com', 'password': 'staff123'},
                ]
            },
            {
                'role_name': 'Program Manager',
                'users': [
                    {'username': 'progmanager1', 'email': 'progmanager1@example.com', 'password': 'progmanager123'},
                    {'username': 'progmanager2', 'email': 'progmanager2@example.com', 'password': 'progmanager123'},
                    {'username': 'progmanager3', 'email': 'progmanager3@example.com', 'password': 'progmanager123'},
                ]
            },
            {
                'role_name': 'Viewer',
                'users': [
                    {'username': 'viewer1', 'email': 'viewer1@example.com', 'password': 'viewer123'},
                    {'username': 'viewer2', 'email': 'viewer2@example.com', 'password': 'viewer123'},
                    {'username': 'viewer3', 'email': 'viewer3@example.com', 'password': 'viewer123'},
                ]
            },
            {
                'role_name': 'Coordinator',
                'users': [
                    {'username': 'coordinator1', 'email': 'coordinator1@example.com', 'password': 'coordinator123'},
                    {'username': 'coordinator2', 'email': 'coordinator2@example.com', 'password': 'coordinator123'},
                    {'username': 'coordinator3', 'email': 'coordinator3@example.com', 'password': 'coordinator123'},
                ]
            },
            {
                'role_name': 'Analyst',
                'users': [
                    {'username': 'analyst1', 'email': 'analyst1@example.com', 'password': 'analyst123'},
                    {'username': 'analyst2', 'email': 'analyst2@example.com', 'password': 'analyst123'},
                    {'username': 'analyst3', 'email': 'analyst3@example.com', 'password': 'analyst123'},
                ]
            }
        ]

        for role_data in default_users:
            role_name = role_data['role_name']
            
            try:
                role = Role.objects.get(name=role_name)
                self.stdout.write(f'Processing role: {role_name}')
                
                for user_data in role_data['users']:
                    username = user_data['username']
                    email = user_data['email']
                    password = user_data['password']
                    
                    # Create or get user
                    user, created = User.objects.get_or_create(
                        username=username,
                        defaults={
                            'email': email,
                            'first_name': username.title(),
                            'last_name': role_name.replace('_', ' ').title(),
                            'is_active': True,
                            'is_staff': True,
                            'is_superuser': True if role_name == 'SuperAdmin' else False
                        }
                    )
                    
                    if created:
                        user.set_password(password)
                        user.save()
                        self.stdout.write(f'  Created user: {username} ({email})')
                    else:
                        self.stdout.write(f'  User already exists: {username} ({email})')
                    
                    # Create or get staff profile
                    staff, staff_created = Staff.objects.get_or_create(
                        user=user,
                        defaults={
                            'first_name': user.first_name,
                            'last_name': user.last_name,
                            'email': user.email,
                            'external_id': uuid.uuid4(),
                            'active': True
                        }
                    )
                    
                    if staff_created:
                        self.stdout.write(f'    Created staff profile for {username}')
                    else:
                        self.stdout.write(f'    Staff profile already exists for {username}')
                    
                    # Assign role to staff
                    staff_role, role_assigned = StaffRole.objects.get_or_create(
                        staff=staff,
                        role=role,
                        defaults={'external_id': uuid.uuid4()}
                    )
                    
                    if role_assigned:
                        self.stdout.write(f'    Assigned {role_name} role to {username}')
                    else:
                        self.stdout.write(f'    {role_name} role already assigned to {username}')
                        
            except Role.DoesNotExist:
                self.stdout.write(self.style.ERROR(f'Role {role_name} does not exist. Please run setup_initial_data first.'))
                continue

        self.stdout.write(self.style.SUCCESS('Default users creation completed!'))
        self.stdout.write('\nDefault Login Credentials:')
        self.stdout.write('SuperAdmin: superadmin, superadmin2, superadmin3 / admin123')
        self.stdout.write('Admin: admin1, admin2, admin3 / admin123')
        self.stdout.write('Manager: manager1, manager2, manager3 / manager123')
        self.stdout.write('Staff: staff1, staff2, staff3 / staff123')
        self.stdout.write('Program Manager: progmanager1, progmanager2, progmanager3 / progmanager123')
        self.stdout.write('Viewer: viewer1, viewer2, viewer3 / viewer123')
        self.stdout.write('Coordinator: coordinator1, coordinator2, coordinator3 / coordinator123')
        self.stdout.write('Analyst: analyst1, analyst2, analyst3 / analyst123')
