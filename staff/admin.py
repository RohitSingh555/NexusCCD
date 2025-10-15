from django.contrib import admin
from .models import StaffSchedule, StaffNote, StaffPermission, StaffClientAssignment, StaffProgramAssignment


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


@admin.register(StaffClientAssignment)
class StaffClientAssignmentAdmin(admin.ModelAdmin):
    list_display = ['staff', 'client', 'assigned_by', 'is_active', 'assigned_at']
    search_fields = ['staff__first_name', 'staff__last_name', 'client__first_name', 'client__last_name', 'client__client_id']
    list_filter = ['is_active', 'assigned_at']
    readonly_fields = ['external_id', 'created_at', 'updated_at', 'assigned_at']


@admin.register(StaffProgramAssignment)
class StaffProgramAssignmentAdmin(admin.ModelAdmin):
    list_display = ['staff', 'program', 'assigned_by', 'is_active', 'assigned_at']
    search_fields = ['staff__first_name', 'staff__last_name', 'program__name', 'program__department__name']
    list_filter = ['is_active', 'assigned_at']
    readonly_fields = ['external_id', 'created_at', 'updated_at', 'assigned_at']