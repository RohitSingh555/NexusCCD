from django import forms
from django.core.exceptions import ValidationError
from django.db import models
from .models import ClientProgramEnrollment, Client, Program, ServiceRestriction
from datetime import date


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
