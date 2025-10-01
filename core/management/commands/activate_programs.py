from django.core.management.base import BaseCommand
from core.models import Program

class Command(BaseCommand):
    help = 'Activate all programs (change status from suggested to active)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--confirm',
            action='store_true',
            help='Confirm that you want to activate all programs',
        )

    def handle(self, *args, **options):
        if not options['confirm']:
            self.stdout.write(
                self.style.WARNING(
                    'This will activate ALL programs. '
                    'Use --confirm flag to proceed.'
                )
            )
            return

        # Get all programs with suggested status
        suggested_programs = Program.objects.filter(status='suggested')
        count = suggested_programs.count()
        
        if count == 0:
            self.stdout.write(
                self.style.WARNING('No programs with "suggested" status found')
            )
            return
        
        # Update all suggested programs to active
        suggested_programs.update(status='active')
        
        self.stdout.write(
            self.style.SUCCESS(
                f'Successfully activated {count} programs'
            )
        )
