from django.core.management.base import BaseCommand
from django.db import transaction
from core.models import ClientProgramEnrollment
from django.conf import settings


class Command(BaseCommand):
    help = 'Delete all enrollments from the client_program_enrollments table'

    def add_arguments(self, parser):
        parser.add_argument(
            '--confirm',
            action='store_true',
            help='Confirm that you want to delete ALL enrollments (required for safety)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without actually deleting (useful for testing)',
        )

    def handle(self, *args, **options):
        # Check if we're in production and warn
        is_production = getattr(settings, 'PRODUCTION', False) or 'production' in str(settings.DATABASES.get('default', {}).get('NAME', '')).lower()
        
        if is_production:
            self.stdout.write(
                self.style.WARNING(
                    '⚠️  WARNING: You are running this on PRODUCTION!\n'
                    'This will permanently delete all enrollment data.\n'
                )
            )

        if not options['confirm']:
            self.stdout.write(
                self.style.ERROR(
                    'This command will delete ALL enrollments from the client_program_enrollments table!\n'
                    'Use --confirm flag to proceed.\n'
                    'Example: python manage.py delete_all_enrollments --confirm\n'
                    'For a dry run (no deletion): python manage.py delete_all_enrollments --confirm --dry-run'
                )
            )
            return

        # Count existing enrollments
        total_count = ClientProgramEnrollment.objects.count()
        
        # Count by status
        status_counts = {}
        for status, label in ClientProgramEnrollment.STATUS_CHOICES:
            count = ClientProgramEnrollment.objects.filter(status=status).count()
            if count > 0:
                status_counts[status] = count
        
        # Count archived vs non-archived
        archived_count = ClientProgramEnrollment.objects.filter(is_archived=True).count()
        non_archived_count = ClientProgramEnrollment.objects.filter(is_archived=False).count()

        self.stdout.write('\n' + '='*60)
        self.stdout.write(self.style.WARNING('ENROLLMENT DELETION SUMMARY'))
        self.stdout.write('='*60)
        self.stdout.write(f'Total enrollments to delete: {total_count}')
        self.stdout.write(f'  - Archived: {archived_count}')
        self.stdout.write(f'  - Non-archived: {non_archived_count}')
        
        if status_counts:
            self.stdout.write('\nBreakdown by status:')
            for status, count in status_counts.items():
                self.stdout.write(f'  - {status}: {count}')
        
        self.stdout.write('='*60 + '\n')

        if total_count == 0:
            self.stdout.write(self.style.WARNING('No enrollments found to delete.'))
            return

        if options['dry_run']:
            self.stdout.write(
                self.style.SUCCESS(
                    'DRY RUN MODE: No data was actually deleted.\n'
                    'Remove --dry-run flag to perform the actual deletion.'
                )
            )
            return

        # Show environment info
        db_name = settings.DATABASES.get('default', {}).get('NAME', 'unknown')
        self.stdout.write(f'Database: {db_name}')
        if is_production:
            self.stdout.write(self.style.ERROR('⚠️  PRODUCTION DATABASE DETECTED!'))

        # Confirm with user - require explicit confirmation
        confirm_text = "DELETE ALL ENROLLMENTS"
        self.stdout.write(
            self.style.ERROR(
                f'\n⚠️  FINAL WARNING: This will permanently delete ALL {total_count} enrollments!\n'
                f'This action CANNOT be undone.\n'
            )
        )
        confirm = input(f'Type "{confirm_text}" to confirm deletion: ')
        
        if confirm != confirm_text:
            self.stdout.write(self.style.ERROR('Operation cancelled. Confirmation text did not match.'))
            return

        try:
            with transaction.atomic():
                self.stdout.write('\nDeleting all enrollments...')
                
                # Delete all enrollments
                deleted_count, _ = ClientProgramEnrollment.objects.all().delete()
                
                # Verify deletion
                remaining_count = ClientProgramEnrollment.objects.count()
                
                if remaining_count == 0:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'\n✅ Successfully deleted all enrollments!\n'
                            f'- {deleted_count} enrollments deleted\n'
                            f'- Remaining enrollments: {remaining_count}'
                        )
                    )
                else:
                    self.stdout.write(
                        self.style.WARNING(
                            f'\n⚠️  Deletion completed, but {remaining_count} enrollments still remain.\n'
                            f'This may indicate a database constraint issue.'
                        )
                    )
                
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'\n❌ Error deleting enrollments: {e}')
            )
            self.stdout.write(
                self.style.ERROR('Transaction rolled back. No data was deleted.')
            )
            raise

