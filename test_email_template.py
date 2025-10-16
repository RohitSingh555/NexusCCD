#!/usr/bin/env python3
"""
Test script to preview the email template format
"""

from django.template.loader import render_to_string
from datetime import date, datetime
import os
import sys
import django

# Add the project directory to Python path
sys.path.append('/home/agilemorph/Desktop/fredvictor/NexusCCD')

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ccd.settings')
django.setup()

# Mock client data for testing
class MockClient:
    def __init__(self, first_name, last_name, preferred_name=None):
        self.first_name = first_name
        self.last_name = last_name
        self.preferred_name = preferred_name

# Test data
clients = [
    MockClient("John", "Doe", "Johnny"),
    MockClient("Jane", "Smith"),
    MockClient("Bob", "Johnson", "Bobby")
]

# Template context
context = {
    'clients': clients,
    'start_date': date.today(),
    'end_date': date.today(),
    'client_count': len(clients),
    'report_date': datetime.now(),
}

# Render the template
html_content = render_to_string('emails/daily_client_report.html', context)

# Save to file for preview
with open('email_preview.html', 'w') as f:
    f.write(html_content)

print("✅ Email template rendered successfully!")
print("📄 Preview saved to: email_preview.html")
print(f"📊 Template shows {len(clients)} clients")
print("\n📧 Email Content Preview:")
print("=" * 50)
print(f"Subject: Daily Client Report - {date.today().strftime('%B %d, %Y')}")
print("=" * 50)
print("Here are the list of clients which are added", date.today().strftime('%B %d, %Y'), "for today.")
print(f"\nTotal new clients added: {len(clients)}")
print("\n📎 Attachment: A CSV file containing detailed information for all", len(clients), "clients created today is attached to this email.")
print("\nClient Names Added Today:")
for client in clients:
    name = f"{client.first_name} {client.last_name}"
    if client.preferred_name:
        name += f" ({client.preferred_name})"
    print(f"- {name}")
print("=" * 50)
