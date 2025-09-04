from django.contrib import admin
from .models import ReportTemplate, ReportExecution


@admin.register(ReportTemplate)
class ReportTemplateAdmin(admin.ModelAdmin):
    list_display = ['name', 'report_type', 'is_active', 'created_by', 'created_at']
    search_fields = ['name', 'description']
    list_filter = ['report_type', 'is_active', 'created_at']
    readonly_fields = ['external_id', 'created_at', 'updated_at']


@admin.register(ReportExecution)
class ReportExecutionAdmin(admin.ModelAdmin):
    list_display = ['template', 'executed_by', 'status', 'created_at']
    search_fields = ['template__name', 'executed_by__first_name', 'executed_by__last_name']
    list_filter = ['status', 'created_at']
    readonly_fields = ['external_id', 'created_at', 'updated_at']
    date_hierarchy = 'created_at'