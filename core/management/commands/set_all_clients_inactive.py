from django.core.management.base import BaseCommand
from django.db import transaction
from core.models import Client
from django.conf import settings


class Command(BaseCommand):
    help = 'Set all active clients to inactive status (since enrollments have been deleted)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--confirm',
            action='store_true',
            help='Confirm that you want to set ALL active clients to inactive (required for safety)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be updated without actually updating (useful for testing)',
        )

    def handle(self, *args, **options):
        # Check if we're in production and warn
        is_production = getattr(settings, 'PRODUCTION', False) or 'production' in str(settings.DATABASES.get('default', {}).get('NAME', '')).lower()
        
        if is_production:
            self.stdout.write(
                self.style.WARNING(
                    '⚠️  WARNING: You are running this on PRODUCTION!\n'
                    'This will permanently update all active clients to inactive status.\n'
                )
            )

        if not options['confirm']:
            self.stdout.write(
                self.style.ERROR(
                    'This command will set ALL active clients (is_inactive=False) to inactive (is_inactive=True)!\n'
                    'Use --confirm flag to proceed.\n'
                    'Example: python manage.py set_all_clients_inactive --confirm\n'
                    'For a dry run (no updates): python manage.py set_all_clients_inactive --confirm --dry-run'
                )
            )
            return

        # Count existing clients by status
        total_clients = Client.objects.count()
        active_clients = Client.objects.filter(is_inactive=False).count()
        inactive_clients = Client.objects.filter(is_inactive=True).count()
        archived_clients = Client.objects.filter(is_archived=True).count()
        non_archived_clients = Client.objects.filter(is_archived=False).count()
        
        # Count active clients that are not archived
        active_non_archived = Client.objects.filter(is_inactive=False, is_archived=False).count()
        active_archived = Client.objects.filter(is_inactive=False, is_archived=True).count()

        self.stdout.write('\n' + '='*60)
        self.stdout.write(self.style.WARNING('CLIENT STATUS UPDATE SUMMARY'))
        self.stdout.write('='*60)
        self.stdout.write(f'Total clients: {total_clients}')
        self.stdout.write(f'  - Currently Active (is_inactive=False): {active_clients}')
        self.stdout.write(f'    • Non-archived active: {active_non_archived}')
        self.stdout.write(f'    • Archived but active: {active_archived}')
        self.stdout.write(f'  - Currently Inactive (is_inactive=True): {inactive_clients}')
        self.stdout.write(f'  - Archived clients: {archived_clients}')
        self.stdout.write(f'  - Non-archived clients: {non_archived_clients}')
        self.stdout.write('='*60)
        self.stdout.write(f'\n📊 Clients that will be updated to inactive: {active_clients}')
        self.stdout.write('='*60 + '\n')

        if active_clients == 0:
            self.stdout.write(self.style.WARNING('No active clients found to update. All clients are already inactive.'))
            return

        if options['dry_run']:
            self.stdout.write(
                self.style.SUCCESS(
                    'DRY RUN MODE: No data was actually updated.\n'
                    'Remove --dry-run flag to perform the actual update.'
                )
            )
            
            # Show sample of clients that would be updated
            if active_clients > 0:
                self.stdout.write('\n📋 Sample of clients that would be updated (first 10):')
                self.stdout.write('-' * 80)
                sample_clients = Client.objects.filter(is_inactive=False)[:10]
                for idx, client in enumerate(sample_clients, 1):
                    archived_status = 'Archived' if client.is_archived else 'Active'
                    self.stdout.write(
                        f"  {idx}. ID: {client.id:6d} | "
                        f"Name: {client.first_name or '(no first name)'} {client.last_name or '(no last name)'} | "
                        f"Status: {archived_status}"
                    )
                if active_clients > 10:
                    self.stdout.write(f"  ... and {active_clients - 10} more clients")
                self.stdout.write('-' * 80)
            
            return

        # Show environment info
        db_name = settings.DATABASES.get('default', {}).get('NAME', 'unknown')
        self.stdout.write(f'Database: {db_name}')
        if is_production:
            self.stdout.write(self.style.ERROR('⚠️  PRODUCTION DATABASE DETECTED!'))

        # Confirm with user - require explicit confirmation
        confirm_text = "SET ALL ACTIVE CLIENTS TO INACTIVE"
        self.stdout.write(
            self.style.ERROR(
                f'\n⚠️  FINAL WARNING: This will permanently update {active_clients} active clients to inactive!\n'
                f'This action CANNOT be undone.\n'
            )
        )
        confirm = input(f'Type "{confirm_text}" to confirm update: ')
        
        if confirm != confirm_text:
            self.stdout.write(self.style.ERROR('Operation cancelled. Confirmation text did not match.'))
            return

        try:
            with transaction.atomic():
                self.stdout.write('\nUpdating all active clients to inactive...')
                
                # Update all active clients to inactive
                updated_count = Client.objects.filter(is_inactive=False).update(is_inactive=True)
                
                # Verify update
                remaining_active = Client.objects.filter(is_inactive=False).count()
                new_inactive_count = Client.objects.filter(is_inactive=True).count()
                
                if remaining_active == 0:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'\n✅ Successfully updated all active clients to inactive!\n'
                            f'- {updated_count} clients updated\n'
                            f'- Remaining active clients: {remaining_active}\n'
                            f'- Total inactive clients: {new_inactive_count}'
                        )
                    )
                else:
                    self.stdout.write(
                        self.style.WARNING(
                            f'\n⚠️  Update completed, but {remaining_active} clients are still active.\n'
                            f'This may indicate a database constraint issue or concurrent updates.'
                        )
                    )
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'- {updated_count} clients updated\n'
                            f'- Total inactive clients: {new_inactive_count}'
                        )
                    )
                
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'\n❌ Error updating clients: {e}')
            )
            self.stdout.write(
                self.style.ERROR('Transaction rolled back. No data was updated.')
            )
            raise

