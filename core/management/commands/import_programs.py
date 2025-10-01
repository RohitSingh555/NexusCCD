from django.core.management.base import BaseCommand
from core.models import Program, Department
import pandas as pd
import os

class Command(BaseCommand):
    help = 'Import programs from CSV or Excel file, avoiding duplicates and setting department to NA'

    def add_arguments(self, parser):
        parser.add_argument(
            'file_path',
            type=str,
            help='Path to the CSV or Excel file containing programs'
        )
        parser.add_argument(
            '--program_column',
            type=str,
            default='Program',
            help='Name of the column containing program names (default: Program)'
        )

    def handle(self, *args, **options):
        file_path = options['file_path']
        program_column = options['program_column']
        
        # Check if file exists
        if not os.path.exists(file_path):
            self.stdout.write(
                self.style.ERROR(f'File not found: {file_path}')
            )
            return
        
        # Get or create NA department
        na_department, created = Department.objects.get_or_create(
            name='NA',
            defaults={'owner': 'System'}
        )
        
        if created:
            self.stdout.write('Created NA department')
        else:
            self.stdout.write('Using existing NA department')
        
        programs_created = 0
        programs_skipped = 0
        
        try:
            # Read the file (supports both CSV and Excel)
            if file_path.endswith('.xlsx') or file_path.endswith('.xls'):
                df = pd.read_excel(file_path)
            else:
                df = pd.read_csv(file_path)
            
            self.stdout.write(f'File columns: {list(df.columns)}')
            
            # Check if program column exists
            if program_column not in df.columns:
                self.stdout.write(
                    self.style.ERROR(f'Column "{program_column}" not found in file. Available columns: {", ".join(df.columns)}')
                )
                return
            
            # Get unique program names (case-insensitive)
            program_series = df[program_column].dropna().astype(str).str.strip()
            unique_programs = program_series.str.lower().unique()
            
            self.stdout.write(f'Found {len(unique_programs)} unique programs in file')
            
            # Create programs
            for program_name_lower in unique_programs:
                # Find the original case version
                original_name = program_series[program_series.str.lower() == program_name_lower].iloc[0]
                
                # Check if program already exists (case-insensitive)
                existing_program = Program.objects.filter(
                    name__iexact=original_name
                ).first()
                
                if existing_program:
                    self.stdout.write(f'Skipped existing program: {original_name}')
                    programs_skipped += 1
                else:
                    # Create new program
                    program = Program.objects.create(
                        name=original_name,
                        department=na_department,
                        location='TBD',
                        capacity_current=0,
                        status='suggested',
                        description=f'Program imported from {os.path.basename(file_path)}'
                    )
                    self.stdout.write(f'Created program: {original_name}')
                    programs_created += 1
                
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error reading file: {str(e)}')
            )
            return
        
        self.stdout.write(
            self.style.SUCCESS(
                f'Import completed! Created {programs_created} programs, skipped {programs_skipped} duplicates'
            )
        )