from django.contrib import admin
from .models import StaffSchedule, StaffNote, StaffPermission


@admin.register(StaffSchedule)
class StaffScheduleAdmin(admin.ModelAdmin):
    list_display = ['staff', 'day_of_week', 'start_time', 'end_time', 'is_active', 'created_at']
    search_fields = ['staff__first_name', 'staff__last_name']
    list_filter = ['day_of_week', 'is_active', 'created_at']
    readonly_fields = ['external_id', 'created_at', 'updated_at']


@admin.register(StaffNote)
class StaffNoteAdmin(admin.ModelAdmin):
    list_display = ['staff', 'title', 'is_private', 'created_at']
    search_fields = ['staff__first_name', 'staff__last_name', 'title', 'content']
    list_filter = ['is_private', 'created_at']
    readonly_fields = ['external_id', 'created_at', 'updated_at']


@admin.register(StaffPermission)
class StaffPermissionAdmin(admin.ModelAdmin):
    list_display = ['staff', 'permission_name', 'is_granted', 'granted_by', 'expires_at', 'granted_at']
    search_fields = ['staff__first_name', 'staff__last_name', 'permission_name']
    list_filter = ['is_granted', 'expires_at', 'granted_at']
    readonly_fields = ['external_id', 'created_at', 'updated_at', 'granted_at']