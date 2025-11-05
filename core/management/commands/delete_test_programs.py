from django.core.management.base import BaseCommand
from django.utils import timezone
from core.models import Program
from datetime import datetime, date, timedelta
import sys


class Command(BaseCommand):
    help = 'Delete test programs created on November 3rd. Use --date to specify the exact date (YYYY-MM-DD) or --year to specify just the year (defaults to 2024). Use --dry-run to preview without deleting.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--date',
            type=str,
            help='Specific date to target (YYYY-MM-DD format, e.g., 2024-11-03)',
        )
        parser.add_argument(
            '--year',
            type=int,
            default=2024,
            help='Year to target (defaults to 2024). Only used if --date is not specified.',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Preview what would be deleted without actually deleting',
        )
        parser.add_argument(
            '--confirm',
            action='store_true',
            help='Confirm deletion (required for actual deletion)',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        confirm = options['confirm']
        target_date = None
        
        # Determine target date
        if options['date']:
            try:
                target_date = datetime.strptime(options['date'], '%Y-%m-%d').date()
            except ValueError:
                self.stdout.write(
                    self.style.ERROR(f'Invalid date format: {options["date"]}. Use YYYY-MM-DD format.')
                )
                return
        else:
            # Default to November 3rd of the specified year
            year = options['year']
            target_date = date(year, 11, 3)
        
        # Query programs created on the target date
        start_datetime = timezone.make_aware(datetime.combine(target_date, datetime.min.time()))
        end_datetime = timezone.make_aware(datetime.combine(target_date, datetime.max.time()))
        
        programs = Program.objects.filter(
            created_at__gte=start_datetime,
            created_at__lt=end_datetime + timedelta(days=1)
        )
        
        count = programs.count()
        
        if count == 0:
            self.stdout.write(
                self.style.WARNING(f'No programs found created on {target_date}')
            )
            return
        
        self.stdout.write(
            self.style.WARNING(
                f'Found {count} programs created on {target_date}'
            )
        )
        
        # Show sample programs
        sample_programs = programs[:10]
        self.stdout.write('\nSample programs to be deleted:')
        for p in sample_programs:
            self.stdout.write(f'  - {p.name} (Dept: {p.department.name}, Created: {p.created_at})')
        
        if count > 10:
            self.stdout.write(f'  ... and {count - 10} more')
        
        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(
                    f'\nDRY RUN: Would delete {count} programs. Run without --dry-run and with --confirm to actually delete.'
                )
            )
            return
        
        if not confirm:
            self.stdout.write(
                self.style.ERROR(
                    f'\nERROR: Deletion requires --confirm flag. This will delete {count} programs.'
                )
            )
            self.stdout.write(
                'To proceed, run: python manage.py delete_test_programs --date {} --confirm'.format(
                    target_date.strftime('%Y-%m-%d')
                )
            )
            return
        
        # Confirm one more time
        self.stdout.write(
            self.style.WARNING(
                f'\nWARNING: About to delete {count} programs created on {target_date}.'
            )
        )
        
        # Delete programs
        deleted_count = 0
        for program in programs:
            try:
                program_name = program.name
                program.delete()
                deleted_count += 1
                if deleted_count % 100 == 0:
                    self.stdout.write(f'Deleted {deleted_count}/{count} programs...')
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'Error deleting program {program.name}: {str(e)}')
                )
        
        self.stdout.write(
            self.style.SUCCESS(
                f'\nSuccessfully deleted {deleted_count} out of {count} programs created on {target_date}'
            )
        )
