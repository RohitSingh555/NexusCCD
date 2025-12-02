"""
Django management command to delete all clients with client_id containing 'CLI' or 'CID'
and all their related data (hard delete).

This script will delete:
- ClientDuplicate records (both primary and duplicate relationships)
- ServiceRestriction records
- Discharge records
- Intake records
- ClientProgramEnrollment records
- ClientExtended records
- Client records

Usage:
    python manage.py delete_cli_clients --confirm
    python manage.py delete_cli_clients --dry-run  # Preview what would be deleted
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q
from django.conf import settings
from core.models import (
    Client, ClientExtended, ClientProgramEnrollment, Intake, Discharge,
    ServiceRestriction, ClientDuplicate
)
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Delete all clients with client_id containing "CLI" or "CID" and all related data (hard delete)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--confirm',
            action='store_true',
            help='Confirm that you want to delete ALL CLI/CID clients and related data (required for safety)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without actually deleting (useful for testing)'
        )

    def handle(self, *args, **options):
        confirm = options.get('confirm', False)
        dry_run = options.get('dry_run', False)

        # Check if running in production
        is_production = getattr(settings, 'ENVIRONMENT', '').lower() == 'production'
        
        if is_production:
            self.stdout.write(self.style.WARNING(
                '\n⚠️  WARNING: You are running this command in PRODUCTION!\n'
                'This will permanently delete all CLI/CID clients and related data.\n'
            ))

        # Find all clients with client_id containing 'CLI' or 'CID'
        clients = Client.objects.filter(
            Q(client_id__icontains='CLI') | Q(client_id__icontains='CID')
        )
        total_clients = clients.count()

        if total_clients == 0:
            self.stdout.write(self.style.SUCCESS('No clients found with client_id containing "CLI" or "CID".'))
            return
        
        # Show breakdown by pattern
        cli_count = Client.objects.filter(client_id__icontains='CLI').count()
        cid_count = Client.objects.filter(client_id__icontains='CID').count()
        self.stdout.write(f'\nFound {cli_count} clients with "CLI" in client_id')
        self.stdout.write(f'Found {cid_count} clients with "CID" in client_id')
        if cli_count > 0 and cid_count > 0:
            # Some clients might match both patterns, so show overlap
            overlap_count = Client.objects.filter(
                Q(client_id__icontains='CLI') & Q(client_id__icontains='CID')
            ).count()
            if overlap_count > 0:
                self.stdout.write(f'Note: {overlap_count} clients match both patterns (counted once in total)')

        # Collect all related data
        client_ids = list(clients.values_list('id', flat=True))
        
        # Count related records
        duplicate_primary_count = ClientDuplicate.objects.filter(primary_client_id__in=client_ids).count()
        duplicate_duplicate_count = ClientDuplicate.objects.filter(duplicate_client_id__in=client_ids).count()
        service_restriction_count = ServiceRestriction.objects.filter(client_id__in=client_ids).count()
        discharge_count = Discharge.objects.filter(client_id__in=client_ids).count()
        intake_count = Intake.objects.filter(client_id__in=client_ids).count()
        enrollment_count = ClientProgramEnrollment.objects.filter(client_id__in=client_ids).count()
        extended_count = ClientExtended.objects.filter(client_id__in=client_ids).count()

        # Display summary
        self.stdout.write(self.style.WARNING('\n' + '='*70))
        self.stdout.write(self.style.WARNING('DELETION SUMMARY'))
        self.stdout.write(self.style.WARNING('='*70))
        self.stdout.write(f'\nClients to delete: {total_clients}')
        self.stdout.write(f'  - ClientDuplicate (as primary): {duplicate_primary_count}')
        self.stdout.write(f'  - ClientDuplicate (as duplicate): {duplicate_duplicate_count}')
        self.stdout.write(f'  - ServiceRestriction: {service_restriction_count}')
        self.stdout.write(f'  - Discharge: {discharge_count}')
        self.stdout.write(f'  - Intake: {intake_count}')
        self.stdout.write(f'  - ClientProgramEnrollment: {enrollment_count}')
        self.stdout.write(f'  - ClientExtended: {extended_count}')
        
        total_records = (
            total_clients + duplicate_primary_count + duplicate_duplicate_count +
            service_restriction_count + discharge_count + intake_count +
            enrollment_count + extended_count
        )
        self.stdout.write(self.style.WARNING(f'\nTOTAL RECORDS TO DELETE: {total_records}'))
        self.stdout.write(self.style.WARNING('='*70 + '\n'))

        if dry_run:
            self.stdout.write(self.style.SUCCESS('\n✓ DRY RUN MODE - No records were actually deleted.'))
            self.stdout.write('Run with --confirm to perform the actual deletion.\n')
            return

        if not confirm:
            self.stdout.write(self.style.ERROR(
                '\n❌ ERROR: This command requires --confirm flag to proceed.\n'
                'This will permanently delete ALL CLI/CID clients and related data!\n'
                'This action CANNOT be undone.\n'
                '\nTo proceed, run: python manage.py delete_cli_clients --confirm\n'
            ))
            return

        # Final confirmation prompt
        self.stdout.write(self.style.WARNING(
            f'\n⚠️  FINAL WARNING: This will permanently delete {total_records} records!\n'
            'This action CANNOT be undone.\n'
        ))
        
        if is_production:
            response = input('Type "DELETE CLI CID CLIENTS" (all caps) to confirm: ')
            if response != 'DELETE CLI CID CLIENTS':
                self.stdout.write(self.style.ERROR('\n❌ Confirmation text did not match. Deletion cancelled.'))
                return
        else:
            response = input('Type "yes" to confirm deletion: ')
            if response.lower() != 'yes':
                self.stdout.write(self.style.ERROR('\n❌ Deletion cancelled.'))
                return

        # Perform deletion in transaction
        try:
            with transaction.atomic():
                self.stdout.write('\nStarting deletion...\n')
                
                # 1. Delete ClientDuplicate records (both directions)
                if duplicate_primary_count > 0:
                    deleted_primary = ClientDuplicate.objects.filter(primary_client_id__in=client_ids).delete()
                    self.stdout.write(self.style.SUCCESS(
                        f'✓ Deleted {deleted_primary[0]} ClientDuplicate records (as primary)'
                    ))
                
                if duplicate_duplicate_count > 0:
                    deleted_duplicate = ClientDuplicate.objects.filter(duplicate_client_id__in=client_ids).delete()
                    self.stdout.write(self.style.SUCCESS(
                        f'✓ Deleted {deleted_duplicate[0]} ClientDuplicate records (as duplicate)'
                    ))
                
                # 2. Delete ServiceRestriction records
                if service_restriction_count > 0:
                    deleted_restrictions = ServiceRestriction.objects.filter(client_id__in=client_ids).delete()
                    self.stdout.write(self.style.SUCCESS(
                        f'✓ Deleted {deleted_restrictions[0]} ServiceRestriction records'
                    ))
                
                # 3. Delete Discharge records
                if discharge_count > 0:
                    deleted_discharges = Discharge.objects.filter(client_id__in=client_ids).delete()
                    self.stdout.write(self.style.SUCCESS(
                        f'✓ Deleted {deleted_discharges[0]} Discharge records'
                    ))
                
                # 4. Delete Intake records
                if intake_count > 0:
                    deleted_intakes = Intake.objects.filter(client_id__in=client_ids).delete()
                    self.stdout.write(self.style.SUCCESS(
                        f'✓ Deleted {deleted_intakes[0]} Intake records'
                    ))
                
                # 5. Delete ClientProgramEnrollment records
                if enrollment_count > 0:
                    deleted_enrollments = ClientProgramEnrollment.objects.filter(client_id__in=client_ids).delete()
                    self.stdout.write(self.style.SUCCESS(
                        f'✓ Deleted {deleted_enrollments[0]} ClientProgramEnrollment records'
                    ))
                
                # 6. Delete ClientExtended records
                if extended_count > 0:
                    deleted_extended = ClientExtended.objects.filter(client_id__in=client_ids).delete()
                    self.stdout.write(self.style.SUCCESS(
                        f'✓ Deleted {deleted_extended[0]} ClientExtended records'
                    ))
                
                # 7. Finally, delete Client records
                deleted_clients = Client.objects.filter(id__in=client_ids).delete()
                self.stdout.write(self.style.SUCCESS(
                    f'✓ Deleted {deleted_clients[0]} Client records'
                ))
                
                self.stdout.write(self.style.SUCCESS(
                    f'\n✅ SUCCESS: Deleted {total_records} records in total.\n'
                ))
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(
                f'\n❌ ERROR: An error occurred during deletion: {str(e)}\n'
                'All changes have been rolled back.\n'
            ))
            logger.error(f"Error deleting CLI/CID clients: {str(e)}", exc_info=True)
            raise

