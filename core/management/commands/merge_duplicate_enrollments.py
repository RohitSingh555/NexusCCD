"""
Django management command to merge duplicate/overlapping enrollments in the database.

This command applies the same merge logic used during file uploads to all existing
enrollments in the database. It finds overlapping or adjacent enrollments for the
same client and program, and merges them into a single enrollment.
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from datetime import timedelta
from core.models import ClientProgramEnrollment, Client
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Merge duplicate/overlapping enrollments for the same client and program using the same logic as upload processing'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be merged without actually merging',
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Show detailed output for each merge operation',
        )
        parser.add_argument(
            '--client-id',
            type=int,
            help='Only process enrollments for a specific client ID',
        )
        parser.add_argument(
            '--program-id',
            type=int,
            help='Only process enrollments for a specific program ID',
        )
        parser.add_argument(
            '--stats',
            action='store_true',
            help='Show detailed statistics about enrollments and potential merges',
        )

    def ranges_overlap_or_adjacent(self, start1, end1, start2, end2):
        """
        Check if two date ranges overlap or are adjacent (within 1 day).
        This is the same logic used in the upload process.
        """
        # If either range has no end date, they overlap if starts are compatible
        if end1 is None and end2 is None:
            return True  # Both open-ended, consider them overlapping
        if end1 is None:
            # Range 1 is open-ended (start1 to infinity)
            # Overlaps if: range 2 starts within range 1, OR range 2 ends after range 1 starts
            return start2 >= start1 or (end2 and end2 >= start1)
        if end2 is None:
            # Range 2 is open-ended (start2 to infinity)
            # Overlaps if: range 1 starts within range 2, OR range 1 ends after range 2 starts
            return start1 >= start2 or (end1 and end1 >= start2)
        
        # Both have end dates - check for overlap or adjacency
        # Overlap: start1 <= end2 AND start2 <= end1
        # Adjacent: end1 + 1 day = start2 OR end2 + 1 day = start1
        overlap = start1 <= end2 and start2 <= end1
        adjacent = (end1 and end1 + timedelta(days=1) == start2) or (end2 and end2 + timedelta(days=1) == start1)
        return overlap or adjacent

    def extract_discharge_reason(self, notes):
        """Extract discharge reason from notes if present"""
        if not notes or 'Reason:' not in notes:
            return None
        try:
            reason_part = notes.split('Reason:')[1].split('|')[0].strip()
            return reason_part if reason_part else None
        except:
            return None

    def find_overlapping_groups(self, enrollments):
        """
        Find groups of overlapping enrollments.
        Returns a list of groups, where each group contains enrollments that overlap.
        """
        if not enrollments:
            return []
        
        # Sort by start_date for easier processing
        sorted_enrollments = sorted(enrollments, key=lambda e: (e.start_date or timezone.now().date()))
        
        groups = []
        processed = set()
        
        for enrollment in sorted_enrollments:
            if enrollment.id in processed:
                continue
            
            # Start a new group with this enrollment
            group = [enrollment]
            processed.add(enrollment.id)
            
            # Find all enrollments that overlap with any enrollment in this group
            changed = True
            while changed:
                changed = False
                for other in sorted_enrollments:
                    if other.id in processed:
                        continue
                    
                    # Check if this enrollment overlaps with any in the current group
                    for group_member in group:
                        if self.ranges_overlap_or_adjacent(
                            group_member.start_date, group_member.end_date,
                            other.start_date, other.end_date
                        ):
                            group.append(other)
                            processed.add(other.id)
                            changed = True
                            break
            
            if len(group) > 1:  # Only return groups with multiple enrollments
                groups.append(group)
        
        return groups

    def merge_enrollment_group(self, group, dry_run=False, verbose=False):
        """
        Merge a group of overlapping enrollments into one.
        Uses the same logic as the upload process.
        """
        if len(group) <= 1:
            return None
        
        # Use the first enrollment as the base (prefer non-archived if available)
        base_enrollment = None
        for e in group:
            if not e.is_archived:
                base_enrollment = e
                break
        if not base_enrollment:
            base_enrollment = group[0]
        
        # Calculate merged dates
        all_start_dates = [e.start_date for e in group if e.start_date]
        earliest_start = min(all_start_dates) if all_start_dates else None
        
        # Collect all discharge information
        all_discharge_info = []
        for e in group:
            if e.end_date:
                discharge_reason = self.extract_discharge_reason(e.notes)
                all_discharge_info.append({
                    'date': e.end_date,
                    'reason': discharge_reason,
                    'notes': e.notes
                })
        
        latest_end = max([d['date'] for d in all_discharge_info]) if all_discharge_info else None
        
        # Collect unique discharge reasons
        discharge_reasons = []
        for info in all_discharge_info:
            if info['reason'] and info['reason'] not in discharge_reasons:
                discharge_reasons.append(info['reason'])
        
        # Build merged notes
        existing_notes = base_enrollment.notes or ''
        notes_parts = []
        
        # Preserve existing notes that aren't discharge-related
        if existing_notes and 'Discharge Date:' not in existing_notes:
            notes_parts.append(existing_notes)
        
        # Add merged discharge information
        if latest_end:
            discharge_note = f'Discharge Date: {latest_end.strftime("%Y-%m-%d")}'
            if discharge_reasons:
                discharge_note += f' | Reason: {", ".join(discharge_reasons)}'
            notes_parts.append(discharge_note)
        
        # Merge notes from other enrollments (non-discharge info)
        for info in all_discharge_info:
            if info['notes'] and 'Discharge Date:' not in info['notes']:
                if info['notes'] not in notes_parts:
                    notes_parts.append(f"Merged: {info['notes']}")
        
        merged_notes = ' | '.join(notes_parts) if notes_parts else None
        
        if verbose:
            client_name = f"{base_enrollment.client.first_name} {base_enrollment.client.last_name}"
            program_name = base_enrollment.program.name
            self.stdout.write(
                f"  Merging {len(group)} enrollments for {client_name} in {program_name}"
            )
            self.stdout.write(
                f"    Base enrollment ID: {base_enrollment.id}"
            )
            self.stdout.write(
                f"    Date range: {earliest_start} to {latest_end}"
            )
            self.stdout.write(
                f"    Enrollments to archive: {[e.id for e in group if e.id != base_enrollment.id]}"
            )
        
        if not dry_run:
            # Ensure end_date >= start_date constraint is satisfied
            if latest_end and earliest_start and latest_end < earliest_start:
                # This shouldn't happen with proper merge logic, but handle it gracefully
                logger.warning(
                    f"End date {latest_end} is before start date {earliest_start} for enrollment {base_enrollment.id}. "
                    f"Using start_date as end_date."
                )
                latest_end = earliest_start
            
            # Update the base enrollment
            original_start = base_enrollment.start_date
            original_end = base_enrollment.end_date
            base_enrollment.start_date = earliest_start
            base_enrollment.end_date = latest_end
            base_enrollment.notes = merged_notes
            base_enrollment.updated_by = 'System - Merge Duplicate Enrollments'
            base_enrollment.is_archived = False  # Ensure base is not archived
            base_enrollment.save()
            
            # Archive other enrollments
            archived_count = 0
            for other_enrollment in group:
                if other_enrollment.id != base_enrollment.id and not other_enrollment.is_archived:
                    other_enrollment.is_archived = True
                    other_enrollment.archived_at = timezone.now()
                    other_enrollment.save()
                    archived_count += 1
            
            # Update client status after merge
            # Refresh client from DB to get latest enrollment data, then update status
            status_updated = False
            try:
                client = Client.objects.get(id=base_enrollment.client_id)
                old_status = client.is_inactive
                status_changed = client.update_inactive_status()
                if status_changed:
                    client.save(update_fields=['is_inactive'])
                    status_updated = True
                    new_status = client.is_inactive
                    status_text = "inactive" if new_status else "active"
                    logger.info(
                        f"Updated client {client.first_name} {client.last_name} (ID: {client.id}) "
                        f"status from {'inactive' if old_status else 'active'} to {status_text} "
                        f"after enrollment merge"
                    )
                    if verbose:
                        self.stdout.write(
                            f"    Client status updated: {'inactive' if old_status else 'active'} → {status_text}"
                        )
                elif verbose:
                    current_status = "inactive" if client.is_inactive else "active"
                    self.stdout.write(f"    Client status remains: {current_status}")
            except Exception as e:
                error_msg = f"Failed to update client status after merge for client {base_enrollment.client_id}: {str(e)}"
                logger.warning(error_msg, exc_info=True)
                if verbose:
                    self.stdout.write(self.style.ERROR(f"    WARNING: {error_msg}"))
            
            return {
                'base_id': base_enrollment.id,
                'archived_count': archived_count,
                'merged_count': len(group),
                'status_updated': status_updated
            }
        else:
            return {
                'base_id': base_enrollment.id,
                'archived_count': len(group) - 1,
                'merged_count': len(group)
            }

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        verbose = options['verbose']
        client_id = options.get('client_id')
        program_id = options.get('program_id')
        
        self.stdout.write(self.style.SUCCESS('\n=== Enrollment Merge Process ===\n'))
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be made\n'))
        
        # Build query for enrollments
        enrollments_query = ClientProgramEnrollment.objects.filter(is_archived=False)
        
        if client_id:
            enrollments_query = enrollments_query.filter(client_id=client_id)
            self.stdout.write(f'Filtering by Client ID: {client_id}')
        
        if program_id:
            enrollments_query = enrollments_query.filter(program_id=program_id)
            self.stdout.write(f'Filtering by Program ID: {program_id}')
        
        # Group enrollments by client and program
        self.stdout.write('Grouping enrollments by client and program...')
        enrollment_groups = defaultdict(list)
        
        for enrollment in enrollments_query.select_related('client', 'program'):
            key = (enrollment.client_id, enrollment.program_id)
            enrollment_groups[key].append(enrollment)
        
        total_groups = len(enrollment_groups)
        total_enrollments = enrollments_query.count()
        self.stdout.write(f'Found {total_enrollments} total enrollments')
        self.stdout.write(f'Found {total_groups} unique client-program combinations\n')
        
        # Statistics tracking
        stats_mode = options.get('stats', False)
        groups_with_multiple = 0
        groups_with_overlaps = 0
        groups_with_no_overlaps = 0
        total_potential_merges = 0
        enrollments_in_groups_with_multiple = 0
        
        # Process each group
        total_merged = 0
        total_archived = 0
        groups_processed = 0
        groups_with_merges = 0
        clients_status_updated = 0
        errors = []
        
        for (client_id, program_id), enrollments in enrollment_groups.items():
            if len(enrollments) <= 1:
                continue  # No duplicates possible
            
            groups_with_multiple += 1
            enrollments_in_groups_with_multiple += len(enrollments)
            
            groups_processed += 1
            
            # Find overlapping groups within this client-program combination
            overlapping_groups = self.find_overlapping_groups(enrollments)
            
            if not overlapping_groups:
                groups_with_no_overlaps += 1
                if stats_mode:
                    client = enrollments[0].client
                    program = enrollments[0].program
                    # Show why they're not overlapping
                    sorted_dates = sorted([(e.start_date, e.end_date) for e in enrollments])
                    gaps = []
                    for i in range(len(sorted_dates) - 1):
                        end1 = sorted_dates[i][1]
                        start2 = sorted_dates[i+1][0]
                        if end1 and start2:
                            gap = (start2 - end1).days
                            if gap > 1:  # More than 1 day gap
                                gaps.append(f"{gap} days")
                    if gaps:
                        self.stdout.write(
                            f"  Skipped: {client.first_name} {client.last_name} - {program.name} "
                            f"({len(enrollments)} enrollments, gaps: {', '.join(gaps)})"
                        )
                continue
            
            groups_with_overlaps += 1
            groups_with_merges += 1
            total_potential_merges += sum(len(g) for g in overlapping_groups)
            
            if verbose:
                client = enrollments[0].client
                program = enrollments[0].program
                self.stdout.write(
                    f"\nProcessing: {client.first_name} {client.last_name} - {program.name}"
                )
            
            for group in overlapping_groups:
                try:
                    # Each merge is in its own transaction to avoid rolling back all changes on error
                    with transaction.atomic():
                        result = self.merge_enrollment_group(group, dry_run=dry_run, verbose=verbose)
                        if result:
                            total_merged += result['merged_count']
                            total_archived += result['archived_count']
                            # Track if client status was updated
                            if result.get('status_updated'):
                                clients_status_updated += 1
                except Exception as e:
                    error_msg = f"Error merging group for client {enrollments[0].client.id}, program {enrollments[0].program.id}: {str(e)}"
                    errors.append(error_msg)
                    logger.error(error_msg, exc_info=True)
                    if verbose:
                        self.stdout.write(self.style.ERROR(f"  ERROR: {error_msg}"))
                    # Continue processing other groups even if one fails
        
        # Final pass: Update status for all clients that had enrollments processed
        # This ensures status is correct even if some clients weren't merged
        if not dry_run:
            self.stdout.write('\nUpdating client statuses for all affected clients...')
            affected_client_ids = set()
            for (client_id, program_id), enrollments in enrollment_groups.items():
                if len(enrollments) > 1:  # Only clients with potential duplicates
                    affected_client_ids.add(client_id)
            
            status_updates_final = 0
            for client_id in affected_client_ids:
                try:
                    client = Client.objects.get(id=client_id)
                    old_status = client.is_inactive
                    status_changed = client.update_inactive_status()
                    if status_changed:
                        client.save(update_fields=['is_inactive'])
                        status_updates_final += 1
                        if verbose:
                            new_status = "inactive" if client.is_inactive else "active"
                            self.stdout.write(
                                f"  Updated client {client.first_name} {client.last_name} (ID: {client_id}) "
                                f"to {new_status}"
                            )
                except Exception as e:
                    logger.warning(f"Failed to update client status for client {client_id}: {e}")
            
            if status_updates_final > 0:
                self.stdout.write(f'Updated status for {status_updates_final} additional client(s)')
        
        # Summary
        self.stdout.write(self.style.SUCCESS('\n=== Summary ===\n'))
        self.stdout.write(f'Total enrollments processed: {total_enrollments}')
        self.stdout.write(f'Unique client-program combinations: {total_groups}')
        self.stdout.write(f'Client-program combinations with 2+ enrollments: {groups_with_multiple}')
        self.stdout.write(f'  - With overlapping dates: {groups_with_overlaps}')
        self.stdout.write(f'  - Without overlapping dates (gaps > 1 day): {groups_with_no_overlaps}')
        self.stdout.write(f'Groups with merges performed: {groups_with_merges}')
        self.stdout.write(f'Total enrollments merged: {total_merged}')
        self.stdout.write(f'Total enrollments archived: {total_archived}')
        self.stdout.write(f'Clients with status updated: {clients_status_updated}')
        
        if stats_mode:
            self.stdout.write(self.style.SUCCESS('\n=== Detailed Statistics ===\n'))
            self.stdout.write(f'Enrollments in groups with multiple: {enrollments_in_groups_with_multiple}')
            self.stdout.write(f'Enrollments in single-enrollment groups: {total_enrollments - enrollments_in_groups_with_multiple}')
            self.stdout.write(f'Average enrollments per client-program (with multiples): {enrollments_in_groups_with_multiple / groups_with_multiple if groups_with_multiple > 0 else 0:.2f}')
            if groups_with_no_overlaps > 0:
                self.stdout.write(
                    self.style.WARNING(
                        f'\n⚠️  Note: {groups_with_no_overlaps} client-program combinations have multiple enrollments '
                        f'but they don\'t overlap (gaps > 1 day). These are NOT merged as they may represent '
                        f'separate enrollment periods.'
                    )
                )
        
        if errors:
            self.stdout.write(self.style.ERROR(f'\n⚠️  Errors encountered: {len(errors)}'))
            if verbose:
                for error in errors:
                    self.stdout.write(self.style.ERROR(f'  - {error}'))
        
        if dry_run:
            self.stdout.write(self.style.WARNING('\nDRY RUN - No changes were made'))
        else:
            if errors:
                self.stdout.write(self.style.WARNING('\n⚠️  Merge process completed with errors'))
            else:
                self.stdout.write(self.style.SUCCESS('\n✅ Merge process completed successfully!'))
        
        self.stdout.write('')

