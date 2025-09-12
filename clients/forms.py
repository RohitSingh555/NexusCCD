from django import forms
from core.models import Client
import json


class ClientForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = ['first_name', 'last_name', 'preferred_name', 'alias', 'dob', 'gender', 
                  'sexual_orientation', 'languages_spoken', 'race', 'immigration_status', 
                  'phone_number', 'email', 'addresses', 'image']
        widgets = {
            'dob': forms.DateInput(attrs={'type': 'date'}),
            'languages_spoken': forms.HiddenInput(),
            'addresses': forms.HiddenInput(),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Initialize addresses from instance or empty list
        if self.instance and self.instance.pk:
            self.addresses_data = self.instance.addresses if self.instance.addresses else []
        else:
            self.addresses_data = []
    
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
