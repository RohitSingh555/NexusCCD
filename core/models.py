import uuid
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.contrib.auth.base_user import BaseUserManager
from django.utils import timezone


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
    profile_photo = models.ImageField(upload_to='profile_photos/', null=True, blank=True)
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

    def save(self, *args, **kwargs):
        # Ensure external_id is always set
        if not self.external_id:
            self.external_id = uuid.uuid4()
        super().save(*args, **kwargs)
    
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
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('suggested', 'Suggested'),
    ]
    
    name = models.CharField(max_length=255, db_index=True)
    department = models.ForeignKey(Department, on_delete=models.CASCADE, db_index=True)
    location = models.CharField(max_length=255, db_index=True)
    capacity_current = models.PositiveIntegerField(default=0)
    capacity_effective_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active', db_index=True)
    description = models.TextField(null=True, blank=True)
    
    class Meta:
        db_table = 'programs'
    
    def __str__(self):
        return f"{self.name} - {self.department.name}"
    
    def get_current_enrollments_count(self, as_of_date=None):
        """Get the current number of active enrollments for this program"""
        if as_of_date is None:
            as_of_date = timezone.now().date()
        
        return ClientProgramEnrollment.objects.filter(
            program=self,
            start_date__lte=as_of_date
        ).filter(
            models.Q(end_date__isnull=True) | models.Q(end_date__gt=as_of_date)
        ).count()
    
    def get_enrollments_count_for_date(self, enrollment_date):
        """Get the number of enrollments that will be active on a specific date"""
        return ClientProgramEnrollment.objects.filter(
            program=self,
            start_date__lte=enrollment_date
        ).filter(
            models.Q(end_date__isnull=True) | models.Q(end_date__gt=enrollment_date)
        ).count()
    
    def get_available_capacity(self, as_of_date=None):
        """Get the number of available spots in this program"""
        if self.capacity_current <= 0:
            return None  # No capacity limit
        
        if as_of_date:
            current_enrollments = self.get_enrollments_count_for_date(as_of_date)
        else:
            current_enrollments = self.get_current_enrollments_count()
        return max(0, self.capacity_current - current_enrollments)
    
    def is_at_capacity(self, as_of_date=None):
        """Check if the program is at or over capacity"""
        if self.capacity_current <= 0:
            return False  # No capacity limit
        
        if as_of_date:
            current_enrollments = self.get_enrollments_count_for_date(as_of_date)
        else:
            current_enrollments = self.get_current_enrollments_count()
        return current_enrollments >= self.capacity_current
    
    def get_capacity_percentage(self, as_of_date=None):
        """Get the capacity utilization percentage"""
        if self.capacity_current <= 0:
            return 0  # No capacity limit
        
        if as_of_date:
            current_enrollments = self.get_enrollments_count_for_date(as_of_date)
        else:
            current_enrollments = self.get_current_enrollments_count()
        return min(100, (current_enrollments / self.capacity_current) * 100)
    
    def can_enroll_client(self, client, start_date=None):
        """Check if a client can be enrolled in this program"""
        if start_date is None:
            start_date = timezone.now().date()
        
        # Check if program is at capacity for the specific date
        if self.is_at_capacity(start_date):
            enrollments_on_date = self.get_enrollments_count_for_date(start_date)
            return False, f"Program '{self.name}' is at full capacity on {start_date.strftime('%B %d, %Y')} ({enrollments_on_date}/{self.capacity_current} clients)."
        
        # Check if client is already enrolled in this program on the specific date
        existing_enrollment = ClientProgramEnrollment.objects.filter(
            client=client,
            program=self,
            start_date__lte=start_date
        ).filter(
            models.Q(end_date__isnull=True) | models.Q(end_date__gt=start_date)
        ).exists()
        
        if existing_enrollment:
            return False, f"Client is already enrolled in '{self.name}' program on {start_date.strftime('%B %d, %Y')}."
        
        return True, "Client can be enrolled."


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
    ethnicity = models.JSONField(default=list, help_text="List of ethnicities (multi-select)")
    citizenship_status = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    indigenous_status = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    country_of_birth = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    image = models.URLField(max_length=500, null=True, blank=True)
    profile_picture = models.ImageField(upload_to='client_photos/', null=True, blank=True)
    contact_information = models.JSONField(default=dict, help_text="Contact information with phone and email")
    addresses = models.JSONField(default=list, help_text="List of addresses with type, street, city, state, zip, country")
    uid_external = models.CharField(max_length=255, null=True, blank=True, unique=True, db_index=True)
    
    def save(self, *args, **kwargs):
        # Auto-generate external ID if not provided
        if not self.uid_external:
            self.uid_external = str(uuid.uuid4())
        super().save(*args, **kwargs)
    
    @property
    def email(self):
        """Get email from contact_information"""
        return self.contact_information.get('email', '') if self.contact_information else ''
    
    @property
    def phone(self):
        """Get phone from contact_information"""
        return self.contact_information.get('phone', '') if self.contact_information else ''

    @property
    def profile_image_url(self):
        """Get profile image URL, prioritizing uploaded file over URL"""
        if self.profile_picture:
            return self.profile_picture.url
        elif self.image:
            return self.image
        return None
    
    class Meta:
        db_table = 'clients'
        indexes = [
            models.Index(fields=['first_name', 'last_name', 'dob'], name='client_name_dob_idx'),
            models.Index(fields=['uid_external'], name='client_uid_external_idx'),
            models.Index(fields=['citizenship_status'], name='client_citizenship_status_idx'),
            models.Index(fields=['indigenous_status'], name='client_indigenous_status_idx'),
            models.Index(fields=['country_of_birth'], name='client_country_of_birth_idx'),
        ]
    
    def __str__(self):
        return f"{self.first_name} {self.last_name}"


class ClientProgramEnrollment(BaseModel):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
        ('suspended', 'Suspended'),
    ]
    
    client = models.ForeignKey(Client, on_delete=models.CASCADE, db_index=True)
    program = models.ForeignKey(Program, on_delete=models.CASCADE, db_index=True)
    start_date = models.DateField(db_index=True)
    end_date = models.DateField(null=True, blank=True, db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', db_index=True)
    notes = models.TextField(null=True, blank=True)
    
    class Meta:
        db_table = 'client_program_enrollments'
        constraints = [
            models.CheckConstraint(
                check=models.Q(end_date__gte=models.F('start_date')),
                name='end_date_after_start_date'
            )
        ]
    
    def __str__(self):
        return f"{self.client} - {self.program.name} ({self.status})"


class Intake(BaseModel):
    SOURCE_CHOICES = [
        ('SMIS', 'SMIS'),
        ('EMHWare', 'EMHWare'),
        ('FFAI', 'FFAI'),
    ]
    
    HOUSING_STATUS_CHOICES = [
        ('homeless', 'Homeless'),
        ('at_risk', 'At Risk of Homelessness'),
        ('stably_housed', 'Stably Housed'),
        ('unknown', 'Unknown'),
    ]
    
    client = models.ForeignKey(Client, on_delete=models.CASCADE, db_index=True)
    program = models.ForeignKey(Program, on_delete=models.CASCADE, db_index=True)
    department = models.ForeignKey(Department, on_delete=models.CASCADE, db_index=True, null=True, blank=True)
    intake_date = models.DateField(db_index=True)
    intake_database = models.CharField(max_length=100, db_index=True, default='CCD')
    referral_source = models.CharField(max_length=20, choices=SOURCE_CHOICES, db_index=True, default='SMIS')
    intake_housing_status = models.CharField(max_length=20, choices=HOUSING_STATUS_CHOICES, db_index=True, default='unknown')
    notes = models.TextField(null=True, blank=True)
    
    class Meta:
        db_table = 'intakes'
        indexes = [
            models.Index(fields=['intake_date'], name='intake_date_idx'),
            models.Index(fields=['referral_source'], name='intake_source_idx'),
            models.Index(fields=['intake_housing_status'], name='intake_housing_idx'),
        ]
    
    def __str__(self):
        return f"{self.client} - {self.program.name} ({self.intake_date})"


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


class ClientDuplicate(BaseModel):
    """Track potential duplicate clients for manual review"""
    
    STATUS_CHOICES = [
        ('pending', 'Pending Review'),
        ('confirmed_duplicate', 'Confirmed Duplicate'),
        ('not_duplicate', 'Not Duplicate'),
        ('merged', 'Merged'),
    ]
    
    CONFIDENCE_LEVELS = [
        ('high', 'High'),
        ('medium', 'Medium'),
        ('low', 'Low'),
        ('very_low', 'Very Low'),
    ]
    
    # The primary client (usually the one that was created first)
    primary_client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='primary_duplicates', db_index=True)
    # The potential duplicate client
    duplicate_client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='duplicate_of', db_index=True)
    # Similarity score (0-1)
    similarity_score = models.FloatField(db_index=True)
    # Type of match (similarity, nickname, etc.)
    match_type = models.CharField(max_length=50, db_index=True)
    # Confidence level based on similarity score
    confidence_level = models.CharField(max_length=20, choices=CONFIDENCE_LEVELS, db_index=True)
    # Status of the duplicate review
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='pending', db_index=True)
    # Additional details about the match
    match_details = models.JSONField(default=dict)
    # Who reviewed this duplicate
    reviewed_by = models.ForeignKey('core.Staff', on_delete=models.SET_NULL, null=True, blank=True, db_index=True)
    # When it was reviewed
    reviewed_at = models.DateTimeField(null=True, blank=True, db_index=True)
    # Notes from the reviewer
    review_notes = models.TextField(null=True, blank=True)
    
    class Meta:
        db_table = 'client_duplicates'
        unique_together = ['primary_client', 'duplicate_client']
        indexes = [
            models.Index(fields=['status', 'confidence_level']),
            models.Index(fields=['similarity_score']),
            models.Index(fields=['match_type']),
        ]
    
    def __str__(self):
        return f"{self.primary_client} <-> {self.duplicate_client} ({self.confidence_level})"
    
    def get_duplicate_group(self):
        """Get all clients in the same duplicate group"""
        # Find all duplicates that share either the primary or duplicate client
        related_duplicates = ClientDuplicate.objects.filter(
            models.Q(primary_client=self.primary_client) | 
            models.Q(duplicate_client=self.primary_client) |
            models.Q(primary_client=self.duplicate_client) | 
            models.Q(duplicate_client=self.duplicate_client)
        ).exclude(id=self.id)
        
        # Collect all unique clients in this group
        clients = {self.primary_client, self.duplicate_client}
        for dup in related_duplicates:
            clients.add(dup.primary_client)
            clients.add(dup.duplicate_client)
        
        return list(clients)
    
    def mark_as_duplicate(self, reviewed_by, notes=None):
        """Mark this as a confirmed duplicate"""
        self.status = 'confirmed_duplicate'
        self.reviewed_by = reviewed_by
        self.reviewed_at = timezone.now()
        self.review_notes = notes
        self.save()
    
    def mark_as_not_duplicate(self, reviewed_by, notes=None):
        """Mark this as not a duplicate"""
        self.status = 'not_duplicate'
        self.reviewed_by = reviewed_by
        self.reviewed_at = timezone.now()
        self.review_notes = notes
        self.save()
    
    def merge_clients(self, reviewed_by, notes=None):
        """Mark this as merged (duplicate client will be merged into primary)"""
        self.status = 'merged'
        self.reviewed_by = reviewed_by
        self.reviewed_at = timezone.now()
        self.review_notes = notes
        self.save()