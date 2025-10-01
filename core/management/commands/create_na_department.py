from django.core.management.base import BaseCommand
from core.models import Department

class Command(BaseCommand):
    help = 'Create NA (Not Assigned) department for programs without specific departments'

    def handle(self, *args, **options):
        # Create NA department
        na_department, created = Department.objects.get_or_create(
            name='NA',
            defaults={
                'owner': 'System',
                'name': 'NA'
            }
        )
        
        if created:
            self.stdout.write(
                self.style.SUCCESS('Created NA department for unassigned programs')
            )
        else:
            self.stdout.write(
                self.style.WARNING('NA department already exists')
            )
