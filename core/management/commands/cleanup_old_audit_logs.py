from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from datetime import timedelta
from core.models import AuditLog
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Delete audit logs older than specified number of days (default: 15 days). Can also clean up delete records specifically.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=15,
            help='Number of days to keep audit logs (default: 15)',
        )
        parser.add_argument(
            '--cleanup-deletes',
            action='store_true',
            help='Clean up delete audit log entries older than 7 days (overrides --days for delete actions)',
        )
        parser.add_argument(
            '--delete-days',
            type=int,
            default=7,
            help='Number of days to keep delete audit logs (only used with --cleanup-deletes, default: 7)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without actually deleting',
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Show detailed output',
        )

    def handle(self, *args, **options):
        days_to_keep = options['days']
        cleanup_deletes = options['cleanup_deletes']
        delete_days = options['delete_days']
        dry_run = options['dry_run']
        verbose = options['verbose']
        
        total_deleted = 0
        
        # If cleanup_deletes is specified, clean up delete records first
        if cleanup_deletes:
            delete_cutoff_date = timezone.now() - timedelta(days=delete_days)
            old_delete_logs = AuditLog.objects.filter(
                action='delete',
                changed_at__lt=delete_cutoff_date
            )
            delete_count = old_delete_logs.count()
            
            if delete_count > 0:
                if verbose:
                    self.stdout.write(f'\nDelete records cutoff date: {delete_cutoff_date.strftime("%Y-%m-%d %H:%M:%S")}')
                    if delete_count > 0:
                        self.stdout.write(f'Oldest delete log: {old_delete_logs.order_by("changed_at").first().changed_at}')
                        self.stdout.write(f'Newest delete log to be deleted: {old_delete_logs.order_by("-changed_at").first().changed_at}')
                
                self.stdout.write(
                    self.style.WARNING(
                        f'\nFound {delete_count} delete audit log(s) older than {delete_days} days to delete.'
                    )
                )
                
                if not dry_run:
                    try:
                        with transaction.atomic():
                            deleted_count = old_delete_logs.delete()[0]
                            total_deleted += deleted_count
                            
                            self.stdout.write(
                                self.style.SUCCESS(
                                    f'✅ Successfully deleted {deleted_count} delete audit log(s) older than {delete_days} days.'
                                )
                            )
                            
                            logger.info(f'Deleted {deleted_count} delete audit logs older than {delete_days} days')
                    except Exception as e:
                        self.stdout.write(
                            self.style.ERROR(f'\n❌ Error deleting delete audit logs: {e}')
                        )
                        logger.error(f'Error deleting old delete audit logs: {e}')
                        raise
                else:
                    self.stdout.write(self.style.SUCCESS(f'\nDRY RUN: Would delete {delete_count} delete audit log(s).'))
            else:
                self.stdout.write(
                    self.style.SUCCESS(
                        f'\nNo delete audit logs older than {delete_days} days found.'
                    )
                )
        
        # Then clean up all other audit logs (if not only cleaning deletes)
        if not cleanup_deletes or days_to_keep != delete_days:
            # Calculate cutoff date
            cutoff_date = timezone.now() - timedelta(days=days_to_keep)
            
            # Find old audit logs (excluding deletes if we already cleaned them)
            if cleanup_deletes:
                old_logs = AuditLog.objects.filter(
                    changed_at__lt=cutoff_date
                ).exclude(action='delete')
            else:
                old_logs = AuditLog.objects.filter(changed_at__lt=cutoff_date)
            
            count = old_logs.count()
            
            if count == 0:
                if not cleanup_deletes:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'\nNo audit logs older than {days_to_keep} days found.'
                        )
                    )
                return
            
            if verbose:
                # Show some examples
                self.stdout.write(f'\nCutoff date: {cutoff_date.strftime("%Y-%m-%d %H:%M:%S")}')
                if count > 0:
                    self.stdout.write(f'Oldest audit log: {old_logs.order_by("changed_at").first().changed_at}')
                    self.stdout.write(f'Newest audit log to be deleted: {old_logs.order_by("-changed_at").first().changed_at}')
            
            self.stdout.write(
                self.style.WARNING(
                    f'\nFound {count} audit log(s) older than {days_to_keep} days to delete.'
                )
            )
            
            if dry_run:
                self.stdout.write(self.style.SUCCESS('\nDRY RUN: No audit logs were deleted.'))
                return
            
            # Delete old audit logs
            try:
                with transaction.atomic():
                    deleted_count = old_logs.delete()[0]
                    total_deleted += deleted_count
                    
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'\n✅ Successfully deleted {deleted_count} audit log(s) older than {days_to_keep} days.'
                        )
                    )
                    
                    logger.info(f'Deleted {deleted_count} audit logs older than {days_to_keep} days')
                    
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'\n❌ Error deleting audit logs: {e}')
                )
                logger.error(f'Error deleting old audit logs: {e}')
                raise
        
        if total_deleted > 0:
            self.stdout.write(
                self.style.SUCCESS(
                    f'\n📊 Total audit logs deleted: {total_deleted}'
                )
            )

