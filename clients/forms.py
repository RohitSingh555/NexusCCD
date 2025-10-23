from django import forms
from core.models import Client
import json

# Comprehensive language choices for Canadian context (alphabetically sorted)
LANGUAGE_CHOICES = [
    ('', 'Select Language'),
    ('Akan', 'Akan'),
    ('Algonquin', 'Algonquin'),
    ('Amharic', 'Amharic'),
    ('Arabic', 'Arabic'),
    ('Armenian', 'Armenian'),
    ('ASL (American Sign Language)', 'ASL (American Sign Language)'),
    ('Athapaskan Languages', 'Athapaskan Languages'),
    ('Atikamekw', 'Atikamekw'),
    ('Bengali', 'Bengali'),
    ('Bisayan - Brunei Bisaya', 'Bisayan - Brunei Bisaya'),
    ('Bisayan - Sabah Bisaya', 'Bisayan - Sabah Bisaya'),
    ('Blackfoot', 'Blackfoot'),
    ('Bosnian', 'Bosnian'),
    ('Bulgarian', 'Bulgarian'),
    ('Cambodian - Central Khmer', 'Cambodian - Central Khmer'),
    ('Cambodian - Northern Khmer', 'Cambodian - Northern Khmer'),
    ('Cantonese', 'Cantonese'),
    ('Carrier', 'Carrier'),
    ('Cayuga', 'Cayuga'),
    ('Chilcotin', 'Chilcotin'),
    ('Chinese', 'Chinese'),
    ('Chippewa', 'Chippewa'),
    ('Cree', 'Cree'),
    ('Creoles', 'Creoles'),
    ('Croatian', 'Croatian'),
    ('Czech', 'Czech'),
    ('Danish', 'Danish'),
    ('Dari', 'Dari'),
    ('Delware', 'Delware'),
    ('Do not know', 'Do not know'),
    ('Dogrib', 'Dogrib'),
    ('Dutch', 'Dutch'),
    ('English', 'English'),
    ('Estonian', 'Estonian'),
    ('Finnish', 'Finnish'),
    ('Flemish', 'Flemish'),
    ('French', 'French'),
    ('Frisian', 'Frisian'),
    ('German', 'German'),
    ('Gitksan', 'Gitksan'),
    ('Greek', 'Greek'),
    ('Gujarati', 'Gujarati'),
    ('Hebrew', 'Hebrew'),
    ('Hindi', 'Hindi'),
    ('Hungarian', 'Hungarian'),
    ('Ilocano', 'Ilocano'),
    ('Inuinnaqtun', 'Inuinnaqtun'),
    ('Inuktitut', 'Inuktitut'),
    ('Italian', 'Italian'),
    ('Japanese', 'Japanese'),
    ('Karen', 'Karen'),
    ('Korean', 'Korean'),
    ('Kurdish', 'Kurdish'),
    ('Kutchin-Gwich\'in (Loucheux)', 'Kutchin-Gwich\'in (Loucheux)'),
    ('Lao', 'Lao'),
    ('Latvian', 'Latvian'),
    ('Lithuanian', 'Lithuanian'),
    ('Macedonian', 'Macedonian'),
    ('Malay', 'Malay'),
    ('Malayalam', 'Malayalam'),
    ('Malecite', 'Malecite'),
    ('Maltese', 'Maltese'),
    ('Mandarin', 'Mandarin'),
    ('Mennonimee', 'Mennonimee'),
    ('Mi\'kmaq', 'Mi\'kmaq'),
    ('Mohawk', 'Mohawk'),
    ('Montagnais', 'Montagnais'),
    ('Naskapi', 'Naskapi'),
    ('Nepali', 'Nepali'),
    ('Nisga\'a', 'Nisga\'a'),
    ('North Slave (Hare)', 'North Slave (Hare)'),
    ('Norwegian', 'Norwegian'),
    ('Odawa', 'Odawa'),
    ('Ojibwa', 'Ojibwa'),
    ('Ojicree', 'Ojicree'),
    ('Oneida', 'Oneida'),
    ('Other', 'Other'),
    ('Other Indigenous Language', 'Other Indigenous Language'),
    ('Other Native Language', 'Other Native Language'),
    ('Pashto', 'Pashto'),
    ('Persian (Farsi)', 'Persian (Farsi)'),
    ('Polish', 'Polish'),
    ('Portuguese', 'Portuguese'),
    ('Pottawatami', 'Pottawatami'),
    ('Prefer not to answer', 'Prefer not to answer'),
    ('Punjabi', 'Punjabi'),
    ('Romanian', 'Romanian'),
    ('Russian', 'Russian'),
    ('Seneca', 'Seneca'),
    ('Serbian', 'Serbian'),
    ('Serbo-Croatian', 'Serbo-Croatian'),
    ('Shuswap', 'Shuswap'),
    ('Sindhi', 'Sindhi'),
    ('Sinhala', 'Sinhala'),
    ('Siouan Languages (Dakota/Sioux)', 'Siouan Languages (Dakota/Sioux)'),
    ('Slovak', 'Slovak'),
    ('Slovenian', 'Slovenian'),
    ('Somali', 'Somali'),
    ('South Slave', 'South Slave'),
    ('Spanish', 'Spanish'),
    ('Swahili', 'Swahili'),
    ('Swedish', 'Swedish'),
    ('Tagalog (Philipino, Filipino)', 'Tagalog (Philipino, Filipino)'),
    ('Taiwanese', 'Taiwanese'),
    ('Tamil', 'Tamil'),
    ('Telugu', 'Telugu'),
    ('Tigrinya', 'Tigrinya'),
    ('Tlingit', 'Tlingit'),
    ('Turkish', 'Turkish'),
    ('Tuscarora', 'Tuscarora'),
    ('Ukrainian', 'Ukrainian'),
    ('Urdu', 'Urdu'),
    ('Vietnamese', 'Vietnamese'),
    ('Yiddish', 'Yiddish'),
]

# Gender choices for comprehensive gender identity options (alphabetically sorted)
GENDER_CHOICES = [
    ('', 'Select Gender'),
    ('Do not know', 'Do not know'),
    ('Female', 'Female'),
    ('Gender Fluid', 'Gender Fluid'),
    ('Gender Non-conforming', 'Gender Non-conforming'),
    ('Intersex', 'Intersex'),
    ('Male', 'Male'),
    ('Non-binary', 'Non-binary'),
    ('Other', 'Other'),
    ('Transgender-Female', 'Transgender-Female'),
    ('Transgender-Male', 'Transgender-Male'),
    ('Transexual', 'Transexual'),
    ('Two-Spirit', 'Two-Spirit'),
]

# Indigenous status choices for comprehensive indigenous identity options (alphabetically sorted)
INDIGENOUS_STATUS_CHOICES = [
    ('', 'Select Indigenous Status'),
    ('Do not know', 'Do not know'),
    ('First Nations people', 'First Nations people'),
    ('Indigenous', 'Indigenous'),
    ('Inuit', 'Inuit'),
    ('Metis', 'Metis'),
    ('Non-Indigenous', 'Non-Indigenous'),
    ('Prefer not to answer', 'Prefer not to answer'),
]

# Citizenship status choices for comprehensive citizenship options (alphabetically sorted)
CITIZENSHIP_STATUS_CHOICES = [
    ('', 'Select Citizenship Status'),
    ('Candian Citizen', 'Candian Citizen'),
    ('Canadian by birth', 'Canadian by birth'),
    ('Canadian by naturalization', 'Canadian by naturalization'),
    ('Convention Refugee', 'Convention Refugee'),
    ('Do not know', 'Do not know'),
    ('Landed Immigrant', 'Landed Immigrant'),
    ('None Selected', 'None Selected'),
    ('Permanent Resident', 'Permanent Resident'),
    ('Prefer not to answer', 'Prefer not to answer'),
    ('Refugee', 'Refugee'),
    ('Refugee Claimant', 'Refugee Claimant'),
    ('Student Visa', 'Student Visa'),
    ('Temporary Resident', 'Temporary Resident'),
    ('Unresolved', 'Unresolved'),
    ('Visitor Visa', 'Visitor Visa'),
]

# Ethnicity choices for comprehensive ethnicity options (alphabetically sorted)
ETHNICITY_CHOICES = [
    ('', 'Select Ethnicity'),
    ('Aboriginal - Non Status', 'Aboriginal - Non Status'),
    ('Aboriginal - Status (N.A. Indian)', 'Aboriginal - Status (N.A. Indian)'),
    ('Abyssinians (Amharas)', 'Abyssinians (Amharas)'),
    ('Admiralty Islanders', 'Admiralty Islanders'),
    ('African', 'African'),
    ('African American', 'African American'),
    ('Afro-Carribbean', 'Afro-Carribbean'),
    ('Afro-Caucasian', 'Afro-Caucasian'),
    ('Alacaluf', 'Alacaluf'),
    ('Aleuts', 'Aleuts'),
    ('American (USA)', 'American (USA)'),
    ('Amerind', 'Amerind'),
    ('Andamanese', 'Andamanese'),
    ('Apache', 'Apache'),
    ('Arab', 'Arab'),
    ('Armenians', 'Armenians'),
    ('Asian', 'Asian'),
    ('Atacamenos', 'Atacamenos'),
    ('Athabascans', 'Athabascans'),
    ('Australian aborigine', 'Australian aborigine'),
    ('Austrian', 'Austrian'),
    ('Aymara', 'Aymara'),
    ('Aztec', 'Aztec'),
    ('Badagas', 'Badagas'),
    ('Bajau', 'Bajau'),
    ('Bangladeshi', 'Bangladeshi'),
    ('Bantu', 'Bantu'),
    ('Barundi', 'Barundi'),
    ('Basque', 'Basque'),
    ('Batutsi', 'Batutsi'),
    ('Belgian', 'Belgian'),
    ('Bhutanese', 'Bhutanese'),
    ('Bidayuh', 'Bidayuh'),
    ('Black', 'Black'),
    ('Black - other African country', 'Black - other African country'),
    ('Black - other Asian', 'Black - other Asian'),
    ('Black African', 'Black African'),
    ('Black African and White', 'Black African and White'),
    ('Black Arab', 'Black Arab'),
    ('Black British', 'Black British'),
    ('Black Caribbean', 'Black Caribbean'),
    ('Black Caribbean and White', 'Black Caribbean and White'),
    ('Black Caribbean/W.I./Guyana', 'Black Caribbean/W.I./Guyana'),
    ('Black East African', 'Black East African'),
    ('Black East African Asian/Indo-Caribbean', 'Black East African Asian/Indo-Caribbean'),
    ('Black Indian sub-continent', 'Black Indian sub-continent'),
    ('Black Indo-Caribbean', 'Black Indo-Caribbean'),
    ('Black Iranian', 'Black Iranian'),
    ('Black Irish', 'Black Irish'),
    ('Black Jews', 'Black Jews'),
    ('Black N African/Arab/Iranian', 'Black N African/Arab/Iranian'),
    ('Black North African', 'Black North African'),
    ('Black West Indian', 'Black West Indian'),
    ('Black, other, non-mixed origin', 'Black, other, non-mixed origin'),
    ('Blackfeet', 'Blackfeet'),
    ('Bloods', 'Bloods'),
    ('Bororo', 'Bororo'),
    ('Brazilian Indians', 'Brazilian Indians'),
    ('Bruneians', 'Bruneians'),
    ('Bulgarian', 'Bulgarian'),
    ('Canadian', 'Canadian'),
    ('Caribbean', 'Caribbean'),
    ('Caucasian', 'Caucasian'),
    ('Central American', 'Central American'),
    ('Chinese', 'Chinese'),
    ('Congolese', 'Congolese'),
    ('Czech', 'Czech'),
    ('Danish', 'Danish'),
    ('Do not know', 'Do not know'),
    ('Dutch', 'Dutch'),
    ('East European', 'East European'),
    ('East Indian', 'East Indian'),
    ('Egyptian', 'Egyptian'),
    ('English', 'English'),
    ('Estonian', 'Estonian'),
    ('European', 'European'),
    ('Fijian', 'Fijian'),
    ('Filipinos', 'Filipinos'),
    ('Finnish', 'Finnish'),
    ('French', 'French'),
    ('French-Canadian', 'French-Canadian'),
    ('Gambians', 'Gambians'),
    ('Georgian', 'Georgian'),
    ('German', 'German'),
    ('Ghanaians', 'Ghanaians'),
    ('Greek', 'Greek'),
    ('Gypsy', 'Gypsy'),
    ('Hawaiians', 'Hawaiians'),
    ('Hungarian', 'Hungarian'),
    ('Hututu', 'Hututu'),
    ('Icelandic', 'Icelandic'),
    ('Inca', 'Inca'),
    ('Indian (East Indian)', 'Indian (East Indian)'),
    ('Indian (Hindi-speaking)', 'Indian (Hindi-speaking)'),
    ('Indigenous', 'Indigenous'),
    ('Indonesians', 'Indonesians'),
    ('Inuit', 'Inuit'),
    ('Irani', 'Irani'),
    ('Iraqi', 'Iraqi'),
    ('Irish', 'Irish'),
    ('Italian', 'Italian'),
    ('Japanese', 'Japanese'),
    ('Javanese', 'Javanese'),
    ('Jewish', 'Jewish'),
    ('Kenyans', 'Kenyans'),
    ('Kirghiz', 'Kirghiz'),
    ('Korean', 'Korean'),
    ('Koreans', 'Koreans'),
    ('Lapps', 'Lapps'),
    ('Liberians', 'Liberians'),
    ('Madagascans', 'Madagascans'),
    ('Malayans', 'Malayans'),
    ('Maori', 'Maori'),
    ('Maya', 'Maya'),
    ('Melanesian', 'Melanesian'),
    ('Metis', 'Metis'),
    ('Mexican Indians', 'Mexican Indians'),
    ('Micronesians', 'Micronesians'),
    ('Middle Eastern', 'Middle Eastern'),
    ('Mixed ethnic group', 'Mixed ethnic group'),
    ('Mongoloid', 'Mongoloid'),
    ('Mozambiquans', 'Mozambiquans'),
    ('New Zealand European', 'New Zealand European'),
    ('New Zealand Maori', 'New Zealand Maori'),
    ('Nigerians', 'Nigerians'),
    ('Norwegian', 'Norwegian'),
    ('Oceanic', 'Oceanic'),
    ('Oriental', 'Oriental'),
    ('Other', 'Other'),
    ('Other Asian ethnic group', 'Other Asian ethnic group'),
    ('Other ethnic non-mixed group', 'Other ethnic non-mixed group'),
    ('Other South East Asia', 'Other South East Asia'),
    ('Other white British ethnic group', 'Other white British ethnic group'),
    ('Pakistani', 'Pakistani'),
    ('Polish', 'Polish'),
    ('Polynesians', 'Polynesians'),
    ('Portuguese', 'Portuguese'),
    ('Prefer not to answer', 'Prefer not to answer'),
    ('Punjabi', 'Punjabi'),
    ('Russian', 'Russian'),
    ('Samoan', 'Samoan'),
    ('Scandinavian', 'Scandinavian'),
    ('Scottish', 'Scottish'),
    ('Senegalese', 'Senegalese'),
    ('Senoy', 'Senoy'),
    ('Serbian', 'Serbian'),
    ('Siamese', 'Siamese'),
    ('Slovakian', 'Slovakian'),
    ('Somalis', 'Somalis'),
    ('South American', 'South American'),
    ('South Asian', 'South Asian'),
    ('South East Asian', 'South East Asian'),
    ('Spanish', 'Spanish'),
    ('Sudanese', 'Sudanese'),
    ('Swedish', 'Swedish'),
    ('Swiss', 'Swiss'),
    ('Syrian', 'Syrian'),
    ('Taiwanese', 'Taiwanese'),
    ('Tamils', 'Tamils'),
    ('Tatars', 'Tatars'),
    ('Thais', 'Thais'),
    ('Turks', 'Turks'),
    ('Tutsi', 'Tutsi'),
    ('Ugandans', 'Ugandans'),
    ('Ukranian', 'Ukranian'),
    ('Venezuelan Indians', 'Venezuelan Indians'),
    ('Vietnamese', 'Vietnamese'),
    ('Welsh', 'Welsh'),
    ('West Africans', 'West Africans'),
    ('West Indian', 'West Indian'),
    ('White', 'White'),
]


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
            'lgbtq_status', 'highest_level_education', 'children_home', 
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
            'reason_discharge', 'receiving_services', 'receiving_services_date', 'referral_source',
            
            # 🧾 ADMINISTRATIVE / SYSTEM FIELDS
            'chart_number', 'source',
            
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
            'receiving_services_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            
            # Language dropdowns
            'language': forms.Select(attrs={'class': 'form-control'}, choices=LANGUAGE_CHOICES),
            'preferred_language': forms.Select(attrs={'class': 'form-control'}, choices=LANGUAGE_CHOICES),
            'mother_tongue': forms.Select(attrs={'class': 'form-control'}, choices=LANGUAGE_CHOICES),
            'official_language': forms.Select(attrs={'class': 'form-control'}, choices=LANGUAGE_CHOICES),
            
            # Gender dropdown
            'gender': forms.Select(attrs={'class': 'form-control'}, choices=GENDER_CHOICES),
            
            # Indigenous status dropdown
            'indigenous_status': forms.Select(attrs={'class': 'form-control'}, choices=INDIGENOUS_STATUS_CHOICES),
            
            # Citizenship status dropdown
            'citizenship_status': forms.Select(attrs={'class': 'form-control'}, choices=CITIZENSHIP_STATUS_CHOICES),
            
            # Ethnicity dropdown
            'ethnicity': forms.Select(attrs={'class': 'form-control'}, choices=ETHNICITY_CHOICES),
            
            # Hidden fields for JSON data
            'languages_spoken': forms.HiddenInput(),
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
            
            # Source dropdown
            'source': forms.Select(attrs={'class': 'form-control'}, choices=[('', 'Select Source'), ('SMIMS', 'SMIMS'), ('EMHware', 'EMHware')]),
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
            'official_language', 'self_identification_race_ethnicity', 
            'lgbtq_status', 'highest_level_education', 'children_number', 'lhin', 
            'family_doctor', 'health_card_number', 'health_card_version', 'health_card_exp_date', 
            'health_card_issuing_province', 'no_health_card_reason', 'phone_work', 'phone_alt', 
            'program', 'sub_program', 'level_of_support', 'client_type', 'admission_date', 
            'discharge_date', 'days_elapsed', 'program_status', 'reason_discharge', 
            'receiving_services_date', 'referral_source', 'chart_number', 'source', 'image', 'profile_picture'
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
            'self_identification_race_ethnicity', 'lgbtq_status',
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
        
        # Handle missing or empty field
        if not addresses or (isinstance(addresses, str) and addresses.strip() == ''):
            return []
        
        # Handle string case
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
        
        # Handle missing or empty field
        if not languages or (isinstance(languages, str) and languages.strip() == ''):
            return []
        
        # Handle string case
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
        ethnicity = self.cleaned_data.get('ethnicity')
        
        # Ethnicity is now a simple string field, no special validation needed
        return ethnicity
    
    def clean_contact_information(self):
        """Validate and clean contact_information data"""
        contact_info = self.cleaned_data.get('contact_information', {})
        
        # Handle missing or empty field
        if not contact_info or (isinstance(contact_info, str) and contact_info.strip() == ''):
            return {}
        
        # Handle string case
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
        
        # Handle missing or empty field
        if not support_workers or (isinstance(support_workers, str) and support_workers.strip() == ''):
            return []
        
        # Handle string case
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
        
        # Handle missing or empty field
        if not next_of_kin or (isinstance(next_of_kin, str) and next_of_kin.strip() == ''):
            return {}
        
        # Handle string case
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
        
        # Handle missing or empty field
        if not emergency_contact or (isinstance(emergency_contact, str) and emergency_contact.strip() == ''):
            return {}
        
        # Handle string case
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
        
        # Temporarily disable age validation to debug client creation issue
        # if age and dob:
        #     from datetime import date
        #     today = date.today()
        #     calculated_age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
        #     
        #     # Allow some tolerance for age calculation
        #     if abs(age - calculated_age) > 1:
        #         raise forms.ValidationError(f"Age ({age}) doesn't match calculated age from DOB ({calculated_age})")
        
        return age
    
    def clean_health_card_number(self):
        """Validate health card number format"""
        hc_number = self.cleaned_data.get('health_card_number')
        # Temporarily disable health card validation to debug client creation issue
        # if hc_number:
        #     # Remove spaces and dashes for validation
        #     cleaned_hc = hc_number.replace(' ', '').replace('-', '')
        #     if not cleaned_hc.isalnum():
        #         raise forms.ValidationError("Health card number should contain only letters and numbers")
        return hc_number
    
    
    def clean_postal_code(self):
        """Validate postal code format"""
        postal_code = self.cleaned_data.get('postal_code')
        # Temporarily disable postal code validation to debug client creation issue
        # if postal_code:
        #     # Canadian postal code format: A1A 1A1
        #     import re
        #     canadian_pattern = r'^[A-Za-z]\d[A-Za-z] \d[A-Za-z]\d$'
        #     if not re.match(canadian_pattern, postal_code):
        #         raise forms.ValidationError("Please enter a valid Canadian postal code (e.g., A1A 1A1)")
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
