from django import forms
from django.core.exceptions import ValidationError
from django.db import models
from .models import ClientProgramEnrollment, ServiceRestriction
from datetime import date
from django.contrib.auth import get_user_model
from .models import Staff


class EnrollmentForm(forms.ModelForm):
    class Meta:
        model = ClientProgramEnrollment
        fields = ['client', 'program', 'start_date', 'end_date', 'status', 'notes']
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'end_date': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }
    
    def __init__(self, *args, **kwargs):
        program_queryset = kwargs.pop('program_queryset', None)
        client_queryset = kwargs.pop('client_queryset', None)
        super().__init__(*args, **kwargs)
        
        if program_queryset is not None:
            self.fields['program'].queryset = program_queryset
        
        if client_queryset is not None:
            self.fields['client'].queryset = client_queryset
    
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
        
        # Check for ANY active restrictions (organization-wide or program-specific)
        # This ensures that ANY restriction blocks enrollment in ANY program
        active_restrictions = ServiceRestriction.objects.filter(
            client=client,
            start_date__lte=start_date
        ).filter(
            models.Q(end_date__isnull=True) | models.Q(end_date__gte=start_date)
        )
        
        if active_restrictions.exists():
            restriction = active_restrictions.first()
            end_date_text = restriction.end_date.strftime('%B %d, %Y') if restriction.end_date else 'indefinite'
            
            # Determine restriction scope for the error message
            if restriction.scope == 'org':
                scope_text = "all programs"
            else:
                scope_text = f"'{restriction.program.name}' program" if restriction.program else "specific programs"
            
            raise ValidationError(
                f"⚠️ ENROLLMENT BLOCKED - ACTIVE SERVICE RESTRICTION\n\n"
                f"Client: {client.first_name} {client.last_name}\n"
                f"Restriction Type: {restriction.get_restriction_type_display()}\n"
                f"Scope: {scope_text}\n"
                f"Period: {restriction.start_date.strftime('%B %d, %Y')} to {end_date_text}\n"
                f"Reason: {restriction.notes or 'No reason provided'}\n\n"
                f"ACTION REQUIRED: Please remove or modify the restriction before enrolling this client."
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
                    f"📊 PROGRAM AT FULL CAPACITY\n\n"
                    f"Program: {program.name}\n"
                    f"Current Enrollments: {current_enrollments}/{program.capacity_current} ({capacity_percentage:.1f}% full)\n"
                    f"Available Spots: {available_capacity}\n\n"
                    f"ACTION REQUIRED: Please try enrolling in a different program or wait for a spot to become available."
                )
            else:
                # Client is already enrolled
                raise ValidationError(f"⚠️ {message}")
    
    def clean_start_date(self):
        start_date = self.cleaned_data.get('start_date')
        if start_date and start_date < date.today():
            raise ValidationError("📅 INVALID START DATE\n\nStart date cannot be in the past. Please select today's date or a future date.")
        return start_date
    
    def clean_end_date(self):
        start_date = self.cleaned_data.get('start_date')
        end_date = self.cleaned_data.get('end_date')
        
        if start_date and end_date and end_date <= start_date:
            raise ValidationError("📅 INVALID END DATE\n\nEnd date must be after start date. Please select a date after the start date.")
        
        return end_date

User = get_user_model()

class UserProfileForm(forms.ModelForm):
    """Form for editing user profile information"""
    remove_profile_photo = forms.BooleanField(
        required=False,
        initial=False,
        widget=forms.CheckboxInput(attrs={'style': 'display: none;'})
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
        print(f"Form cleaned_data: {self.cleaned_data}")
        print(f"remove_profile_photo value: {self.cleaned_data.get('remove_profile_photo')}")
        print(f"remove_profile_photo type: {type(self.cleaned_data.get('remove_profile_photo'))}")
        if self.cleaned_data.get('remove_profile_photo'):
            print("Removing profile photo...")
            if user.profile_photo:
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


class ServiceRestrictionForm(forms.ModelForm):
    """Form for creating and editing service restrictions"""
    
    client_profile_image = forms.ImageField(
        required=False,
        help_text="Upload a profile image for the client (optional)",
        widget=forms.FileInput(attrs={
            'class': 'w-full px-4 py-3 border border-neutral-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-brand-sky focus:border-transparent',
            'accept': 'image/*'
        })
    )
    
    class Meta:
        model = ServiceRestriction
        fields = ['client', 'scope', 'program', 'restriction_type', 'start_date', 'end_date', 'is_indefinite', 'behaviors', 'notes']
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date', 'class': 'w-full px-4 py-3 border border-neutral-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-brand-sky focus:border-transparent'}),
            'end_date': forms.DateInput(attrs={'type': 'date', 'class': 'w-full px-4 py-3 border border-neutral-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-brand-sky focus:border-transparent'}),
            'behaviors': forms.CheckboxSelectMultiple(attrs={'class': 'space-y-2'}),
            'notes': forms.Textarea(attrs={'rows': 4, 'class': 'w-full px-4 py-3 border border-neutral-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-brand-sky focus:border-transparent'}),
            'is_indefinite': forms.CheckboxInput(attrs={'class': 'h-4 w-4 text-brand-sky focus:ring-brand-sky border-neutral-300 rounded'}),
        }
    
    def __init__(self, *args, **kwargs):
        program_queryset = kwargs.pop('program_queryset', None)
        super().__init__(*args, **kwargs)
        
        # Set up field styling
        self.fields['client'].widget.attrs.update({
            'class': 'w-full px-4 py-3 border border-neutral-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-brand-sky focus:border-transparent'
        })
        self.fields['scope'].widget.attrs.update({
            'class': 'w-full px-4 py-3 border border-neutral-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-brand-sky focus:border-transparent'
        })
        self.fields['program'].widget.attrs.update({
            'class': 'w-full px-4 py-3 border border-neutral-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-brand-sky focus:border-transparent'
        })
        self.fields['restriction_type'].widget.attrs.update({
            'class': 'w-full px-4 py-3 border border-neutral-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-brand-sky focus:border-transparent'
        })
        
        # Filter programs if provided
        if program_queryset is not None:
            self.fields['program'].queryset = program_queryset
        
        # Add help text
        self.fields['is_indefinite'].help_text = "Check this box if the restriction has no end date"
        self.fields['behaviors'].help_text = "Select all behaviors that apply to this restriction (only shown for Behavioral Issues type)"
        self.fields['notes'].help_text = "Additional notes about the restriction (required for Behavioral Issues type)"
        
        # Set initial value for behaviors field to empty list and make it not required by default
        if 'behaviors' in self.fields:
            self.fields['behaviors'].initial = []
            self.fields['behaviors'].required = False
    
    def clean(self):
        print("ServiceRestrictionForm.clean called")
        cleaned_data = super().clean()
        print(f"Super clean completed, cleaned_data: {cleaned_data}")
        
        is_indefinite = cleaned_data.get('is_indefinite')
        end_date = cleaned_data.get('end_date')
        start_date = cleaned_data.get('start_date')
        restriction_type = cleaned_data.get('restriction_type')
        behaviors = cleaned_data.get('behaviors')
        notes = cleaned_data.get('notes')
        
        # Debug: Print form data
        print(f"Form data: {cleaned_data}")
        print(f"Restriction type: {restriction_type}")
        print(f"Behaviors: {behaviors}")
        print(f"Notes: {notes}")
        print(f"Is indefinite: {is_indefinite}")
        print(f"Start date: {start_date}")
        print(f"End date: {end_date}")
        
        # If indefinite is checked, clear end_date
        if is_indefinite and end_date:
            cleaned_data['end_date'] = None
        
        # Validate date logic
        if start_date and end_date and not is_indefinite:
            if end_date <= start_date:
                raise ValidationError("End date must be after start date.")
        
        # Validate behavioral issues type
        if restriction_type == 'behaviors':
            if not behaviors or len(behaviors) == 0:
                raise ValidationError("At least one behavior must be selected for Behavioral Issues restrictions.")
            if not notes or not notes.strip():
                raise ValidationError("Notes are required for Behavioral Issues restrictions to describe the specific behaviors.")
        
        # Ensure behaviors is always a list (but only required for behavioral issues type)
        if behaviors is None:
            cleaned_data['behaviors'] = []
        
        return cleaned_data
    
    def clean_start_date(self):
        start_date = self.cleaned_data.get('start_date')
        if start_date and start_date < date.today():
            raise ValidationError("Start date cannot be in the past.")
        return start_date
    
    def clean_behaviors(self):
        print("ServiceRestrictionForm.clean_behaviors called")
        behaviors = self.cleaned_data.get('behaviors')
        print(f"Raw behaviors value: {behaviors}")
        if behaviors is None:
            print("Behaviors is None, returning empty list")
            return []
        print(f"Returning behaviors: {behaviors}")
        return behaviors
    
    def clean_client_profile_image(self):
        client_profile_image = self.cleaned_data.get('client_profile_image')
        if client_profile_image:
            # Check file size (max 5MB)
            if client_profile_image.size > 5 * 1024 * 1024:
                raise ValidationError("Profile image must be smaller than 5MB.")
            
            # Check file type
            allowed_types = ['image/jpeg', 'image/png', 'image/gif', 'image/webp']
            if client_profile_image.content_type not in allowed_types:
                raise ValidationError("Please upload a valid image file (JPEG, PNG, GIF, or WebP).")
        
        return client_profile_image
    
    def save(self, commit=True):
        print(f"ServiceRestrictionForm.save called with commit={commit}")
        instance = super().save(commit=False)
        print(f"Instance created: {instance}")
        print(f"Instance client: {instance.client}")
        print(f"Instance scope: {instance.scope}")
        print(f"Instance restriction_type: {instance.restriction_type}")
        
        if commit:
            print("Saving instance...")
            instance.save()
            print(f"Instance saved with ID: {instance.id}")
            
            # Handle client profile image upload after restriction is saved
            client_profile_image = self.cleaned_data.get('client_profile_image')
            if client_profile_image:
                print("Updating client profile picture...")
                # Update the client's profile picture
                client = instance.client
                client.profile_picture = client_profile_image
                client.save()
                print("Client profile picture updated")
        
        return instance