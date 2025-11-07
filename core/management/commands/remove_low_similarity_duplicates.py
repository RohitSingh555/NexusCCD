from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Count
from core.models import ClientDuplicate
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Remove duplicate entries that have similarity score below 90% (0.9)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--threshold',
            type=float,
            default=0.9,
            help='Similarity threshold below which duplicates will be removed (default: 0.9 = 90%%)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without actually deleting',
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Show detailed output including which duplicates will be removed',
        )
        parser.add_argument(
            '--status',
            type=str,
            choices=['pending', 'confirmed_duplicate', 'not_duplicate', 'merged', 'all'],
            default='all',
            help='Filter by status. Options: pending, confirmed_duplicate, not_duplicate, merged, all (default: all)',
        )

    def handle(self, *args, **options):
        threshold = options['threshold']
        dry_run = options['dry_run']
        verbose = options['verbose']
        status_filter = options['status']
        
        # Build query for duplicates below threshold
        duplicates_query = ClientDuplicate.objects.filter(similarity_score__lt=threshold)
        
        # Apply status filter if specified
        if status_filter != 'all':
            duplicates_query = duplicates_query.filter(status=status_filter)
        
        # Count duplicates to be removed
        count = duplicates_query.count()
        
        if count == 0:
            self.stdout.write(
                self.style.SUCCESS(
                    f'\n✅ No duplicate entries found with similarity below {threshold * 100:.1f}%%.'
                )
            )
            return
        
        # Show summary
        self.stdout.write(
            self.style.WARNING(
                f'\n📊 Found {count} duplicate entry/entries with similarity below {threshold * 100:.1f}%%.'
            )
        )
        
        if verbose:
            self.stdout.write('\n📋 Details of duplicates to be removed:')
            self.stdout.write('-' * 80)
            for dup in duplicates_query.select_related('primary_client', 'duplicate_client')[:50]:  # Show first 50
                primary_name = f"{dup.primary_client.first_name} {dup.primary_client.last_name}"
                duplicate_name = f"{dup.duplicate_client.first_name} {dup.duplicate_client.last_name}"
                self.stdout.write(
                    f"  • {primary_name} <-> {duplicate_name} "
                    f"(Similarity: {dup.similarity_score * 100:.1f}%%, "
                    f"Status: {dup.status}, "
                    f"Match Type: {dup.match_type})"
                )
            if count > 50:
                self.stdout.write(f"  ... and {count - 50} more entries")
            self.stdout.write('-' * 80)
        
        # Show status breakdown
        if status_filter == 'all':
            status_breakdown = duplicates_query.values('status').annotate(
                count=Count('id')
            )
            self.stdout.write('\n📊 Breakdown by status:')
            for item in status_breakdown:
                self.stdout.write(f"  • {item['status']}: {item['count']} entries")
        
        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(
                    f'\n🔍 DRY RUN: Would delete {count} duplicate entry/entries.'
                )
            )
            self.stdout.write(
                self.style.WARNING(
                    '\n⚠️  Run without --dry-run to actually delete these entries.'
                )
            )
            return
        
        # Confirm deletion
        self.stdout.write(
            self.style.WARNING(
                f'\n⚠️  About to delete {count} duplicate entry/entries with similarity below {threshold * 100:.1f}%%.'
            )
        )
        
        # Delete duplicates
        try:
            with transaction.atomic():
                deleted_count = duplicates_query.delete()[0]
                
                self.stdout.write(
                    self.style.SUCCESS(
                        f'\n✅ Successfully deleted {deleted_count} duplicate entry/entries with similarity below {threshold * 100:.1f}%%.'
                    )
                )
                
                logger.info(f'Deleted {deleted_count} duplicate entries with similarity below {threshold}')
                
                # Show summary by status if all statuses were processed
                if status_filter == 'all':
                    remaining = ClientDuplicate.objects.count()
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'\n📊 Remaining duplicate entries in database: {remaining}'
                        )
                    )
                    
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'\n❌ Error deleting duplicate entries: {e}')
            )
            logger.error(f'Error deleting low similarity duplicates: {e}')
            raise

