from django.contrib import admin
from .models import ProgramCapacity, ProgramLocation, ProgramService


@admin.register(ProgramCapacity)
class ProgramCapacityAdmin(admin.ModelAdmin):
    list_display = ['program', 'effective_date', 'capacity', 'created_at']
    search_fields = ['program__name', 'notes']
    list_filter = ['effective_date', 'created_at']
    readonly_fields = ['external_id', 'created_at', 'updated_at']


@admin.register(ProgramLocation)
class ProgramLocationAdmin(admin.ModelAdmin):
    list_display = ['program', 'name', 'is_primary', 'created_at']
    search_fields = ['program__name', 'name']
    list_filter = ['is_primary', 'created_at']
    readonly_fields = ['external_id', 'created_at', 'updated_at']


@admin.register(ProgramService)
class ProgramServiceAdmin(admin.ModelAdmin):
    list_display = ['program', 'name', 'is_active', 'created_at']
    search_fields = ['program__name', 'name', 'description']
    list_filter = ['is_active', 'created_at']
    readonly_fields = ['external_id', 'created_at', 'updated_at']