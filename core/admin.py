from django.contrib import admin
from .models import (
    Department, Role, Staff, StaffRole, Program, SubProgram, ProgramStaff,
    Client, ClientProgramEnrollment, Intake, Discharge, ServiceRestriction,
    AuditLog
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


@admin.register(SubProgram)
class SubProgramAdmin(admin.ModelAdmin):
    list_display = ['name', 'program', 'is_active', 'created_at']
    search_fields = ['name', 'program__name']
    list_filter = ['program', 'is_active', 'created_at']
    readonly_fields = ['external_id', 'created_at', 'updated_at']


@admin.register(ProgramStaff)
class ProgramStaffAdmin(admin.ModelAdmin):
    list_display = ['program', 'staff', 'is_manager', 'created_at']
    search_fields = ['program__name', 'staff__first_name', 'staff__last_name']
    list_filter = ['is_manager', 'created_at']
    readonly_fields = ['external_id', 'created_at', 'updated_at']


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ['client_id', 'first_name', 'last_name', 'preferred_name', 'dob', 'age', 'gender', 'program_status', 'created_at']
    search_fields = [
        'client_id', 'first_name', 'last_name', 'middle_name', 'preferred_name', 'alias', 
        'chart_number', 'health_card_number', 'phone', 'email', 'city', 'province', 
        'program', 'referral_source'
    ]
    list_filter = [
        'gender', 'gender_identity', 'citizenship_status', 'indigenous_status', 'aboriginal_status',
        'lgbtq_status', 'marital_status', 'program_status', 'client_type', 'level_of_support',
        'receiving_services', 'permission_to_phone', 'permission_to_email', 'children_home',
        'language_interpreter_required', 'province', 'city', 'lhin', 'created_at'
    ]
    readonly_fields = ['external_id', 'created_at', 'updated_at', 'age', 'calculated_age']
    fieldsets = (
        ('🧍 Client Personal Details', {
            'fields': (
                'client_id', 'last_name', 'first_name', 'middle_name', 'preferred_name', 'alias',
                'dob', 'age', 'calculated_age', 'gender', 'gender_identity', 'pronoun', 'marital_status',
                'citizenship_status', 'location_county', 'province', 'city', 'postal_code',
                'address', 'address_2'
            )
        }),
        ('🌍 Cultural & Demographic Info', {
            'fields': (
                'language', 'preferred_language', 'mother_tongue', 'official_language',
                'language_interpreter_required', 'self_identification_race_ethnicity', 'ethnicity',
                'aboriginal_status', 'lgbtq_status', 'highest_level_education', 'children_home',
                'children_number', 'lhin'
            )
        }),
        ('💊 Medical & Health Information', {
            'fields': (
                'medical_conditions', 'primary_diagnosis', 'family_doctor', 'health_card_number',
                'health_card_version', 'health_card_exp_date', 'health_card_issuing_province',
                'no_health_card_reason'
            )
        }),
        ('👥 Contact & Permissions', {
            'fields': (
                'permission_to_phone', 'permission_to_email', 'phone', 'phone_work', 'phone_alt',
                'email', 'next_of_kin', 'emergency_contact', 'comments'
            )
        }),
        ('🧑‍💼 Program / Enrollment Details', {
            'fields': (
                'program', 'sub_program', 'support_workers', 'level_of_support', 'client_type',
                'admission_date', 'discharge_date', 'days_elapsed', 'program_status',
                'reason_discharge', 'receiving_services', 'referral_source'
            )
        }),
        ('🧾 Administrative / System Fields', {
            'fields': ('chart_number',)
        }),
        ('📸 Images & Media', {
            'fields': ('image', 'profile_picture')
        }),
        ('🔧 Legacy Fields', {
            'fields': (
                'contact_information', 'addresses', 'languages_spoken', 'indigenous_status',
                'country_of_birth', 'sexual_orientation'
            ),
            'classes': ('collapse',)
        }),
        ('📊 System Information', {
            'fields': ('uid_external', 'external_id', 'created_at', 'updated_at', 'updated_by'),
            'classes': ('collapse',)
        })
    )


@admin.register(ClientProgramEnrollment)
class ClientProgramEnrollmentAdmin(admin.ModelAdmin):
    list_display = ['client', 'program', 'start_date', 'end_date', 'status', 'created_at']
    search_fields = ['client__first_name', 'client__last_name', 'program__name']
    list_filter = ['start_date', 'end_date', 'status', 'created_at']
    readonly_fields = ['external_id', 'created_at', 'updated_at']


@admin.register(Intake)
class IntakeAdmin(admin.ModelAdmin):
    list_display = ['client', 'program', 'intake_date', 'referral_source', 'intake_housing_status', 'created_at']
    search_fields = ['client__first_name', 'client__last_name', 'program__name', 'intake_database']
    list_filter = ['intake_date', 'referral_source', 'intake_housing_status', 'created_at']
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

