from django import forms
from core.models import Client
import json


class ClientForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = [
            'first_name', 'last_name', 'preferred_name', 'alias', 'dob', 'gender', 
            'sexual_orientation', 'languages_spoken', 'ethnicity', 'citizenship_status', 
            'indigenous_status', 'country_of_birth', 'contact_information', 'addresses', 'image',
            'profile_picture', 'address_2', 'permission_to_phone', 'permission_to_email',
            'phone_work', 'phone_alt', 'medical_conditions', 'primary_diagnosis',
            'support_workers', 'next_of_kin', 'emergency_contact', 'comments'
        ]
        widgets = {
            'dob': forms.DateInput(attrs={'type': 'date'}),
            'languages_spoken': forms.HiddenInput(),
            'ethnicity': forms.HiddenInput(),
            'contact_information': forms.HiddenInput(),
            'addresses': forms.HiddenInput(),
            'support_workers': forms.HiddenInput(),
            'next_of_kin': forms.HiddenInput(),
            'emergency_contact': forms.HiddenInput(),
            'profile_picture': forms.FileInput(attrs={
                'accept': 'image/*',
                'class': 'hidden'
            }),
            'medical_conditions': forms.Textarea(attrs={'rows': 3}),
            'comments': forms.Textarea(attrs={'rows': 3}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Make JSON fields optional
        self.fields['languages_spoken'].required = False
        self.fields['ethnicity'].required = False
        self.fields['contact_information'].required = False
        self.fields['addresses'].required = False
        self.fields['support_workers'].required = False
        self.fields['next_of_kin'].required = False
        self.fields['emergency_contact'].required = False
        
        # Initialize addresses from instance or empty list
        if self.instance and self.instance.pk:
            self.addresses_data = self.instance.addresses if self.instance.addresses else []
            self.contact_data = self.instance.contact_information if self.instance.contact_information else {}
            self.ethnicity_data = self.instance.ethnicity if self.instance.ethnicity else []
            self.support_workers_data = self.instance.support_workers if self.instance.support_workers else []
            self.next_of_kin_data = self.instance.next_of_kin if self.instance.next_of_kin else {}
            self.emergency_contact_data = self.instance.emergency_contact if self.instance.emergency_contact else {}
        else:
            self.addresses_data = []
            self.contact_data = {}
            self.ethnicity_data = []
            self.support_workers_data = []
            self.next_of_kin_data = {}
            self.emergency_contact_data = {}
    
    def clean_addresses(self):
        """Validate and clean addresses data"""
        addresses = self.cleaned_data.get('addresses', [])
        
        if isinstance(addresses, str):
            try:
                addresses = json.loads(addresses)
            except json.JSONDecodeError:
                raise forms.ValidationError("Invalid JSON format for addresses")
        
        if not isinstance(addresses, list):
            raise forms.ValidationError("Addresses must be a list")
        
        # Filter out empty addresses
        valid_addresses = []
        for address in addresses:
            if isinstance(address, dict) and any(address.get(field) for field in ['street', 'city', 'state', 'zip']):
                # Only validate if address has some data
                required_fields = ['type', 'street', 'city', 'state', 'zip']
                for field in required_fields:
                    if field not in address:
                        address[field] = ''
                valid_addresses.append(address)
        
        return valid_addresses
    
    def clean_languages_spoken(self):
        """Validate and clean languages_spoken data"""
        languages = self.cleaned_data.get('languages_spoken', [])
        
        if isinstance(languages, str):
            try:
                languages = json.loads(languages)
            except json.JSONDecodeError:
                raise forms.ValidationError("Invalid JSON format for languages")
        
        if not isinstance(languages, list):
            raise forms.ValidationError("Languages must be a list")
        
        return languages
    
    def clean_ethnicity(self):
        """Validate and clean ethnicity data"""
        ethnicity = self.cleaned_data.get('ethnicity', [])
        
        if isinstance(ethnicity, str):
            try:
                ethnicity = json.loads(ethnicity)
            except json.JSONDecodeError:
                raise forms.ValidationError("Invalid JSON format for ethnicity")
        
        if not isinstance(ethnicity, list):
            raise forms.ValidationError("Ethnicity must be a list")
        
        return ethnicity
    
    def clean_contact_information(self):
        """Validate and clean contact_information data"""
        contact_info = self.cleaned_data.get('contact_information', {})
        
        if isinstance(contact_info, str):
            try:
                contact_info = json.loads(contact_info)
            except json.JSONDecodeError:
                raise forms.ValidationError("Invalid JSON format for contact information")
        
        if not isinstance(contact_info, dict):
            raise forms.ValidationError("Contact information must be a dictionary")
        
        # Validate phone and email if provided
        if 'phone' in contact_info and contact_info['phone']:
            phone = contact_info['phone']
            if not phone.replace('+', '').replace('-', '').replace('(', '').replace(')', '').replace(' ', '').isdigit():
                raise forms.ValidationError("Invalid phone number format")
        
        if 'email' in contact_info and contact_info['email']:
            email = contact_info['email']
            if '@' not in email or '.' not in email.split('@')[-1]:
                raise forms.ValidationError("Invalid email format")
        
        return contact_info

    def clean_support_workers(self):
        """Validate and clean support_workers data"""
        support_workers = self.cleaned_data.get('support_workers', [])
        
        if isinstance(support_workers, str):
            try:
                support_workers = json.loads(support_workers)
            except json.JSONDecodeError:
                raise forms.ValidationError("Invalid JSON format for support workers")
        
        if not isinstance(support_workers, list):
            raise forms.ValidationError("Support workers must be a list")
        
        return support_workers

    def clean_next_of_kin(self):
        """Validate and clean next_of_kin data"""
        next_of_kin = self.cleaned_data.get('next_of_kin', {})
        
        if isinstance(next_of_kin, str):
            try:
                next_of_kin = json.loads(next_of_kin)
            except json.JSONDecodeError:
                raise forms.ValidationError("Invalid JSON format for next of kin")
        
        if not isinstance(next_of_kin, dict):
            raise forms.ValidationError("Next of kin must be a dictionary")
        
        return next_of_kin

    def clean_emergency_contact(self):
        """Validate and clean emergency_contact data"""
        emergency_contact = self.cleaned_data.get('emergency_contact', {})
        
        if isinstance(emergency_contact, str):
            try:
                emergency_contact = json.loads(emergency_contact)
            except json.JSONDecodeError:
                raise forms.ValidationError("Invalid JSON format for emergency contact")
        
        if not isinstance(emergency_contact, dict):
            raise forms.ValidationError("Emergency contact must be a dictionary")
        
        return emergency_contact

    def clean_profile_picture(self):
        """Validate profile picture file"""
        profile_picture = self.cleaned_data.get('profile_picture')
        
        if profile_picture:
            # Check file size (5MB = 5 * 1024 * 1024 bytes)
            max_size = 5 * 1024 * 1024  # 5MB in bytes
            if profile_picture.size > max_size:
                raise forms.ValidationError('File size must be less than 5MB')
            
            # Check file type by reading the file header
            try:
                profile_picture.seek(0)
                header = profile_picture.read(10)
                profile_picture.seek(0)  # Reset file pointer
                
                # Check for common image file signatures
                is_image = (
                    header.startswith(b'\xff\xd8\xff') or  # JPEG
                    header.startswith(b'\x89PNG\r\n\x1a\n') or  # PNG
                    header.startswith(b'GIF87a') or  # GIF87a
                    header.startswith(b'GIF89a') or  # GIF89a
                    header.startswith(b'RIFF') and b'WEBP' in header[:12]  # WebP
                )
                
                if not is_image:
                    raise forms.ValidationError('Please upload a valid image file (JPEG, PNG, GIF, or WebP)')
            except Exception:
                raise forms.ValidationError('Please upload a valid image file')
        
        return profile_picture
