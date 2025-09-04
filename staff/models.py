from django.db import models
from core.models import Staff, BaseModel


class StaffSchedule(BaseModel):
    staff = models.ForeignKey(Staff, on_delete=models.CASCADE, db_index=True)
    day_of_week = models.PositiveSmallIntegerField(db_index=True)  # 0=Monday, 6=Sunday
    start_time = models.TimeField()
    end_time = models.TimeField()
    is_active = models.BooleanField(default=True, db_index=True)
    
    class Meta:
        db_table = 'staff_schedules'
        indexes = [
            models.Index(fields=['staff', 'day_of_week']),
            models.Index(fields=['is_active']),
        ]
    
    def __str__(self):
        return f"{self.staff} - {self.get_day_display()}"


class StaffNote(BaseModel):
    staff = models.ForeignKey(Staff, on_delete=models.CASCADE, db_index=True)
    title = models.CharField(max_length=255)
    content = models.TextField()
    is_private = models.BooleanField(default=False, db_index=True)
    
    class Meta:
        db_table = 'staff_notes'
        indexes = [
            models.Index(fields=['staff', 'created_at']),
            models.Index(fields=['is_private']),
        ]
    
    def __str__(self):
        return f"{self.staff} - {self.title}"


class StaffPermission(BaseModel):
    staff = models.ForeignKey(Staff, on_delete=models.CASCADE, db_index=True)
    permission_name = models.CharField(max_length=255, db_index=True)
    is_granted = models.BooleanField(default=True, db_index=True)
    granted_by = models.ForeignKey(Staff, on_delete=models.SET_NULL, null=True, blank=True, 
                                  related_name='granted_permissions', db_index=True)
    granted_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True, db_index=True)
    
    class Meta:
        db_table = 'staff_permissions'
        unique_together = ['staff', 'permission_name']
        indexes = [
            models.Index(fields=['staff', 'permission_name']),
            models.Index(fields=['is_granted']),
            models.Index(fields=['expires_at']),
        ]
    
    def __str__(self):
        return f"{self.staff} - {self.permission_name}"