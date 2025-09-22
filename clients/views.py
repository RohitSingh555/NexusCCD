from django.shortcuts import render, get_object_or_404
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, TemplateView
from django.urls import reverse_lazy
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_protect
from django.utils.decorators import method_decorator
from django.db.models import Q
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from core.models import Client, Program, Department, Intake, ClientProgramEnrollment, ClientDuplicate
from core.fuzzy_matching import fuzzy_matcher
from .forms import ClientForm
import pandas as pd
import json
import uuid
from datetime import datetime
import logging
from django.http import HttpResponse
from django.views.decorators.http import require_http_methods

logger = logging.getLogger(__name__)

class ClientListView(ListView):
    model = Client
    template_name = 'clients/client_list.html'
    context_object_name = 'clients'
    paginate_by = 10

class ClientDetailView(DetailView):
    model = Client
    template_name = 'clients/client_detail.html'
    context_object_name = 'client'
    slug_field = 'external_id'
    slug_url_kwarg = 'external_id'

class ClientCreateView(CreateView):
    model = Client
    form_class = ClientForm
    template_name = 'clients/client_form.html'
    success_url = reverse_lazy('clients:list')
    
    def form_valid(self, form):
        client = form.save(commit=False)
        
        # Check for potential duplicates using fuzzy matching
        client_data = {
            'first_name': client.first_name,
            'last_name': client.last_name,
            'email': client.email,
            'phone': client.phone,
        }
        
        # Only check for duplicates if no unique identifiers (email/phone)
        if not client.email and not client.phone:
            existing_clients = Client.objects.exclude(id=client.id)
            potential_duplicates = fuzzy_matcher.find_potential_duplicates(
                client_data, existing_clients, similarity_threshold=0.7
            )
            
            if potential_duplicates:
                # Create duplicate warnings for manual review
                for duplicate_client, match_type, similarity in potential_duplicates:
                    confidence_level = fuzzy_matcher.get_duplicate_confidence_level(similarity)
                    
                    # Create or update duplicate record
                    ClientDuplicate.objects.update_or_create(
                        primary_client=duplicate_client,
                        duplicate_client=client,
                        defaults={
                            'similarity_score': similarity,
                            'match_type': match_type,
                            'confidence_level': confidence_level,
                            'match_details': {
                                'primary_name': f"{duplicate_client.first_name} {duplicate_client.last_name}",
                                'duplicate_name': f"{client.first_name} {client.last_name}",
                                'primary_email': duplicate_client.email,
                                'primary_phone': duplicate_client.phone,
                            }
                        }
                    )
                
                messages.warning(
                    self.request, 
                    f'Client created with potential duplicates detected. Please review the Probable Duplicate Clients page.'
                )
            else:
                messages.success(self.request, 'Client created successfully.')
        else:
            messages.success(self.request, 'Client created successfully.')
        
        client.save()
        return super().form_valid(form)

class ClientUpdateView(UpdateView):
    model = Client
    form_class = ClientForm
    template_name = 'clients/client_form.html'
    slug_field = 'external_id'
    slug_url_kwarg = 'external_id'
    success_url = reverse_lazy('clients:list')
    
    def form_valid(self, form):
        messages.success(self.request, 'Client updated successfully.')
        return super().form_valid(form)

class ClientDeleteView(DeleteView):
    model = Client
    template_name = 'clients/client_confirm_delete.html'
    slug_field = 'external_id'
    slug_url_kwarg = 'external_id'
    success_url = reverse_lazy('clients:list')

class ClientUploadView(TemplateView):
    template_name = 'clients/client_upload.html'

@method_decorator(csrf_exempt, name='dispatch')
@require_http_methods(["POST"])
def upload_clients(request):
    """Handle CSV/Excel file upload and process client data"""
    try:
        if 'file' not in request.FILES:
            return JsonResponse({'success': False, 'error': 'No file provided'}, status=400)
        
        file = request.FILES['file']
        file_extension = file.name.split('.')[-1].lower()
        
        if file_extension not in ['csv', 'xlsx', 'xls']:
            return JsonResponse({'success': False, 'error': 'Invalid file format. Please upload CSV or Excel files.'}, status=400)
        
        # Read the file
        try:
            if file_extension == 'csv':
                df = pd.read_csv(file)
            else:
                df = pd.read_excel(file)
        except Exception as e:
            return JsonResponse({'success': False, 'error': f'Error reading file: {str(e)}'}, status=400)
        
        # Validate required columns
        required_columns = ['first_name', 'last_name', 'email', 'phone_number']
        missing_columns = [col for col in required_columns if col not in df.columns]
        
        if missing_columns:
            return JsonResponse({
                'success': False, 
                'error': f'Missing required columns: {", ".join(missing_columns)}'
            }, status=400)
        
        # Check for intake-related columns
        has_intake_data = any(col in df.columns for col in ['program_name', 'source', 'intake_date'])
        
        # Process the data
        created_count = 0
        updated_count = 0
        skipped_count = 0
        errors = []
        duplicate_details = []  # Track duplicate details for user feedback
        
        def normalize_name(name):
            """Normalize name for comparison"""
            if not name:
                return ""
            return " ".join(name.lower().split())
        
        def calculate_name_similarity(name1, name2):
            """Calculate similarity between two names (0-1 scale)"""
            if not name1 or not name2:
                return 0
            
            name1_norm = normalize_name(name1)
            name2_norm = normalize_name(name2)
            
            if name1_norm == name2_norm:
                return 1.0
            
            # Simple similarity check - if one name contains the other
            if name1_norm in name2_norm or name2_norm in name1_norm:
                return 0.8
            
            # Check for common words
            words1 = set(name1_norm.split())
            words2 = set(name2_norm.split())
            if words1 and words2:
                common_words = len(words1.intersection(words2))
                total_words = len(words1.union(words2))
                return common_words / total_words if total_words > 0 else 0
            
            return 0
        
        def _is_duplicate_data(existing_client, new_data):
            """Check if the new data is essentially the same as existing client data"""
            # Compare key fields to determine if this is truly a duplicate
            key_fields = ['first_name', 'last_name', 'preferred_name', 'alias', 'gender', 
                         'sexual_orientation', 'citizenship_status', 'dob']
            
            for field in key_fields:
                existing_value = getattr(existing_client, field, None)
                new_value = new_data.get(field, None)
                
                # Handle date comparison
                if field == 'dob':
                    if existing_value and new_value:
                        if existing_value != new_value:
                            return False
                    elif existing_value != new_value:  # One is None, other isn't
                        return False
                else:
                    # Handle string comparison
                    existing_str = str(existing_value or '').strip()
                    new_str = str(new_value or '').strip()
                    if existing_str != new_str:
                        return False
            
            # Compare languages_spoken
            existing_languages = set(existing_client.languages_spoken or [])
            new_languages = set(new_data.get('languages_spoken', []))
            if existing_languages != new_languages:
                return False
            
            # Compare addresses (simplified comparison)
            existing_addresses = existing_client.addresses or []
            new_addresses = new_data.get('addresses', [])
            if len(existing_addresses) != len(new_addresses):
                return False
            
            # Compare contact information
            existing_contact = existing_client.contact_information or {}
            new_contact = new_data.get('contact_information', {})
            if existing_contact.get('email') != new_contact.get('email'):
                return False
            if existing_contact.get('phone') != new_contact.get('phone'):
                return False
            
            # If we get here, the data is essentially the same
            return True
        
        def process_intake_data(client, row, index):
            """Process intake data for a client"""
            try:
                program_name = str(row.get('program_name', '')).strip() if pd.notna(row.get('program_name', '')) else ''
                program_department = str(row.get('program_department', '')).strip() if pd.notna(row.get('program_department', '')) else ''
                source = str(row.get('source', '')).strip() if pd.notna(row.get('source', '')) else 'SMIS'
                intake_date = pd.to_datetime(row.get('intake_date', datetime.now().date())).date() if pd.notna(row.get('intake_date', '')) else datetime.now().date()
                intake_database = str(row.get('intake_database', '')).strip() if pd.notna(row.get('intake_database', '')) else 'CCD'
                referral_source = str(row.get('referral_source', '')).strip() if pd.notna(row.get('referral_source', '')) else source
                intake_housing_status = str(row.get('intake_housing_status', '')).strip() if pd.notna(row.get('intake_housing_status', '')) else 'unknown'
                
                if not program_name:
                    logger.warning(f"No program name provided for client {client.first_name} {client.last_name}")
                    return
                
                # Get or create department
                department = None
                if program_department:
                    department, created = Department.objects.get_or_create(
                        name=program_department,
                        defaults={'owner': 'System'}
                    )
                    if created:
                        logger.info(f"Created new department: {program_department}")
                else:
                    # Default to Social Services if no department specified
                    department, created = Department.objects.get_or_create(
                        name='Social Services',
                        defaults={'owner': 'System'}
                    )
                
                # Get or create program
                program, created = Program.objects.get_or_create(
                    name=program_name,
                    department=department,
                    defaults={
                        'location': 'TBD',
                        'status': 'suggested' if created else 'active',
                        'description': f'Program created from intake data - {source}'
                    }
                )
                
                if created:
                    logger.info(f"Created new program: {program_name} (status: suggested)")
                else:
                    # If program exists but is suggested, keep it as suggested
                    if program.status == 'suggested':
                        logger.info(f"Program {program_name} already exists with suggested status")
                
                # Create intake record
                intake, created = Intake.objects.get_or_create(
                    client=client,
                    program=program,
                    defaults={
                        'department': department,
                        'intake_date': intake_date,
                        'intake_database': intake_database,
                        'referral_source': referral_source,
                        'intake_housing_status': intake_housing_status,
                        'notes': f'Intake created from {source} upload'
                    }
                )
                
                if created:
                    logger.info(f"Created intake record for {client.first_name} {client.last_name} in {program_name}")
                else:
                    logger.info(f"Intake record already exists for {client.first_name} {client.last_name} in {program_name}")
                
                # Create enrollment with pending status
                enrollment, created = ClientProgramEnrollment.objects.get_or_create(
                    client=client,
                    program=program,
                    defaults={
                        'start_date': intake_date,
                        'status': 'pending',
                        'notes': f'Enrollment created from {source} intake'
                    }
                )
                
                if created:
                    logger.info(f"Created pending enrollment for {client.first_name} {client.last_name} in {program_name}")
                else:
                    logger.info(f"Enrollment already exists for {client.first_name} {client.last_name} in {program_name}")
                    
            except Exception as e:
                logger.error(f"Error processing intake data for row {index + 2}: {str(e)}")
                errors.append(f"Row {index + 2} (Intake): {str(e)}")
        
        def find_duplicate_client(client_data):
            """Find duplicate client based on email, phone, and name similarity"""
            contact_info = client_data.get('contact_information', {})
            email = contact_info.get('email', '').strip()
            phone = contact_info.get('phone', '').strip()
            full_name = f"{client_data.get('first_name', '')} {client_data.get('last_name', '')}".strip()
            
            # Priority 1: Exact email match
            if email:
                exact_email_match = Client.objects.filter(
                    contact_information__email=email
                ).first()
                if exact_email_match:
                    return exact_email_match, "exact_email"
            
            # Priority 2: Exact phone match
            if phone:
                exact_phone_match = Client.objects.filter(
                    contact_information__phone=phone
                ).first()
                if exact_phone_match:
                    return exact_phone_match, "exact_phone"
            
            # Priority 3: Email and phone combination (if both provided)
            if email and phone:
                email_phone_match = Client.objects.filter(
                    contact_information__email=email,
                    contact_information__phone=phone
                ).first()
                if email_phone_match:
                    return email_phone_match, "email_phone"
            
            # Priority 4: Name similarity check (only if name is provided and similar enough)
            if full_name:
                # Get all clients to check name similarity
                all_clients = Client.objects.all()
                for client in all_clients:
                    client_full_name = f"{client.first_name} {client.last_name}".strip()
                    similarity = calculate_name_similarity(full_name, client_full_name)
                    
                    # If names are very similar (80%+ similarity), consider it a duplicate
                    if similarity >= 0.8:
                        return client, f"name_similarity_{similarity:.2f}"
            
            return None, None
        
        for index, row in df.iterrows():
            try:
                # Clean and prepare data
                email = str(row['email']).strip() if pd.notna(row['email']) else ''
                phone = str(row['phone_number']).strip() if pd.notna(row['phone_number']) else ''
                
                # Handle date of birth with default
                try:
                    if pd.notna(row['dob']) and str(row['dob']).strip():
                        dob = pd.to_datetime(row['dob']).date()
                    else:
                        # Default to 1900-01-01 if no date provided
                        dob = datetime(1900, 1, 1).date()
                except:
                    # If date parsing fails, use default
                    dob = datetime(1900, 1, 1).date()
                
                client_data = {
                    'first_name': str(row['first_name']).strip() if pd.notna(row['first_name']) else '',
                    'last_name': str(row['last_name']).strip() if pd.notna(row['last_name']) else '',
                    'dob': dob,
                    'preferred_name': str(row.get('preferred_name', '')).strip() if pd.notna(row.get('preferred_name', '')) else '',
                    'alias': str(row.get('alias', '')).strip() if pd.notna(row.get('alias', '')) else '',
                    'gender': str(row.get('gender', '')).strip() if pd.notna(row.get('gender', '')) else 'Unknown',
                    'sexual_orientation': str(row.get('sexual_orientation', '')).strip() if pd.notna(row.get('sexual_orientation', '')) else '',
                    'citizenship_status': str(row.get('immigration_status', '')).strip() if pd.notna(row.get('immigration_status', '')) else '',
                    'contact_information': {
                        'email': email,
                        'phone': phone,
                    }
                }
                
                # Handle languages_spoken (expect comma-separated string)
                languages = str(row.get('languages_spoken', '')).strip() if pd.notna(row.get('languages_spoken', '')) else ''
                if languages:
                    client_data['languages_spoken'] = [lang.strip() for lang in languages.split(',') if lang.strip()]
                else:
                    client_data['languages_spoken'] = []
                
                # Handle addresses (expect JSON string or individual address fields)
                addresses = []
                if 'addresses' in row and pd.notna(row['addresses']):
                    try:
                        addresses = json.loads(str(row['addresses']))
                    except:
                        addresses = []
                elif 'street' in row and pd.notna(row['street']):
                    address = {
                        'type': str(row.get('address_type', 'Home')).strip(),
                        'street': str(row['street']).strip(),
                        'city': str(row.get('city', '')).strip(),
                        'state': str(row.get('state', '')).strip(),
                        'zip': str(row.get('zip', '')).strip(),
                        'country': str(row.get('country', 'USA')).strip()
                    }
                    if any(address.values()):
                        addresses = [address]
                
                client_data['addresses'] = addresses
                
                # Check for duplicates using our custom logic
                duplicate_client, match_type = find_duplicate_client(client_data)
                client = None  # Initialize client variable
                is_duplicate = False  # Initialize is_duplicate variable
                
                # Always create the client first
                client = Client.objects.create(**client_data)
                created_count += 1
                logger.info(f"Created new client: {client.email or client.phone}")
                
                # If we found a potential duplicate, create a duplicate relationship for review
                if duplicate_client:
                    client_name = f"{client_data.get('first_name', '')} {client_data.get('last_name', '')}".strip()
                    existing_name = f"{duplicate_client.first_name} {duplicate_client.last_name}".strip()
                    
                    if match_type == "exact_email":
                        # Check if this is actually a duplicate (same data) or different data
                        is_duplicate = _is_duplicate_data(duplicate_client, client_data)
                        
                        if is_duplicate:
                            # Same data - create duplicate relationship for review
                            similarity = 1.0  # 100% match
                            confidence_level = fuzzy_matcher.get_duplicate_confidence_level(similarity)
                            
                            ClientDuplicate.objects.update_or_create(
                                primary_client=duplicate_client,
                                duplicate_client=client,
                                defaults={
                                    'similarity_score': similarity,
                                    'match_type': 'exact_email',
                                    'confidence_level': confidence_level,
                                    'match_details': {
                                        'primary_name': f"{duplicate_client.first_name} {duplicate_client.last_name}",
                                        'duplicate_name': f"{client.first_name} {client.last_name}",
                                        'primary_email': duplicate_client.email,
                                        'primary_phone': duplicate_client.phone,
                                    }
                                }
                            )
                            
                            duplicate_details.append({
                                'type': 'created_with_duplicate',
                                'reason': 'Exact email match - created with duplicate flag',
                                'client_name': client_name,
                                'existing_name': existing_name,
                                'match_field': f"Email: {duplicate_client.email}"
                            })
                            logger.info(f"Created client with exact email duplicate flag: {duplicate_client.email}")
                        else:
                            # Different data - update existing client instead of creating new one
                            client.delete()  # Remove the newly created client
                            created_count -= 1  # Adjust count
                            
                            for key, value in client_data.items():
                                if key not in ['contact_information']:  # Don't update contact info
                                    setattr(duplicate_client, key, value)
                            duplicate_client.save()
                            client = duplicate_client  # Set client for intake processing
                            updated_count += 1
                            duplicate_details.append({
                                'type': 'updated',
                                'reason': 'Exact email match (updated data)',
                                'client_name': client_name,
                                'existing_name': existing_name,
                                'match_field': f"Email: {duplicate_client.email}"
                            })
                            logger.info(f"Updated client by exact email match: {duplicate_client.email}")
                    elif match_type == "exact_phone":
                        # Check if this is actually a duplicate (same data) or different data
                        is_duplicate = _is_duplicate_data(duplicate_client, client_data)
                        
                        if is_duplicate:
                            # Same data - create duplicate relationship for review
                            similarity = 1.0  # 100% match
                            confidence_level = fuzzy_matcher.get_duplicate_confidence_level(similarity)
                            
                            ClientDuplicate.objects.update_or_create(
                                primary_client=duplicate_client,
                                duplicate_client=client,
                                defaults={
                                    'similarity_score': similarity,
                                    'match_type': 'exact_phone',
                                    'confidence_level': confidence_level,
                                    'match_details': {
                                        'primary_name': f"{duplicate_client.first_name} {duplicate_client.last_name}",
                                        'duplicate_name': f"{client.first_name} {client.last_name}",
                                        'primary_email': duplicate_client.email,
                                        'primary_phone': duplicate_client.phone,
                                    }
                                }
                            )
                            
                            duplicate_details.append({
                                'type': 'created_with_duplicate',
                                'reason': 'Exact phone match - created with duplicate flag',
                                'client_name': client_name,
                                'existing_name': existing_name,
                                'match_field': f"Phone: {duplicate_client.phone}"
                            })
                            logger.info(f"Created client with exact phone duplicate flag: {duplicate_client.phone}")
                        else:
                            # Different data - update existing client instead of creating new one
                            client.delete()  # Remove the newly created client
                            created_count -= 1  # Adjust count
                            
                            for key, value in client_data.items():
                                if key not in ['contact_information']:  # Don't update contact info
                                    setattr(duplicate_client, key, value)
                            duplicate_client.save()
                            client = duplicate_client  # Set client for intake processing
                            updated_count += 1
                            duplicate_details.append({
                                'type': 'updated',
                                'reason': 'Exact phone match (updated data)',
                                'client_name': client_name,
                                'existing_name': existing_name,
                                'match_field': f"Phone: {duplicate_client.phone}"
                            })
                            logger.info(f"Updated client by exact phone match: {duplicate_client.phone}")
                    elif match_type.startswith("email_phone"):
                        # Check if this is actually a duplicate (same data) or different data
                        is_duplicate = _is_duplicate_data(duplicate_client, client_data)
                        
                        if is_duplicate:
                            # Same data - create duplicate relationship for review
                            similarity = 1.0  # 100% match
                            confidence_level = fuzzy_matcher.get_duplicate_confidence_level(similarity)
                            
                            ClientDuplicate.objects.update_or_create(
                                primary_client=duplicate_client,
                                duplicate_client=client,
                                defaults={
                                    'similarity_score': similarity,
                                    'match_type': 'email_phone',
                                    'confidence_level': confidence_level,
                                    'match_details': {
                                        'primary_name': f"{duplicate_client.first_name} {duplicate_client.last_name}",
                                        'duplicate_name': f"{client.first_name} {client.last_name}",
                                        'primary_email': duplicate_client.email,
                                        'primary_phone': duplicate_client.phone,
                                    }
                                }
                            )
                            
                            duplicate_details.append({
                                'type': 'created_with_duplicate',
                                'reason': 'Email and phone match - created with duplicate flag',
                                'client_name': client_name,
                                'existing_name': existing_name,
                                'match_field': f"Email: {duplicate_client.email}, Phone: {duplicate_client.phone}"
                            })
                            logger.info(f"Created client with email+phone duplicate flag: {duplicate_client.email}")
                        else:
                            # Different data - update existing client instead of creating new one
                            client.delete()  # Remove the newly created client
                            created_count -= 1  # Adjust count
                            
                            for key, value in client_data.items():
                                if key not in ['contact_information']:  # Don't update contact info
                                    setattr(duplicate_client, key, value)
                            duplicate_client.save()
                            client = duplicate_client  # Set client for intake processing
                            updated_count += 1
                            duplicate_details.append({
                                'type': 'updated',
                                'reason': 'Email and phone match (updated data)',
                                'client_name': client_name,
                                'existing_name': existing_name,
                                'match_field': f"Email: {duplicate_client.email}, Phone: {duplicate_client.phone}"
                            })
                            logger.info(f"Updated client by email+phone match: {duplicate_client.email}")
                    elif match_type.startswith("name_similarity"):
                        # Create duplicate relationship for name similarity
                        similarity = float(match_type.split('_')[-1])
                        confidence_level = fuzzy_matcher.get_duplicate_confidence_level(similarity)
                        
                        ClientDuplicate.objects.update_or_create(
                            primary_client=duplicate_client,
                            duplicate_client=client,
                            defaults={
                                'similarity_score': similarity,
                                'match_type': 'name_similarity',
                                'confidence_level': confidence_level,
                                'match_details': {
                                    'primary_name': f"{duplicate_client.first_name} {duplicate_client.last_name}",
                                    'duplicate_name': f"{client.first_name} {client.last_name}",
                                    'primary_email': duplicate_client.email,
                                    'primary_phone': duplicate_client.phone,
                                }
                            }
                        )
                        
                        duplicate_details.append({
                            'type': 'created_with_duplicate',
                            'reason': f'Name similarity ({similarity:.0%}) - created with duplicate flag',
                            'client_name': client_name,
                            'existing_name': existing_name,
                            'match_field': f"Similarity: {similarity:.0%}"
                        })
                        logger.info(f"Created client with name similarity duplicate flag ({similarity:.2f}): {client_data.get('first_name')} {client_data.get('last_name')}")
                
                # Process intake data if available and we have a client
                if has_intake_data and client is not None:
                    process_intake_data(client, row, index)
                    
            except Exception as e:
                errors.append(f"Row {index + 2}: {str(e)}")
                logger.error(f"Error processing row {index + 2}: {str(e)}")
        
        # Prepare response
        duplicate_created_count = len([d for d in duplicate_details if d['type'] == 'created_with_duplicate'])
        
        response_data = {
            'success': True,
            'message': f'Upload completed successfully!',
            'stats': {
                'total_rows': len(df),
                'created': created_count,
                'updated': updated_count,
                'skipped': skipped_count,
                'duplicates_flagged': duplicate_created_count,
                'errors': len(errors)
            },
            'duplicate_details': duplicate_details[:20],  # Limit to first 20 duplicates for display
            'errors': errors[:10] if errors else [],  # Limit to first 10 errors
            'notes': [
                'Missing date of birth values were set to 1900-01-01',
                'Missing gender values were set to "Unknown"',
                f'{duplicate_created_count} clients were created with potential duplicate flags for review'
            ] if created_count > 0 or updated_count > 0 or duplicate_created_count > 0 else []
        }
        
        return JsonResponse(response_data)
        
    except Exception as e:
        logger.error(f"Upload error: {str(e)}")
        return JsonResponse({'success': False, 'error': f'Upload failed: {str(e)}'}, status=500)

@require_http_methods(["GET"])
def download_sample(request, file_type):
    """Generate and download sample CSV or Excel file"""
    
    # Sample data
    sample_data = [
        {
            'first_name': 'John',
            'last_name': 'Smith',
            'email': 'john.smith@email.com',
            'phone_number': '(555) 123-4567',
            'dob': '1985-03-15',
            'preferred_name': 'Johnny',
            'alias': 'JS',
            'gender': 'Male',
            'sexual_orientation': 'Straight',
            'race': 'White',
            'immigration_status': 'Citizen',
            'languages_spoken': 'English, Spanish',
            'street': '123 Main Street',
            'city': 'New York',
            'state': 'NY',
            'zip': '10001',
            'country': 'USA',
            'source': 'SMIS',
            'program_name': 'Housing Assistance Program',
            'program_department': 'Social Services',
            'intake_date': '2024-01-15',
            'intake_database': 'CCD',
            'referral_source': 'SMIS',
            'intake_housing_status': 'homeless'
        },
        {
            'first_name': 'Maria',
            'last_name': 'Garcia',
            'email': 'maria.garcia@email.com',
            'phone_number': '(555) 234-5678',
            'dob': '1990-07-22',
            'preferred_name': 'Maria',
            'alias': 'MG',
            'gender': 'Female',
            'sexual_orientation': 'Straight',
            'race': 'Hispanic',
            'immigration_status': 'Permanent Resident',
            'languages_spoken': 'Spanish, English',
            'street': '456 Oak Avenue',
            'city': 'Los Angeles',
            'state': 'CA',
            'zip': '90210',
            'country': 'USA',
            'source': 'EMHWare',
            'program_name': 'Job Training Program',
            'program_department': 'Employment',
            'intake_date': '2024-01-16',
            'intake_database': 'CCD',
            'referral_source': 'EMHWare',
            'intake_housing_status': 'at_risk'
        },
        {
            'first_name': 'David',
            'last_name': 'Johnson',
            'email': 'david.johnson@email.com',
            'phone_number': '(555) 345-6789',
            'dob': '1978-11-08',
            'preferred_name': 'Dave',
            'alias': 'DJ',
            'gender': 'Male',
            'sexual_orientation': 'Gay',
            'race': 'Black',
            'immigration_status': 'Citizen',
            'languages_spoken': 'English',
            'street': '789 Pine Street',
            'city': 'Chicago',
            'state': 'IL',
            'zip': '60601',
            'country': 'USA',
            'source': 'FFAI',
            'program_name': 'Mental Health Services',
            'program_department': 'Healthcare',
            'intake_date': '2024-01-17',
            'intake_database': 'CCD',
            'referral_source': 'FFAI',
            'intake_housing_status': 'homeless'
        },
        {
            'first_name': 'Sarah',
            'last_name': 'Williams',
            'email': 'sarah.williams@email.com',
            'phone_number': '(555) 456-7890',
            'dob': '1992-05-14',
            'preferred_name': 'Sarah',
            'alias': 'SW',
            'gender': 'Female',
            'sexual_orientation': 'Bisexual',
            'race': 'Asian',
            'immigration_status': 'Citizen',
            'languages_spoken': 'English, Mandarin',
            'street': '321 Elm Street',
            'city': 'Seattle',
            'state': 'WA',
            'zip': '98101',
            'country': 'USA',
            'source': 'FFAI',
            'program_name': 'Mental Health Services',
            'program_department': 'Healthcare',
            'intake_date': '2024-01-17',
            'intake_database': 'CCD',
            'referral_source': 'FFAI',
            'intake_housing_status': 'homeless'
        },
        {
            'first_name': 'Michael',
            'last_name': 'Brown',
            'email': 'michael.brown@email.com',
            'phone_number': '(555) 567-8901',
            'dob': '1987-09-30',
            'preferred_name': 'Mike',
            'alias': 'MB',
            'gender': 'Male',
            'sexual_orientation': 'Straight',
            'race': 'White',
            'immigration_status': 'Citizen',
            'languages_spoken': 'English, French',
            'street': '654 Maple Drive',
            'city': 'Boston',
            'state': 'MA',
            'zip': '02101',
            'country': 'USA',
            'source': 'FFAI',
            'program_name': 'Mental Health Services',
            'program_department': 'Healthcare',
            'intake_date': '2024-01-17',
            'intake_database': 'CCD',
            'referral_source': 'FFAI',
            'intake_housing_status': 'homeless'
        },
        {
            'first_name': 'Lisa',
            'last_name': 'Davis',
            'email': 'lisa.davis@email.com',
            'phone_number': '(555) 678-9012',
            'dob': '1995-01-12',
            'preferred_name': 'Lisa',
            'alias': 'LD',
            'gender': 'Female',
            'sexual_orientation': 'Straight',
            'race': 'Native American',
            'immigration_status': 'Citizen',
            'languages_spoken': 'English, Navajo',
            'street': '987 Cedar Lane',
            'city': 'Phoenix',
            'state': 'AZ',
            'zip': '85001',
            'country': 'USA',
            'source': 'FFAI',
            'program_name': 'Mental Health Services',
            'program_department': 'Healthcare',
            'intake_date': '2024-01-17',
            'intake_database': 'CCD',
            'referral_source': 'FFAI',
            'intake_housing_status': 'homeless'
        },
        {
            'first_name': 'James',
            'last_name': 'Wilson',
            'email': 'james.wilson@email.com',
            'phone_number': '(555) 789-0123',
            'dob': '1983-12-03',
            'preferred_name': 'Jim',
            'alias': 'JW',
            'gender': 'Male',
            'sexual_orientation': 'Straight',
            'race': 'White',
            'immigration_status': 'Citizen',
            'languages_spoken': 'English, German',
            'street': '147 Birch Street',
            'city': 'Denver',
            'state': 'CO',
            'zip': '80201',
            'country': 'USA',
            'source': 'FFAI',
            'program_name': 'Mental Health Services',
            'program_department': 'Healthcare',
            'intake_date': '2024-01-17',
            'intake_database': 'CCD',
            'referral_source': 'FFAI',
            'intake_housing_status': 'homeless'
        },
        {
            'first_name': 'Jennifer',
            'last_name': 'Martinez',
            'email': 'jennifer.martinez@email.com',
            'phone_number': '(555) 890-1234',
            'dob': '1991-06-18',
            'preferred_name': 'Jen',
            'alias': 'JM',
            'gender': 'Female',
            'sexual_orientation': 'Lesbian',
            'race': 'Hispanic',
            'immigration_status': 'Citizen',
            'languages_spoken': 'English, Spanish',
            'street': '258 Spruce Avenue',
            'city': 'Miami',
            'state': 'FL',
            'zip': '33101',
            'country': 'USA',
            'source': 'FFAI',
            'program_name': 'Mental Health Services',
            'program_department': 'Healthcare',
            'intake_date': '2024-01-17',
            'intake_database': 'CCD',
            'referral_source': 'FFAI',
            'intake_housing_status': 'homeless'
        },
        {
            'first_name': 'Robert',
            'last_name': 'Anderson',
            'email': 'robert.anderson@email.com',
            'phone_number': '(555) 901-2345',
            'dob': '1989-04-25',
            'preferred_name': 'Rob',
            'alias': 'RA',
            'gender': 'Male',
            'sexual_orientation': 'Straight',
            'race': 'Black',
            'immigration_status': 'Citizen',
            'languages_spoken': 'English',
            'street': '369 Walnut Street',
            'city': 'Atlanta',
            'state': 'GA',
            'zip': '30301',
            'country': 'USA',
            'source': 'FFAI',
            'program_name': 'Mental Health Services',
            'program_department': 'Healthcare',
            'intake_date': '2024-01-17',
            'intake_database': 'CCD',
            'referral_source': 'FFAI',
            'intake_housing_status': 'homeless'
        },
        {
            'first_name': 'Amanda',
            'last_name': 'Taylor',
            'email': 'amanda.taylor@email.com',
            'phone_number': '(555) 012-3456',
            'dob': '1993-08-07',
            'preferred_name': 'Mandy',
            'alias': 'AT',
            'gender': 'Female',
            'sexual_orientation': 'Straight',
            'race': 'White',
            'immigration_status': 'Citizen',
            'languages_spoken': 'English, Italian',
            'street': '741 Cherry Lane',
            'city': 'Portland',
            'state': 'OR',
            'zip': '97201',
            'country': 'USA',
            'source': 'SMIS',
            'program_name': 'Housing Assistance Program',
            'program_department': 'Social Services',
            'intake_date': '2024-01-18',
            'intake_database': 'CCD',
            'referral_source': 'SMIS',
            'intake_housing_status': 'stably_housed'
        }
    ]
    
    df = pd.DataFrame(sample_data)
    
    if file_type == 'csv':
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="sample_clients.csv"'
        df.to_csv(response, index=False)
        return response
    elif file_type == 'xlsx':
        response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = 'attachment; filename="sample_clients.xlsx"'
        
        # Create Excel file in memory
        from io import BytesIO
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Clients')
        output.seek(0)
        response.write(output.getvalue())
        return response
    else:
        return HttpResponse('Invalid file type', status=400)


@csrf_protect
@require_http_methods(["POST"])
def bulk_delete_clients(request):
    """Bulk delete clients"""
    try:
        import json
        data = json.loads(request.body)
        client_ids = data.get('client_ids', [])
        
        if not client_ids:
            return JsonResponse({
                'success': False, 
                'error': 'No client IDs provided'
            }, status=400)
        
        # Get clients to delete
        clients_to_delete = Client.objects.filter(external_id__in=client_ids)
        deleted_count = clients_to_delete.count()
        
        if deleted_count == 0:
            return JsonResponse({
                'success': False, 
                'error': 'No clients found with provided IDs'
            }, status=404)
        
        # Delete clients
        clients_to_delete.delete()
        
        logger.info(f"Bulk deleted {deleted_count} clients: {client_ids}")
        
        return JsonResponse({
            'success': True,
            'deleted_count': deleted_count,
            'message': f'Successfully deleted {deleted_count} client(s)'
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False, 
            'error': 'Invalid JSON data'
        }, status=400)
    except Exception as e:
        logger.error(f"Error in bulk delete: {str(e)}")
        return JsonResponse({
            'success': False, 
            'error': f'An error occurred: {str(e)}'
        }, status=500)


class ClientDedupeView(TemplateView):
    """View for managing client duplicates"""
    template_name = 'clients/client_dedupe.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get filter parameters
        status_filter = self.request.GET.get('status', 'pending')
        confidence_filter = self.request.GET.get('confidence', '')
        
        # Build query
        duplicates_query = ClientDuplicate.objects.select_related(
            'primary_client', 'duplicate_client'
        ).all()
        
        if status_filter:
            duplicates_query = duplicates_query.filter(status=status_filter)
        
        if confidence_filter:
            duplicates_query = duplicates_query.filter(confidence_level=confidence_filter)
        
        # Order by confidence level and similarity score
        duplicates_query = duplicates_query.order_by(
            '-confidence_level', '-similarity_score', '-created_at'
        )
        
        # Group duplicates by primary client for better organization
        grouped_duplicates = {}
        for duplicate in duplicates_query:
            primary_id = duplicate.primary_client.id
            if primary_id not in grouped_duplicates:
                grouped_duplicates[primary_id] = {
                    'primary_client': duplicate.primary_client,
                    'duplicates': []
                }
            grouped_duplicates[primary_id]['duplicates'].append(duplicate)
        
        # Get statistics
        total_duplicates = ClientDuplicate.objects.count()
        pending_duplicates = ClientDuplicate.objects.filter(status='pending').count()
        high_confidence_duplicates = ClientDuplicate.objects.filter(
            confidence_level='high', status='pending'
        ).count()
        
        context.update({
            'grouped_duplicates': grouped_duplicates,
            'status_filter': status_filter,
            'confidence_filter': confidence_filter,
            'status_choices': ClientDuplicate.STATUS_CHOICES,
            'confidence_choices': ClientDuplicate.CONFIDENCE_LEVELS,
            'total_duplicates': total_duplicates,
            'pending_duplicates': pending_duplicates,
            'high_confidence_duplicates': high_confidence_duplicates,
        })
        
        return context


@method_decorator(csrf_exempt, name='dispatch')
@require_http_methods(["POST"])
def mark_duplicate_action(request, duplicate_id, action):
    """Handle duplicate actions (confirm, not_duplicate, merge)"""
    try:
        duplicate = get_object_or_404(ClientDuplicate, id=duplicate_id)
        
        # Get the current user (you might need to adjust this based on your auth system)
        reviewed_by = None
        if hasattr(request, 'user') and request.user.is_authenticated:
            # Try to get staff profile
            try:
                reviewed_by = request.user.staff_profile
            except:
                pass
        
        # Get notes from request
        data = json.loads(request.body) if request.body else {}
        notes = data.get('notes', '')
        
        if action == 'confirm':
            duplicate.mark_as_duplicate(reviewed_by, notes)
            message = f'Marked {duplicate.duplicate_client} as duplicate of {duplicate.primary_client}'
        elif action == 'not_duplicate':
            duplicate.mark_as_not_duplicate(reviewed_by, notes)
            message = f'Confirmed {duplicate.duplicate_client} is not a duplicate of {duplicate.primary_client}'
        elif action == 'merge':
            duplicate.merge_clients(reviewed_by, notes)
            message = f'Marked {duplicate.duplicate_client} for merging with {duplicate.primary_client}'
        else:
            return JsonResponse({
                'success': False,
                'error': 'Invalid action'
            }, status=400)
        
        return JsonResponse({
            'success': True,
            'message': message
        })
        
    except Exception as e:
        logger.error(f"Error in mark_duplicate_action: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': f'An error occurred: {str(e)}'
        }, status=500)


@method_decorator(csrf_exempt, name='dispatch')
@require_http_methods(["POST"])
def bulk_duplicate_action(request):
    """Handle bulk actions on duplicates"""
    try:
        data = json.loads(request.body)
        duplicate_ids = data.get('duplicate_ids', [])
        action = data.get('action', '')
        notes = data.get('notes', '')
        
        if not duplicate_ids:
            return JsonResponse({
                'success': False,
                'error': 'No duplicate IDs provided'
            }, status=400)
        
        if not action:
            return JsonResponse({
                'success': False,
                'error': 'No action specified'
            }, status=400)
        
        # Get the current user
        reviewed_by = None
        if hasattr(request, 'user') and request.user.is_authenticated:
            try:
                reviewed_by = request.user.staff_profile
            except:
                pass
        
        # Get duplicates
        duplicates = ClientDuplicate.objects.filter(id__in=duplicate_ids)
        updated_count = 0
        
        for duplicate in duplicates:
            if action == 'confirm':
                duplicate.mark_as_duplicate(reviewed_by, notes)
            elif action == 'not_duplicate':
                duplicate.mark_as_not_duplicate(reviewed_by, notes)
            elif action == 'merge':
                duplicate.merge_clients(reviewed_by, notes)
            else:
                continue
            updated_count += 1
        
        return JsonResponse({
            'success': True,
            'message': f'Updated {updated_count} duplicate(s)',
            'updated_count': updated_count
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON data'
        }, status=400)
    except Exception as e:
        logger.error(f"Error in bulk_duplicate_action: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': f'An error occurred: {str(e)}'
        }, status=500)