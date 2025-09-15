# Generated manually for data migration

from django.db import migrations


def migrate_contact_information(apps, schema_editor):
    """Migrate existing email and phone data to contact_information field"""
    Client = apps.get_model('core', 'Client')
    
    for client in Client.objects.all():
        # Initialize contact_information if it doesn't exist
        if not client.contact_information:
            client.contact_information = {}
        
        # Migrate email if it exists in the old field
        if hasattr(client, 'email') and client.email:
            client.contact_information['email'] = client.email
        
        # Migrate phone if it exists in the old field  
        if hasattr(client, 'phone_number') and client.phone_number:
            client.contact_information['phone'] = client.phone_number
        
        # Save the client with updated contact_information
        client.save(update_fields=['contact_information'])


def reverse_migrate_contact_information(apps, schema_editor):
    """Reverse migration - extract email and phone from contact_information"""
    Client = apps.get_model('core', 'Client')
    
    for client in Client.objects.all():
        if client.contact_information:
            # This is a reverse migration, so we don't actually restore the old fields
            # since they've been removed. This is just for completeness.
            pass


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0004_remove_client_client_email_idx_and_more'),
    ]

    operations = [
        migrations.RunPython(
            migrate_contact_information,
            reverse_migrate_contact_information,
        ),
    ]
