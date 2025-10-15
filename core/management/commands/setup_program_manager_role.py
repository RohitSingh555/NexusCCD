from django.core.management.base import BaseCommand
from core.models import Role


class Command(BaseCommand):
    help = 'Creates or updates the Manager role'

    def handle(self, *args, **kwargs):
        role, created = Role.objects.update_or_create(
            name='Manager',
            defaults={
                'description': 'Can manage assigned programs and services with restricted access',
                'permissions': [
                    'view_assigned_programs',
                    'view_assigned_services',
                    'view_assigned_departments',
                    'manage_restrictions_assigned_programs',
                    'manage_enrollments_assigned_programs',
                    'view_reports_readonly',
                ]
            }
        )
        
        if created:
            self.stdout.write(self.style.SUCCESS('Successfully created Manager role'))
        else:
            self.stdout.write(self.style.SUCCESS('Successfully updated Manager role'))
        
        # Display role details
        self.stdout.write(self.style.SUCCESS(f'\nRole Details:'))
        self.stdout.write(f'Name: {role.name}')
        self.stdout.write(f'Description: {role.description}')
        self.stdout.write(f'Permissions: {", ".join(role.permissions)}')