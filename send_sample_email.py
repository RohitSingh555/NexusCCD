#!/usr/bin/env python3
"""
Standalone script to send a sample daily client report email
"""

import os
import sys
import django
from datetime import date, datetime
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
import csv
import io

# Add the project directory to Python path
sys.path.append('/home/agilemorph/Desktop/fredvictor/NexusCCD')

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ccd.settings')
django.setup()

# Sample client data
sample_clients = [
    {
        'first_name': 'John',
        'last_name': 'Doe',
        'preferred_name': 'Johnny',
        'dob': date(1990, 5, 15),
        'gender': 'Male',
        'phone': '555-0101',
        'email': 'john.doe@example.com',
        'city': 'Toronto',
        'province': 'Ontario',
        'created_at': datetime.now()
    },
    {
        'first_name': 'Jane',
        'last_name': 'Smith',
        'preferred_name': None,
        'dob': date(1985, 8, 22),
        'gender': 'Female',
        'phone': '555-0102',
        'email': 'jane.smith@example.com',
        'city': 'Vancouver',
        'province': 'British Columbia',
        'created_at': datetime.now()
    },
    {
        'first_name': 'Bob',
        'last_name': 'Johnson',
        'preferred_name': 'Bobby',
        'dob': date(1992, 3, 10),
        'gender': 'Male',
        'phone': '555-0103',
        'email': 'bob.johnson@example.com',
        'city': 'Montreal',
        'province': 'Quebec',
        'created_at': datetime.now()
    },
    {
        'first_name': 'Alice',
        'last_name': 'Brown',
        'preferred_name': None,
        'dob': date(1988, 12, 5),
        'gender': 'Female',
        'phone': '555-0104',
        'email': 'alice.brown@example.com',
        'city': 'Calgary',
        'province': 'Alberta',
        'created_at': datetime.now()
    },
    {
        'first_name': 'Charlie',
        'last_name': 'Wilson',
        'preferred_name': 'Chuck',
        'dob': date(1995, 7, 18),
        'gender': 'Male',
        'phone': '555-0105',
        'email': 'charlie.wilson@example.com',
        'city': 'Ottawa',
        'province': 'Ontario',
        'created_at': datetime.now()
    }
]

def generate_csv_data(clients):
    """Generate CSV data for the clients"""
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow([
        'First Name', 'Last Name', 'Preferred Name', 'Date of Birth', 
        'Gender', 'Phone', 'Email', 'City', 'Province', 'Created At'
    ])
    
    # Write client data
    for client in clients:
        writer.writerow([
            client['first_name'],
            client['last_name'],
            client['preferred_name'] or '',
            client['dob'].strftime('%Y-%m-%d'),
            client['gender'],
            client['phone'],
            client['email'],
            client['city'],
            client['province'],
            client['created_at'].strftime('%Y-%m-%d %H:%M:%S')
        ])
    
    return output.getvalue()

def send_sample_email():
    """Send a sample daily client report email"""
    
    # Email details
    recipient_email = 'rushikesh.wadekar@theagilemorph.com'
    today = date.today()
    now = datetime.now()
    
    # Generate CSV data
    csv_data = generate_csv_data(sample_clients)
    
    # Template context
    context = {
        'clients': sample_clients,
        'start_date': today,
        'end_date': today,
        'client_count': len(sample_clients),
        'report_date': now,
    }
    
    # Generate HTML content
    html_content = render_to_string('emails/daily_client_report.html', context)
    
    # Create email subject
    subject = f'Daily Client Report - {today.strftime("%B %d, %Y")}'
    
    # Create email message
    msg = EmailMultiAlternatives(
        subject=subject,
        body=f'Daily client report for {today.strftime("%B %d, %Y")}. Please see attached CSV file.',
        from_email='agilemorphsolutions@gmail.com',
        to=[recipient_email]
    )
    
    # Attach HTML content
    msg.attach_alternative(html_content, "text/html")
    
    # Attach CSV file
    csv_filename = f'daily_client_report_{today.strftime("%Y%m%d")}.csv'
    msg.attach(csv_filename, csv_data, 'text/csv')
    
    # Send email
    try:
        result = msg.send()
        print(f'✅ Sample email sent successfully to {recipient_email}!')
        print(f'📧 Subject: {subject}')
        print(f'📊 Clients included: {len(sample_clients)}')
        print(f'📎 CSV attachment: {csv_filename}')
        print(f'📅 Report date: {today.strftime("%B %d, %Y")}')
        return True
    except Exception as e:
        print(f'❌ Error sending email: {str(e)}')
        return False

if __name__ == '__main__':
    print('🚀 Sending sample daily client report email...')
    print('=' * 60)
    
    success = send_sample_email()
    
    if success:
        print('=' * 60)
        print('✅ Sample email sent successfully!')
        print('📧 Check your inbox at: rushikesh.wadekar@theagilemorph.com')
        print('📋 Email includes:')
        print('   - Simple format as requested')
        print('   - List of 5 sample clients')
        print('   - CSV attachment with detailed data')
        print('   - Professional HTML formatting')
    else:
        print('=' * 60)
        print('❌ Failed to send sample email')
        print('🔧 Please check Gmail SMTP configuration')
