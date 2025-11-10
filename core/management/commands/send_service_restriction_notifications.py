from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import ServiceRestriction
from core.notification_utils import create_service_restriction_notification


class Command(BaseCommand):
    help = "Generate in-app notifications for service restrictions that are nearing expiration."

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=7,
            help='Number of days ahead to consider for upcoming expirations (default: 7).',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Preview the number of notifications that would be created without saving anything.',
        )

    def handle(self, *args, **options):
        days = max(1, options['days'])
        dry_run = options['dry_run']

        today = timezone.now().date()
        window_end = today + timedelta(days=days)

        restrictions = ServiceRestriction.objects.filter(
            end_date__isnull=False,
            end_date__gte=today,
            end_date__lte=window_end,
            is_archived=False,
        ).select_related('client', 'program')

        if not restrictions.exists():
            self.stdout.write(self.style.WARNING("No service restrictions found within the selected window."))
            return

        total_created = 0
        for restriction in restrictions:
            if dry_run:
                self.stdout.write(
                    f"[DRY RUN] Would create notifications for restriction {restriction.external_id} "
                    f"ending on {restriction.end_date}"
                )
                continue

            created = create_service_restriction_notification(restriction, event_type='expiring')
            total_created += created

        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(
                    f"[DRY RUN] {restrictions.count()} restriction(s) evaluated within {days} day(s)."
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Created {total_created} notification(s) for {restrictions.count()} restriction(s) "
                    f"within {days} day(s)."
                )
            )

