import pytest
import django
import os
import json

# Ensure Django is configured when running under plain pytest
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ccd.settings")
django.setup()

from core.models import Client, ClientDuplicate
from django.contrib.auth import get_user_model
from django.test import Client as DjangoTestClient


@pytest.mark.django_db
class TestClientMergeLegacyIds:
    """Test that merge functionality correctly saves legacy client IDs and secondary_source_id"""
    
    def test_merge_clients_saves_legacy_ids_from_different_sources(self):
        """Test that merging clients from different sources saves both IDs in legacy_client_ids"""
        # Create primary client from SMIS
        primary_client = Client.objects.create(
            first_name="John",
            last_name="Doe",
            client_id="SMIMS_123",
            source="SMIS"
        )
        
        # Create duplicate client from EMHware
        duplicate_client = Client.objects.create(
            first_name="John",
            last_name="Doe",
            client_id="EMH_456",
            source="EMHware"
        )
        
        # Create a duplicate relationship
        duplicate = ClientDuplicate.objects.create(
            primary_client=primary_client,
            duplicate_client=duplicate_client,
            similarity_score=0.95,
            match_type="name_dob_match",
            confidence_level="high",
            status="pending"
        )
        
        # Prepare merge data - select some fields from duplicate
        merge_data = {
            'selected_fields': {
                'email': {'source': 'duplicate'},
                'phone': {'source': 'primary'}
            },
            'notes': 'Test merge'
        }
        
        # Get a test client and make the merge request
        test_client = DjangoTestClient()
        User = get_user_model()
        # Create a superuser for testing
        user = User.objects.create_superuser(
            email='test@example.com',
            username='testuser',
            password='testpass123',
            first_name='Test',
            last_name='User'
        )
        test_client.force_login(user)
        
        # Make the merge request
        from django.urls import reverse
        url = reverse('clients:merge_clients', args=[duplicate.id])
        response = test_client.post(
            url,
            data=json.dumps(merge_data),
            content_type='application/json'
        )
        
        # Check response
        assert response.status_code == 200
        response_data = json.loads(response.content)
        assert response_data['success'] is True
        
        # Refresh primary client from database
        primary_client.refresh_from_db()
        
        # Verify legacy_client_ids contains both IDs
        assert len(primary_client.legacy_client_ids) == 2
        
        # Check that both sources are present
        sources = [entry['source'] for entry in primary_client.legacy_client_ids]
        assert 'SMIS' in sources
        assert 'EMHware' in sources
        
        # Check that both client IDs are present
        client_ids = [entry['client_id'] for entry in primary_client.legacy_client_ids]
        assert 'SMIMS_123' in client_ids
        assert 'EMH_456' in client_ids
        
        # Verify secondary_source_id is set to duplicate's client_id
        assert primary_client.secondary_source_id == 'EMH_456'
        
        # Verify duplicate client is deleted
        assert not Client.objects.filter(id=duplicate_client.id).exists()
        
        # Verify duplicate relationship is deleted
        assert not ClientDuplicate.objects.filter(id=duplicate.id).exists()
    
    def test_merge_clients_preserves_existing_legacy_ids(self):
        """Test that existing legacy IDs are preserved when merging"""
        # Create primary client with existing legacy IDs
        primary_client = Client.objects.create(
            first_name="Jane",
            last_name="Smith",
            client_id="SMIMS_789",
            source="SMIS",
            legacy_client_ids=[
                {'source': 'SMIS', 'client_id': 'SMIMS_789'},
                {'source': 'EMHware', 'client_id': 'EMH_OLD_999'}
            ]
        )
        
        # Create duplicate client from EMHware
        duplicate_client = Client.objects.create(
            first_name="Jane",
            last_name="Smith",
            client_id="EMH_NEW_888",
            source="EMHware"
        )
        
        # Create a duplicate relationship
        duplicate = ClientDuplicate.objects.create(
            primary_client=primary_client,
            duplicate_client=duplicate_client,
            similarity_score=0.92,
            match_type="name_dob_match",
            confidence_level="high",
            status="pending"
        )
        
        # Prepare merge data
        merge_data = {
            'selected_fields': {
                'email': {'source': 'primary'}
            },
            'notes': 'Test merge with existing legacy IDs'
        }
        
        # Get a test client and make the merge request
        test_client = DjangoTestClient()
        User = get_user_model()
        user = User.objects.create_superuser(
            email='test2@example.com',
            username='testuser2',
            password='testpass123',
            first_name='Test',
            last_name='User'
        )
        test_client.force_login(user)
        
        # Make the merge request
        from django.urls import reverse
        url = reverse('clients:merge_clients', args=[duplicate.id])
        response = test_client.post(
            url,
            data=json.dumps(merge_data),
            content_type='application/json'
        )
        
        # Check response
        assert response.status_code == 200
        
        # Refresh primary client from database
        primary_client.refresh_from_db()
        
        # Verify legacy_client_ids contains all three IDs (2 existing + 1 new)
        assert len(primary_client.legacy_client_ids) == 3
        
        # Check that all client IDs are present
        client_ids = [entry['client_id'] for entry in primary_client.legacy_client_ids]
        assert 'SMIMS_789' in client_ids
        assert 'EMH_OLD_999' in client_ids
        assert 'EMH_NEW_888' in client_ids
        
        # Verify secondary_source_id is set
        assert primary_client.secondary_source_id == 'EMH_NEW_888'
    
    def test_merge_clients_without_client_ids(self):
        """Test merge when clients don't have client_id or source"""
        # Create primary client without client_id
        primary_client = Client.objects.create(
            first_name="Bob",
            last_name="Johnson",
            source="SMIS"
            # No client_id
        )
        
        # Create duplicate client without source
        duplicate_client = Client.objects.create(
            first_name="Bob",
            last_name="Johnson",
            client_id="NO_SOURCE_123"
            # No source
        )
        
        # Create a duplicate relationship
        duplicate = ClientDuplicate.objects.create(
            primary_client=primary_client,
            duplicate_client=duplicate_client,
            similarity_score=0.90,
            match_type="name_dob_match",
            confidence_level="medium",
            status="pending"
        )
        
        # Prepare merge data
        merge_data = {
            'selected_fields': {
                'email': {'source': 'primary'}
            },
            'notes': 'Test merge without complete IDs'
        }
        
        # Get a test client and make the merge request
        test_client = DjangoTestClient()
        User = get_user_model()
        user = User.objects.create_superuser(
            email='test3@example.com',
            username='testuser3',
            password='testpass123',
            first_name='Test',
            last_name='User'
        )
        test_client.force_login(user)
        
        # Make the merge request
        from django.urls import reverse
        url = reverse('clients:merge_clients', args=[duplicate.id])
        response = test_client.post(
            url,
            data=json.dumps(merge_data),
            content_type='application/json'
        )
        
        # Check response
        assert response.status_code == 200
        
        # Refresh primary client from database
        primary_client.refresh_from_db()
        
        # Since primary has no client_id, legacy_client_ids should be empty or only have duplicate's if it had both
        # But duplicate has no source, so it won't be added either
        # So legacy_client_ids should remain empty or only have existing entries
        assert isinstance(primary_client.legacy_client_ids, list)
        
        # secondary_source_id should still be set if duplicate has client_id
        assert primary_client.secondary_source_id == 'NO_SOURCE_123'
    
    def test_merge_clients_same_source_prevents_duplicates(self):
        """Test that merging clients from same source doesn't create duplicate entries"""
        # Create primary client from SMIS
        primary_client = Client.objects.create(
            first_name="Alice",
            last_name="Williams",
            client_id="SMIMS_111",
            source="SMIS"
        )
        
        # Create duplicate client also from SMIS
        duplicate_client = Client.objects.create(
            first_name="Alice",
            last_name="Williams",
            client_id="SMIMS_222",
            source="SMIS"
        )
        
        # Create a duplicate relationship
        duplicate = ClientDuplicate.objects.create(
            primary_client=primary_client,
            duplicate_client=duplicate_client,
            similarity_score=0.88,
            match_type="name_dob_match",
            confidence_level="high",
            status="pending"
        )
        
        # Prepare merge data
        merge_data = {
            'selected_fields': {
                'email': {'source': 'duplicate'}
            },
            'notes': 'Test merge same source'
        }
        
        # Get a test client and make the merge request
        test_client = DjangoTestClient()
        User = get_user_model()
        user = User.objects.create_superuser(
            email='test4@example.com',
            username='testuser4',
            password='testpass123',
            first_name='Test',
            last_name='User'
        )
        test_client.force_login(user)
        
        # Make the merge request
        from django.urls import reverse
        url = reverse('clients:merge_clients', args=[duplicate.id])
        response = test_client.post(
            url,
            data=json.dumps(merge_data),
            content_type='application/json'
        )
        
        # Check response
        assert response.status_code == 200
        
        # Refresh primary client from database
        primary_client.refresh_from_db()
        
        # Verify both IDs are in legacy_client_ids
        assert len(primary_client.legacy_client_ids) == 2
        
        # Check that both client IDs are present
        client_ids = [entry['client_id'] for entry in primary_client.legacy_client_ids]
        assert 'SMIMS_111' in client_ids
        assert 'SMIMS_222' in client_ids
        
        # Verify secondary_source_id is set
        assert primary_client.secondary_source_id == 'SMIMS_222'

