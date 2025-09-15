from django import forms
from core.models import Client
import json


class ClientForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = ['first_name', 'last_name', 'preferred_name', 'alias', 'dob', 'gender', 
                  'sexual_orientation', 'languages_spoken', 'ethnicity', 'citizenship_status', 
                  'indigenous_status', 'country_of_birth', 'contact_information', 'addresses', 'image']
        widgets = {
            'dob': forms.DateInput(attrs={'type': 'date'}),
            'languages_spoken': forms.HiddenInput(),
            'ethnicity': forms.HiddenInput(),
            'contact_information': forms.HiddenInput(),
            'addresses': forms.HiddenInput(),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Initialize addresses from instance or empty list
        if self.instance and self.instance.pk:
            self.addresses_data = self.instance.addresses if self.instance.addresses else []
            self.contact_data = self.instance.contact_information if self.instance.contact_information else {}
            self.ethnicity_data = self.instance.ethnicity if self.instance.ethnicity else []
        else:
            self.addresses_data = []
            self.contact_data = {}
            self.ethnicity_data = []
    
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
