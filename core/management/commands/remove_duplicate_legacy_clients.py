from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q
from core.models import (
    Client, ClientProgramEnrollment, Intake, Discharge,
    ServiceRestriction, ClientDuplicate
)
from staff.models import StaffClientAssignment
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Remove duplicate clients that have the same legacy_id and source, keeping only the latest ones'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without actually deleting',
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Show detailed output including which clients will be deleted',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        verbose = options['verbose']
        
        self.stdout.write('\n🔍 Searching for duplicate clients with same client_id+source or legacy_id+source...')
        
        # Group 1: Check for duplicates based on client_id + source (direct fields)
        self.stdout.write('  Checking client_id + source (direct fields)...')
        direct_duplicate_groups = defaultdict(list)
        
        # Get all clients with client_id and source
        clients_with_id = Client.objects.filter(
            client_id__isnull=False,
            source__isnull=False
        ).exclude(
            client_id='',
            source=''
        ).select_related()
        
        for client in clients_with_id:
            key = (client.client_id, client.source)
            direct_duplicate_groups[key].append(client)
        
        # Find groups with duplicates (more than 1 client)
        direct_duplicates = {key: clients for key, clients in direct_duplicate_groups.items() if len(clients) > 1}
        
        # Group 2: Check for duplicates based on legacy_client_ids JSONField
        self.stdout.write('  Checking legacy_client_ids JSONField...')
        legacy_groups = defaultdict(list)
        
        # Get all clients with legacy_client_ids
        clients_with_legacy = Client.objects.filter(
            legacy_client_ids__isnull=False
        ).exclude(legacy_client_ids=[]).select_related()
        
        for client in clients_with_legacy:
            if not client.legacy_client_ids or not isinstance(client.legacy_client_ids, list):
                continue
            
            # Extract all (legacy_id, source) pairs from this client's legacy_client_ids
            for legacy_entry in client.legacy_client_ids:
                if isinstance(legacy_entry, dict):
                    legacy_id = legacy_entry.get('client_id')
                    source = legacy_entry.get('source')
                    
                    if legacy_id and source:
                        key = (legacy_id, source)
                        legacy_groups[key].append(client)
        
        # Find groups with duplicates (more than 1 client)
        legacy_duplicates = {key: clients for key, clients in legacy_groups.items() if len(clients) > 1}
        
        # Combine both duplicate groups
        # Use a set to track which clients are already in a duplicate group to avoid double-counting
        all_duplicate_groups = {}
        processed_clients = set()
        
        # Add direct field duplicates
        for key, clients in direct_duplicates.items():
            all_duplicate_groups[f"client_id+source:{key[0]}|{key[1]}"] = clients
            processed_clients.update(c.id for c in clients)
        
        # Add legacy_client_ids duplicates (only if client not already processed)
        for key, clients in legacy_duplicates.items():
            # Filter out clients already in direct duplicates
            unique_clients = [c for c in clients if c.id not in processed_clients]
            if len(unique_clients) > 1:
                all_duplicate_groups[f"legacy_id+source:{key[0]}|{key[1]}"] = unique_clients
        
        duplicate_groups = all_duplicate_groups
        
        if not duplicate_groups:
            self.stdout.write(
                self.style.SUCCESS(
                    '\n✅ No duplicate clients found with same client_id+source or legacy_id+source.'
                )
            )
            return
        
        # Count total duplicates to be deleted
        total_duplicates = sum(len(clients) - 1 for clients in duplicate_groups.values())
        total_groups = len(duplicate_groups)
        
        self.stdout.write(
            self.style.WARNING(
                f'\n📊 Found {total_groups} group(s) with duplicate client_id+source or legacy_id+source combinations.'
            )
        )
        self.stdout.write(
            self.style.WARNING(
                f'📊 Total duplicate clients to be deleted: {total_duplicates}'
            )
        )
        
        if verbose:
            self.stdout.write('\n📋 Details of duplicate groups:')
            self.stdout.write('-' * 100)
            for group_key, clients in list(duplicate_groups.items())[:20]:  # Show first 20
                # Sort by created_at to identify which will be kept
                sorted_clients = sorted(clients, key=lambda c: c.created_at, reverse=True)
                keep_client = sorted_clients[0]
                delete_clients = sorted_clients[1:]
                
                # Parse the group key to show readable info
                if group_key.startswith('client_id+source:'):
                    parts = group_key.replace('client_id+source:', '').split('|')
                    display_key = f"client_id: {parts[0]}, source: {parts[1]}"
                else:
                    parts = group_key.replace('legacy_id+source:', '').split('|')
                    display_key = f"legacy_id: {parts[0]}, source: {parts[1]}"
                
                self.stdout.write(
                    f"\n  {display_key} ({len(clients)} clients)"
                )
                self.stdout.write(
                    f"    ✅ KEEP: {keep_client.first_name} {keep_client.last_name} "
                    f"(ID: {keep_client.id}, client_id: {keep_client.client_id}, Created: {keep_client.created_at})"
                )
                for del_client in delete_clients:
                    self.stdout.write(
                        f"    ❌ DELETE: {del_client.first_name} {del_client.last_name} "
                        f"(ID: {del_client.id}, client_id: {del_client.client_id}, Created: {del_client.created_at})"
                    )
            if total_groups > 20:
                self.stdout.write(f"\n  ... and {total_groups - 20} more groups")
            self.stdout.write('-' * 100)
        
        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(
                    f'\n🔍 DRY RUN: Would delete {total_duplicates} duplicate client(s).'
                )
            )
            self.stdout.write(
                self.style.WARNING(
                    '\n⚠️  Run without --dry-run to actually delete these clients and their related records.'
                )
            )
            return
        
        # Collect all clients to delete
        clients_to_delete = []
        clients_to_keep = []
        
        for group_key, clients in duplicate_groups.items():
            # Sort by created_at descending (latest first)
            sorted_clients = sorted(clients, key=lambda c: c.created_at, reverse=True)
            keep_client = sorted_clients[0]
            delete_clients = sorted_clients[1:]
            
            clients_to_keep.append(keep_client)
            clients_to_delete.extend(delete_clients)
        
        # Count related records that will be deleted
        if verbose:
            self.stdout.write('\n📊 Counting related records to be deleted...')
            enrollment_count = ClientProgramEnrollment.objects.filter(client__in=clients_to_delete).count()
            intake_count = Intake.objects.filter(client__in=clients_to_delete).count()
            discharge_count = Discharge.objects.filter(client__in=clients_to_delete).count()
            restriction_count = ServiceRestriction.objects.filter(client__in=clients_to_delete).count()
            staff_assignment_count = StaffClientAssignment.objects.filter(client__in=clients_to_delete).count()
            
            # Count ClientDuplicate records that reference these clients
            duplicate_record_count = ClientDuplicate.objects.filter(
                Q(primary_client__in=clients_to_delete) | 
                Q(duplicate_client__in=clients_to_delete)
            ).count()
            
            self.stdout.write(f'  • ClientProgramEnrollments: {enrollment_count}')
            self.stdout.write(f'  • Intakes: {intake_count}')
            self.stdout.write(f'  • Discharges: {discharge_count}')
            self.stdout.write(f'  • ServiceRestrictions: {restriction_count}')
            self.stdout.write(f'  • StaffClientAssignments: {staff_assignment_count}')
            self.stdout.write(f'  • ClientDuplicate records: {duplicate_record_count}')
        
        # Confirm deletion
        self.stdout.write(
            self.style.WARNING(
                f'\n⚠️  About to delete {total_duplicates} duplicate client(s) and all their related records.'
            )
        )
        
        try:
            with transaction.atomic():
                deleted_count = 0
                related_deleted = {
                    'enrollments': 0,
                    'intakes': 0,
                    'discharges': 0,
                    'restrictions': 0,
                    'staff_assignments': 0,
                    'duplicate_records': 0,
                }
                
                # Delete ClientDuplicate records that reference clients being deleted
                # (These need to be deleted before the clients themselves)
                duplicate_records = ClientDuplicate.objects.filter(
                    Q(primary_client__in=clients_to_delete) | 
                    Q(duplicate_client__in=clients_to_delete)
                )
                related_deleted['duplicate_records'] = duplicate_records.count()
                duplicate_records.delete()
                
                # Delete clients (CASCADE will handle most related records automatically)
                for client in clients_to_delete:
                    # Count related records before deletion
                    if verbose:
                        related_deleted['enrollments'] += ClientProgramEnrollment.objects.filter(client=client).count()
                        related_deleted['intakes'] += Intake.objects.filter(client=client).count()
                        related_deleted['discharges'] += Discharge.objects.filter(client=client).count()
                        related_deleted['restrictions'] += ServiceRestriction.objects.filter(client=client).count()
                        related_deleted['staff_assignments'] += StaffClientAssignment.objects.filter(client=client).count()
                    
                    client.delete()
                    deleted_count += 1
                
                self.stdout.write(
                    self.style.SUCCESS(
                        f'\n✅ Successfully deleted {deleted_count} duplicate client(s) and all related records.'
                    )
                )
                
                if verbose:
                    self.stdout.write('\n📊 Summary of deleted records:')
                    self.stdout.write(f'  • Clients: {deleted_count}')
                    self.stdout.write(f'  • ClientProgramEnrollments: {related_deleted["enrollments"]}')
                    self.stdout.write(f'  • Intakes: {related_deleted["intakes"]}')
                    self.stdout.write(f'  • Discharges: {related_deleted["discharges"]}')
                    self.stdout.write(f'  • ServiceRestrictions: {related_deleted["restrictions"]}')
                    self.stdout.write(f'  • StaffClientAssignments: {related_deleted["staff_assignments"]}')
                    self.stdout.write(f'  • ClientDuplicate records: {related_deleted["duplicate_records"]}')
                
                logger.info(f'Deleted {deleted_count} duplicate clients with same legacy_id and source')
                
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'\n❌ Error deleting duplicate clients: {e}')
            )
            logger.error(f'Error deleting duplicate clients: {e}', exc_info=True)
            raise

