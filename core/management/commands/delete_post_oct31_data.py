from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from datetime import datetime, date
from core.models import (
    Program, ClientProgramEnrollment, ServiceRestriction, SubProgram,
    ProgramStaff, ProgramManagerAssignment, create_audit_log
)
from programs.models import ProgramService
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Delete all programs, services, and enrollments created after October 31st'

    def add_arguments(self, parser):
        parser.add_argument(
            '--year',
            type=int,
            default=2024,
            help='Year for October 31st cutoff (default: 2024)',
        )
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
        parser.add_argument(
            '--create-audit-logs',
            action='store_true',
            help='Create audit log entries for deleted records',
        )

    def handle(self, *args, **options):
        year = options['year']
        cutoff_date = date(year, 10, 31)
        cutoff_datetime = timezone.make_aware(datetime.combine(cutoff_date, datetime.max.time()))
        
        self.stdout.write(
            self.style.WARNING(
                f'\n⚠️  This command will delete all records created AFTER {cutoff_date.strftime("%B %d, %Y")}\n'
            )
        )
        
        # Find records created after Oct 31
        programs = Program.objects.filter(created_at__gt=cutoff_datetime)
        enrollments = ClientProgramEnrollment.objects.filter(created_at__gt=cutoff_datetime)
        restrictions = ServiceRestriction.objects.filter(created_at__gt=cutoff_datetime)
        subprograms = SubProgram.objects.filter(created_at__gt=cutoff_datetime)
        
        # Get ProgramService records
        try:
            program_services = ProgramService.objects.filter(created_at__gt=cutoff_datetime)
        except Exception:
            program_services = ProgramService.objects.none()
        
        # Count related records that will be deleted via CASCADE
        program_ids = list(programs.values_list('id', flat=True))
        program_staff_count = ProgramStaff.objects.filter(program_id__in=program_ids).count() if program_ids else 0
        
        try:
            program_manager_count = ProgramManagerAssignment.objects.filter(program_id__in=program_ids).count() if program_ids else 0
        except Exception:
            program_manager_count = 0
        
        # Count enrollments for programs that will be deleted
        enrollment_count_for_programs = ClientProgramEnrollment.objects.filter(program_id__in=program_ids).count() if program_ids else 0
        
        # Summary
        program_count = programs.count()
        enrollment_count = enrollments.count()
        restriction_count = restrictions.count()
        subprogram_count = subprograms.count()
        program_service_count = program_services.count()
        
        total_enrollments = enrollment_count + enrollment_count_for_programs
        
        self.stdout.write(
            self.style.WARNING(
                f'\n📊 Found the following records created after {cutoff_date.strftime("%B %d, %Y")}:\n'
                f'  - {program_count} programs\n'
                f'  - {total_enrollments} enrollments ({enrollment_count} direct + {enrollment_count_for_programs} via programs)\n'
                f'  - {restriction_count} service restrictions\n'
                f'  - {subprogram_count} subprograms\n'
                f'  - {program_service_count} program services\n'
                f'  - {program_staff_count} program staff assignments\n'
                f'  - {program_manager_count} program manager assignments\n'
            )
        )
        
        if program_count == 0 and enrollment_count == 0 and restriction_count == 0 and subprogram_count == 0 and program_service_count == 0:
            self.stdout.write(
                self.style.SUCCESS(
                    f'\n✅ No records found created after {cutoff_date.strftime("%B %d, %Y")}.'
                )
            )
            return
        
        if options['dry_run']:
            self.stdout.write(self.style.SUCCESS('\n🔍 DRY RUN: No data was deleted.'))
            return
        
        if not options['confirm']:
            self.stdout.write(
                self.style.ERROR(
                    '\n❌ This command will DELETE all the above records!\n'
                    'Use --confirm flag to proceed.\n'
                    f'Example: python manage.py delete_post_oct31_data --year {year} --confirm'
                )
            )
            return
        
        # Final confirmation
        confirm_text = f"DELETE ALL POST OCT31 {year}"
        confirm = input(f'\n⚠️  Are you absolutely sure you want to delete these records? Type "{confirm_text}" to confirm: ')
        
        if confirm != confirm_text:
            self.stdout.write(self.style.ERROR('Operation cancelled.'))
            return
        
        try:
            with transaction.atomic():
                deleted_counts = {
                    'programs': 0,
                    'enrollments': 0,
                    'restrictions': 0,
                    'subprograms': 0,
                    'program_services': 0,
                    'program_staff': 0,
                    'program_managers': 0
                }
                
                # Delete enrollments first (before programs)
                if enrollments.exists():
                    self.stdout.write('\nDeleting enrollments created after Oct 31...')
                    if options.get('create_audit_logs'):
                        # Create audit logs for enrollments
                        for enrollment in enrollments:
                            try:
                                create_audit_log(
                                    entity_name='Enrollment',
                                    entity_id=enrollment.external_id,
                                    action='delete',
                                    changed_by=None,
                                    diff_data={
                                        'client': str(enrollment.client),
                                        'program': str(enrollment.program),
                                        'start_date': str(enrollment.start_date),
                                        'end_date': str(enrollment.end_date) if enrollment.end_date else None,
                                        'status': enrollment.status,
                                    }
                                )
                            except Exception as e:
                                logger.error(f"Error creating audit log for enrollment {enrollment.external_id}: {e}")
                    
                    deleted_counts['enrollments'] = enrollments.delete()[0]
                    self.stdout.write(self.style.SUCCESS(f'  ✅ Deleted {deleted_counts["enrollments"]} enrollments'))
                
                # Delete service restrictions
                if restrictions.exists():
                    self.stdout.write('\nDeleting service restrictions created after Oct 31...')
                    if options.get('create_audit_logs'):
                        for restriction in restrictions:
                            try:
                                create_audit_log(
                                    entity_name='Restriction',
                                    entity_id=restriction.external_id,
                                    action='delete',
                                    changed_by=None,
                                    diff_data={
                                        'client': str(restriction.client),
                                        'scope': restriction.scope,
                                        'program': str(restriction.program) if restriction.program else None,
                                        'start_date': str(restriction.start_date),
                                        'end_date': str(restriction.end_date) if restriction.end_date else None,
                                    }
                                )
                            except Exception as e:
                                logger.error(f"Error creating audit log for restriction {restriction.external_id}: {e}")
                    
                    deleted_counts['restrictions'] = restrictions.delete()[0]
                    self.stdout.write(self.style.SUCCESS(f'  ✅ Deleted {deleted_counts["restrictions"]} service restrictions'))
                
                # Delete subprograms
                if subprograms.exists():
                    self.stdout.write('\nDeleting subprograms created after Oct 31...')
                    deleted_counts['subprograms'] = subprograms.delete()[0]
                    self.stdout.write(self.style.SUCCESS(f'  ✅ Deleted {deleted_counts["subprograms"]} subprograms'))
                
                # Delete program services
                if program_services.exists():
                    self.stdout.write('\nDeleting program services created after Oct 31...')
                    deleted_counts['program_services'] = program_services.delete()[0]
                    self.stdout.write(self.style.SUCCESS(f'  ✅ Deleted {deleted_counts["program_services"]} program services'))
                
                # Delete program staff assignments (related to programs)
                if program_ids and program_staff_count > 0:
                    self.stdout.write('\nDeleting program staff assignments...')
                    deleted_counts['program_staff'] = ProgramStaff.objects.filter(program_id__in=program_ids).delete()[0]
                    self.stdout.write(self.style.SUCCESS(f'  ✅ Deleted {deleted_counts["program_staff"]} program staff assignments'))
                
                # Delete program manager assignments
                if program_ids and program_manager_count > 0:
                    self.stdout.write('\nDeleting program manager assignments...')
                    deleted_counts['program_managers'] = ProgramManagerAssignment.objects.filter(program_id__in=program_ids).delete()[0]
                    self.stdout.write(self.style.SUCCESS(f'  ✅ Deleted {deleted_counts["program_managers"]} program manager assignments'))
                
                # Delete enrollments for programs that will be deleted
                if program_ids and enrollment_count_for_programs > 0:
                    self.stdout.write('\nDeleting enrollments for programs being deleted...')
                    program_enrollments = ClientProgramEnrollment.objects.filter(program_id__in=program_ids)
                    if options.get('create_audit_logs'):
                        for enrollment in program_enrollments:
                            try:
                                create_audit_log(
                                    entity_name='Enrollment',
                                    entity_id=enrollment.external_id,
                                    action='delete',
                                    changed_by=None,
                                    diff_data={
                                        'client': str(enrollment.client),
                                        'program': str(enrollment.program),
                                        'start_date': str(enrollment.start_date),
                                        'end_date': str(enrollment.end_date) if enrollment.end_date else None,
                                        'status': enrollment.status,
                                    }
                                )
                            except Exception as e:
                                logger.error(f"Error creating audit log for enrollment {enrollment.external_id}: {e}")
                    
                    additional_enrollments = program_enrollments.delete()[0]
                    deleted_counts['enrollments'] += additional_enrollments
                    self.stdout.write(self.style.SUCCESS(f'  ✅ Deleted {additional_enrollments} additional enrollments'))
                
                # Delete programs last (after all related data)
                if programs.exists():
                    self.stdout.write('\nDeleting programs created after Oct 31...')
                    if options.get('create_audit_logs'):
                        for program in programs:
                            try:
                                create_audit_log(
                                    entity_name='Program',
                                    entity_id=program.external_id,
                                    action='delete',
                                    changed_by=None,
                                    diff_data={
                                        'name': program.name,
                                        'department': str(program.department),
                                        'location': program.location or '',
                                        'capacity_current': program.capacity_current,
                                        'status': program.status,
                                    }
                                )
                            except Exception as e:
                                logger.error(f"Error creating audit log for program {program.external_id}: {e}")
                    
                    deleted_counts['programs'] = programs.delete()[0]
                    self.stdout.write(self.style.SUCCESS(f'  ✅ Deleted {deleted_counts["programs"]} programs'))
                
                # Build summary
                total_deleted = sum(deleted_counts.values())
                
                summary_lines = [
                    f'\n✅ Successfully deleted all records created after {cutoff_date.strftime("%B %d, %Y")}!',
                    '   Summary:',
                    f'   - {deleted_counts["programs"]} programs',
                    f'   - {deleted_counts["enrollments"]} enrollments',
                    f'   - {deleted_counts["restrictions"]} service restrictions',
                    f'   - {deleted_counts["subprograms"]} subprograms',
                    f'   - {deleted_counts["program_services"]} program services',
                    f'   - {deleted_counts["program_staff"]} program staff assignments',
                    f'   - {deleted_counts["program_managers"]} program manager assignments',
                    f'\n   Total records deleted: {total_deleted}'
                ]
                
                self.stdout.write(
                    self.style.SUCCESS('\n'.join(summary_lines))
                )
                
                logger.info(f'Deleted {total_deleted} records created after {cutoff_date}')
                
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'\n❌ Error deleting records: {e}')
            )
            import traceback
            self.stdout.write(traceback.format_exc())
            logger.error(f'Error deleting post-Oct31 records: {e}')
            raise

