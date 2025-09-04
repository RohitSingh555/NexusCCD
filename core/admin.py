from django.contrib import admin
from .models import (
    Department, Role, Staff, StaffRole, Program, ProgramStaff,
    Client, ClientProgramEnrollment, Intake, Discharge, ServiceRestriction,
    AuditLog, PendingChange
)


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ['name', 'owner', 'created_at']
    search_fields = ['name', 'owner']
    list_filter = ['created_at']
    readonly_fields = ['external_id', 'created_at', 'updated_at']


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ['name', 'created_at']
    search_fields = ['name']
    readonly_fields = ['external_id', 'created_at', 'updated_at']


@admin.register(Staff)
class StaffAdmin(admin.ModelAdmin):
    list_display = ['user', 'created_at']
    search_fields = ['user__first_name', 'user__last_name', 'user__email']
    list_filter = ['created_at']
    readonly_fields = ['external_id', 'created_at', 'updated_at']


@admin.register(StaffRole)
class StaffRoleAdmin(admin.ModelAdmin):
    list_display = ['staff', 'role', 'created_at']
    search_fields = ['staff__first_name', 'staff__last_name', 'role__name']
    list_filter = ['role', 'created_at']
    readonly_fields = ['external_id', 'created_at', 'updated_at']


@admin.register(Program)
class ProgramAdmin(admin.ModelAdmin):
    list_display = ['name', 'department', 'location', 'capacity_current', 'created_at']
    search_fields = ['name', 'department__name', 'location']
    list_filter = ['department', 'created_at']
    readonly_fields = ['external_id', 'created_at', 'updated_at']


@admin.register(ProgramStaff)
class ProgramStaffAdmin(admin.ModelAdmin):
    list_display = ['program', 'staff', 'is_manager', 'created_at']
    search_fields = ['program__name', 'staff__first_name', 'staff__last_name']
    list_filter = ['is_manager', 'created_at']
    readonly_fields = ['external_id', 'created_at', 'updated_at']


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ['first_name', 'last_name', 'preferred_name', 'dob', 'gender', 'created_at']
    search_fields = ['first_name', 'last_name', 'preferred_name', 'alias', 'email', 'phone_number']
    list_filter = ['gender', 'race', 'immigration_status', 'created_at']
    readonly_fields = ['external_id', 'created_at', 'updated_at']
    fieldsets = (
        ('Basic Information', {
            'fields': ('first_name', 'last_name', 'preferred_name', 'alias', 'dob')
        }),
        ('Demographics', {
            'fields': ('gender', 'sexual_orientation', 'race', 'immigration_status', 'languages_spoken')
        }),
        ('Contact Information', {
            'fields': ('phone_number', 'email', 'address', 'image')
        }),
        ('System Information', {
            'fields': ('uid_external', 'external_id', 'created_at', 'updated_at')
        })
    )


@admin.register(ClientProgramEnrollment)
class ClientProgramEnrollmentAdmin(admin.ModelAdmin):
    list_display = ['client', 'program', 'start_date', 'end_date', 'created_at']
    search_fields = ['client__first_name', 'client__last_name', 'program__name']
    list_filter = ['start_date', 'end_date', 'created_at']
    readonly_fields = ['external_id', 'created_at', 'updated_at']


@admin.register(Intake)
class IntakeAdmin(admin.ModelAdmin):
    list_display = ['client', 'program', 'intake_date', 'source_system', 'created_at']
    search_fields = ['client__first_name', 'client__last_name', 'program__name', 'source_system']
    list_filter = ['intake_date', 'source_system', 'created_at']
    readonly_fields = ['external_id', 'created_at', 'updated_at']


@admin.register(Discharge)
class DischargeAdmin(admin.ModelAdmin):
    list_display = ['client', 'program', 'discharge_date', 'created_at']
    search_fields = ['client__first_name', 'client__last_name', 'program__name', 'reason']
    list_filter = ['discharge_date', 'created_at']
    readonly_fields = ['external_id', 'created_at', 'updated_at']


@admin.register(ServiceRestriction)
class ServiceRestrictionAdmin(admin.ModelAdmin):
    list_display = ['client', 'scope', 'program', 'start_date', 'end_date', 'created_at']
    search_fields = ['client__first_name', 'client__last_name', 'reason']
    list_filter = ['scope', 'start_date', 'end_date', 'created_at']
    readonly_fields = ['external_id', 'created_at', 'updated_at']


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ['entity', 'entity_id', 'action', 'changed_by', 'changed_at']
    search_fields = ['entity', 'changed_by__first_name', 'changed_by__last_name']
    list_filter = ['entity', 'action', 'changed_at']
    readonly_fields = ['external_id', 'created_at', 'updated_at', 'changed_at']
    date_hierarchy = 'changed_at'


@admin.register(PendingChange)
class PendingChangeAdmin(admin.ModelAdmin):
    list_display = ['entity', 'entity_id', 'requested_by', 'status', 'created_at']
    search_fields = ['entity', 'requested_by__first_name', 'requested_by__last_name']
    list_filter = ['entity', 'status', 'created_at']
    readonly_fields = ['external_id', 'created_at', 'updated_at']
    date_hierarchy = 'created_at'