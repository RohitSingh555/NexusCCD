from django.core.management.base import BaseCommand
from core.models import Client


class Command(BaseCommand):
    help = 'Fix contact information for existing clients'

    def handle(self, *args, **options):
        clients = Client.objects.all()
        self.stdout.write(f'Found {clients.count()} clients')
        
        sample_contacts = [
            {'email': 'rohit.singh@email.com', 'phone': '(555) 123-4567'},
            {'email': 'hemo.globin@email.com', 'phone': '(555) 234-5678'},
            {'email': 'john.smith@email.com', 'phone': '(555) 345-6789'},
            {'email': 'maria.garcia@email.com', 'phone': '(555) 456-7890'},
            {'email': 'sarah.williams@email.com', 'phone': '(555) 567-8901'},
            {'email': 'david.johnson@email.com', 'phone': '(555) 678-9012'},
            {'email': 'lisa.davis@email.com', 'phone': '(555) 789-0123'},
            {'email': 'james.wilson@email.com', 'phone': '(555) 890-1234'},
            {'email': 'jennifer.martinez@email.com', 'phone': '(555) 901-2345'},
            {'email': 'robert.anderson@email.com', 'phone': '(555) 012-3456'},
        ]
        
        for i, client in enumerate(clients):
            if i < len(sample_contacts):
                client.contact_information = sample_contacts[i]
                client.save()
                self.stdout.write(f'Updated {client.first_name} {client.last_name}: {sample_contacts[i]}')
            else:
                # For additional clients, create generic contact info
                client.contact_information = {
                    'email': f'{client.first_name.lower()}.{client.last_name.lower()}@email.com',
                    'phone': f'(555) {100 + i:03d}-{2000 + i:04d}'
                }
                client.save()
                self.stdout.write(f'Updated {client.first_name} {client.last_name}: {client.contact_information}')
        
        self.stdout.write(self.style.SUCCESS('Contact information updated successfully!'))
        
        # Verify the data
        self.stdout.write('\nVerifying data:')
        for client in clients[:5]:
            self.stdout.write(f'{client.first_name} {client.last_name}: Email={client.email}, Phone={client.phone}')
