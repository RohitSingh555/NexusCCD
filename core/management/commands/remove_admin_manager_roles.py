from django.core.management.base import BaseCommand
from core.models import Role, StaffRole

class Command(BaseCommand):
    help = 'Remove Admin and Manager roles from the system'

    def handle(self, *args, **options):
        # Remove Admin and Manager roles
        admin_role = Role.objects.filter(name='Admin').first()
        manager_role = Role.objects.filter(name='Manager').first()
        
        if admin_role:
            # Remove all staff role assignments for Admin
            StaffRole.objects.filter(role=admin_role).delete()
            admin_role.delete()
            self.stdout.write(self.style.SUCCESS('Removed Admin role'))
        
        if manager_role:
            # Remove all staff role assignments for Manager
            StaffRole.objects.filter(role=manager_role).delete()
            manager_role.delete()
            self.stdout.write(self.style.SUCCESS('Removed Manager role'))
        
        self.stdout.write(self.style.SUCCESS('Admin and Manager roles removed successfully'))