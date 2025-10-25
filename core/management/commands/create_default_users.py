from django.core.management.base import BaseCommand
from core.models import Role, Staff, StaffRole
from django.contrib.auth import get_user_model
import uuid

User = get_user_model()

class Command(BaseCommand):
    help = 'Create default users for each role'

    def handle(self, *args, **options):
        # Default users for each role - one user per role
        default_users = [
            {
                'role_name': 'SuperAdmin',
                'users': [
                    {'username': 'superadmin', 'email': 'superadmin@live.com', 'password': 'SuperAdmin@2024'},
                ]
            },
            {
                'role_name': 'Admin',
                'users': [
                    {'username': 'admin', 'email': 'admin@live.com', 'password': 'Admin@2024'},
                ]
            },
            {
                'role_name': 'Manager',
                'users': [
                    {'username': 'manager', 'email': 'manager@live.com', 'password': 'Manager@2024'},
                ]
            },
            {
                'role_name': 'Leader',
                'users': [
                    {'username': 'leader', 'email': 'leader@live.com', 'password': 'Leader@2024'},
                ]
            },
            {
                'role_name': 'Staff',
                'users': [
                    {'username': 'staff', 'email': 'staff@live.com', 'password': 'Staff@2024'},
                ]
            },
            {
                'role_name': 'User',
                'users': [
                    {'username': 'user', 'email': 'user@live.com', 'password': 'User@2024'},
                ]
            },
            {
                'role_name': 'Analyst',
                'users': [
                    {'username': 'analyst', 'email': 'analyst@live.com', 'password': 'Analyst@2024'},
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
        self.stdout.write('\n' + '='*60)
        self.stdout.write('🔐 LIVE DEPLOYMENT CREDENTIALS')
        self.stdout.write('='*60)
        self.stdout.write('SuperAdmin: superadmin / SuperAdmin@2024')
        self.stdout.write('Admin: admin / Admin@2024')
        self.stdout.write('Manager: manager / Manager@2024')
        self.stdout.write('Leader: leader / Leader@2024')
        self.stdout.write('Staff: staff / Staff@2024')
        self.stdout.write('User: user / User@2024')
        self.stdout.write('Analyst: analyst / Analyst@2024')
        self.stdout.write('='*60)
        self.stdout.write('⚠️  IMPORTANT: Change these passwords after first login!')
        self.stdout.write('='*60)
