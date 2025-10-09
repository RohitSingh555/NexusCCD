from django import forms
from core.models import Client
import json


class ClientForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = [
            # 🧍 CLIENT PERSONAL DETAILS
            'client_id', 'last_name', 'first_name', 'middle_name', 'preferred_name', 'alias', 
            'dob', 'age', 'gender', 'gender_identity', 'pronoun', 'marital_status', 
            'citizenship_status', 'location_county', 'province', 'city', 'postal_code', 
            'address', 'address_2',
            
            # 🌍 CULTURAL & DEMOGRAPHIC INFO
            'language', 'preferred_language', 'mother_tongue', 'official_language', 
            'language_interpreter_required', 'self_identification_race_ethnicity', 'ethnicity', 
            'aboriginal_status', 'lgbtq_status', 'highest_level_education', 'children_home', 
            'children_number', 'lhin',
            
            # 💊 MEDICAL & HEALTH INFORMATION
            'medical_conditions', 'primary_diagnosis', 'family_doctor', 'health_card_number', 
            'health_card_version', 'health_card_exp_date', 'health_card_issuing_province', 
            'no_health_card_reason',
            
            # 👥 CONTACT & PERMISSIONS
            'permission_to_phone', 'permission_to_email', 'phone', 'phone_work', 'phone_alt', 
            'email', 'next_of_kin', 'emergency_contact', 'comments',
            
            # 🧑‍💼 PROGRAM / ENROLLMENT DETAILS
            'program', 'sub_program', 'support_workers', 'level_of_support', 'client_type', 
            'admission_date', 'discharge_date', 'days_elapsed', 'program_status', 
            'reason_discharge', 'receiving_services', 'referral_source',
            
            # 🧾 ADMINISTRATIVE / SYSTEM FIELDS
            'chart_number',
            
            # Legacy fields
            'image', 'profile_picture', 'contact_information', 'addresses', 'languages_spoken',
            'indigenous_status', 'country_of_birth', 'sexual_orientation'
        ]
        widgets = {
            # Date fields
            'dob': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'health_card_exp_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'admission_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'discharge_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            
            # Hidden fields for JSON data
            'languages_spoken': forms.HiddenInput(),
            'ethnicity': forms.HiddenInput(),
            'contact_information': forms.HiddenInput(),
            'addresses': forms.HiddenInput(),
            'support_workers': forms.HiddenInput(),
            'next_of_kin': forms.HiddenInput(),
            'emergency_contact': forms.HiddenInput(),
            
            # File upload
            'profile_picture': forms.FileInput(attrs={
                'accept': 'image/*',
                'class': 'form-control'
            }),
            
            # Text areas
            'medical_conditions': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'comments': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'reason_discharge': forms.Textarea(attrs={'rows': 2, 'class': 'form-control'}),
            'no_health_card_reason': forms.Textarea(attrs={'rows': 2, 'class': 'form-control'}),
            
            # Checkboxes
            'language_interpreter_required': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'children_home': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'permission_to_phone': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'permission_to_email': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'receiving_services': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
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
        
        # Make most new fields optional
        optional_fields = [
            'client_id', 'middle_name', 'preferred_name', 'alias', 'age', 'gender_identity', 
            'pronoun', 'marital_status', 'location_county', 'province', 'city', 'postal_code', 
            'address', 'address_2', 'language', 'preferred_language', 'mother_tongue', 
            'official_language', 'self_identification_race_ethnicity', 'aboriginal_status', 
            'lgbtq_status', 'highest_level_education', 'children_number', 'lhin', 
            'family_doctor', 'health_card_number', 'health_card_version', 'health_card_exp_date', 
            'health_card_issuing_province', 'no_health_card_reason', 'phone_work', 'phone_alt', 
            'program', 'sub_program', 'level_of_support', 'client_type', 'admission_date', 
            'discharge_date', 'days_elapsed', 'program_status', 'reason_discharge', 
            'referral_source', 'chart_number', 'image', 'profile_picture'
        ]
        
        for field in optional_fields:
            if field in self.fields:
                self.fields[field].required = False
        
        # Add CSS classes to all text input fields
        text_fields = [
            'client_id', 'last_name', 'first_name', 'middle_name', 'preferred_name', 'alias',
            'gender', 'gender_identity', 'pronoun', 'marital_status', 'citizenship_status',
            'location_county', 'province', 'city', 'postal_code', 'address', 'address_2',
            'language', 'preferred_language', 'mother_tongue', 'official_language',
            'self_identification_race_ethnicity', 'aboriginal_status', 'lgbtq_status',
            'highest_level_education', 'lhin', 'family_doctor', 'health_card_number',
            'health_card_version', 'health_card_issuing_province', 'no_health_card_reason',
            'phone', 'phone_work', 'phone_alt', 'email', 'program', 'sub_program',
            'level_of_support', 'client_type', 'program_status', 'reason_discharge',
            'referral_source', 'chart_number', 'primary_diagnosis'
        ]
        
        for field in text_fields:
            if field in self.fields:
                self.fields[field].widget.attrs.update({
                    'class': 'form-control'
                })
        
        # Add CSS classes to number fields
        number_fields = ['age', 'children_number', 'days_elapsed']
        for field in number_fields:
            if field in self.fields:
                self.fields[field].widget.attrs.update({
                    'class': 'form-control',
                    'type': 'number'
                })
        
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
    
    def clean_age(self):
        """Validate age field"""
        age = self.cleaned_data.get('age')
        dob = self.cleaned_data.get('dob')
        
        if age and dob:
            from datetime import date
            today = date.today()
            calculated_age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
            
            # Allow some tolerance for age calculation
            if abs(age - calculated_age) > 1:
                raise forms.ValidationError(f"Age ({age}) doesn't match calculated age from DOB ({calculated_age})")
        
        return age
    
    def clean_health_card_number(self):
        """Validate health card number format"""
        hc_number = self.cleaned_data.get('health_card_number')
        if hc_number:
            # Remove spaces and dashes for validation
            cleaned_hc = hc_number.replace(' ', '').replace('-', '')
            if not cleaned_hc.isalnum():
                raise forms.ValidationError("Health card number should contain only letters and numbers")
        return hc_number
    
    def clean_phone(self):
        """Validate phone number format"""
        phone = self.cleaned_data.get('phone')
        if phone:
            # Remove common phone formatting characters
            cleaned_phone = phone.replace('+', '').replace('-', '').replace('(', '').replace(')', '').replace(' ', '')
            if not cleaned_phone.isdigit() or len(cleaned_phone) < 10:
                raise forms.ValidationError("Please enter a valid phone number (at least 10 digits)")
        return phone
    
    def clean_phone_work(self):
        """Validate work phone number format"""
        phone = self.cleaned_data.get('phone_work')
        if phone:
            cleaned_phone = phone.replace('+', '').replace('-', '').replace('(', '').replace(')', '').replace(' ', '')
            if not cleaned_phone.isdigit() or len(cleaned_phone) < 10:
                raise forms.ValidationError("Please enter a valid work phone number (at least 10 digits)")
        return phone
    
    def clean_phone_alt(self):
        """Validate alternative phone number format"""
        phone = self.cleaned_data.get('phone_alt')
        if phone:
            cleaned_phone = phone.replace('+', '').replace('-', '').replace('(', '').replace(')', '').replace(' ', '')
            if not cleaned_phone.isdigit() or len(cleaned_phone) < 10:
                raise forms.ValidationError("Please enter a valid alternative phone number (at least 10 digits)")
        return phone
    
    def clean_postal_code(self):
        """Validate postal code format"""
        postal_code = self.cleaned_data.get('postal_code')
        if postal_code:
            # Canadian postal code format: A1A 1A1
            import re
            canadian_pattern = r'^[A-Za-z]\d[A-Za-z] \d[A-Za-z]\d$'
            if not re.match(canadian_pattern, postal_code):
                raise forms.ValidationError("Please enter a valid Canadian postal code (e.g., A1A 1A1)")
        return postal_code
    
    def clean_children_number(self):
        """Validate children number"""
        children_number = self.cleaned_data.get('children_number')
        if children_number is not None and children_number < 0:
            raise forms.ValidationError("Number of children cannot be negative")
        return children_number
    
    def clean_days_elapsed(self):
        """Validate days elapsed"""
        days_elapsed = self.cleaned_data.get('days_elapsed')
        if days_elapsed is not None and days_elapsed < 0:
            raise forms.ValidationError("Days elapsed cannot be negative")
        return days_elapsed
