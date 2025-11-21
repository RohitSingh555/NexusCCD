from datetime import timedelta
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from django.template.loader import render_to_string

from .models import (
    Notification,
    ServiceRestrictionNotificationSubscription,
    Staff,
    Role,
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
        
        # Send email notifications
        for subscription in subscriptions:
            staff = subscription.staff
            staff_user = getattr(staff, 'user', None)
            
            if not staff or (staff_user and not staff_user.is_active):
                continue
            
            # Get email address
            email_address = subscription.email or (staff.email if hasattr(staff, 'email') else None) or (staff_user.email if staff_user else None)
            
            if not email_address:
                continue
            
            # Check if notification was created for this staff member
            if not any(n.staff == staff for n in notifications_to_create):
                continue
            
            try:
                # Build email content
                client_name = metadata_template['client_name']
                restriction_url = f"{settings.FRONTEND_URL if hasattr(settings, 'FRONTEND_URL') else 'http://dev.fredvictor.org'}{metadata_template['restriction_detail_url']}"
                
                email_subject = title
                email_body = f"""
{message}

View restriction details: {restriction_url}

Client: {client_name}
Scope: {restriction.scope or 'General'}
"""
                if restriction.program:
                    email_body += f"Program: {restriction.program.name}\n"
                if restriction.start_date:
                    email_body += f"Start Date: {restriction.start_date.strftime('%B %d, %Y')}\n"
                if restriction.end_date:
                    email_body += f"End Date: {restriction.end_date.strftime('%B %d, %Y')}\n"
                
                # Send email
                send_mail(
                    subject=email_subject,
                    message=email_body,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[email_address],
                    fail_silently=False,
                )
            except Exception as e:
                # Log error but don't fail the whole process
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Failed to send email notification to {email_address}: {str(e)}")

    return len(notifications_to_create)


def notify_superadmin_for_approval(restriction, action='created', user=None):
    """
    Notify SuperAdmin users when Manager/Leader creates or updates a service restriction.
    
    Parameters
    ----------
    restriction : ServiceRestriction
        The restriction instance that needs approval.
    action : str
        Either 'created' or 'updated'.
    user : User
        The user who performed the action.
    """
    try:
        # Get all SuperAdmin users
        superadmin_role = Role.objects.filter(name='SuperAdmin').first()
        if not superadmin_role:
            return 0
        
        superadmin_staff = Staff.objects.filter(
            staffrole__role=superadmin_role,
            active=True
        ).distinct()
        
        if not superadmin_staff.exists():
            return 0
        
        user_name = user.get_full_name() or user.username if user else 'Unknown User'
        client_name = f"{restriction.client.first_name} {restriction.client.last_name}"
        
        # Create notifications for SuperAdmin users
        notifications_to_create = []
        emails_to_send = []
        
        for staff in superadmin_staff:
            staff_user = getattr(staff, 'user', None)
            if not staff_user or not staff_user.is_active:
                continue
            
            # Determine user role for message (from the user who created/updated, not the SuperAdmin)
            user_role = 'User'
            if user and hasattr(user, 'staff_profile'):
                try:
                    user_staff = user.staff_profile
                    user_staff_roles = [r.role.name for r in user_staff.staffrole_set.select_related('role').all()]
                    if 'Manager' in user_staff_roles:
                        user_role = 'Manager'
                    elif 'Leader' in user_staff_roles:
                        user_role = 'Leader'
                except Exception:
                    pass
            
            # Create in-app notification
            title = f"Service Restriction {action.capitalize()} - Approval Required"
            message = (
                f"{user_name} ({user_role}) "
                f"{action} a service restriction for {client_name}. Please review and approve."
            )
            
            metadata = {
                'restriction_external_id': str(restriction.external_id),
                'client_external_id': str(restriction.client.external_id),
                'client_name': client_name,
                'action': action,
                'created_by': user_name,
                'restriction_detail_url': f"/core/restrictions/{restriction.external_id}/",
                'client_detail_url': f"/clients/{restriction.client.external_id}/",
            }
            
            # Check if notification already exists
            if Notification.objects.filter(
                staff=staff,
                category='restriction_approval',
                metadata__restriction_external_id=str(restriction.external_id),
                metadata__action=action
            ).exists():
                continue
            
            notifications_to_create.append(
                Notification(
                    staff=staff,
                    category='restriction_approval',
                    title=title,
                    message=message,
                    metadata=metadata,
                )
            )
            
            # Prepare email
            email_address = staff.email if hasattr(staff, 'email') else (staff_user.email if staff_user else None)
            if email_address:
                emails_to_send.append({
                    'email': email_address,
                    'staff': staff,
                    'title': title,
                    'message': message,
                    'restriction': restriction,
                    'client_name': client_name,
                    'user_name': user_name,
                })
        
        # Create notifications
        if notifications_to_create:
            Notification.objects.bulk_create(notifications_to_create)
        
        # Send emails
        for email_data in emails_to_send:
            try:
                from django.conf import settings
                restriction_url = f"{settings.FRONTEND_URL if hasattr(settings, 'FRONTEND_URL') else 'http://dev.fredvictor.org'}/core/restrictions/{restriction.external_id}/"
                
                email_body = f"""
{email_data['message']}

View restriction details: {restriction_url}

Client: {email_data['client_name']}
Scope: {restriction.scope or 'General'}
"""
                if restriction.program:
                    email_body += f"Program: {restriction.program.name}\n"
                if restriction.start_date:
                    email_body += f"Start Date: {restriction.start_date.strftime('%B %d, %Y')}\n"
                if restriction.end_date:
                    email_body += f"End Date: {restriction.end_date.strftime('%B %d, %Y')}\n"
                
                send_mail(
                    subject=email_data['title'],
                    message=email_body,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[email_data['email']],
                    fail_silently=False,
                )
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Failed to send approval email to {email_data['email']}: {str(e)}")
        
        return len(notifications_to_create)
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error notifying SuperAdmin for approval: {str(e)}")
        return 0


