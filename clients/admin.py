from django.contrib import admin
from .models import ClientNote, ClientDocument, ClientContact


@admin.register(ClientNote)
class ClientNoteAdmin(admin.ModelAdmin):
    list_display = ['client', 'title', 'is_private', 'created_at']
    search_fields = ['client__first_name', 'client__last_name', 'title', 'content']
    list_filter = ['is_private', 'created_at']
    readonly_fields = ['external_id', 'created_at', 'updated_at']


@admin.register(ClientDocument)
class ClientDocumentAdmin(admin.ModelAdmin):
    list_display = ['client', 'title', 'file_type', 'file_size', 'created_at']
    search_fields = ['client__first_name', 'client__last_name', 'title']
    list_filter = ['file_type', 'created_at']
    readonly_fields = ['external_id', 'created_at', 'updated_at']


@admin.register(ClientContact)
class ClientContactAdmin(admin.ModelAdmin):
    list_display = ['client', 'name', 'relationship', 'contact_type', 'is_primary', 'created_at']
    search_fields = ['client__first_name', 'client__last_name', 'name', 'relationship']
    list_filter = ['contact_type', 'is_primary', 'created_at']
    readonly_fields = ['external_id', 'created_at', 'updated_at']