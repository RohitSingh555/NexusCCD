from django.core.management.base import BaseCommand
from core.models import Staff
import uuid

class Command(BaseCommand):
    help = 'Fix Staff records with missing external_id'

    def handle(self, *args, **options):
        # Get all staff records
        all_staff = Staff.objects.all()
        fixed_count = 0
        
        for staff in all_staff:
            # Check if external_id is None or empty
            if not staff.external_id or str(staff.external_id).strip() == '':
                staff.external_id = uuid.uuid4()
                staff.save()
                fixed_count += 1
                self.stdout.write(f'Fixed external_id for staff: {staff.first_name} {staff.last_name}')
        
        self.stdout.write(f'Fixed {fixed_count} staff records')
        self.stdout.write(self.style.SUCCESS('All staff external_ids have been fixed!'))