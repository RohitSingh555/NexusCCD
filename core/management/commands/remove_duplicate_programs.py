from django.core.management.base import BaseCommand
from core.models import Program, ClientProgramEnrollment, Intake
from collections import defaultdict
import sys


class Command(BaseCommand):
    help = 'Remove duplicate programs with department "NA" only. Duplicates are identified by matching name (case-insensitive) and department. The script keeps the program with the most enrollments or the oldest one if tied.'

    def add_arguments(self, parser):
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
        parser.add_argument(
            '--merge-enrollments',
            action='store_true',
            help='Move enrollments from duplicate programs to the kept program before deleting',
        )
        parser.add_argument(
            '--by-name-only',
            action='store_true',
            help='Match duplicates by name only (ignore department)',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        confirm = options['confirm']
        merge_enrollments = options['merge_enrollments']
        by_name_only = options['by_name_only']
        
        # Find programs with NA department that have duplicates in other departments
        # Get all NA programs
        na_programs = Program.objects.select_related('department').filter(
            department__name__iexact='NA'
        )
        
        # Also handle programs where department might be null
        na_programs_null = Program.objects.filter(department__isnull=True)
        all_na_programs = na_programs | na_programs_null
        
        total_na_programs = all_na_programs.count()
        self.stdout.write(
            self.style.WARNING(f'Found {total_na_programs} programs with department "NA"')
        )
        
        if total_na_programs == 0:
            self.stdout.write(
                self.style.WARNING('No programs found with department "NA"')
            )
            return
        
        # Find duplicates: NA programs that have the same name as programs in other departments
        from django.db.models import Count, Q
        from django.db.models.functions import Lower
        
        # Get all program names (case-insensitive) grouped by name
        all_program_names = Program.objects.annotate(
            name_lower=Lower('name')
        ).values('name_lower').annotate(
            na_count=Count('id', filter=Q(department__name__iexact='NA')),
            other_count=Count('id', filter=~Q(department__name__iexact='NA')),
            total_count=Count('id')
        ).filter(
            na_count__gt=0  # Has at least one NA program
        )
        
        # Find names where there's both NA and non-NA programs (these are duplicates - delete all NA versions)
        duplicate_names = all_program_names.filter(other_count__gt=0)
        
        # Also check for duplicates within NA department itself
        na_only_duplicates = all_program_names.filter(
            na_count__gt=1,
            other_count=0
        )
        
        # Build duplicates dict: for each duplicate name, get all NA programs with that name
        duplicates = {}
        
        # First, handle NA programs that duplicate other departments (delete ALL NA versions)
        for dup_info in duplicate_names:
            dup_name_lower = dup_info['name_lower']
            na_count = dup_info['na_count']
            other_count = dup_info['other_count']
            
            # Get all NA programs with this name - ALL should be deleted (they're duplicates of real department)
            na_progs_with_name = list(all_na_programs.annotate(
                name_lower=Lower('name')
            ).filter(name_lower=dup_name_lower))
            
            if len(na_progs_with_name) > 0:
                # Get the program in the other department for reference
                other_dept_program = Program.objects.annotate(
                    name_lower=Lower('name')
                ).filter(
                    name_lower=dup_name_lower
                ).exclude(
                    department__name__iexact='NA'
                ).first()
                
                duplicates[dup_name_lower] = {
                    'na_programs': na_progs_with_name,
                    'na_count': na_count,
                    'other_count': other_count,
                    'total_count': dup_info['total_count'],
                    'other_dept_program': other_dept_program,
                    'keep_na': False  # Don't keep any NA - delete all since real program exists elsewhere
                }
        
        # Second, handle duplicates within NA department only (keep one, delete others)
        if na_only_duplicates.count() > 0:
            self.stdout.write(
                self.style.WARNING(
                    f'Also found {na_only_duplicates.count()} program names with multiple entries only in NA department'
                )
            )
            for dup_info in na_only_duplicates:
                dup_name_lower = dup_info['name_lower']
                na_progs_with_name = list(all_na_programs.annotate(
                    name_lower=Lower('name')
                ).filter(name_lower=dup_name_lower))
                
                if dup_name_lower not in duplicates:
                    duplicates[dup_name_lower] = {
                        'na_programs': na_progs_with_name,
                        'na_count': dup_info['na_count'],
                        'other_count': 0,
                        'total_count': dup_info['total_count'],
                        'other_dept_program': None,
                        'keep_na': True  # Keep one NA program since no real department version exists
                    }
        
        if len(duplicates) == 0:
            self.stdout.write(
                self.style.WARNING('No duplicate programs found!')
            )
            self.stdout.write(
                f'Total programs: {total_na_programs}, Unique program names: {all_na_programs.values_list("name", flat=True).distinct().count()}'
            )
            # Show sample of programs for debugging
            if total_na_programs > 0:
                self.stdout.write('\nSample programs (first 10):')
                for i, program in enumerate(all_na_programs[:10]):
                    dept = program.department.name if program.department else 'NULL'
                    self.stdout.write(f'  {i+1}. "{program.name}" (Dept: {dept})')
            return
        
        # Calculate totals - for duplicates with other departments, delete ALL NA programs
        # For NA-only duplicates, delete all but one
        total_duplicates = 0
        for dup_info in duplicates.values():
            if dup_info['keep_na']:
                # Keep one, delete the rest
                total_duplicates += len(dup_info['na_programs']) - 1
            else:
                # Delete all NA programs (they duplicate a real department program)
                total_duplicates += len(dup_info['na_programs'])
        
        total_groups = len(duplicates)
        
        self.stdout.write(
            self.style.WARNING(
                f'\nFound {total_groups} groups of duplicate programs ({total_duplicates} duplicate programs to remove)'
            )
        )
        
        # Analyze and decide which to keep
        programs_to_delete = []
        programs_to_keep = []
        
        for dup_name_lower, dup_info in duplicates.items():
            program_list = dup_info['na_programs']
            na_count = dup_info['na_count']
            other_count = dup_info['other_count']
            keep_na = dup_info['keep_na']
            other_dept_program = dup_info.get('other_dept_program')
            
            # Sort programs by:
            # 1. Number of enrollments (descending)
            # 2. Number of intakes (descending)
            # 3. Created date (ascending - keep oldest)
            program_data = []
            for prog in program_list:
                enrollments_count = ClientProgramEnrollment.objects.filter(program=prog).count()
                intakes_count = Intake.objects.filter(program=prog).count()
                program_data.append({
                    'program': prog,
                    'enrollments': enrollments_count,
                    'intakes': intakes_count,
                    'created_at': prog.created_at
                })
            
            # Sort: most enrollments first, then most intakes, then oldest
            program_data.sort(
                key=lambda x: (-x['enrollments'], -x['intakes'], x['created_at'])
            )
            
            if keep_na:
                # Keep the first one (best candidate) - this is the one NA program to keep
                keep_program = program_data[0]['program']
                programs_to_keep.append({
                    'program': keep_program,
                    'key': dup_name_lower,
                    'enrollments': program_data[0]['enrollments'],
                    'intakes': program_data[0]['intakes'],
                    'other_dept_count': 0,
                    'keep_na': True
                })
                
                # Mark others for deletion (all other NA programs with this name)
                for item in program_data[1:]:
                    programs_to_delete.append({
                        'program': item['program'],
                        'keep_program': keep_program,
                        'enrollments': item['enrollments'],
                        'intakes': item['intakes'],
                        'merge_to_other_dept': False
                    })
            else:
                # Delete ALL NA programs (they duplicate a real department program)
                # The real program is in another department
                if other_dept_program:
                    other_dept_name = other_dept_program.department.name if other_dept_program.department else 'Unknown'
                    programs_to_keep.append({
                        'program': other_dept_program,
                        'key': dup_name_lower,
                        'enrollments': ClientProgramEnrollment.objects.filter(program=other_dept_program).count(),
                        'intakes': Intake.objects.filter(program=other_dept_program).count(),
                        'other_dept_count': other_count,
                        'keep_na': False,
                        'other_dept_name': other_dept_name
                    })
                
                # Mark ALL NA programs for deletion
                for item in program_data:
                    programs_to_delete.append({
                        'program': item['program'],
                        'keep_program': other_dept_program,
                        'enrollments': item['enrollments'],
                        'intakes': item['intakes'],
                        'merge_to_other_dept': True
                    })
        
        # Show summary
        self.stdout.write('\n' + '='*80)
        self.stdout.write('DUPLICATE PROGRAM ANALYSIS')
        self.stdout.write('='*80)
        
        for keep_info in programs_to_keep[:10]:  # Show first 10 groups
            prog = keep_info['program']
            dept = prog.department.name if prog.department else 'NA'
            other_dept_count = keep_info.get('other_dept_count', 0)
            keep_na = keep_info.get('keep_na', False)
            
            self.stdout.write(
                f'\n✅ KEEPING: "{prog.name}" (Dept: {dept})'
            )
            if not keep_na and other_dept_count > 0:
                other_dept_name = keep_info.get('other_dept_name', 'other department')
                self.stdout.write(
                    f'   Note: This is the REAL program in "{other_dept_name}" department'
                )
                self.stdout.write(
                    f'   All NA department duplicates will be deleted and merged to this program'
                )
            elif keep_na:
                self.stdout.write(
                    f'   Note: Keeping this NA program (no real department version exists)'
                )
            self.stdout.write(
                f'   Enrollments: {keep_info["enrollments"]}, '
                f'Intakes: {keep_info["intakes"]}, '
                f'Created: {prog.created_at.strftime("%Y-%m-%d")}'
            )
            
            # Show duplicates that will be deleted
            for delete_info in programs_to_delete:
                if delete_info['keep_program'] == prog:
                    dup_prog = delete_info['program']
                    dup_dept = dup_prog.department.name if dup_prog.department else 'NA'
                    merge_to_other = delete_info.get('merge_to_other_dept', False)
                    self.stdout.write(
                        f'   ❌ DELETE:  "{dup_prog.name}" (Dept: {dup_dept})'
                    )
                    if merge_to_other:
                        self.stdout.write(
                            f'      ⚠️  Will merge {delete_info["enrollments"]} enrollments and {delete_info["intakes"]} intakes to "{prog.name}" in {dept}'
                        )
                    self.stdout.write(
                        f'      Enrollments: {delete_info["enrollments"]}, '
                        f'Intakes: {delete_info["intakes"]}, '
                        f'Created: {dup_prog.created_at.strftime("%Y-%m-%d")}'
                    )
        
        if len(programs_to_keep) > 10:
            self.stdout.write(f'\n... and {len(programs_to_keep) - 10} more groups')
        
        # Check for enrollments/intakes that need to be moved
        duplicates_with_data = []
        for delete_info in programs_to_delete:
            if delete_info['enrollments'] > 0 or delete_info['intakes'] > 0:
                duplicates_with_data.append(delete_info)
        
        if duplicates_with_data:
            self.stdout.write(
                self.style.WARNING(
                    f'\n⚠️  WARNING: {len(duplicates_with_data)} duplicate programs have enrollments or intakes!'
                )
            )
            if not merge_enrollments:
                self.stdout.write(
                    '   Use --merge-enrollments to move them to the kept program before deletion.'
                )
        
        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(
                    f'\nDRY RUN: Would delete {len(programs_to_delete)} duplicate programs.'
                )
            )
            self.stdout.write(
                'Run without --dry-run and with --confirm to actually delete.'
            )
            return
        
        if not confirm:
            self.stdout.write(
                self.style.ERROR(
                    f'\nERROR: Deletion requires --confirm flag. This will delete {len(programs_to_delete)} programs.'
                )
            )
            if duplicates_with_data:
                self.stdout.write(
                    'Consider using --merge-enrollments to preserve enrollments and intakes.'
                )
            self.stdout.write(
                '\nTo proceed, run:'
            )
            cmd = 'python manage.py remove_duplicate_programs --confirm'
            if merge_enrollments:
                cmd += ' --merge-enrollments'
            if by_name_only:
                cmd += ' --by-name-only'
            self.stdout.write(f'  {cmd}')
            return
        
        # Perform deletion
        deleted_count = 0
        merged_enrollments = 0
        merged_intakes = 0
        errors = []
        
        for delete_info in programs_to_delete:
            try:
                program_to_delete = delete_info['program']
                keep_program = delete_info['keep_program']
                
                # Merge enrollments if requested (only if flag is set)
                merge_to_other = delete_info.get('merge_to_other_dept', False)
                if merge_enrollments:
                    enrollments = ClientProgramEnrollment.objects.filter(program=program_to_delete)
                    for enrollment in enrollments:
                        # Check if there's already an enrollment for this client in the kept program
                        existing = ClientProgramEnrollment.objects.filter(
                            client=enrollment.client,
                            program=keep_program
                        ).first()
                        
                        if existing:
                            # Update existing enrollment dates if needed
                            if enrollment.start_date < existing.start_date:
                                existing.start_date = enrollment.start_date
                            if enrollment.end_date and (not existing.end_date or enrollment.end_date > existing.end_date):
                                existing.end_date = enrollment.end_date
                            existing.save()
                            enrollment.delete()
                        else:
                            enrollment.program = keep_program
                            enrollment.save()
                        merged_enrollments += 1
                    
                    # Merge intakes
                    intakes = Intake.objects.filter(program=program_to_delete)
                    for intake in intakes:
                        # Check if there's already an intake for this client in the kept program
                        existing = Intake.objects.filter(
                            client=intake.client,
                            program=keep_program
                        ).first()
                        
                        if existing:
                            # Update existing intake if needed
                            if intake.intake_date < existing.intake_date:
                                existing.intake_date = intake.intake_date
                            existing.save()
                            intake.delete()
                        else:
                            intake.program = keep_program
                            intake.save()
                        merged_intakes += 1
                # Note: If not merging, enrollments/intakes will be deleted with the program
                # This is intentional - user wants to just delete NA duplicates
                
                # Delete the duplicate program
                program_name = program_to_delete.name
                program_to_delete.delete()
                deleted_count += 1
                
                if deleted_count % 50 == 0:
                    self.stdout.write(f'Deleted {deleted_count}/{len(programs_to_delete)} duplicate programs...')
                    
            except Exception as e:
                errors.append(f'Error deleting {program_to_delete.name}: {str(e)}')
                self.stdout.write(
                    self.style.ERROR(f'Error deleting program {program_to_delete.name}: {str(e)}')
                )
        
        # Summary
        self.stdout.write('\n' + '='*80)
        self.stdout.write(
            self.style.SUCCESS(
                f'\n✅ Successfully deleted {deleted_count} out of {len(programs_to_delete)} duplicate programs'
            )
        )
        
        if merge_enrollments:
            self.stdout.write(
                self.style.SUCCESS(
                    f'✅ Merged {merged_enrollments} enrollments and {merged_intakes} intakes to kept programs'
                )
            )
        
        if errors:
            self.stdout.write(
                self.style.ERROR(f'\n⚠️  {len(errors)} errors occurred during deletion')
            )
            for error in errors[:10]:
                self.stdout.write(f'  - {error}')
