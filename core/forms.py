from django import forms
from django.core.exceptions import ValidationError
from django.db import models
from .models import ClientProgramEnrollment, Client, Program, ServiceRestriction
from datetime import date
from django.contrib.auth import get_user_model
from .models import Staff, Department


class EnrollmentForm(forms.ModelForm):
    class Meta:
        model = ClientProgramEnrollment
        fields = ['client', 'program', 'start_date', 'end_date']
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'end_date': forms.DateInput(attrs={'type': 'date'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Set default start date to today
        if not self.instance.pk:
            self.fields['start_date'].initial = date.today()
    
    def clean(self):
        cleaned_data = super().clean()
        client = cleaned_data.get('client')
        program = cleaned_data.get('program')
        start_date = cleaned_data.get('start_date')
        
        if client and program and start_date:
            # Check for service restrictions
            self.check_service_restrictions(client, program, start_date)
            
            # Check program capacity
            self.check_program_capacity(client, program, start_date)
        
        return cleaned_data
    
    def check_service_restrictions(self, client, program, start_date):
        """Check if client has service restrictions that would prevent enrollment"""
        today = date.today()
        
        # Check for organization-wide restrictions
        org_restrictions = ServiceRestriction.objects.filter(
            client=client,
            scope='org',
            start_date__lte=start_date
        ).filter(
            models.Q(end_date__isnull=True) | models.Q(end_date__gte=start_date)
        )
        
        if org_restrictions.exists():
            restriction = org_restrictions.first()
            end_date_text = restriction.end_date.strftime('%B %d, %Y') if restriction.end_date else 'indefinite'
            raise ValidationError(
                f"🚫 {client.first_name} {client.last_name} is currently restricted from all programs. "
                f"Restriction period: {restriction.start_date.strftime('%B %d, %Y')} to {end_date_text}. "
                f"Reason: {restriction.reason}"
            )
        
        # Check for program-specific restrictions
        program_restrictions = ServiceRestriction.objects.filter(
            client=client,
            scope='program',
            program=program,
            start_date__lte=start_date
        ).filter(
            models.Q(end_date__isnull=True) | models.Q(end_date__gte=start_date)
        )
        
        if program_restrictions.exists():
            restriction = program_restrictions.first()
            end_date_text = restriction.end_date.strftime('%B %d, %Y') if restriction.end_date else 'indefinite'
            raise ValidationError(
                f"🚫 {client.first_name} {client.last_name} is restricted from '{program.name}' program. "
                f"Restriction period: {restriction.start_date.strftime('%B %d, %Y')} to {end_date_text}. "
                f"Reason: {restriction.reason}"
            )
    
    def check_program_capacity(self, client, program, start_date):
        """Check if the program has available capacity for enrollment"""
        can_enroll, message = program.can_enroll_client(client, start_date)
        
        if not can_enroll:
            if "capacity" in message.lower():
                # Program is at capacity
                current_enrollments = program.get_current_enrollments_count(start_date)
                available_capacity = program.get_available_capacity(start_date)
                capacity_percentage = program.get_capacity_percentage(start_date)
                
                raise ValidationError(
                    f"📊 Program '{program.name}' is at full capacity! "
                    f"Current enrollments: {current_enrollments}/{program.capacity_current} "
                    f"({capacity_percentage:.1f}% full). "
                    f"Available spots: {available_capacity}. "
                    f"Please try enrolling in a different program or wait for a spot to become available."
                )
            else:
                # Client is already enrolled
                raise ValidationError(f"⚠️ {message}")
    
    def clean_start_date(self):
        start_date = self.cleaned_data.get('start_date')
        if start_date and start_date < date.today():
            raise ValidationError("📅 Start date cannot be in the past. Please select today's date or a future date.")
        return start_date
    
    def clean_end_date(self):
        start_date = self.cleaned_data.get('start_date')
        end_date = self.cleaned_data.get('end_date')
        
        if start_date and end_date and end_date <= start_date:
            raise ValidationError("📅 End date must be after start date. Please select a date after the start date.")
        
        return end_date

User = get_user_model()

class UserProfileForm(forms.ModelForm):
    """Form for editing user profile information"""
    remove_profile_photo = forms.BooleanField(
        required=False,
        initial=False,
        label="Remove profile photo"
    )
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'username', 'profile_photo']
        widgets = {
            'first_name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 border border-neutral-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-brand-sky focus:border-transparent',
                'placeholder': 'Enter your first name'
            }),
            'last_name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 border border-neutral-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-brand-sky focus:border-transparent',
                'placeholder': 'Enter your last name'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'w-full px-4 py-3 border border-neutral-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-brand-sky focus:border-transparent',
                'placeholder': 'Enter your email address'
            }),
            'username': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 border border-neutral-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-brand-sky focus:border-transparent',
                'placeholder': 'Enter your username'
            }),
            'profile_photo': forms.FileInput(attrs={
                'class': 'w-full px-4 py-3 border border-neutral-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-brand-sky focus:border-transparent',
                'accept': 'image/*'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['profile_photo'].required = False
        self.fields['email'].required = False

    def save(self, commit=True):
        user = super().save(commit=False)
        if self.cleaned_data.get('remove_profile_photo'):
            user.profile_photo.delete(save=False)  # Delete the file
            user.profile_photo = None
        if commit:
            user.save()
        return user

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if not email:
            # If no email provided, use the existing email
            return self.instance.email
        # Check if email is already taken by another user
        existing_user = User.objects.filter(email=email).exclude(pk=self.instance.pk).first()
        if existing_user:
            raise ValidationError("This email address is already in use by another user.")
        return email

    def clean_username(self):
        username = self.cleaned_data.get('username')
        if not username:
            # If no username provided, use the existing username
            return self.instance.username
        existing_user = User.objects.filter(username=username).exclude(pk=self.instance.pk).first()
        if existing_user:
            raise ValidationError("This username is already taken by another user.")
        return username

    def clean_profile_photo(self):
        profile_photo = self.cleaned_data.get('profile_photo')
        if profile_photo:
            # Check if it's a new uploaded file (has content_type) or existing file
            if hasattr(profile_photo, 'content_type'):
                # It's a new uploaded file

                if profile_photo.size > 5 * 1024 * 1024:
                    raise ValidationError("Profile photo must be smaller than 5MB.")
                
                # Check file type
                allowed_types = ['image/jpeg', 'image/png', 'image/gif', 'image/webp']
                if profile_photo.content_type not in allowed_types:
                    raise ValidationError("Please upload a valid image file (JPEG, PNG, GIF, or WebP).")
            # If it's an existing file (ImageFieldFile), we don't need to validate it again
        return profile_photo

class StaffProfileForm(forms.ModelForm):
    """Form for editing staff profile information"""
    class Meta:
        model = Staff
        fields = ['first_name', 'last_name', 'email', 'active']
        widgets = {
            'first_name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 border border-neutral-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-brand-sky focus:border-transparent',
                'placeholder': 'Enter your first name'
            }),
            'last_name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-3 border border-neutral-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-brand-sky focus:border-transparent',
                'placeholder': 'Enter your last name'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'w-full px-4 py-3 border border-neutral-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-brand-sky focus:border-transparent',
                'placeholder': 'Enter your email address'
            }),
            'active': forms.CheckboxInput(attrs={
                'class': 'h-4 w-4 text-brand-sky focus:ring-brand-sky border-neutral-300 rounded'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make fields optional
        self.fields['first_name'].required = False
        self.fields['last_name'].required = False
        self.fields['email'].required = False
        self.fields['active'].required = False

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if email:
            # Check if email is already taken by another staff member
            existing_staff = Staff.objects.filter(email=email).exclude(pk=self.instance.pk).first()
            if existing_staff:
                raise ValidationError("This email address is already in use by another staff member.")
        return email


class PasswordChangeForm(forms.Form):
    """Form for changing user password"""
    current_password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'w-full px-4 py-3 border border-neutral-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-brand-sky focus:border-transparent',
            'placeholder': 'Enter your current password'
        }),
        label='Current Password'
    )
    new_password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'w-full px-4 py-3 border border-neutral-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-brand-sky focus:border-transparent',
            'placeholder': 'Enter your new password'
        }),
        label='New Password',
        min_length=8,
        help_text='Password must be at least 8 characters long.'
    )
    confirm_password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'w-full px-4 py-3 border border-neutral-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-brand-sky focus:border-transparent',
            'placeholder': 'Confirm your new password'
        }),
        label='Confirm New Password'
    )

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_current_password(self):
        current_password = self.cleaned_data.get('current_password')
        if not self.user.check_password(current_password):
            raise ValidationError("Current password is incorrect.")
        return current_password

    def clean(self):
        cleaned_data = super().clean()
        new_password = cleaned_data.get('new_password')
        confirm_password = cleaned_data.get('confirm_password')

        if new_password and confirm_password and new_password != confirm_password:
            raise ValidationError("New passwords do not match.")

        return cleaned_data