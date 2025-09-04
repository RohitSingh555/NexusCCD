from django.db import models
from core.models import Client, BaseModel


class ClientNote(BaseModel):
    client = models.ForeignKey(Client, on_delete=models.CASCADE, db_index=True)
    title = models.CharField(max_length=255)
    content = models.TextField()
    is_private = models.BooleanField(default=False, db_index=True)
    
    class Meta:
        db_table = 'client_notes'
        indexes = [
            models.Index(fields=['client', 'created_at']),
            models.Index(fields=['is_private']),
        ]
    
    def __str__(self):
        return f"{self.client} - {self.title}"


class ClientDocument(BaseModel):
    client = models.ForeignKey(Client, on_delete=models.CASCADE, db_index=True)
    title = models.CharField(max_length=255)
    file_url = models.URLField(max_length=500)
    file_type = models.CharField(max_length=50, db_index=True)
    file_size = models.PositiveIntegerField(null=True, blank=True)
    
    class Meta:
        db_table = 'client_documents'
        indexes = [
            models.Index(fields=['client', 'created_at']),
            models.Index(fields=['file_type']),
        ]
    
    def __str__(self):
        return f"{self.client} - {self.title}"


class ClientContact(BaseModel):
    CONTACT_TYPES = [
        ('emergency', 'Emergency'),
        ('family', 'Family'),
        ('friend', 'Friend'),
        ('professional', 'Professional'),
        ('other', 'Other'),
    ]
    
    client = models.ForeignKey(Client, on_delete=models.CASCADE, db_index=True)
    name = models.CharField(max_length=255)
    relationship = models.CharField(max_length=100)
    contact_type = models.CharField(max_length=20, choices=CONTACT_TYPES, db_index=True)
    phone_number = models.CharField(max_length=20, null=True, blank=True)
    email = models.EmailField(null=True, blank=True)
    address = models.JSONField(default=dict)
    is_primary = models.BooleanField(default=False, db_index=True)
    
    class Meta:
        db_table = 'client_contacts'
        indexes = [
            models.Index(fields=['client', 'contact_type']),
            models.Index(fields=['is_primary']),
        ]
    
    def __str__(self):
        return f"{self.client} - {self.name} ({self.relationship})"