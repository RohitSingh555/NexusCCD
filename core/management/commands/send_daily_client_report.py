import csv
import io
from datetime import datetime, timedelta
from django.core.management.base import BaseCommand
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings
from django.utils import timezone
from core.models import Client, EmailRecipient, Department


class Command(BaseCommand):
    help = 'Send daily client report to configured email recipients'

    def add_arguments(self, parser):
        parser.add_argument(
            '--test',
            action='store_true',
            help='Send test email to first recipient only',
        )
        parser.add_argument(
            '--frequency',
            type=str,
            choices=['daily', 'weekly', 'monthly'],
            default='daily',
            help='Frequency of the report (daily, weekly, monthly)',
        )
        parser.add_argument(
            '--days',
            type=int,
            help='Number of days to look back for client data (overrides frequency)',
        )

    def handle(self, *args, **options):
        self.stdout.write('Starting client report generation...')
        
        # Calculate date range based on frequency or days
        end_date = timezone.now().date()
        
        if options['days']:
            # Use explicit days if provided
            start_date = end_date - timedelta(days=options['days'])
            frequency = 'custom'
        else:
            # Use frequency-based calculation
            frequency = options['frequency']
            days_map = {
                'daily': 1,
                'weekly': 7,
                'monthly': 30
            }
            days = days_map.get(frequency, 1)
            start_date = end_date - timedelta(days=days)
        
        self.stdout.write(f'Looking for newly created clients between {start_date} and {end_date} ({frequency})')
        
        # Get clients created in the specified period
        clients = Client.objects.filter(
            created_at__date__gte=start_date,
            created_at__date__lte=end_date
        ).select_related().order_by('-created_at')
        
        self.stdout.write(f'Found {clients.count()} newly created clients in the specified period')
        
        if not clients.exists():
            self.stdout.write('No newly created clients found for the specified period. Exiting.')
            return
        
        # Get active email recipients for this frequency
        if options['days']:
            # If using custom days, get all active recipients
            recipients = EmailRecipient.objects.filter(is_active=True)
        else:
            # Filter by frequency
            recipients = EmailRecipient.objects.filter(
                is_active=True,
                frequency=frequency
            )
        
        if not recipients.exists():
            self.stdout.write('No active email recipients found. Exiting.')
            return
        
        # If test mode, only send to first recipient
        if options['test']:
            recipients = recipients[:1]
            self.stdout.write(f'Test mode: Sending to {recipients[0].email} only')
        
        # Generate CSV data
        csv_data = self.generate_csv_data(clients)
        
        # Generate HTML email content
        html_content = self.generate_html_content(clients, start_date, end_date)
        
        # Send emails
        success_count = 0
        for recipient in recipients:
            if self.send_email(recipient, clients, csv_data, html_content, start_date, end_date):
                success_count += 1
        
        self.stdout.write(
            self.style.SUCCESS(f'Daily client report completed. {success_count}/{recipients.count()} emails sent successfully.')
        )

    def generate_csv_data(self, clients):
        """Generate CSV data for the clients"""
        output = io.StringIO()
        writer = csv.writer(output)
        
        # CSV headers
        headers = [
            'Client ID', 'First Name', 'Last Name', 'Preferred Name', 'Date of Birth', 'Age',
            'Gender', 'Phone', 'Email', 'Address', 'City', 'Province', 'Postal Code',
            'Program', 'Program Status', 'Admission Date', 'Discharge Date',
            'Health Card Number', 'Referral Source', 'Created At', 'Created By'
        ]
        writer.writerow(headers)
        
        # CSV data rows
        for client in clients:
            row = [
                client.client_id or '',
                client.first_name or '',
                client.last_name or '',
                client.preferred_name or '',
                client.dob.strftime('%Y-%m-%d') if client.dob else '',
                client.age or client.calculated_age or '',
                client.gender or '',
                client.phone or '',
                client.email or '',
                client.address or '',
                client.city or '',
                client.province or '',
                client.postal_code or '',
                client.program or '',
                client.program_status or '',
                client.admission_date.strftime('%Y-%m-%d') if client.admission_date else '',
                client.discharge_date.strftime('%Y-%m-%d') if client.discharge_date else '',
                client.health_card_number or '',
                client.referral_source or '',
                client.created_at.strftime('%Y-%m-%d %H:%M:%S') if client.created_at else '',
                client.updated_by or ''
            ]
            writer.writerow(row)
        
        return output.getvalue()

    def generate_html_content(self, clients, start_date, end_date):
        """Generate HTML content for the email"""
        context = {
            'clients': clients,
            'start_date': start_date,
            'end_date': end_date,
            'client_count': clients.count(),
            'report_date': timezone.now().date(),
        }
        
        return render_to_string('emails/daily_client_report.html', context)

    def send_email(self, recipient, clients, csv_data, html_content, start_date, end_date):
        """Send email to a specific recipient"""
        from core.models import EmailLog
        
        subject = f'Daily Client Report - {timezone.now().strftime("%B %d, %Y")}'
        csv_filename = f'new_clients_report_{start_date}_{end_date}.csv'
        
        # Create email message
        msg = EmailMultiAlternatives(
            subject=subject,
            body=f'Daily new client report for {start_date} to {end_date}. Please see attached CSV file.',
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[recipient.email]
        )
        
        # Attach HTML content
        msg.attach_alternative(html_content, "text/html")
        
        # Attach CSV file
        msg.attach(csv_filename, csv_data, 'text/csv')
        
        # Create email log entry
        email_log = EmailLog(
            email_type='daily_report',
            subject=subject,
            recipient_email=recipient.email,
            recipient_name=recipient.name,
            email_body=html_content,
            csv_attachment=csv_data,
            csv_filename=csv_filename,
            client_count=clients.count(),
            report_date=start_date,
            frequency=recipient.frequency,
            status='pending'
        )
        
        try:
            # Send email
            msg.send()
            email_log.status = 'sent'
            email_log.save()
            self.stdout.write(f'Email sent successfully to {recipient.email}')
            return True
        except Exception as e:
            email_log.status = 'failed'
            email_log.error_message = str(e)
            email_log.save()
            self.stdout.write(f'Error sending email to {recipient.email}: {str(e)}')
            return False
