from django.core.management.base import BaseCommand
from django.db import transaction
from core.models import Client, ClientProgramEnrollment, Intake
from django.contrib.auth import get_user_model

User = get_user_model()

class Command(BaseCommand):
    help = 'Delete all clients and related data from the database'

    def add_arguments(self, parser):
        parser.add_argument(
            '--confirm',
            action='store_true',
            help='Confirm that you want to delete ALL clients (required for safety)',
        )

    def handle(self, *args, **options):
        if not options['confirm']:
            self.stdout.write(
                self.style.ERROR(
                    'This command will delete ALL clients and related data!\n'
                    'Use --confirm flag to proceed.\n'
                    'Example: python manage.py delete_all_clients --confirm'
                )
            )
            return

        # Count existing data
        client_count = Client.objects.count()
        enrollment_count = ClientProgramEnrollment.objects.count()
        intake_count = Intake.objects.count()

        self.stdout.write(f'Found {client_count} clients, {enrollment_count} enrollments, {intake_count} intakes')

        if client_count == 0:
            self.stdout.write(self.style.WARNING('No clients found to delete.'))
            return

        # Confirm with user
        confirm = input(f'\nAre you absolutely sure you want to delete ALL {client_count} clients? Type "DELETE ALL" to confirm: ')
        
        if confirm != "DELETE ALL":
            self.stdout.write(self.style.ERROR('Operation cancelled.'))
            return

        try:
            with transaction.atomic():
                # Delete in order to avoid foreign key constraints
                self.stdout.write('Deleting client program enrollments...')
                ClientProgramEnrollment.objects.all().delete()
                
                self.stdout.write('Deleting intake records...')
                Intake.objects.all().delete()
                
                self.stdout.write('Deleting clients...')
                Client.objects.all().delete()
                
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Successfully deleted all clients and related data!\n'
                        f'- {client_count} clients deleted\n'
                        f'- {enrollment_count} enrollments deleted\n'
                        f'- {intake_count} intakes deleted'
                    )
                )
                
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error deleting clients: {e}')
            )
