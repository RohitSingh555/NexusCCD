from django.db import models
from core.models import BaseModel, Staff


class ReportTemplate(BaseModel):
    name = models.CharField(max_length=255, unique=True)
    description = models.TextField()
    report_type = models.CharField(max_length=50, db_index=True)
    query_sql = models.TextField()
    parameters = models.JSONField(default=dict)
    is_active = models.BooleanField(default=True, db_index=True)
    created_by = models.ForeignKey(Staff, on_delete=models.CASCADE, db_index=True)
    
    class Meta:
        db_table = 'report_templates'
        indexes = [
            models.Index(fields=['report_type']),
            models.Index(fields=['is_active']),
            models.Index(fields=['created_by']),
        ]
    
    def __str__(self):
        return self.name


class ReportExecution(BaseModel):
    template = models.ForeignKey(ReportTemplate, on_delete=models.CASCADE, db_index=True)
    executed_by = models.ForeignKey(Staff, on_delete=models.CASCADE, db_index=True)
    parameters_used = models.JSONField(default=dict)
    status = models.CharField(max_length=20, db_index=True)
    result_file_url = models.URLField(max_length=500, null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)
    execution_time = models.DurationField(null=True, blank=True)
    
    class Meta:
        db_table = 'report_executions'
        indexes = [
            models.Index(fields=['template', 'executed_by']),
            models.Index(fields=['status']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        return f"{self.template.name} - {self.executed_by} - {self.created_at}"