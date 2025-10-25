from django.core.management.base import BaseCommand
from django.db import transaction
from core.models import Program, Department, ClientProgramEnrollment, ProgramManagerAssignment
from django.contrib.auth import get_user_model

User = get_user_model()

class Command(BaseCommand):
    help = 'Delete all programs and related data from the database'

    def add_arguments(self, parser):
        parser.add_argument(
            '--confirm',
            action='store_true',
            help='Confirm that you want to delete ALL programs (required for safety)',
        )

    def handle(self, *args, **options):
        if not options['confirm']:
            self.stdout.write(
                self.style.ERROR(
                    'This command will delete ALL programs and related data!\n'
                    'Use --confirm flag to proceed.\n'
                    'Example: python manage.py delete_all_programs --confirm'
                )
            )
            return

        # Count existing data
        program_count = Program.objects.count()
        enrollment_count = ClientProgramEnrollment.objects.count()
        assignment_count = ProgramManagerAssignment.objects.count()

        self.stdout.write(f'Found {program_count} programs, {enrollment_count} enrollments, {assignment_count} manager assignments')

        if program_count == 0:
            self.stdout.write(self.style.WARNING('No programs found to delete.'))
            return

        # Show programs by department
        self.stdout.write('\nPrograms by department:')
        for dept in Department.objects.all():
            dept_programs = Program.objects.filter(department=dept)
            if dept_programs.exists():
                self.stdout.write(f'  {dept.name}: {dept_programs.count()} programs')

        # Confirm with user
        confirm = input(f'\nAre you absolutely sure you want to delete ALL {program_count} programs? Type "DELETE ALL PROGRAMS" to confirm: ')
        
        if confirm != "DELETE ALL PROGRAMS":
            self.stdout.write(self.style.ERROR('Operation cancelled.'))
            return

        try:
            with transaction.atomic():
                # Delete in order to avoid foreign key constraints
                self.stdout.write('Deleting client program enrollments...')
                ClientProgramEnrollment.objects.all().delete()
                
                self.stdout.write('Deleting program manager assignments...')
                ProgramManagerAssignment.objects.all().delete()
                
                self.stdout.write('Deleting programs...')
                Program.objects.all().delete()
                
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Successfully deleted all programs and related data!\n'
                        f'- {program_count} programs deleted\n'
                        f'- {enrollment_count} enrollments deleted\n'
                        f'- {assignment_count} manager assignments deleted'
                    )
                )
                
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error deleting programs: {e}')
            )
