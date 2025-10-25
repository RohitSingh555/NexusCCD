#!/usr/bin/env python
"""
Script to delete all clients from the database.
Run this from the Django shell: python manage.py shell < delete_clients_script.py
"""

from django.db import transaction
from core.models import Client, ClientProgramEnrollment, Intake

# Count existing data
client_count = Client.objects.count()
enrollment_count = ClientProgramEnrollment.objects.count()
intake_count = Intake.objects.count()

print(f'Found {client_count} clients, {enrollment_count} enrollments, {intake_count} intakes')

if client_count == 0:
    print('No clients found to delete.')
    exit()

# Confirm deletion
confirm = input(f'\nAre you absolutely sure you want to delete ALL {client_count} clients? Type "DELETE ALL" to confirm: ')

if confirm != "DELETE ALL":
    print('Operation cancelled.')
    exit()

try:
    with transaction.atomic():
        print('Deleting client program enrollments...')
        ClientProgramEnrollment.objects.all().delete()
        
        print('Deleting intake records...')
        Intake.objects.all().delete()
        
        print('Deleting clients...')
        Client.objects.all().delete()
        
        print(f'Successfully deleted all clients and related data!')
        print(f'- {client_count} clients deleted')
        print(f'- {enrollment_count} enrollments deleted')
        print(f'- {intake_count} intakes deleted')
        
except Exception as e:
    print(f'Error deleting clients: {e}')
