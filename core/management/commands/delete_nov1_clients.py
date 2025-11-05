from django.core.management.base import BaseCommand
from django.db import transaction, models
from django.utils import timezone
from datetime import datetime, date
from core.models import (
    Client, ClientProgramEnrollment, Intake, Discharge, 
    ServiceRestriction, ClientDuplicate, ClientExtended
)
try:
    from staff.models import StaffClientAssignment
except ImportError:
    StaffClientAssignment = None


class Command(BaseCommand):
    help = 'Delete all clients created today and all their related data'

    def add_arguments(self, parser):
        parser.add_argument(
            '--confirm',
            action='store_true',
            help='Confirm deletion (required for safety)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without actually deleting',
        )

    def handle(self, *args, **options):
        # Get today's date
        today = timezone.now().date()
        
        # Create date range for today (start of day to end of day)
        today_start = timezone.make_aware(datetime.combine(today, datetime.min.time()))
        today_end = timezone.make_aware(datetime.combine(today, datetime.max.time()))
        
        self.stdout.write(f'Looking for clients created today ({today.strftime("%B %d, %Y")})...')
        
        # Find clients created today
        clients = Client.objects.filter(created_at__gte=today_start, created_at__lte=today_end)
        client_count = clients.count()
        
        if client_count == 0:
            self.stdout.write(self.style.WARNING(f'No clients found created today ({today.strftime("%B %d, %Y")}).'))
            return
        
        # Get related data counts
        client_ids = list(clients.values_list('id', flat=True))
        
        enrollment_count = ClientProgramEnrollment.objects.filter(client_id__in=client_ids).count()
        intake_count = Intake.objects.filter(client_id__in=client_ids).count()
        discharge_count = Discharge.objects.filter(client_id__in=client_ids).count()
        restriction_count = ServiceRestriction.objects.filter(client_id__in=client_ids).count()
        
        # Duplicate relationships (both as primary and duplicate)
        duplicate_count = ClientDuplicate.objects.filter(
            models.Q(primary_client_id__in=client_ids) | models.Q(duplicate_client_id__in=client_ids)
        ).count()
        
        extended_count = ClientExtended.objects.filter(client_id__in=client_ids).count()
        
        # Staff assignments
        staff_assignment_count = 0
        if StaffClientAssignment:
            staff_assignment_count = StaffClientAssignment.objects.filter(client_id__in=client_ids).count()
        
        # Also check for duplicates where today's clients are involved
        duplicate_primary_count = ClientDuplicate.objects.filter(primary_client_id__in=client_ids).count()
        duplicate_duplicate_count = ClientDuplicate.objects.filter(duplicate_client_id__in=client_ids).count()
        
        self.stdout.write(self.style.WARNING(
            f'\nFound the following records to delete:\n'
            f'  - {client_count} clients created today ({today.strftime("%B %d, %Y")})\n'
            f'  - {enrollment_count} client program enrollments\n'
            f'  - {intake_count} intake records\n'
            f'  - {discharge_count} discharge records\n'
            f'  - {restriction_count} service restriction records\n'
            f'  - {duplicate_primary_count + duplicate_duplicate_count} duplicate relationships\n'
            f'  - {extended_count} client extended records\n'
            f'  - {staff_assignment_count} staff client assignments\n'
        ))
        
        if options['dry_run']:
            self.stdout.write(self.style.SUCCESS('\nDRY RUN: No data was deleted.'))
            return
        
        if not options['confirm']:
            self.stdout.write(
                self.style.ERROR(
                    '\nThis command will DELETE all the above records!\n'
                    'Use --confirm flag to proceed.\n'
                    'Example: python manage.py delete_nov1_clients --confirm'
                )
            )
            return
        
        # Final confirmation
        confirm = input(f'\nAre you absolutely sure you want to delete these {client_count} clients and all related data? Type "DELETE" to confirm: ')
        
        if confirm != "DELETE":
            self.stdout.write(self.style.ERROR('Operation cancelled.'))
            return
        
        try:
            with transaction.atomic():
                # Delete in order to avoid foreign key constraint issues
                
                self.stdout.write('\nDeleting duplicate relationships...')
                deleted_duplicates = ClientDuplicate.objects.filter(
                    models.Q(primary_client_id__in=client_ids) | models.Q(duplicate_client_id__in=client_ids)
                ).delete()[0]
                self.stdout.write(self.style.SUCCESS(f'  Deleted {deleted_duplicates} duplicate relationships'))
                
                self.stdout.write('Deleting client program enrollments...')
                deleted_enrollments = ClientProgramEnrollment.objects.filter(client_id__in=client_ids).delete()[0]
                self.stdout.write(self.style.SUCCESS(f'  Deleted {deleted_enrollments} enrollments'))
                
                self.stdout.write('Deleting intake records...')
                deleted_intakes = Intake.objects.filter(client_id__in=client_ids).delete()[0]
                self.stdout.write(self.style.SUCCESS(f'  Deleted {deleted_intakes} intake records'))
                
                self.stdout.write('Deleting discharge records...')
                deleted_discharges = Discharge.objects.filter(client_id__in=client_ids).delete()[0]
                self.stdout.write(self.style.SUCCESS(f'  Deleted {deleted_discharges} discharge records'))
                
                self.stdout.write('Deleting service restriction records...')
                deleted_restrictions = ServiceRestriction.objects.filter(client_id__in=client_ids).delete()[0]
                self.stdout.write(self.style.SUCCESS(f'  Deleted {deleted_restrictions} service restrictions'))
                
                self.stdout.write('Deleting client extended records...')
                deleted_extended = ClientExtended.objects.filter(client_id__in=client_ids).delete()[0]
                self.stdout.write(self.style.SUCCESS(f'  Deleted {deleted_extended} extended records'))
                
                deleted_staff_assignments = 0
                if StaffClientAssignment:
                    self.stdout.write('Deleting staff client assignments...')
                    deleted_staff_assignments = StaffClientAssignment.objects.filter(client_id__in=client_ids).delete()[0]
                    self.stdout.write(self.style.SUCCESS(f'  Deleted {deleted_staff_assignments} staff assignments'))
                
                self.stdout.write('Deleting clients...')
                deleted_clients = clients.delete()[0]
                self.stdout.write(self.style.SUCCESS(f'  Deleted {deleted_clients} clients'))
                
                # Build summary message
                summary_lines = [
                    f'\n✅ Successfully deleted all clients created today ({today.strftime("%B %d, %Y")}) and related data!',
                    '   Total deleted:',
                    f'   - {deleted_clients} clients',
                    f'   - {deleted_enrollments} enrollments',
                    f'   - {deleted_intakes} intake records',
                    f'   - {deleted_discharges} discharge records',
                    f'   - {deleted_restrictions} service restrictions',
                    f'   - {deleted_duplicates} duplicate relationships',
                    f'   - {deleted_extended} extended records'
                ]
                
                if deleted_staff_assignments > 0:
                    summary_lines.append(f'   - {deleted_staff_assignments} staff client assignments')
                
                self.stdout.write(
                    self.style.SUCCESS('\n'.join(summary_lines))
                )
                
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'\n❌ Error deleting clients: {e}')
            )
            import traceback
            self.stdout.write(traceback.format_exc())
            raise

