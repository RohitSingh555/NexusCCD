from datetime import timedelta
from django.utils import timezone

from .models import (
    Notification,
    ServiceRestrictionNotificationSubscription,
)


def _build_restriction_metadata(restriction, event_type):
    metadata = {
        'restriction_external_id': str(restriction.external_id),
        'client_external_id': str(restriction.client.external_id),
        'client_name': f"{restriction.client.first_name} {restriction.client.last_name}",
        'event_type': event_type,
        'restriction_detail_url': f"/core/restrictions/{restriction.external_id}/",
        'client_detail_url': f"/clients/{restriction.client.external_id}/",
    }

    if restriction.program:
        metadata['program'] = restriction.program.name

    if restriction.scope:
        metadata['scope'] = restriction.scope

    if restriction.start_date:
        metadata['start_date'] = restriction.start_date.isoformat()

    if restriction.end_date:
        metadata['end_date'] = restriction.end_date.isoformat()

    return metadata


def create_service_restriction_notification(restriction, event_type='new'):
    """
    Create staff notifications for service restriction events based on subscriptions.

    Parameters
    ----------
    restriction : ServiceRestriction
        The restriction instance that triggered the notification.
    event_type : str
        Either 'new' or 'expiring'.
    """
    event_type = event_type or 'new'
    if event_type not in {'new', 'expiring'}:
        return 0

    subscription_filter = {}
    if event_type == 'new':
        subscription_filter['notify_new'] = True
    else:
        subscription_filter['notify_expiring'] = True

    subscriptions = (
        ServiceRestrictionNotificationSubscription.objects
        .filter(**subscription_filter)
        .select_related('staff', 'staff__user')
    )

    if not subscriptions.exists():
        return 0

    metadata_template = _build_restriction_metadata(restriction, event_type)
    title_client_name = metadata_template['client_name']

    if event_type == 'new':
        title = f"New restriction for {title_client_name}"
        message = (
            f"A new service restriction was created for {title_client_name}."
            f" Scope: {restriction.scope or 'General'}."
        )
    else:
        title = f"Restriction expiring soon for {title_client_name}"
        if restriction.end_date:
            days_remaining = (restriction.end_date - timezone.now().date()).days
            if days_remaining < 0:
                days_text = "expired"
            elif days_remaining == 0:
                days_text = "today"
            elif days_remaining == 1:
                days_text = "in 1 day"
            else:
                days_text = f"in {days_remaining} days"
            message = (
                f"The restriction for {title_client_name} is due to end {days_text}"
                f" on {restriction.end_date.strftime('%b %d, %Y')}."
            )
        else:
            message = (
                f"The restriction for {title_client_name} is nearing the scheduled end date."
            )

    notifications_to_create = []
    existing_query_kwargs = {
        'category': 'service_restriction',
        'metadata__restriction_external_id': metadata_template['restriction_external_id'],
        'metadata__event_type': event_type,
    }

    for subscription in subscriptions:
        staff = subscription.staff
        staff_user = getattr(staff, 'user', None)

        if not staff or (staff_user and not staff_user.is_active):
            continue

        if Notification.objects.filter(staff=staff, **existing_query_kwargs).exists():
            continue

        notifications_to_create.append(
            Notification(
                staff=staff,
                category='service_restriction',
                title=title,
                message=message,
                metadata=metadata_template.copy(),
            )
        )

    if notifications_to_create:
        Notification.objects.bulk_create(notifications_to_create)

    return len(notifications_to_create)


