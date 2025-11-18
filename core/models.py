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
    owner = models.ForeignKey('Staff', on_delete=models.SET_NULL, null=True, blank=True, related_name='owned_departments', help_text="Department leader/owner")
    is_archived = models.BooleanField(default=False, db_index=True, help_text="Whether this department is archived")
    archived_at = models.DateTimeField(null=True, blank=True, db_index=True, help_text="Timestamp when this department was archived")
    
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

    def is_program_manager(self):
        """Check if staff has manager role"""
        return self.staffrole_set.filter(role__name='Manager').exists()
    
    def is_staff_only(self):
        """Check if staff has only Staff role (not Manager or other roles)"""
        staff_roles = self.staffrole_set.select_related('role').all()
        role_names = [staff_role.role.name for staff_role in staff_roles]
        return 'Staff' in role_names and not any(role in ['SuperAdmin', 'Manager', 'Leader'] for role in role_names)
    
    def is_leader(self):
        """Check if staff has Leader role"""
        return self.staffrole_set.filter(role__name='Leader').exists()
    
    def get_assigned_departments(self):
        """Get all departments assigned to this leader"""
        if not self.is_leader():
            return Department.objects.none()
        # Use the related_name to get assignments, then get departments
        assignments = self.department_leader_assignments.filter(is_active=True)
        department_ids = list(assignments.values_list('department_id', flat=True))
        if not department_ids:
            return Department.objects.none()
        return Department.objects.filter(id__in=department_ids)
    
    def get_assigned_programs_via_departments(self):
        """Get all programs in assigned departments for leaders"""
        if not self.is_leader():
            return Program.objects.none()
        assigned_departments = self.get_assigned_departments()
        return Program.objects.filter(
            department__in=assigned_departments
        ).distinct()
    
    def get_assigned_programs(self):
        """Get all programs assigned to this program manager"""
        if not self.is_program_manager():
            return Program.objects.none()
        return Program.objects.filter(
            manager_assignments__staff=self,
            manager_assignments__is_active=True
        ).distinct()

    def get_assigned_services(self):
        """Get all services assigned to this program manager"""
        if not self.is_program_manager():
            from programs.models import ProgramService
            return ProgramService.objects.none()
        from programs.models import ProgramService
        return ProgramService.objects.filter(
            manager_assignments__staff=self,
            manager_assignments__is_active=True
        ).distinct()
    
    def get_assigned_departments(self):
        """Get all departments for assigned programs"""
        if not self.is_program_manager():
            return Department.objects.none()
        return Department.objects.filter(
            program__manager_assignments__staff=self,
            program__manager_assignments__is_active=True
        ).distinct()
    
    def can_access_program(self, program):
        """Check if program manager can access a specific program"""
        if not self.is_program_manager():
            return False
        return self.program_manager_assignments.filter(
            program=program,
            is_active=True
        ).exists()
    
    def can_access_service(self, service):
        """Check if program manager can access a specific service"""
        if not self.is_program_manager():
            return False
        return self.service_manager_assignments.filter(
            program_service=service,
            is_active=True
        ).exists()
    
    def can_manage_enrollment(self, enrollment):
        """Check if program manager can manage a specific enrollment"""
        if not self.is_program_manager():
            return False
        return self.can_access_program(enrollment.program)


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
    capacity_current = models.PositiveIntegerField(default=100)
    no_capacity_limit = models.BooleanField(default=False, help_text="Program does not enforce a fixed capacity limit")
    capacity_effective_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active', db_index=True)
    description = models.TextField(null=True, blank=True)
    
    # Audit fields
    created_by = models.CharField(max_length=255, null=True, blank=True, help_text="Name of the person who created this record")
    updated_by = models.CharField(max_length=255, null=True, blank=True, help_text="Name of the person who last updated this record")
    is_archived = models.BooleanField(default=False, db_index=True, help_text="Whether this program is archived")
    archived_at = models.DateTimeField(null=True, blank=True, db_index=True, help_text="Timestamp when this program was archived")
    
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
    
    def get_total_enrollments_count(self):
        """Get the total number of enrollments for this program (including future enrollments)"""
        return ClientProgramEnrollment.objects.filter(
            program=self
        ).filter(
            models.Q(end_date__isnull=True) | models.Q(end_date__gt=timezone.now().date())
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
        if self.no_capacity_limit or self.capacity_current <= 0:
            return None  # No capacity limit
        
        if as_of_date:
            current_enrollments = self.get_enrollments_count_for_date(as_of_date)
        else:
            current_enrollments = self.get_current_enrollments_count()
        return max(0, self.capacity_current - current_enrollments)
    
    def is_at_capacity(self, as_of_date=None):
        """Check if the program is at or over capacity"""
        if self.no_capacity_limit or self.capacity_current <= 0:
            return False  # No capacity limit
        
        if as_of_date:
            current_enrollments = self.get_enrollments_count_for_date(as_of_date)
        else:
            current_enrollments = self.get_current_enrollments_count()
        return current_enrollments >= self.capacity_current
    
    def get_capacity_percentage(self, as_of_date=None):
        """Get the capacity utilization percentage"""
        if self.no_capacity_limit or self.capacity_current <= 0:
            return 0  # No capacity limit
        
        if as_of_date:
            current_enrollments = self.get_enrollments_count_for_date(as_of_date)
        else:
            current_enrollments = self.get_current_enrollments_count()
        return min(100, (current_enrollments / self.capacity_current) * 100)
    
    def can_enroll_client(self, client, start_date=None, exclude_instance=None):
        """Check if a client can be enrolled in this program"""
        if start_date is None:
            start_date = timezone.now().date()
        
        # Check for service restrictions first
        restriction_check = self.check_client_restrictions(client, start_date)
        if not restriction_check[0]:
            return restriction_check
        
        # Check if program is at capacity for the specific date
        if not self.no_capacity_limit and self.is_at_capacity(start_date):
            enrollments_on_date = self.get_enrollments_count_for_date(start_date)
            return False, f"Program '{self.name}' is at full capacity on {start_date.strftime('%B %d, %Y')} ({enrollments_on_date}/{self.capacity_current} clients)."
        
        # Check if client is already enrolled in this program on the specific date
        existing_enrollments = ClientProgramEnrollment.objects.filter(
            client=client,
            program=self,
            start_date__lte=start_date
        ).filter(
            models.Q(end_date__isnull=True) | models.Q(end_date__gt=start_date)
        )
        
        # Exclude the current instance if provided (for editing existing enrollments)
        if exclude_instance:
            existing_enrollments = existing_enrollments.exclude(pk=exclude_instance.pk)
        
        if existing_enrollments.exists():
            return False, f"Client is already enrolled in '{self.name}' program on {start_date.strftime('%B %d, %Y')}."
        
        return True, "Client can be enrolled."
    
    def check_client_restrictions(self, client, start_date):
        """Check if client has service restrictions that would prevent enrollment in this program"""
        from .models import ServiceRestriction
        
        # Check for active restrictions that are not archived
        active_restrictions = ServiceRestriction.objects.filter(
            client=client,
            is_archived=False,  # Only check non-archived restrictions
            start_date__lte=start_date
        ).filter(
            models.Q(end_date__isnull=True) | models.Q(end_date__gte=start_date)
        )
        
        # Check for global restrictions (scope='org') - these block ALL programs
        global_restrictions = active_restrictions.filter(scope='org')
        if global_restrictions.exists():
            restriction = global_restrictions.first()
            end_date_text = restriction.end_date.strftime('%B %d, %Y') if restriction.end_date else 'indefinite'
            
            return False, (
                f"⚠️ ENROLLMENT BLOCKED - ACTIVE GLOBAL SERVICE RESTRICTION\n\n"
                f"Client: {client.first_name} {client.last_name}\n"
                f"Restriction Type: {restriction.get_restriction_type_display()}\n"
                f"Scope: ALL PROGRAMS (Global Restriction)\n"
                f"Period: {restriction.start_date.strftime('%B %d, %Y')} to {end_date_text}\n"
                f"Reason: {restriction.notes or 'No reason provided'}\n\n"
                f"ACTION REQUIRED: This client cannot be enrolled in ANY program due to a global restriction. Please remove or modify the restriction before enrolling this client."
            )
        
        # Check for program-specific restrictions (scope='program') - these only block the specific program
        program_restrictions = active_restrictions.filter(scope='program', program=self)
        if program_restrictions.exists():
            restriction = program_restrictions.first()
            end_date_text = restriction.end_date.strftime('%B %d, %Y') if restriction.end_date else 'indefinite'
            
            return False, (
                f"⚠️ ENROLLMENT BLOCKED - ACTIVE PROGRAM-SPECIFIC SERVICE RESTRICTION\n\n"
                f"Client: {client.first_name} {client.last_name}\n"
                f"Restriction Type: {restriction.get_restriction_type_display()}\n"
                f"Scope: '{self.name}' program only\n"
                f"Period: {restriction.start_date.strftime('%B %d, %Y')} to {end_date_text}\n"
                f"Reason: {restriction.notes or 'No reason provided'}\n\n"
                f"ACTION REQUIRED: This client cannot be enrolled in the '{self.name}' program due to a program-specific restriction. The client can still be enrolled in other programs."
            )
        
        return True, "No restrictions found."


class SubProgram(BaseModel):
    name = models.CharField(max_length=255, db_index=True)
    program = models.ForeignKey(Program, on_delete=models.CASCADE, related_name='subprograms', db_index=True)
    description = models.TextField(null=True, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    
    class Meta:
        db_table = 'subprograms'
        unique_together = ['name', 'program']
    
    def __str__(self):
        return f"{self.name} - {self.program.name}"


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
    # 🧍 CLIENT PERSONAL DETAILS
    client_id = models.CharField(max_length=100, null=True, blank=True, db_index=True, help_text="External client ID")
    last_name = models.CharField(max_length=100, db_index=True)
    first_name = models.CharField(max_length=100, db_index=True)
    middle_name = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    preferred_name = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    alias = models.CharField(max_length=100, null=True, blank=True, db_index=True, help_text="Last Name at Birth")
    dob = models.DateField(db_index=True, null=True, blank=True)
    age = models.IntegerField(null=True, blank=True, help_text="Calculated from DOB")
    gender = models.CharField(max_length=50, null=True, blank=True, db_index=True)
    gender_identity = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    pronoun = models.CharField(max_length=50, null=True, blank=True, db_index=True)
    marital_status = models.CharField(max_length=50, null=True, blank=True, db_index=True)
    citizenship_status = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    location_county = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    province = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    city = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    postal_code = models.CharField(max_length=20, null=True, blank=True, db_index=True)
    address = models.CharField(max_length=500, null=True, blank=True)
    address_2 = models.CharField(max_length=255, null=True, blank=True, help_text="Address line 2")
    
    # 🌍 CULTURAL & DEMOGRAPHIC INFO
    language = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    preferred_language = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    mother_tongue = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    official_language = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    language_interpreter_required = models.BooleanField(default=False, db_index=True)
    self_identification_race_ethnicity = models.CharField(max_length=200, null=True, blank=True, db_index=True)
    ethnicity = models.JSONField(default=list, help_text="List of ethnicities (multi-select)")
    aboriginal_status = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    lgbtq_status = models.CharField(max_length=100, null=True, blank=True, db_index=True, help_text="LGBTQ+ Status")
    veteran_status = models.CharField(max_length=100, null=True, blank=True, db_index=True, help_text="Veteran Status")
    legal_status = models.CharField(max_length=100, null=True, blank=True, db_index=True, help_text="Legal Status")
    highest_level_education = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    children_home = models.BooleanField(default=False, db_index=True)
    children_number = models.IntegerField(null=True, blank=True)
    lhin = models.CharField(max_length=100, null=True, blank=True, db_index=True, help_text="Local Health Integration Network")
    
    # 💊 MEDICAL & HEALTH INFORMATION
    medical_conditions = models.TextField(null=True, blank=True, help_text="Medical conditions")
    primary_diagnosis = models.CharField(max_length=255, null=True, blank=True, help_text="Primary diagnosis")
    family_doctor = models.CharField(max_length=255, null=True, blank=True)
    health_card_number = models.CharField(max_length=50, null=True, blank=True, db_index=True, help_text="HC# (Health Card Number)")
    health_card_version = models.CharField(max_length=10, null=True, blank=True, help_text="HC Version")
    health_card_exp_date = models.DateField(null=True, blank=True, help_text="HC Exp Date")
    health_card_issuing_province = models.CharField(max_length=100, null=True, blank=True, help_text="HC Issuing Province")
    no_health_card_reason = models.CharField(max_length=255, null=True, blank=True, help_text="No HC Reason")
    
    # 👥 CONTACT & PERMISSIONS
    permission_to_phone = models.BooleanField(default=False, db_index=True, help_text="Permission to contact by phone")
    permission_to_email = models.BooleanField(default=False, db_index=True, help_text="Permission to contact by email")
    preferred_communication_method = models.CharField(max_length=50, null=True, blank=True, db_index=True, help_text="Preferred Method of Communication")
    phone = models.CharField(max_length=20, null=True, blank=True, db_index=True)
    phone_work = models.CharField(max_length=20, null=True, blank=True, help_text="Work phone number")
    phone_alt = models.CharField(max_length=20, null=True, blank=True, help_text="Alternative phone number")
    email = models.EmailField(max_length=254, null=True, blank=True, db_index=True)
    next_of_kin = models.JSONField(default=dict, help_text="Next of kin contact information")
    emergency_contact = models.JSONField(default=dict, help_text="Emergency contact information")
    comments = models.TextField(null=True, blank=True, help_text="Additional comments and notes")
    
    # 🧑‍💼 PROGRAM / ENROLLMENT DETAILS
    program = models.CharField(max_length=255, null=True, blank=True, db_index=True)
    sub_program = models.CharField(max_length=255, null=True, blank=True, db_index=True)
    support_workers = models.JSONField(default=list, help_text="List of assigned support workers")
    level_of_support = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    client_type = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    admission_date = models.DateField(null=True, blank=True, db_index=True)
    discharge_date = models.DateField(null=True, blank=True, db_index=True)
    days_elapsed = models.IntegerField(null=True, blank=True)
    program_status = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    reason_discharge = models.CharField(max_length=255, null=True, blank=True, help_text="Reason for Discharge/Program Status")
    receiving_services = models.BooleanField(default=False, db_index=True)
    receiving_services_date = models.DateField(null=True, blank=True, db_index=True, help_text="Date when client actually started receiving services")
    referral_source = models.CharField(max_length=255, null=True, blank=True, db_index=True)
    
    # 🧾 ADMINISTRATIVE / SYSTEM FIELDS
    chart_number = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    source = models.CharField(max_length=50, choices=[('SMIS', 'SMIS'), ('EMHware', 'EMHware')], null=True, blank=True, db_index=True, help_text="Source system where client data originated")
    legacy_client_ids = models.JSONField(default=list, help_text="List of legacy client IDs from different sources (e.g., [{'source': 'SMIS', 'client_id': '123'}, {'source': 'EMHware', 'client_id': '456'}])")
    secondary_source_id = models.CharField(max_length=100, null=True, blank=True, db_index=True, help_text="Client ID of the duplicate client that was merged into this client")
    emhware_id = models.CharField(max_length=100, null=True, blank=True, db_index=True, help_text="Client ID from EMHware system")
    smis_id = models.CharField(max_length=100, null=True, blank=True, db_index=True, help_text="Client ID from SMIS system")
    is_archived = models.BooleanField(default=False, db_index=True, help_text="Whether this client is archived")
    archived_at = models.DateTimeField(null=True, blank=True, db_index=True, help_text="Timestamp when this client was archived")
    is_inactive = models.BooleanField(default=False, db_index=True, help_text="Whether this client is inactive (has zero active enrollments)")
    
    # Legacy fields (keeping for backward compatibility)
    image = models.URLField(max_length=500, null=True, blank=True)
    profile_picture = models.ImageField(upload_to='client_photos/', null=True, blank=True)
    contact_information = models.JSONField(default=dict, help_text="Contact information with phone and email")
    addresses = models.JSONField(default=list, help_text="List of addresses with type, street, city, state, zip, country")
    uid_external = models.CharField(max_length=255, null=True, blank=True, unique=True, db_index=True)
    languages_spoken = models.JSONField(default=list)
    indigenous_status = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    country_of_birth = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    sexual_orientation = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    
    # Audit fields
    created_by = models.CharField(max_length=255, null=True, blank=True, help_text="Name of the person who created this record")
    updated_by = models.CharField(max_length=255, null=True, blank=True, help_text="Name of the person who last updated this record")
    
    def save(self, *args, **kwargs):
        # Auto-generate external ID if not provided
        if not self.uid_external:
            self.uid_external = str(uuid.uuid4())
        
        # Calculate age from DOB
        if self.dob and not self.age:
            from datetime import date
            today = date.today()
            dob_date = self.dob
            self.age = today.year - dob_date.year - ((today.month, today.day) < (dob_date.month, dob_date.day))
        
        # Automatically set is_inactive=True when discharge_date is set
        if self.discharge_date and not self.is_inactive:
            self.is_inactive = True
        
        # Set updated_by if not already set
        if not self.updated_by:
            # Try to get the current user from the request if available
            from django.contrib.auth import get_user_model
            User = get_user_model()
            # This will be set by the view when saving
            pass
        
        super().save(*args, **kwargs)
    
    @property
    def email_legacy(self):
        """Get email from contact_information (legacy)"""
        return self.contact_information.get('email', '') if self.contact_information else ''
    
    @property
    def phone_legacy(self):
        """Get phone from contact_information (legacy)"""
        return self.contact_information.get('phone', '') if self.contact_information else ''

    @property
    def profile_image_url(self):
        """Get profile image URL, prioritizing uploaded file over URL"""
        # Check if profile_picture exists and file is accessible
        if self.profile_picture:
            try:
                # Verify the file exists before returning URL
                if self.profile_picture.storage.exists(self.profile_picture.name):
                    return self.profile_picture.url
                else:
                    # File doesn't exist, fall back to image URL if available
                    if self.image:
                        return self.image
                    return None
            except Exception:
                # If there's an error accessing the file, fall back to image URL
                if self.image:
                    return self.image
                return None
        elif self.image:
            return self.image
        return None
    
    @property
    def calculated_age(self):
        """Calculate age from DOB"""
        if self.dob:
            from datetime import date
            today = date.today()
            dob_date = self.dob
            return today.year - dob_date.year - ((today.month, today.day) < (dob_date.month, dob_date.day))
        return None
    
    def has_active_enrollments(self, as_of_date=None):
        """
        Check if client has any active enrollments.
        An enrollment is active if:
        - is_archived=False
        - start_date <= as_of_date (or today if not provided)
        - end_date is None OR end_date > as_of_date
        """
        from django.utils import timezone
        from django.db.models import Q
        
        if as_of_date is None:
            as_of_date = timezone.now().date()
        
        active_enrollments = self.clientprogramenrollment_set.filter(
            is_archived=False,
            start_date__lte=as_of_date
        ).filter(
            Q(end_date__isnull=True) | Q(end_date__gt=as_of_date)
        )
        
        return active_enrollments.exists()
    
    def update_inactive_status(self, as_of_date=None):
        """
        Update is_inactive status based on active enrollments.
        Client is inactive if they have zero active enrollments.
        Returns True if status was changed, False otherwise.
        """
        has_active = self.has_active_enrollments(as_of_date)
        was_inactive = self.is_inactive
        self.is_inactive = not has_active
        
        # Return True if status changed
        return was_inactive != self.is_inactive
    
    class Meta:
        db_table = 'clients'
        indexes = [
            models.Index(fields=['first_name', 'last_name', 'dob'], name='client_name_dob_idx'),
            models.Index(fields=['uid_external'], name='client_uid_external_idx'),
            models.Index(fields=['client_id'], name='client_id_idx'),
            models.Index(fields=['chart_number'], name='client_chart_number_idx'),
            models.Index(fields=['citizenship_status'], name='client_citizenship_status_idx'),
            models.Index(fields=['indigenous_status'], name='client_indigenous_status_idx'),
            models.Index(fields=['country_of_birth'], name='client_country_of_birth_idx'),
            models.Index(fields=['permission_to_phone'], name='client_permission_phone_idx'),
            models.Index(fields=['permission_to_email'], name='client_permission_email_idx'),
            models.Index(fields=['program'], name='client_program_idx'),
            models.Index(fields=['program_status'], name='client_program_status_idx'),
            models.Index(fields=['client_type'], name='client_type_idx'),
            models.Index(fields=['admission_date'], name='client_admission_date_idx'),
            models.Index(fields=['discharge_date'], name='client_discharge_date_idx'),
            models.Index(fields=['health_card_number'], name='client_health_card_idx'),
            models.Index(fields=['lhin'], name='client_lhin_idx'),
            models.Index(fields=['location_county'], name='client_location_county_idx'),
            models.Index(fields=['province'], name='client_province_idx'),
            models.Index(fields=['city'], name='client_city_idx'),
            models.Index(fields=['postal_code'], name='client_postal_code_idx'),
            models.Index(fields=['source'], name='client_source_idx'),
        ]
    
    def __str__(self):
        return f"{self.first_name} {self.last_name}"

class ClientExtended(BaseModel):
    client = models.OneToOneField('Client', on_delete=models.CASCADE, related_name='extended')

    # 🧍 Demographics / Core
    indigenous_identity = models.CharField(max_length=200, null=True, blank=True)
    military_status = models.CharField(max_length=200, null=True, blank=True)
    refugee_status = models.CharField(max_length=200, null=True, blank=True)
    household_size = models.IntegerField(null=True, blank=True)
    family_head_client_no = models.CharField(max_length=100, null=True, blank=True)
    relationship = models.CharField(max_length=100, null=True, blank=True)
    primary_worker = models.CharField(max_length=200, null=True, blank=True)
    chronically_homeless = models.BooleanField(default=False)
    num_bednights_current_stay = models.IntegerField(null=True, blank=True)
    length_homeless_3yrs = models.IntegerField(null=True, blank=True)
    income_source = models.CharField(max_length=200, null=True, blank=True)
    taxation_year_filed = models.CharField(max_length=20, null=True, blank=True)
    status_id = models.CharField(max_length=200, null=True, blank=True)
    picture_id = models.CharField(max_length=200, null=True, blank=True)
    other_id = models.CharField(max_length=200, null=True, blank=True)
    bnl_consent = models.BooleanField(default=False)

    # 🏥 Health & Supports
    allergies = models.TextField(null=True, blank=True)
    harm_reduction_support = models.BooleanField(default=False)
    medication_support = models.BooleanField(default=False)
    pregnancy_support = models.BooleanField(default=False)
    mental_health_support = models.BooleanField(default=False)
    physical_health_support = models.BooleanField(default=False)
    daily_activities_support = models.BooleanField(default=False)
    other_health_supports = models.TextField(null=True, blank=True)

    # ♿ Accessibility
    cannot_use_stairs = models.BooleanField(default=False)
    limited_mobility = models.BooleanField(default=False)
    wheelchair_accessibility = models.BooleanField(default=False)
    vision_hearing_speech_supports = models.TextField(null=True, blank=True)
    english_translator = models.BooleanField(default=False)
    reading_supports = models.BooleanField(default=False)
    other_accessibility_supports = models.TextField(null=True, blank=True)

    # 🐾 Lifestyle & Legal
    pet_owner = models.BooleanField(default=False)
    legal_support = models.BooleanField(default=False)
    immigration_support = models.BooleanField(default=False)
    religious_cultural_supports = models.TextField(null=True, blank=True)
    safety_concerns = models.TextField(null=True, blank=True)
    intimate_partner_violence_support = models.BooleanField(default=False)
    human_trafficking_support = models.BooleanField(default=False)
    other_supports = models.TextField(null=True, blank=True)

    # 🏠 Housing / Intake / Discharge
    access_to_housing_application = models.CharField(max_length=255, null=True, blank=True)
    access_to_housing_no = models.CharField(max_length=100, null=True, blank=True)
    access_point_application = models.CharField(max_length=255, null=True, blank=True)
    access_point_no = models.CharField(max_length=100, null=True, blank=True)
    cars = models.CharField(max_length=255, null=True, blank=True)
    cars_no = models.CharField(max_length=100, null=True, blank=True)
    discharge_disposition = models.CharField(max_length=255, null=True, blank=True)
    intake_status = models.CharField(max_length=100, null=True, blank=True)
    lived_last_12_months = models.TextField(null=True, blank=True)
    reason_for_service = models.TextField(null=True, blank=True)
    intake_date = models.DateField(null=True, blank=True)
    service_end_date = models.DateField(null=True, blank=True)
    rejection_date = models.DateField(null=True, blank=True)
    rejection_reason = models.TextField(null=True, blank=True)
    room = models.CharField(max_length=50, null=True, blank=True)
    bed = models.CharField(max_length=50, null=True, blank=True)
    occupancy_status = models.CharField(max_length=100, null=True, blank=True)
    bed_nights_historical = models.IntegerField(null=True, blank=True)
    restriction_reason = models.TextField(null=True, blank=True)
    restriction_date = models.DateField(null=True, blank=True)
    restriction_duration_days = models.IntegerField(null=True, blank=True)
    restriction_status = models.CharField(max_length=100, null=True, blank=True)
    early_termination_by = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        db_table = 'client_extended'

    @property
    def days_elapsed(self):
        """Calculate days elapsed between intake date and service end date (or current date if ongoing)"""
        if not self.intake_date:
            return None
        
        from django.utils import timezone
        
        end_date = self.service_end_date or timezone.now().date()
        delta = end_date - self.intake_date
        return delta.days

    def __str__(self):
        return f"Extended Info for {self.client}"

class ClientProgramEnrollment(BaseModel):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
        ('suspended', 'Suspended'),
        ('archived', 'Archived'),
    ]
    
    client = models.ForeignKey(Client, on_delete=models.CASCADE, db_index=True)
    program = models.ForeignKey(Program, on_delete=models.CASCADE, db_index=True)
    sub_program = models.ForeignKey(SubProgram, on_delete=models.CASCADE, null=True, blank=True, db_index=True)
    start_date = models.DateField(db_index=True)
    end_date = models.DateField(null=True, blank=True, db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', db_index=True)
    notes = models.TextField(null=True, blank=True)
    
    # Additional enrollment details
    days_elapsed = models.IntegerField(blank=True, help_text='Number of days elapsed since enrollment start', null=True)
    receiving_services_date = models.DateField(blank=True, db_index=True, help_text='Date when client started receiving services', null=True)
    
    # Audit fields
    created_by = models.CharField(max_length=255, null=True, blank=True, help_text="Name of the person who created this record")
    updated_by = models.CharField(max_length=255, null=True, blank=True, help_text="Name of the person who last updated this record")
    is_archived = models.BooleanField(default=False, db_index=True, help_text="Whether this enrollment is archived")
    archived_at = models.DateTimeField(null=True, blank=True, db_index=True, help_text="Timestamp when this enrollment was archived")
    
    class Meta:
        db_table = 'client_program_enrollments'
        ordering = ['-start_date', 'program__name']
        constraints = [
            models.CheckConstraint(
                check=models.Q(end_date__gte=models.F('start_date')),
                name='end_date_after_start_date'
            )
        ]
    
    def __str__(self):
        return f"{self.client} - {self.program.name} ({self.status})"
    
    def calculate_status(self, today=None):
        """Determine the current status based on dates and archival state."""
        if today is None:
            today = timezone.now().date()
        
        if self.is_archived:
            return 'archived'
        
        if self.status in ['cancelled', 'suspended']:
            return self.status
        
        if self.start_date and self.start_date > today:
            return 'pending'
        
        if self.end_date and self.end_date < today:
            return 'completed'
        
        return 'active'
    
    @property
    def calculated_status(self):
        annotated = getattr(self, 'computed_status', None)
        if annotated:
            return annotated
        return self.calculate_status()
    
    def get_calculated_status_display(self):
        mapping = {
            'pending': 'Pending',
            'active': 'Active',
            'completed': 'Completed',
            'cancelled': 'Cancelled',
            'suspended': 'Suspended',
            'archived': 'Archived',
        }
        status = self.calculated_status
        return mapping.get(status, status.title())
    
    @property
    def calculated_status_display(self):
        return self.get_calculated_status_display()

    def get_status_display(self):
        """Override Django's auto-generated display method to use calculated status."""
        return self.get_calculated_status_display()
    
    @property
    def discharge_reason(self):
        """Extract discharge reason from notes if present"""
        if not self.notes or not self.end_date:
            return None
        
        # Check if notes contain discharge information
        if "Discharge Date:" in self.notes and "Reason:" in self.notes:
            try:
                # Format: "Discharge Date: YYYY-MM-DD | Reason: {reason}"
                reason_part = self.notes.split("Reason:")[-1]
                # Get everything after "Reason:" and before any next "|" separator
                if "|" in reason_part:
                    reason = reason_part.split("|")[0].strip()
                else:
                    reason = reason_part.strip()
                return reason if reason else None
            except (IndexError, AttributeError):
                return None
        
        # If notes contain "discharge" but not in the standard format, return full notes
        if "discharge" in self.notes.lower():
            return self.notes
        
        return None


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
    referral_source = models.CharField(max_length=255, null=True, blank=True, db_index=True)
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
        ('org', 'Agency-wide'),
        ('program', 'Program-Specific'),
    ]
    
    BEHAVIOR_CHOICES = [
        ('weapons', 'Weapons'),
        ('physical_sexual_assault', 'Physical & Sexual Assault'),
        ('serious_threat_of_violence', 'Serious Threat of Violence'),
        ('domestic_violence', 'Domestic Violence'),
        ('threatening_behaviour_destroying_property_throwing_objects', 'Threatening Behaviour/Destroying Property/Throwing Objects'),
        ('abusive_or_oppressive_language', 'Abusive and/or Oppressive Language'),
        ('minor_physical_violence', 'Minor Physical Violence'),
        ('other', 'Other'),
    ]
    
    DETAILED_BEHAVIOR_CHOICES = [
        ('weapons', 'Weapons'),
        ('physical_sexual_assault', 'Physical & Sexual Assault'),
        ('serious_threat_of_violence', 'Serious Threat of Violence'),
        ('domestic_violence', 'Domestic Violence'),
        ('threatening_behaviour_destroying_property_throwing_objects', 'Threatening Behaviour/Destroying Property/Throwing Objects'),
        ('abusive_or_oppressive_language', 'Abusive and/or Oppressive Language'),
        ('minor_physical_violence', 'Minor Physical Violence'),
        ('other', 'Other'),
    ]
    
    client = models.ForeignKey(Client, on_delete=models.CASCADE, db_index=True)
    scope = models.CharField(max_length=10, choices=SCOPE_CHOICES, db_index=True)
    program = models.ForeignKey(Program, on_delete=models.CASCADE, null=True, blank=True, db_index=True)
    restriction_type = models.JSONField(default=list, help_text="List of behaviors that led to this restriction")
    is_bill_168 = models.BooleanField(default=False, db_index=True, help_text="Check if this is a Bill 168 (Violence Against Staff) restriction")
    is_no_trespass = models.BooleanField(default=False, db_index=True, help_text="Check if this is a No Trespass Order")
    start_date = models.DateField(db_index=True)
    end_date = models.DateField(null=True, blank=True, db_index=True)
    is_indefinite = models.BooleanField(default=False, db_index=True, help_text="Check if this restriction has no end date")
    is_archived = models.BooleanField(default=False, db_index=True, help_text="Check if this restriction has been archived")
    archived_at = models.DateTimeField(null=True, blank=True, db_index=True, help_text="Timestamp when this restriction was archived")
    behaviors = models.JSONField(default=list, help_text="List of behaviors that led to this restriction")
    notes = models.TextField(null=True, blank=True, help_text="Additional notes about the restriction")
    
    # Staff member who entered the restriction (agency/program agnostic)
    entered_by = models.ForeignKey('Staff', on_delete=models.SET_NULL, null=True, blank=True, db_index=True, related_name='restrictions_entered', help_text="Staff member who entered this restriction")
    
    # Staff member who is affected by or involved in the restriction
    affected_staff = models.ForeignKey('Staff', on_delete=models.SET_NULL, null=True, blank=True, db_index=True, related_name='restrictions_affecting', help_text="Staff member who is affected by or involved in this restriction")
    
    # Audit fields
    created_by = models.CharField(max_length=255, null=True, blank=True, help_text="Name of the person who created this record")
    updated_by = models.CharField(max_length=255, null=True, blank=True, help_text="Name of the person who last updated this record")
    
    class Meta:
        db_table = 'service_restrictions'
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(scope='program', program__isnull=False) |
                    models.Q(scope='org')
                ),
                name='valid_scope_program_combination'
            ),
            models.CheckConstraint(
                check=(
                    models.Q(is_indefinite=True, end_date__isnull=True) |
                    models.Q(is_indefinite=False)
                ),
                name='indefinite_restriction_no_end_date'
            )
        ]
    
    def __str__(self):
        return f"{self.client} - {self.get_restriction_type_display()}"
    
    def get_restriction_type_display(self):
        """Get display text for restriction type (behaviors)"""
        if not self.restriction_type:
            return "No behaviors specified"
        
        # Get the display names for the selected behaviors
        behavior_dict = dict(self.BEHAVIOR_CHOICES)
        display_names = []
        
        for behavior in self.restriction_type:
            if behavior in behavior_dict:
                display_names.append(behavior_dict[behavior])
        
        if display_names:
            return ", ".join(display_names)
        else:
            return "No behaviors specified"
    
    def get_behavior_tags(self):
        """Get behaviors as a list of tuples (value, display_name) for template rendering"""
        # Behaviors are stored in the behaviors field, not restriction_type
        if not self.behaviors or not isinstance(self.behaviors, list):
            return []
        
        # Use DETAILED_BEHAVIOR_CHOICES which matches what the form uses
        behavior_dict = dict(self.DETAILED_BEHAVIOR_CHOICES)
        tags = []
        
        for behavior in self.behaviors:
            if behavior in behavior_dict:
                tags.append((behavior, behavior_dict[behavior]))
        
        return tags
    
    def is_active(self):
        """Check if the restriction is currently active"""
        from django.utils import timezone
        today = timezone.now().date()
        
        # If archived, it's not active
        if self.is_archived:
            return False
        
        if self.is_indefinite:
            return self.start_date <= today
        else:
            return self.start_date <= today and (self.end_date is None or self.end_date >= today)
    
    def is_expired(self):
        """Check if the restriction has expired (past end date)"""
        from django.utils import timezone
        today = timezone.now().date()
        
        # If archived, it's considered expired
        if self.is_archived:
            return True
        
        # If indefinite, it never expires
        if self.is_indefinite:
            return False
        
        # If no end date, it doesn't expire
        if self.end_date is None:
            return False
        
        # Check if past end date
        return today > self.end_date
    
    def get_duration_display(self):
        """Get a human-readable duration display"""
        if self.is_indefinite:
            return "Indefinite"
        elif self.end_date:
            from datetime import timedelta
            duration = self.end_date - self.start_date
            days = duration.days
            if days < 30:
                return f"{days} days"
            elif days < 365:
                months = days // 30
                return f"{months} month{'s' if months > 1 else ''}"
            else:
                years = days // 365
                return f"{years} year{'s' if years > 1 else ''}"
        else:
            # Show date range from start date to present
            from django.utils import timezone
            today = timezone.now().date()
            duration = today - self.start_date
            days = duration.days
            if days < 30:
                return f"{days} days (since {self.start_date.strftime('%b %d, %Y')})"
            elif days < 365:
                months = days // 30
                return f"{months} month{'s' if months > 1 else ''} (since {self.start_date.strftime('%b %d, %Y')})"
            else:
                years = days // 365
                return f"{years} year{'s' if years > 1 else ''} (since {self.start_date.strftime('%b %d, %Y')})"


class AuditLog(BaseModel):
    ACTION_CHOICES = [
        ('create', 'Create'),
        ('update', 'Update'),
        ('delete', 'Delete'),
        ('archive', 'Archive'),
        ('restore', 'Restore'),
        ('import', 'Import'),
        ('login', 'Login'),
        ('logout', 'Logout'),
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


def create_audit_log(entity_name, entity_id, action, changed_by=None, diff_data=None):
    """Create an audit log entry"""
    from django.contrib.auth import get_user_model
    User = get_user_model()
    
    
    # Get the staff profile if changed_by is a User
    staff_profile = None
    if changed_by and hasattr(changed_by, 'staff_profile'):
        staff_profile = changed_by.staff_profile
    elif changed_by and isinstance(changed_by, Staff):
        staff_profile = changed_by
    elif changed_by:
        # Try to find staff profile by user
        try:
            staff_profile = Staff.objects.filter(user=changed_by).first()
        except Exception as e:
            pass
    
    
    # Create the audit log entry
    try:
        audit_log = AuditLog.objects.create(
            entity=entity_name,
            entity_id=entity_id,
            action=action,
            changed_by=staff_profile,
            diff_json=diff_data or {}
        )
        return audit_log
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error creating AuditLog: {e}")
        return None




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
    # Source of detection (upload, scan, manual, etc.)
    detection_source = models.CharField(
        max_length=50, 
        null=True, 
        blank=True, 
        db_index=True,
        help_text="How this duplicate was detected (e.g., 'scan', 'upload', 'manual')"
    )
    
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
    
    def get_duplicate_reason(self):
        """Get a human-readable reason why this client was flagged as a duplicate"""
        match_type = self.match_type.lower()
        
        # Map match types to human-readable reasons
        reason_map = {
            'exact_email': 'Matching Email Address',
            'exact_phone': 'Matching Phone Number',
            'email_phone': 'Matching Email Address and Phone Number',
            'name_dob_match': 'Matching Name and Date of Birth',
            'similarity': 'Similar Name',
            'nickname': 'Similar Name (Possible Nickname)',
        }
        
        # Handle similarity-based match types with scores
        if match_type.startswith('name_similarity_'):
            similarity = match_type.replace('name_similarity_', '')
            try:
                similarity_float = float(similarity)
                return f'Similar Name ({int(similarity_float * 100)}% match)'
            except (ValueError, TypeError):
                return 'Similar Name'
        
        if match_type.startswith('dob_name_similarity_'):
            similarity = match_type.replace('dob_name_similarity_', '')
            try:
                similarity_float = float(similarity)
                return f'Matching Date of Birth and Similar Name ({int(similarity_float * 100)}% match)'
            except (ValueError, TypeError):
                return 'Matching Date of Birth and Similar Name'
        
        # Check if we have a direct mapping
        if match_type in reason_map:
            return reason_map[match_type]
        
        # Fallback: format the match_type in a readable way
        return match_type.replace('_', ' ').title()
    
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

class ProgramManagerAssignment(BaseModel):
    """Assigns a staff member with Manager role to specific programs"""
    staff = models.ForeignKey(Staff, on_delete=models.CASCADE, db_index=True, related_name='program_manager_assignments')
    program = models.ForeignKey(Program, on_delete=models.CASCADE, db_index=True, related_name='manager_assignments')
    assigned_by = models.ForeignKey(Staff, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_program_managers')
    assigned_at = models.DateTimeField(auto_now_add=True, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)
    notes = models.TextField(null=True, blank=True)
    
    class Meta:
        db_table = 'program_manager_assignments'
        unique_together = ['staff', 'program']
        indexes = [
            models.Index(fields=['staff', 'is_active']),
            models.Index(fields=['program', 'is_active']),
        ]
    
    def __str__(self):
        return f"{self.staff} - Manager for {self.program.name}"

class ProgramServiceManagerAssignment(BaseModel):
    """Assigns a staff member with Manager role to specific program services"""
    staff = models.ForeignKey(Staff, on_delete=models.CASCADE, db_index=True, related_name='service_manager_assignments')
    program_service = models.ForeignKey('programs.ProgramService', on_delete=models.CASCADE, db_index=True, related_name='manager_assignments')
    assigned_by = models.ForeignKey(Staff, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_service_managers')
    assigned_at = models.DateTimeField(auto_now_add=True, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)
    notes = models.TextField(null=True, blank=True)
    
    class Meta:
        db_table = 'program_service_manager_assignments'
        unique_together = ['staff', 'program_service']
        indexes = [
            models.Index(fields=['staff', 'is_active']),
            models.Index(fields=['program_service', 'is_active']),
        ]
    
    def __str__(self):
        return f"{self.staff} - Service Manager for {self.program_service.name}"

class DepartmentLeaderAssignment(BaseModel):
    """Assigns a staff member with Leader role to specific departments"""
    staff = models.ForeignKey(Staff, on_delete=models.CASCADE, db_index=True, related_name='department_leader_assignments')
    department = models.ForeignKey(Department, on_delete=models.CASCADE, db_index=True, related_name='leader_assignments')
    assigned_by = models.ForeignKey(Staff, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_department_leaders')
    assigned_at = models.DateTimeField(auto_now_add=True, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)
    notes = models.TextField(null=True, blank=True)
    
    class Meta:
        db_table = 'department_leader_assignments'
        unique_together = ['staff', 'department']
        indexes = [
            models.Index(fields=['staff', 'is_active']),
            models.Index(fields=['department', 'is_active']),
        ]
    
    def __str__(self):
        return f"{self.staff} - Leader for {self.department.name}"


class EmailRecipientManager(models.Manager):
    """Custom manager for EmailRecipient with role-based filtering"""
    
    def for_user(self, user):
        """Filter EmailRecipients based on user's role and permissions"""
        if not user.is_authenticated:
            return self.none()
        
        # Superuser and SuperAdmin can see all
        if user.is_superuser:
            return self.all()
        
        try:
            from core.security import SecurityManager
            user_roles = SecurityManager.get_user_roles(user)
            
            # SuperAdmin and Admin can see all
            if any(role in ['SuperAdmin', 'Admin'] for role in user_roles):
                return self.all()
            
            # Manager and Leader can see department recipients
            if any(role in ['Manager', 'Leader'] for role in user_roles):
                staff = user.staff_profile
                return self.filter(
                    Q(department__in=staff.departments.all()) | Q(department__isnull=True)
                )
            
            # Staff and others cannot see any
            return self.none()
            
        except Exception:
            return self.none()


class EmailRecipient(BaseModel):
    """Stores email addresses that will receive daily client reports"""
    FREQUENCY_CHOICES = [
        ('daily', 'Daily (Last 24 Hours)'),
        ('weekly', 'Weekly (Last 7 Days)'),
        ('monthly', 'Monthly (Last 30 Days)'),
    ]
    
    email = models.EmailField(unique=True, db_index=True)
    name = models.CharField(max_length=255, help_text="Name of the recipient")
    frequency = models.CharField(max_length=20, choices=FREQUENCY_CHOICES, default='daily', help_text="How often to send reports")
    is_active = models.BooleanField(default=True, db_index=True)
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True, help_text="Optional: restrict to specific department")
    notes = models.TextField(null=True, blank=True, help_text="Additional notes about this recipient")
    
    # Custom manager
    objects = EmailRecipientManager()
    
    class Meta:
        db_table = 'email_recipients'
        indexes = [
            models.Index(fields=['email', 'is_active']),
            models.Index(fields=['department', 'is_active']),
        ]
        permissions = [
            ('manage_email_subscriptions', 'Can manage email subscriptions'),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.email})"


class ServiceRestrictionNotificationSubscription(BaseModel):
    """Store per-staff notification preferences for service restriction alerts."""
    staff = models.OneToOneField(
        'core.Staff',
        on_delete=models.CASCADE,
        related_name='service_restriction_notification',
        help_text="Staff member who owns this subscription"
    )
    email = models.EmailField(
        null=True,
        blank=True,
        help_text="Destination email for service restriction alerts (defaults to staff email if empty)"
    )
    notify_new = models.BooleanField(
        default=True,
        help_text="Receive notifications when new service restrictions are created"
    )
    notify_expiring = models.BooleanField(
        default=True,
        help_text="Receive notifications when service restrictions are nearing expiration"
    )

    class Meta:
        db_table = 'service_restriction_notification_subscriptions'
        verbose_name = "Service Restriction Notification Subscription"
        verbose_name_plural = "Service Restriction Notification Subscriptions"

    def __str__(self):
        return f"Service Restriction Alerts for {self.staff}"


class NotificationManager(models.Manager):
    """Custom manager for filtering notifications by staff user."""

    def for_user(self, user):
        if not user.is_authenticated:
            return self.none()

        staff_profile = getattr(user, 'staff_profile', None)
        if not staff_profile:
            return self.none()

        return self.filter(staff=staff_profile)


class Notification(BaseModel):
    """Generic notification for staff users with read/unread tracking."""

    CATEGORY_CHOICES = [
        ('service_restriction', 'Service Restriction'),
    ]

    staff = models.ForeignKey(
        'core.Staff',
        on_delete=models.CASCADE,
        related_name='notifications'
    )
    category = models.CharField(
        max_length=100,
        choices=CATEGORY_CHOICES,
        default='service_restriction'
    )
    title = models.CharField(max_length=255)
    message = models.TextField()
    metadata = models.JSONField(default=dict, blank=True)
    is_read = models.BooleanField(default=False, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True)

    objects = NotificationManager()

    class Meta:
        db_table = 'notifications'
        indexes = [
            models.Index(fields=['staff', 'is_read', 'created_at']),
            models.Index(fields=['category', 'created_at']),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} → {self.staff}"

    def mark_read(self):
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=['is_read', 'read_at', 'updated_at'])

    def mark_unread(self):
        if self.is_read:
            self.is_read = False
            self.read_at = None
            self.save(update_fields=['is_read', 'read_at', 'updated_at'])


class EmailLog(BaseModel):
    """Stores information about sent emails for tracking and audit purposes"""
    EMAIL_TYPE_CHOICES = [
        ('daily_report', 'Daily Client Report'),
        ('weekly_report', 'Weekly Client Report'),
        ('monthly_report', 'Monthly Client Report'),
        ('test_email', 'Test Email'),
        ('custom', 'Custom Email'),
    ]
    
    STATUS_CHOICES = [
        ('sent', 'Sent Successfully'),
        ('failed', 'Failed to Send'),
        ('pending', 'Pending'),
    ]
    
    email_type = models.CharField(max_length=20, choices=EMAIL_TYPE_CHOICES, default='daily_report')
    subject = models.CharField(max_length=255, help_text="Email subject line")
    recipient_email = models.EmailField(help_text="Email address of the recipient")
    recipient_name = models.CharField(max_length=255, null=True, blank=True, help_text="Name of the recipient")
    email_body = models.TextField(help_text="HTML content of the email")
    csv_attachment = models.TextField(null=True, blank=True, help_text="CSV data that was attached")
    csv_filename = models.CharField(max_length=255, null=True, blank=True, help_text="Name of the CSV file attached")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='sent')
    sent_at = models.DateTimeField(auto_now_add=True, help_text="When the email was sent")
    error_message = models.TextField(null=True, blank=True, help_text="Error message if sending failed")
    client_count = models.PositiveIntegerField(default=0, help_text="Number of clients included in the report")
    report_date = models.DateField(help_text="Date the report covers")
    frequency = models.CharField(max_length=20, choices=EmailRecipient.FREQUENCY_CHOICES, default='daily')
    
    class Meta:
        db_table = 'email_logs'
        indexes = [
            models.Index(fields=['recipient_email', 'sent_at']),
            models.Index(fields=['email_type', 'status']),
            models.Index(fields=['report_date']),
            models.Index(fields=['sent_at']),
        ]
        ordering = ['-sent_at']
    
    def __str__(self):
        return f"{self.email_type} to {self.recipient_email} on {self.sent_at.strftime('%Y-%m-%d %H:%M')}"


class ClientUploadLog(BaseModel):
    """Track client upload operations for performance monitoring and debugging"""
    
    STATUS_CHOICES = [
        ('success', 'Success'),
        ('failed', 'Failed'),
        ('partial', 'Partial Success'),
    ]
    
    # File information
    file_name = models.CharField(max_length=255, db_index=True)
    file_size = models.BigIntegerField(help_text="File size in bytes")
    file_type = models.CharField(max_length=10, db_index=True, help_text="csv, xlsx, or xls")
    source = models.CharField(max_length=50, db_index=True, help_text="SMIS or EMHware")
    
    # Upload metrics
    total_rows = models.IntegerField(default=0, help_text="Total number of rows in the uploaded file")
    records_created = models.IntegerField(default=0)
    records_updated = models.IntegerField(default=0)
    records_skipped = models.IntegerField(default=0)
    duplicates_flagged = models.IntegerField(default=0)
    errors_count = models.IntegerField(default=0)
    
    # Timing information
    started_at = models.DateTimeField(db_index=True, help_text="When the upload process started")
    completed_at = models.DateTimeField(null=True, blank=True, db_index=True, help_text="When the upload process completed")
    duration_seconds = models.FloatField(null=True, blank=True, help_text="Upload duration in seconds")
    
    # Status and errors
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='success', db_index=True)
    error_message = models.TextField(null=True, blank=True, help_text="Error message if upload failed")
    error_details = models.JSONField(default=list, help_text="List of error messages from processing")
    
    # User information
    uploaded_by = models.ForeignKey('core.Staff', on_delete=models.SET_NULL, null=True, blank=True, db_index=True, related_name='client_uploads')
    
    # Additional metadata
    upload_details = models.JSONField(default=dict, help_text="Additional upload metadata")
    
    class Meta:
        db_table = 'client_upload_logs'
        ordering = ['-started_at']
        indexes = [
            models.Index(fields=['status', 'started_at']),
            models.Index(fields=['uploaded_by', 'started_at']),
            models.Index(fields=['source', 'started_at']),
        ]
    
    def __str__(self):
        return f"Upload: {self.file_name} - {self.status} ({self.total_rows} rows)"
    
    def calculate_duration(self):
        """Calculate duration if both start and end times are available"""
        if self.started_at and self.completed_at:
            delta = self.completed_at - self.started_at
            return delta.total_seconds()
        return None
    
    def save(self, *args, **kwargs):
        # Auto-calculate duration on save
        if self.completed_at:
            self.duration_seconds = self.calculate_duration()
        super().save(*args, **kwargs)