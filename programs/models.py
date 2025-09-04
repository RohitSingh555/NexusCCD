from django.db import models
from core.models import Program, BaseModel


class ProgramCapacity(BaseModel):
    program = models.ForeignKey(Program, on_delete=models.CASCADE, db_index=True)
    effective_date = models.DateField(db_index=True)
    capacity = models.PositiveIntegerField()
    notes = models.TextField(null=True, blank=True)
    
    class Meta:
        db_table = 'program_capacities'
        unique_together = ['program', 'effective_date']
        indexes = [
            models.Index(fields=['program', 'effective_date']),
        ]
    
    def __str__(self):
        return f"{self.program.name} - {self.effective_date} - {self.capacity}"


class ProgramLocation(BaseModel):
    program = models.ForeignKey(Program, on_delete=models.CASCADE, db_index=True)
    name = models.CharField(max_length=255)
    address = models.JSONField(default=dict)
    is_primary = models.BooleanField(default=False, db_index=True)
    
    class Meta:
        db_table = 'program_locations'
        indexes = [
            models.Index(fields=['program', 'is_primary']),
        ]
    
    def __str__(self):
        return f"{self.program.name} - {self.name}"


class ProgramService(BaseModel):
    program = models.ForeignKey(Program, on_delete=models.CASCADE, db_index=True)
    name = models.CharField(max_length=255)
    description = models.TextField()
    is_active = models.BooleanField(default=True, db_index=True)
    
    class Meta:
        db_table = 'program_services'
        indexes = [
            models.Index(fields=['program', 'is_active']),
        ]
    
    def __str__(self):
        return f"{self.program.name} - {self.name}"