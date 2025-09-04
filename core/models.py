import uuid
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.contrib.auth.base_user import BaseUserManager


class CustomUserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('The Email field must be set')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        return self.create_user(email, password, **extra_fields)


class User(AbstractUser):
    external_id = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True)
    email = models.EmailField(unique=True, db_index=True)
    username = models.CharField(max_length=150, unique=True, db_index=True)
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username', 'first_name', 'last_name']
    
    objects = CustomUserManager()
    
    class Meta:
        db_table = 'users'
        indexes = [
            models.Index(fields=['email']),
            models.Index(fields=['username']),
            models.Index(fields=['is_active']),
        ]
    
    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.email})"


class BaseModel(models.Model):
    external_id = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        abstract = True


class Department(BaseModel):
    name = models.CharField(max_length=255, unique=True, db_index=True)
    owner = models.CharField(max_length=255, null=True, blank=True)
    
    class Meta:
        db_table = 'departments'
        constraints = [
            models.UniqueConstraint(
                fields=['name'],
                name='unique_lowercase_name',
                condition=models.Q(name__isnull=False)
            )
        ]
    
    def __str__(self):
        return self.name


class Role(BaseModel):
    name = models.CharField(max_length=100, unique=True, db_index=True)
    description = models.TextField(null=True, blank=True)
    permissions = models.JSONField(default=list)
    
    class Meta:
        db_table = 'roles'
    
    def __str__(self):
        return self.name


class Staff(BaseModel):
    user = models.OneToOneField('core.User', on_delete=models.CASCADE, related_name='staff_profile', null=True, blank=True)
    first_name = models.CharField(max_length=100, db_index=True, null=True, blank=True)
    last_name = models.CharField(max_length=100, db_index=True, null=True, blank=True)
    email = models.EmailField(unique=True, db_index=True, null=True, blank=True)
    active = models.BooleanField(default=True, db_index=True)
    
    class Meta:
        db_table = 'staff'
        constraints = [
            models.UniqueConstraint(
                fields=['email'],
                name='unique_staff_email',
                condition=models.Q(email__isnull=False)
            )
        ]
    
    def __str__(self):
        if self.user:
            return f"{self.user.first_name} {self.user.last_name}"
        return f"{self.first_name} {self.last_name}"


class StaffRole(BaseModel):
    staff = models.ForeignKey(Staff, on_delete=models.CASCADE, db_index=True)
    role = models.ForeignKey(Role, on_delete=models.CASCADE, db_index=True)
    
    class Meta:
        db_table = 'staff_roles'
        unique_together = ['staff', 'role']
    
    def __str__(self):
        return f"{self.staff} - {self.role}"


class Program(BaseModel):
    name = models.CharField(max_length=255, db_index=True)
    department = models.ForeignKey(Department, on_delete=models.CASCADE, db_index=True)
    location = models.CharField(max_length=255, db_index=True)
    capacity_current = models.PositiveIntegerField(default=0)
    capacity_effective_date = models.DateField(null=True, blank=True)
    
    class Meta:
        db_table = 'programs'
    
    def __str__(self):
        return f"{self.name} - {self.department.name}"


class ProgramStaff(BaseModel):
    program = models.ForeignKey(Program, on_delete=models.CASCADE, db_index=True)
    staff = models.ForeignKey(Staff, on_delete=models.CASCADE, db_index=True)
    is_manager = models.BooleanField(default=False, db_index=True)
    
    class Meta:
        db_table = 'program_staff'
        unique_together = ['program', 'staff']
    
    def __str__(self):
        return f"{self.staff} - {self.program.name}"


class Client(BaseModel):
    first_name = models.CharField(max_length=100, db_index=True)
    last_name = models.CharField(max_length=100, db_index=True)
    preferred_name = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    alias = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    dob = models.DateField(db_index=True)
    gender = models.CharField(max_length=50, db_index=True)
    sexual_orientation = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    languages_spoken = models.JSONField(default=list)
    race = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    immigration_status = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    image = models.URLField(max_length=500, null=True, blank=True)
    phone_number = models.CharField(max_length=20, null=True, blank=True, db_index=True)
    email = models.EmailField(null=True, blank=True, db_index=True)
    address = models.JSONField(default=dict)
    uid_external = models.CharField(max_length=255, null=True, blank=True, unique=True, db_index=True)
    
    class Meta:
        db_table = 'clients'
        indexes = [
            models.Index(fields=['first_name', 'last_name', 'dob'], name='client_name_dob_idx'),
            models.Index(fields=['uid_external'], name='client_uid_external_idx'),
            models.Index(fields=['email'], name='client_email_idx'),
            models.Index(fields=['phone_number'], name='client_phone_idx'),
        ]
    
    def __str__(self):
        return f"{self.first_name} {self.last_name}"


class ClientProgramEnrollment(BaseModel):
    client = models.ForeignKey(Client, on_delete=models.CASCADE, db_index=True)
    program = models.ForeignKey(Program, on_delete=models.CASCADE, db_index=True)
    start_date = models.DateField(db_index=True)
    end_date = models.DateField(null=True, blank=True, db_index=True)
    
    class Meta:
        db_table = 'client_program_enrollments'
        constraints = [
            models.CheckConstraint(
                check=models.Q(end_date__gte=models.F('start_date')),
                name='end_date_after_start_date'
            )
        ]
    
    def __str__(self):
        return f"{self.client} - {self.program.name}"


class Intake(BaseModel):
    client = models.ForeignKey(Client, on_delete=models.CASCADE, db_index=True)
    program = models.ForeignKey(Program, on_delete=models.CASCADE, db_index=True)
    intake_date = models.DateField(db_index=True)
    source_system = models.CharField(max_length=100, db_index=True)
    
    class Meta:
        db_table = 'intakes'
    
    def __str__(self):
        return f"{self.client} - {self.program.name} - {self.intake_date}"


class Discharge(BaseModel):
    client = models.ForeignKey(Client, on_delete=models.CASCADE, db_index=True)
    program = models.ForeignKey(Program, on_delete=models.CASCADE, db_index=True)
    discharge_date = models.DateField(db_index=True)
    reason = models.TextField()
    
    class Meta:
        db_table = 'discharges'
    
    def __str__(self):
        return f"{self.client} - {self.program.name} - {self.discharge_date}"


class ServiceRestriction(BaseModel):
    SCOPE_CHOICES = [
        ('org', 'Organization'),
        ('program', 'Program'),
    ]
    
    client = models.ForeignKey(Client, on_delete=models.CASCADE, db_index=True)
    scope = models.CharField(max_length=10, choices=SCOPE_CHOICES, db_index=True)
    program = models.ForeignKey(Program, on_delete=models.CASCADE, null=True, blank=True, db_index=True)
    start_date = models.DateField(db_index=True)
    end_date = models.DateField(null=True, blank=True, db_index=True)
    reason = models.TextField()
    
    class Meta:
        db_table = 'service_restrictions'
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(scope='org', program__isnull=True) |
                    models.Q(scope='program', program__isnull=False)
                ),
                name='valid_scope_program_combination'
            )
        ]
    
    def __str__(self):
        return f"{self.client} - {self.get_scope_display()}"


class AuditLog(BaseModel):
    ACTION_CHOICES = [
        ('create', 'Create'),
        ('update', 'Update'),
        ('delete', 'Delete'),
        ('import', 'Import'),
    ]
    
    entity = models.CharField(max_length=100, db_index=True)
    entity_id = models.UUIDField(db_index=True)
    action = models.CharField(max_length=20, choices=ACTION_CHOICES, db_index=True)
    changed_by = models.ForeignKey('core.Staff', on_delete=models.SET_NULL, null=True, blank=True, db_index=True)
    changed_at = models.DateTimeField(auto_now_add=True, db_index=True)
    diff_json = models.JSONField()
    
    class Meta:
        db_table = 'audit_logs'
    
    def __str__(self):
        return f"{self.entity} {self.action} - {self.changed_at}"


class PendingChange(BaseModel):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('declined', 'Declined'),
    ]
    
    entity = models.CharField(max_length=100, db_index=True)
    entity_id = models.UUIDField(db_index=True)
    diff_json = models.JSONField()
    requested_by = models.ForeignKey('core.Staff', on_delete=models.CASCADE, db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', db_index=True)
    reviewed_by = models.ForeignKey('core.Staff', on_delete=models.SET_NULL, null=True, blank=True, 
                                   related_name='reviewed_changes', db_index=True)
    reviewed_at = models.DateTimeField(null=True, blank=True, db_index=True)
    rationale = models.TextField(null=True, blank=True)
    
    class Meta:
        db_table = 'pending_changes'
    
    def __str__(self):
        return f"{self.entity} change - {self.status}"