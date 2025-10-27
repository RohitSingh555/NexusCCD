from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, TemplateView
from django.urls import reverse_lazy, reverse
from django.contrib import messages
from core.message_utils import success_message, error_message, warning_message, info_message, create_success, update_success, delete_success, validation_error, permission_error, not_found_error
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_protect
from django.utils.decorators import method_decorator
from django.utils import timezone
from django.db.models import Q
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.db import IntegrityError
from django.http import HttpResponse
import csv
from core.models import Client, Program, Department, Intake, ClientProgramEnrollment, ClientDuplicate
from core.views import ProgramManagerAccessMixin, AnalystAccessMixin, jwt_required
from core.fuzzy_matching import fuzzy_matcher
from .forms import ClientForm
import pandas as pd
import json
import uuid
from datetime import datetime
import logging
from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_http_methods
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
import csv
import io
from django.contrib.auth.decorators import user_passes_test
from functools import wraps
from core.security import require_permission, SecurityManager

logger = logging.getLogger(__name__)


def admin_or_superuser_required(view_func):
    """Decorator to require admin or superuser access"""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'success': False, 'error': 'Authentication required'}, status=401)
        
        if not (request.user.is_staff or request.user.is_superuser):
            return JsonResponse({'success': False, 'error': 'Admin or superuser access required'}, status=403)
        
        return view_func(request, *args, **kwargs)
    return wrapper

@method_decorator(jwt_required, name='dispatch')
class ClientListView(AnalystAccessMixin, ProgramManagerAccessMixin, ListView):
    model = Client
    template_name = 'clients/client_list.html'
    context_object_name = 'clients'
    paginate_by = 10
    
    def get_paginate_by(self, queryset):
        """Get the number of items to paginate by from request parameters"""
        per_page = self.request.GET.get('per_page', '10')
        try:
            per_page = int(per_page)
            # Limit to reasonable values
            if per_page < 5:
                per_page = 5
            elif per_page > 100:
                per_page = 100
        except (ValueError, TypeError):
            per_page = 10
        return per_page
    
    def get_queryset(self):
        from django.db.models import Q
        from datetime import date
        
        # Start with base queryset - don't use ProgramManagerAccessMixin's get_queryset
        # because it tries to select_related('program') which doesn't exist on Client model
        queryset = Client.objects.all().order_by('-created_at')
        
        # For program managers and staff-only users, we need to filter clients based on their relationships
        if self.request.user.is_authenticated:
            try:
                staff = self.request.user.staff_profile
                user_roles = staff.staffrole_set.select_related('role').all()
                role_names = [staff_role.role.name for staff_role in user_roles]
                
                if staff.is_program_manager():
                    # Get assigned programs
                    assigned_programs = staff.get_assigned_programs()
                    
                    # Create a Q object to combine all the relationship filters
                    relationship_filters = Q()
                    
                    # 1. Clients enrolled in programs they manage
                    relationship_filters |= Q(
                        clientprogramenrollment__program__in=assigned_programs
                    )
                    
                    # 2. Clients they have created enrollments for
                    # (This would require tracking who created enrollments - using created_by field)
                    staff_name = f"{staff.user.first_name} {staff.user.last_name}".strip() or staff.user.username
                    relationship_filters |= Q(
                        clientprogramenrollment__created_by=staff_name
                    )
                    
                    # 3. Clients they have created restrictions for
                    relationship_filters |= Q(
                        servicerestriction__created_by=staff_name
                    )
                    
                    # 4. Clients they have updated (using updated_by field)
                    relationship_filters |= Q(
                        updated_by=staff_name
                    )
                    
                    # Apply the combined filter
                    queryset = queryset.filter(relationship_filters).distinct()
                elif 'Staff' in role_names and not any(role in ['SuperAdmin', 'Manager', 'Leader'] for role in role_names):
                    # Staff-only users see clients from both assigned programs AND directly assigned clients
                    from staff.models import StaffProgramAssignment, StaffClientAssignment
                    
                    # Create a Q object to combine both types of assignments
                    relationship_filters = Q()
                    
                    # 1. Clients enrolled in their assigned programs
                    assigned_program_ids = StaffProgramAssignment.objects.filter(
                        staff=staff,
                        is_active=True
                    ).values_list('program_id', flat=True)
                    if assigned_program_ids:
                        relationship_filters |= Q(
                            clientprogramenrollment__program_id__in=assigned_program_ids
                        )
                    
                    # 2. Directly assigned clients
                    assigned_client_ids = StaffClientAssignment.objects.filter(
                        staff=staff,
                        is_active=True
                    ).values_list('client_id', flat=True)
                    if assigned_client_ids:
                        relationship_filters |= Q(
                            id__in=assigned_client_ids
                        )
                    
                    # Apply the combined filter
                    if relationship_filters:
                        queryset = queryset.filter(relationship_filters).distinct()
                    else:
                        # If no assignments, show no clients
                        queryset = queryset.none()
                
                elif staff.is_leader():
                    # Leader users see only clients enrolled in programs from their assigned departments
                    from core.models import Department
                    assigned_departments = Department.objects.filter(
                        leader_assignments__staff=staff,
                        leader_assignments__is_active=True
                    ).distinct()
                    assigned_programs = Program.objects.filter(
                        department__in=assigned_departments
                    ).distinct()
                    queryset = queryset.filter(
                        clientprogramenrollment__program__in=assigned_programs
                    ).distinct()
            except Exception:
                pass
        
        search_query = self.request.GET.get('search', '').strip()
        program_filter = self.request.GET.get('program', '').strip()
        age_range = self.request.GET.get('age_range', '').strip()
        gender_filter = self.request.GET.get('gender', '').strip()
        
        # No need to filter duplicates - they are physically deleted
        # when marked as duplicates
        
        if search_query:
            # Search across multiple fields using Q objects
            queryset = queryset.filter(
                Q(first_name__icontains=search_query) |
                Q(last_name__icontains=search_query) |
                Q(preferred_name__icontains=search_query) |
                Q(alias__icontains=search_query) |
                Q(contact_information__email__icontains=search_query) |
                Q(contact_information__phone__icontains=search_query) |
                Q(client_id__icontains=search_query) |
                Q(uid_external__icontains=search_query)
            ).distinct()
        
        if program_filter:
            # Filter clients enrolled in the selected program
            queryset = queryset.filter(
                clientprogramenrollment__program_id=program_filter,
                clientprogramenrollment__status__in=['active', 'pending']
            ).distinct()
        
        # Age range filtering
        if age_range:
            today = date.today()
            
            if age_range == 'under18':
                # Under 18: born after (today - 18 years)
                min_birth_date = date(today.year - 18, today.month, today.day)
                queryset = queryset.filter(dob__gt=min_birth_date)
            elif age_range == '18-30':
                # 18-30: born between (today - 30 years) and (today - 18 years)
                max_birth_date = date(today.year - 18, today.month, today.day)
                min_birth_date = date(today.year - 30, today.month, today.day)
                queryset = queryset.filter(dob__lte=max_birth_date, dob__gt=min_birth_date)
            elif age_range == '30-50':
                # 30-50: born between (today - 50 years) and (today - 30 years)
                max_birth_date = date(today.year - 30, today.month, today.day)
                min_birth_date = date(today.year - 50, today.month, today.day)
                queryset = queryset.filter(dob__lte=max_birth_date, dob__gt=min_birth_date)
            elif age_range == 'over50':
                # Over 50: born before (today - 50 years)
                max_birth_date = date(today.year - 50, today.month, today.day)
                queryset = queryset.filter(dob__lte=max_birth_date)
        
        # Gender filtering
        if gender_filter:
            queryset = queryset.filter(gender=gender_filter)
        
        # Program manager filtering - only apply if user has permission and manager is selected
        manager_filter = self.request.GET.get('manager', '')
        if manager_filter and self.request.user.is_authenticated:
            try:
                staff = self.request.user.staff_profile
                user_roles = staff.staffrole_set.select_related('role').all()
                role_names = [staff_role.role.name for staff_role in user_roles]
                
                # Only apply manager filter if user is SuperAdmin or Admin
                if any(role in ['SuperAdmin', 'Admin'] for role in role_names):
                    # Get programs managed by the selected manager
                    from core.models import ProgramManagerAssignment
                    managed_programs = Program.objects.filter(
                        manager_assignments__staff_id=manager_filter,
                        manager_assignments__is_active=True
                    ).distinct()
                    
                    # Filter clients enrolled in those programs
                    queryset = queryset.filter(
                        clientprogramenrollment__program__in=managed_programs
                    ).distinct()
            except Exception:
                pass  # If user doesn't have permission, ignore the manager filter
        
        return queryset.order_by('-created_at')
    
    def get_context_data(self, **kwargs):
        # Don't use ProgramManagerAccessMixin's get_context_data to avoid conflicts
        context = super(ProgramManagerAccessMixin, self).get_context_data(**kwargs)
        context['search_query'] = self.request.GET.get('search', '')
        context['program_filter'] = self.request.GET.get('program', '')
        context['age_range'] = self.request.GET.get('age_range', '')
        context['gender_filter'] = self.request.GET.get('gender', '')
        context['manager_filter'] = self.request.GET.get('manager', '')
        context['per_page'] = self.request.GET.get('per_page', '10')
        
        # Add gender choices for the filter dropdown
        from .forms import GENDER_CHOICES
        context['gender_choices'] = GENDER_CHOICES
        # Filter programs for program managers
        if self.request.user.is_authenticated:
            try:
                staff = self.request.user.staff_profile
                if staff.is_program_manager():
                    context['programs'] = staff.get_assigned_programs().filter(status='active').order_by('name')
                else:
                    context['programs'] = Program.objects.filter(status='active').order_by('name')
            except Exception:
                context['programs'] = Program.objects.filter(status='active').order_by('name')
        else:
            context['programs'] = Program.objects.filter(status='active').order_by('name')
        
        # Force pagination to be enabled if there are any results
        if context.get('paginator') and context['paginator'].count > 0:
            context['is_paginated'] = True
        
        # Get program managers (users with Manager role) - only for SuperAdmin and Admin
        from core.models import ProgramManagerAssignment, Staff, Role
        if self.request.user.is_authenticated:
            try:
                staff = self.request.user.staff_profile
                user_roles = staff.staffrole_set.select_related('role').all()
                role_names = [staff_role.role.name for staff_role in user_roles]
                
                # Only show manager filter to SuperAdmin and Admin
                if any(role in ['SuperAdmin', 'Admin'] for role in role_names):
                    try:
                        manager_role = Role.objects.get(name='Manager')
                        context['program_managers'] = Staff.objects.filter(
                            staffrole__role=manager_role
                        ).select_related('user').distinct().order_by('first_name', 'last_name')
                    except Role.DoesNotExist:
                        context['program_managers'] = Staff.objects.none()
                else:
                    context['program_managers'] = Staff.objects.none()
            except Exception:
                context['program_managers'] = Staff.objects.none()
        else:
            context['program_managers'] = Staff.objects.none()
        
        # Add current filter values (like programs page)
        context['current_program'] = self.request.GET.get('program', '')
        context['current_manager'] = self.request.GET.get('manager', '')
        
        # Calculate age for each client
        from datetime import date
        today = date.today()
        for client in context['clients']:
            if client.dob:
                age = today.year - client.dob.year
                # Adjust if birthday hasn't occurred this year
                if today.month < client.dob.month or (today.month == client.dob.month and today.day < client.dob.day):
                    age -= 1
                client.age = age
            else:
                client.age = None
        
        return context

class ClientDetailView(AnalystAccessMixin, DetailView):
    model = Client
    template_name = 'clients/client_detail.html'
    context_object_name = 'client'
    slug_field = 'external_id'
    slug_url_kwarg = 'external_id'
    
    def get(self, request, *args, **kwargs):
        """Override get method to handle permission checks before rendering"""
        try:
            # First, try to get the object
            self.object = self.get_object()
        except Exception:
            # If object doesn't exist, redirect to permission error
            from django.shortcuts import redirect
            from django.urls import reverse
            return redirect(f"{reverse('core:permission_error')}?type=client_not_related&resource=client")
        
        # Check if user is a program manager and has access to this client
        if not request.user.is_superuser:
            try:
                staff = request.user.staff_profile
                user_roles = staff.staffrole_set.select_related('role').all()
                role_names = [staff_role.role.name for staff_role in user_roles]
                
                
                if staff.is_program_manager():
                    # Check if this client is in the filtered queryset from ClientListView
                    from django.db.models import Q
                    
                    # Get assigned programs
                    assigned_programs = staff.get_assigned_programs()
                    
                    # Create the same relationship filters as in ClientListView
                    relationship_filters = Q()
                    relationship_filters |= Q(clientprogramenrollment__program__in=assigned_programs)
                    
                    staff_name = f"{staff.user.first_name} {staff.user.last_name}".strip() or staff.user.username
                    relationship_filters |= Q(clientprogramenrollment__created_by=staff_name)
                    relationship_filters |= Q(servicerestriction__created_by=staff_name)
                    relationship_filters |= Q(updated_by=staff_name)
                    
                    # Check if this client matches any of the relationship filters
                    if not Client.objects.filter(pk=self.object.pk).filter(relationship_filters).exists():
                        from django.shortcuts import redirect
                        from django.urls import reverse
                        return redirect(f"{reverse('core:permission_error')}?type=client_not_related&resource=client&name={self.object.first_name} {self.object.last_name}")
                
                elif 'Staff' in role_names and not any(role in ['SuperAdmin', 'Manager', 'Leader'] for role in role_names):
                    # Staff users can access clients from both assigned programs AND directly assigned clients
                    from staff.models import StaffProgramAssignment, StaffClientAssignment
                    from django.db.models import Q
                    
                    # Create a Q object to combine both types of assignments
                    relationship_filters = Q()
                    
                    # 1. Clients enrolled in their assigned programs
                    assigned_program_ids = StaffProgramAssignment.objects.filter(
                        staff=staff,
                        is_active=True
                    ).values_list('program_id', flat=True)
                    if assigned_program_ids:
                        relationship_filters |= Q(
                            clientprogramenrollment__program_id__in=assigned_program_ids
                        )
                    
                    # 2. Directly assigned clients
                    assigned_client_ids = StaffClientAssignment.objects.filter(
                        staff=staff,
                        is_active=True
                    ).values_list('client_id', flat=True)
                    if assigned_client_ids:
                        relationship_filters |= Q(
                            id__in=assigned_client_ids
                        )
                    
                    # Check if this client matches any of the relationship filters
                    if relationship_filters:
                        # If we have filters, check if this client matches them
                        if not Client.objects.filter(
                            pk=self.object.pk
                        ).filter(relationship_filters).exists():
                            from django.shortcuts import redirect
                            from django.urls import reverse
                            return redirect(f"{reverse('core:permission_error')}?type=client_not_assigned&resource=client&name={self.object.first_name} {self.object.last_name}")
                    else:
                        # If no filters (no assignments), deny access
                        from django.shortcuts import redirect
                        from django.urls import reverse
                        return redirect(f"{reverse('core:permission_error')}?type=client_not_assigned&resource=client&name={self.object.first_name} {self.object.last_name}")
                
                elif staff.is_leader():
                    # Leaders can only access clients enrolled in programs from their assigned departments
                    from core.models import Department
                    assigned_departments = Department.objects.filter(
                        leader_assignments__staff=staff,
                        leader_assignments__is_active=True
                    ).distinct()
                    assigned_programs = Program.objects.filter(
                        department__in=assigned_departments
                    ).distinct()
                    
                    # Check if this client is enrolled in any of their assigned programs
                    if not Client.objects.filter(
                        pk=self.object.pk,
                        clientprogramenrollment__program__in=assigned_programs
                    ).exists():
                        from django.shortcuts import redirect
                        from django.urls import reverse
                        return redirect(f"{reverse('core:permission_error')}?type=client_not_assigned&resource=client&name={self.object.first_name} {self.object.last_name}")
                        
            except Exception:
                from django.shortcuts import redirect
                from django.urls import reverse
                return redirect(f"{reverse('core:permission_error')}?type=access_denied&resource=client")
        
        # If we get here, user has access, proceed with normal rendering
        context = self.get_context_data(object=self.object)
        return self.render_to_response(context)

class ClientCreateView(AnalystAccessMixin, CreateView):
    model = Client
    form_class = ClientForm
    template_name = 'clients/client_form_tailwind.html'
    success_url = reverse_lazy('clients:list')
    
    def dispatch(self, request, *args, **kwargs):
        """Check if user has permission to create clients"""
        if request.user.is_authenticated:
            try:
                staff = request.user.staff_profile
                user_roles = staff.staffrole_set.select_related('role').all()
                role_names = [staff_role.role.name for staff_role in user_roles]
                
                # Staff role users cannot create clients
                if 'Staff' in role_names and not any(role in ['SuperAdmin', 'Admin', 'Manager', 'Leader'] for role in role_names):
                    messages.error(request, 'You do not have permission to create clients. Contact your administrator.')
                    return redirect('clients:list')
            except Exception:
                pass
        
        return super().dispatch(request, *args, **kwargs)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['programs'] = Program.objects.filter(status='active').prefetch_related('subprograms').order_by('name')
        return context
    
    def form_valid(self, form):
        print("DEBUG: ClientCreateView.form_valid called")
        print("DEBUG: Form is valid:", form.is_valid())
        print("DEBUG: Form errors:", form.errors)
        print("DEBUG: Form cleaned_data keys:", list(form.cleaned_data.keys()))
        print("DEBUG: POST data keys:", list(self.request.POST.keys()))
        print("DEBUG: Program enrollment POST data:", {k: v for k, v in self.request.POST.items() if k.startswith('program_enrollments')})
        
        client = form.save(commit=False)
        
        # Set updated_by field
        if self.request.user.is_authenticated:
            client.updated_by = f"{self.request.user.first_name} {self.request.user.last_name}".strip()
            if not client.updated_by:
                client.updated_by = self.request.user.username or self.request.user.email
        
        # Check for potential duplicates using fuzzy matching
        client_data = {
            'first_name': client.first_name,
            'last_name': client.last_name,
            'email': client.email,
            'phone': client.phone,
        }
        
        # Save the client first before checking for duplicates
        client.save()
        
        # Handle program enrollments
        self.handle_program_enrollments(client)
        
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
                
                warning_message(
                    self.request, 
                    f'Client created with potential duplicates detected. Please review the Probable Duplicate Clients page.'
                )
            else:
                create_success(self.request, 'Client')
        else:
            create_success(self.request, 'Client')
        
        # Create audit log entry
        try:
            from core.models import create_audit_log
            create_audit_log(
                entity_name='Client',
                entity_id=client.external_id,
                action='create',
                changed_by=self.request.user,
                diff_data={
                    'first_name': client.first_name,
                    'last_name': client.last_name,
                    'preferred_name': client.preferred_name or '',
                    'alias': client.alias or '',
                    'dob': str(client.dob) if client.dob else '',
                    'gender': client.gender or '',
                    'sexual_orientation': client.sexual_orientation or '',
                    'languages_spoken': str(client.languages_spoken) if client.languages_spoken else '',
                    'ethnicity': str(client.ethnicity) if client.ethnicity else '',
                    'citizenship_status': client.citizenship_status or '',
                    'indigenous_status': client.indigenous_status or '',
                    'country_of_birth': client.country_of_birth or '',
                    'contact_information': str(client.contact_information) if client.contact_information else '',
                    'addresses': str(client.addresses) if client.addresses else '',
                    'address_2': client.address_2 or '',
                    'permission_to_email': client.permission_to_email,
                    'permission_to_phone': client.permission_to_phone,
                    'phone_work': client.phone_work or '',
                    'phone_alt': client.phone_alt or '',
                    'client_id': client.client_id or '',
                    'medical_conditions': client.medical_conditions or '',
                    'primary_diagnosis': client.primary_diagnosis or '',
                    'support_workers': str(client.support_workers) if client.support_workers else '',
                    'next_of_kin': str(client.next_of_kin) if client.next_of_kin else '',
                    'emergency_contact': str(client.emergency_contact) if client.emergency_contact else '',
                    'comments': client.comments or '',
                    'created_by': client.updated_by
                }
            )
        except Exception as e:
            logger.error(f"Error creating audit log for client: {e}")
        
        return super().form_valid(form)
    
    def form_invalid(self, form):
        print("DEBUG: ClientCreateView.form_invalid called")
        print("DEBUG: Form is valid:", form.is_valid())
        print("DEBUG: Form errors:", form.errors)
        print("DEBUG: Form non_field_errors:", form.non_field_errors)
        print("DEBUG: POST data keys:", list(self.request.POST.keys()))
        print("DEBUG: Program enrollment POST data:", {k: v for k, v in self.request.POST.items() if k.startswith('program_enrollments')})
        return super().form_invalid(form)
    
    def handle_program_enrollments(self, client):
        """Handle multiple program enrollments from form data"""
        program_enrollments_data = {}
        
        print("DEBUG: handle_program_enrollments called")
        print("DEBUG: POST data keys:", [key for key in self.request.POST.keys() if key.startswith('program_enrollments')])
        print("DEBUG: All POST data:", dict(self.request.POST))
        
        # Extract program enrollment data from POST
        for key, value in self.request.POST.items():
            if key.startswith('program_enrollments['):
                # Parse key like "program_enrollments[0][program]"
                import re
                match = re.match(r'program_enrollments\[(\d+)\]\[(\w+)\]', key)
                if match:
                    index = match.group(1)
                    field = match.group(2)
                    
                    if index not in program_enrollments_data:
                        program_enrollments_data[index] = {}
                    program_enrollments_data[index][field] = value
                    print(f"DEBUG: Found enrollment data - {key}: {value}")
        
        print("DEBUG: Parsed enrollment data:", program_enrollments_data)
        
        # Create program enrollments
        for index, enrollment_data in program_enrollments_data.items():
            program_id = enrollment_data.get('program')
            sub_programs_json = enrollment_data.get('sub_programs', '[]')
            start_date = enrollment_data.get('start_date')
            end_date = enrollment_data.get('end_date')
            status = enrollment_data.get('status', 'pending')
            level_of_support = enrollment_data.get('level_of_support', '')
            client_type = enrollment_data.get('client_type', '')
            referral_source = enrollment_data.get('referral_source', '')
            support_workers = enrollment_data.get('support_workers', '')
            receiving_services = enrollment_data.get('receiving_services', 'false') == 'true'
            receiving_services_date = enrollment_data.get('receiving_services_date', '')
            days_elapsed = enrollment_data.get('days_elapsed', '')
            reason_discharge = enrollment_data.get('reason_discharge', '')
            
            # Only create enrollment if program is selected
            print(f"DEBUG: Processing enrollment {index} - program_id: {program_id}, start_date: {start_date}")
            print(f"DEBUG: Full enrollment data for {index}: {enrollment_data}")
            if program_id and start_date:
                try:
                    program = Program.objects.get(id=program_id)
                    print(f"DEBUG: Found program: {program.name}")
                    
                    # Parse sub-programs from JSON
                    import json
                    try:
                        if sub_programs_json and sub_programs_json.strip():
                            # Handle malformed JSON like just "["
                            if sub_programs_json.strip() == '[':
                                sub_program_names = []
                            else:
                                sub_program_names = json.loads(sub_programs_json)
                        else:
                            sub_program_names = []
                    except json.JSONDecodeError as e:
                        print(f"DEBUG: Invalid JSON for sub_programs: '{sub_programs_json}' - Error: {e}")
                        sub_program_names = []
                    
                    # Create notes with all the details
                    notes_parts = []
                    if sub_program_names:
                        notes_parts.append(f"Sub-programs: {', '.join(sub_program_names)}")
                    if level_of_support:
                        notes_parts.append(f"Level of Support: {level_of_support}")
                    if client_type:
                        notes_parts.append(f"Client Type: {client_type}")
                    if referral_source:
                        notes_parts.append(f"Referral Source: {referral_source}")
                    if support_workers:
                        notes_parts.append(f"Support Workers: {support_workers}")
                    if receiving_services:
                        notes_parts.append("Receiving Services: Yes")
                    if receiving_services_date:
                        notes_parts.append(f"Receiving Services Date: {receiving_services_date}")
                    if days_elapsed:
                        notes_parts.append(f"Days Elapsed: {days_elapsed}")
                    if reason_discharge:
                        notes_parts.append(f"Reason: {reason_discharge}")
                    
                    notes = " | ".join(notes_parts) if notes_parts else "Enrollment created from client form"
                    
                    # Set created_by and updated_by fields
                    created_by = f"{self.request.user.first_name} {self.request.user.last_name}".strip()
                    if not created_by:
                        created_by = self.request.user.username or self.request.user.email
                    
                    enrollment = ClientProgramEnrollment.objects.create(
                        client=client,
                        program=program,
                        start_date=start_date,
                        end_date=end_date if end_date else None,
                        status=status,
                        notes=notes,
                        receiving_services_date=receiving_services_date if receiving_services_date else None,
                        days_elapsed=int(days_elapsed) if days_elapsed else None,
                        created_by=created_by,
                        updated_by=created_by
                    )
                    print(f"DEBUG: Created enrollment: {enrollment}")
                    print(f"DEBUG: Enrollment ID: {enrollment.id}")
                    print(f"DEBUG: Client: {enrollment.client}")
                    print(f"DEBUG: Program: {enrollment.program}")
                except Program.DoesNotExist:
                    print(f"DEBUG: Program with ID {program_id} not found")
                    logger.warning(f"Program with ID {program_id} not found")
                except Exception as e:
                    print(f"DEBUG: Error creating program enrollment: {e}")
                    logger.error(f"Error creating program enrollment: {e}")
            else:
                print(f"DEBUG: Skipping enrollment {index} - missing program_id or start_date")

class ClientUpdateView(AnalystAccessMixin, UpdateView):
    model = Client
    form_class = ClientForm
    template_name = 'clients/client_form_tailwind.html'
    slug_field = 'external_id'
    slug_url_kwarg = 'external_id'
    success_url = reverse_lazy('clients:list')
    
    def dispatch(self, request, *args, **kwargs):
        """Check if user has permission to edit clients"""
        if request.user.is_authenticated:
            try:
                staff = request.user.staff_profile
                user_roles = staff.staffrole_set.select_related('role').all()
                role_names = [staff_role.role.name for staff_role in user_roles]
                
                # Staff role users cannot edit clients
                if 'Staff' in role_names and not any(role in ['SuperAdmin', 'Admin', 'Manager', 'Leader'] for role in role_names):
                    messages.error(request, 'You do not have permission to edit clients. Contact your administrator.')
                    return redirect('clients:list')
            except Exception:
                pass
        
        return super().dispatch(request, *args, **kwargs)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['programs'] = Program.objects.filter(status='active').prefetch_related('subprograms').order_by('name')
        context['existing_enrollments'] = ClientProgramEnrollment.objects.filter(client=self.object).select_related('program', 'sub_program')
        return context
    
    def form_valid(self, form):
        client = form.save(commit=False)
        
        # Store original values for audit log
        original_client = Client.objects.get(pk=client.pk)
        changes = {}
        
        # Check for changes in all client fields
        # Basic Information
        if original_client.first_name != client.first_name:
            changes['first_name'] = f"{original_client.first_name} → {client.first_name}"
        if original_client.last_name != client.last_name:
            changes['last_name'] = f"{original_client.last_name} → {client.last_name}"
        if original_client.preferred_name != client.preferred_name:
            changes['preferred_name'] = f"{original_client.preferred_name or ''} → {client.preferred_name or ''}"
        if original_client.alias != client.alias:
            changes['alias'] = f"{original_client.alias or ''} → {client.alias or ''}"
        if original_client.dob != client.dob:
            changes['dob'] = f"{original_client.dob or ''} → {client.dob or ''}"
        if original_client.gender != client.gender:
            changes['gender'] = f"{original_client.gender or ''} → {client.gender or ''}"
        if original_client.sexual_orientation != client.sexual_orientation:
            changes['sexual_orientation'] = f"{original_client.sexual_orientation or ''} → {client.sexual_orientation or ''}"
        
        # Languages and Ethnicity
        if original_client.languages_spoken != client.languages_spoken:
            changes['languages_spoken'] = f"{str(original_client.languages_spoken) or ''} → {str(client.languages_spoken) or ''}"
        if original_client.ethnicity != client.ethnicity:
            changes['ethnicity'] = f"{str(original_client.ethnicity) or ''} → {str(client.ethnicity) or ''}"
        
        # Status Information
        if original_client.citizenship_status != client.citizenship_status:
            changes['citizenship_status'] = f"{original_client.citizenship_status or ''} → {client.citizenship_status or ''}"
        if original_client.indigenous_status != client.indigenous_status:
            changes['indigenous_status'] = f"{original_client.indigenous_status or ''} → {client.indigenous_status or ''}"
        if original_client.country_of_birth != client.country_of_birth:
            changes['country_of_birth'] = f"{original_client.country_of_birth or ''} → {client.country_of_birth or ''}"
        
        # Contact Information
        if original_client.contact_information != client.contact_information:
            changes['contact_information'] = f"{str(original_client.contact_information) or ''} → {str(client.contact_information) or ''}"
        if original_client.addresses != client.addresses:
            changes['addresses'] = f"{str(original_client.addresses) or ''} → {str(client.addresses) or ''}"
        if original_client.address_2 != client.address_2:
            changes['address_2'] = f"{original_client.address_2 or ''} → {client.address_2 or ''}"
        
        # Contact Permissions
        if original_client.permission_to_email != client.permission_to_email:
            changes['permission_to_email'] = f"{original_client.permission_to_email} → {client.permission_to_email}"
        if original_client.permission_to_phone != client.permission_to_phone:
            changes['permission_to_phone'] = f"{original_client.permission_to_phone} → {client.permission_to_phone}"
        
        # Phone Numbers
        if original_client.phone_work != client.phone_work:
            changes['phone_work'] = f"{original_client.phone_work or ''} → {client.phone_work or ''}"
        if original_client.phone_alt != client.phone_alt:
            changes['phone_alt'] = f"{original_client.phone_alt or ''} → {client.phone_alt or ''}"
        
        # Client ID
        if original_client.client_id != client.client_id:
            changes['client_id'] = f"{original_client.client_id or ''} → {client.client_id or ''}"
        
        # Medical Information
        if original_client.medical_conditions != client.medical_conditions:
            changes['medical_conditions'] = f"{original_client.medical_conditions or ''} → {client.medical_conditions or ''}"
        if original_client.primary_diagnosis != client.primary_diagnosis:
            changes['primary_diagnosis'] = f"{original_client.primary_diagnosis or ''} → {client.primary_diagnosis or ''}"
        
        # Support and Emergency Contacts
        if original_client.support_workers != client.support_workers:
            changes['support_workers'] = f"{str(original_client.support_workers) or ''} → {str(client.support_workers) or ''}"
        if original_client.next_of_kin != client.next_of_kin:
            changes['next_of_kin'] = f"{str(original_client.next_of_kin) or ''} → {str(client.next_of_kin) or ''}"
        if original_client.emergency_contact != client.emergency_contact:
            changes['emergency_contact'] = f"{str(original_client.emergency_contact) or ''} → {str(client.emergency_contact) or ''}"
        
        # Comments
        if original_client.comments != client.comments:
            changes['comments'] = f"{original_client.comments or ''} → {client.comments or ''}"
        
        # Set updated_by field
        if self.request.user.is_authenticated:
            client.updated_by = f"{self.request.user.first_name} {self.request.user.last_name}".strip()
            if not client.updated_by:
                client.updated_by = self.request.user.username or self.request.user.email
        
        client.save()
        
        # Handle program enrollments
        self.handle_program_enrollments(client)
        
        # Create audit log entry if there were changes
        if changes:
            try:
                from core.models import create_audit_log
                create_audit_log(
                    entity_name='Client',
                    entity_id=client.external_id,
                    action='update',
                    changed_by=self.request.user,
                    diff_data=changes
                )
            except Exception as e:
                logger.error(f"Error creating audit log for client update: {e}")
        
        update_success(self.request, 'Client')
        return super().form_valid(form)
    
    def handle_program_enrollments(self, client):
        """Handle multiple program enrollments from form data"""
        program_enrollments_data = {}
        
        print("DEBUG: ClientUpdateView.handle_program_enrollments called")
        print("DEBUG: POST data keys:", [key for key in self.request.POST.keys() if key.startswith('program_enrollments')])
        
        # Extract program enrollment data from POST
        for key, value in self.request.POST.items():
            if key.startswith('program_enrollments['):
                # Parse key like "program_enrollments[0][program]"
                import re
                match = re.match(r'program_enrollments\[(\d+)\]\[(\w+)\]', key)
                if match:
                    index = match.group(1)
                    field = match.group(2)
                    
                    if index not in program_enrollments_data:
                        program_enrollments_data[index] = {}
                    program_enrollments_data[index][field] = value
                    print(f"DEBUG: Found enrollment data - {key}: {value}")
        
        print("DEBUG: Parsed enrollment data:", program_enrollments_data)
        
        # Clear existing enrollments for this client (optional - you might want to keep them)
        # ClientProgramEnrollment.objects.filter(client=client).delete()
        
        # Create/update program enrollments
        for index, enrollment_data in program_enrollments_data.items():
            program_id = enrollment_data.get('program')
            sub_programs_json = enrollment_data.get('sub_programs', '[]')
            start_date = enrollment_data.get('start_date')
            end_date = enrollment_data.get('end_date')
            status = enrollment_data.get('status', 'pending')
            level_of_support = enrollment_data.get('level_of_support', '')
            client_type = enrollment_data.get('client_type', '')
            referral_source = enrollment_data.get('referral_source', '')
            support_workers = enrollment_data.get('support_workers', '')
            receiving_services = enrollment_data.get('receiving_services', 'false') == 'true'
            receiving_services_date = enrollment_data.get('receiving_services_date', '')
            days_elapsed = enrollment_data.get('days_elapsed', '')
            reason_discharge = enrollment_data.get('reason_discharge', '')
            
            # Only create enrollment if program is selected
            if program_id and start_date:
                try:
                    program = Program.objects.get(id=program_id)
                    
                    # Parse sub-programs from JSON
                    import json
                    try:
                        if sub_programs_json and sub_programs_json.strip():
                            # Handle malformed JSON like just "["
                            if sub_programs_json.strip() == '[':
                                sub_program_names = []
                            else:
                                sub_program_names = json.loads(sub_programs_json)
                        else:
                            sub_program_names = []
                    except json.JSONDecodeError as e:
                        print(f"DEBUG: Invalid JSON for sub_programs: '{sub_programs_json}' - Error: {e}")
                        sub_program_names = []
                    
                    # Create notes with all the details
                    notes_parts = []
                    if sub_program_names:
                        notes_parts.append(f"Sub-programs: {', '.join(sub_program_names)}")
                    if level_of_support:
                        notes_parts.append(f"Level of Support: {level_of_support}")
                    if client_type:
                        notes_parts.append(f"Client Type: {client_type}")
                    if referral_source:
                        notes_parts.append(f"Referral Source: {referral_source}")
                    if support_workers:
                        notes_parts.append(f"Support Workers: {support_workers}")
                    if receiving_services:
                        notes_parts.append("Receiving Services: Yes")
                    if receiving_services_date:
                        notes_parts.append(f"Receiving Services Date: {receiving_services_date}")
                    if days_elapsed:
                        notes_parts.append(f"Days Elapsed: {days_elapsed}")
                    if reason_discharge:
                        notes_parts.append(f"Reason: {reason_discharge}")
                    
                    notes = " | ".join(notes_parts) if notes_parts else "Enrollment updated from client form"
                    
                    enrollment = ClientProgramEnrollment.objects.create(
                        client=client,
                        program=program,
                        start_date=start_date,
                        end_date=end_date if end_date else None,
                        status=status,
                        notes=notes,
                        receiving_services_date=receiving_services_date if receiving_services_date else None,
                        days_elapsed=int(days_elapsed) if days_elapsed else None,
                        created_by=self.request.user.get_full_name() or self.request.user.username,
                        updated_by=self.request.user.get_full_name() or self.request.user.username
                    )
                    print(f"DEBUG: Created enrollment: {enrollment}")
                    print(f"DEBUG: Enrollment ID: {enrollment.id}")
                except Program.DoesNotExist:
                    logger.warning(f"Program with ID {program_id} not found")
                except Exception as e:
                    logger.error(f"Error creating program enrollment: {e}")

class ClientDeleteView(DeleteView):
    model = Client
    template_name = 'clients/client_confirm_delete.html'
    slug_field = 'external_id'
    slug_url_kwarg = 'external_id'
    success_url = reverse_lazy('clients:list')
    
    def dispatch(self, request, *args, **kwargs):
        """Check if user has permission to delete clients"""
        if request.user.is_authenticated:
            try:
                staff = request.user.staff_profile
                user_roles = staff.staffrole_set.select_related('role').all()
                role_names = [staff_role.role.name for staff_role in user_roles]
                
                # Staff role users cannot delete clients
                if 'Staff' in role_names and not any(role in ['SuperAdmin', 'Admin', 'Manager', 'Leader'] for role in role_names):
                    messages.error(request, 'You do not have permission to delete clients. Contact your administrator.')
                    return redirect('clients:list')
            except Exception:
                pass
        
        return super().dispatch(request, *args, **kwargs)
    
    def form_valid(self, form):
        client = self.get_object()
        
        # Store client data for audit log before deletion
        client_data = {
            'first_name': client.first_name,
            'last_name': client.last_name,
            'preferred_name': client.preferred_name or '',
            'alias': client.alias or '',
            'dob': str(client.dob) if client.dob else '',
            'gender': client.gender or '',
            'sexual_orientation': client.sexual_orientation or '',
            'languages_spoken': str(client.languages_spoken) if client.languages_spoken else '',
            'ethnicity': str(client.ethnicity) if client.ethnicity else '',
            'citizenship_status': client.citizenship_status or '',
            'indigenous_status': client.indigenous_status or '',
            'country_of_birth': client.country_of_birth or '',
            'contact_information': str(client.contact_information) if client.contact_information else '',
            'addresses': str(client.addresses) if client.addresses else '',
            'address_2': client.address_2 or '',
            'permission_to_email': client.permission_to_email,
            'permission_to_phone': client.permission_to_phone,
            'phone_work': client.phone_work or '',
            'phone_alt': client.phone_alt or '',
            'client_id': client.client_id or '',
            'medical_conditions': client.medical_conditions or '',
            'primary_diagnosis': client.primary_diagnosis or '',
            'support_workers': str(client.support_workers) if client.support_workers else '',
            'next_of_kin': str(client.next_of_kin) if client.next_of_kin else '',
            'emergency_contact': str(client.emergency_contact) if client.emergency_contact else '',
            'comments': client.comments or '',
            'deleted_by': f"{self.request.user.first_name} {self.request.user.last_name}".strip() or self.request.user.username
        }
        
        # Create audit log entry before deletion
        try:
            from core.models import create_audit_log
            create_audit_log(
                entity_name='Client',
                entity_id=client.external_id,
                action='delete',
                changed_by=self.request.user,
                diff_data=client_data
            )
        except Exception as e:
            logger.error(f"Error creating audit log for client deletion: {e}")
        
        delete_success(self.request, 'Client')
        return super().form_valid(form)

class ClientUploadView(TemplateView):
    template_name = 'clients/client_upload.html'
    
    def dispatch(self, request, *args, **kwargs):
        """Check if user has permission to upload clients"""
        if request.user.is_authenticated:
            try:
                staff = request.user.staff_profile
                user_roles = staff.staffrole_set.select_related('role').all()
                role_names = [staff_role.role.name for staff_role in user_roles]
                
                # Staff role users cannot upload clients
                if 'Staff' in role_names and not any(role in ['SuperAdmin', 'Manager','Admin'] for role in role_names):
                    messages.error(request, 'You do not have permission to upload clients. Contact your administrator.')
                    return redirect('clients:list')
            except Exception:
                pass
        
        return super().dispatch(request, *args, **kwargs)

@csrf_exempt
@require_http_methods(["POST"])
def upload_clients(request):
    """Handle CSV/Excel file upload and process client data"""
    # Check if user has permission to upload clients
    if request.user.is_authenticated:
        try:
            staff = request.user.staff_profile
            user_roles = staff.staffrole_set.select_related('role').all()
            role_names = [staff_role.role.name for staff_role in user_roles]
            
            # Staff role users cannot upload clients
            if 'Staff' in role_names and not any(role in ['SuperAdmin', 'Admin', 'Manager', 'Leader'] for role in role_names):
                return JsonResponse({'success': False, 'error': 'You do not have permission to upload clients. Contact your administrator.'}, status=403)
        except Exception:
            pass
    
    try:
        if 'file' not in request.FILES:
            return JsonResponse({'success': False, 'error': 'No file provided'}, status=400)
        
        # Get the source parameter
        source = request.POST.get('source', 'SMIMS')  # Default to SMIMS if not provided
        if source not in ['SMIMS', 'EMHware']:
            return JsonResponse({'success': False, 'error': 'Invalid source. Must be SMIMS or EMHware.'}, status=400)
        
        file = request.FILES['file']
        file_extension = file.name.split('.')[-1].lower()
        
        if file_extension not in ['csv', 'xlsx', 'xls']:
            return JsonResponse({'success': False, 'error': 'Invalid file format. Please upload CSV or Excel files.'}, status=400)
        
        # Read the file
        try:
            if file_extension == 'csv':
                # Try different encodings for CSV files
                encodings_to_try = ['latin-1', 'cp1252', 'iso-8859-1', 'utf-8', 'utf-16', 'utf-16le', 'utf-16be']
                df = None
                last_error = None
                
                for encoding in encodings_to_try:
                    try:
                        file.seek(0)  # Reset file pointer
                        df = pd.read_csv(file, encoding=encoding)
                        break
                    except (UnicodeDecodeError, UnicodeError) as e:
                        last_error = str(e)
                        continue
                    except Exception as e:
                        # Handle other pandas errors (like parsing issues)
                        last_error = str(e)
                        continue
                
                # If all encodings fail, try with error handling using StringIO
                if df is None:
                    try:
                        import io
                        file.seek(0)
                        # Read the file content and handle encoding errors
                        content = file.read()
                        # Try to decode with error replacement
                        try:
                            decoded_content = content.decode('latin-1')
                        except:
                            decoded_content = content.decode('utf-8', errors='replace')
                        
                        # Create StringIO object and read with pandas
                        string_io = io.StringIO(decoded_content)
                        df = pd.read_csv(string_io)
                    except Exception as e:
                        return JsonResponse({'success': False, 'error': f'Could not read CSV file with any supported encoding. Last error: {last_error}. Fallback error: {str(e)}'}, status=400)
            
            else:
                df = pd.read_excel(file)
        except Exception as e:
            return JsonResponse({'success': False, 'error': f'Error reading file: {str(e)}'}, status=400)
        
        # Create case-insensitive field mapping
        def create_field_mapping(df_columns):
            """Create a mapping from case-insensitive column names to standardized field names"""
            import os
            import json
            
            # Load field mapping from JSON file
            current_dir = os.path.dirname(os.path.abspath(__file__))
            json_file_path = os.path.join(current_dir, 'field_mapping.json')
            
            try:
                with open(json_file_path, 'r') as f:
                    field_mapping_data = json.load(f)
                    field_mapping = field_mapping_data['field_mapping']
            except (FileNotFoundError, json.JSONDecodeError) as e:
                logger.error(f"Error loading field mapping from JSON: {e}")
                # Fallback to basic mapping if JSON file is not found or corrupted
                field_mapping = {
                    'first_name': ['first_name', 'first name', 'firstname', 'fname', 'given name', 'First Name', 'FIRST NAME'],
                    'last_name': ['last_name', 'last name', 'lastname', 'lname', 'surname', 'family name', 'Last Name', 'LAST NAME'],
                    'email': ['email', 'e-mail', 'email address', 'e_mail'],
                    'phone': ['phone_number', 'phone number', 'phone', 'telephone', 'tel', 'mobile', 'cell', 'Phone', 'PHONE'],
                    'dob': ['dob', 'date of birth', 'birthdate', 'birth date', 'dateofbirth', 'DOB', 'DOB'],
                }
            
            # Create reverse mapping from column names to standardized names
            column_mapping = {}
            df_columns_lower = [col.lower().strip() for col in df_columns]
            
            print(f"DEBUG: CSV columns: {df_columns}")
            print(f"DEBUG: Looking for DOB column mapping...")
            
            for standard_name, variations in field_mapping.items():
                for variation in variations:
                    variation_lower = variation.lower().strip()
                    if variation_lower in df_columns_lower:
                        # Find the original column name (case-sensitive)
                        original_col = df_columns[df_columns_lower.index(variation_lower)]
                        column_mapping[original_col] = standard_name
                        if standard_name == 'dob':
                            print(f"DEBUG: DOB column found: '{original_col}' -> '{standard_name}'")
                        break
            
            return column_mapping
        
        # Create field mapping
        column_mapping = create_field_mapping(df.columns)
        
        # Debug: Log the column mapping
        print(f"DEBUG: Column mapping: {column_mapping}")
        print(f"DEBUG: DataFrame columns: {list(df.columns)}")
        
        # Debug: Check if phone_number column is being mapped correctly
        if 'phone_number' in df.columns:
            print(f"DEBUG: phone_number column found in CSV")
            print(f"DEBUG: phone_number column mapped to: '{column_mapping.get('phone_number', 'NOT_MAPPED')}'")
        else:
            print(f"DEBUG: phone_number column NOT found in CSV")
            print(f"DEBUG: Available columns with 'phone' in name: {[col for col in df.columns if 'phone' in col.lower()]}")
        
        # Debug: Check if client_id column is being mapped correctly
        if 'client_id' in df.columns:
            print(f"DEBUG: client_id column found in CSV")
            print(f"DEBUG: client_id column mapped to: '{column_mapping.get('client_id', 'NOT_MAPPED')}'")
        else:
            print(f"DEBUG: client_id column NOT found in CSV")
            print(f"DEBUG: Available columns with 'client' in name: {[col for col in df.columns if 'client' in col.lower()]}")
        
        # Debug: Check if we have client_id column (now required for all uploads)
        # Check if any column maps to client_id (not just exact column name)
        has_client_id = any(column_mapping.get(col) == 'client_id' for col in df.columns)
        print(f"DEBUG: Has client_id column: {has_client_id}")
        if has_client_id:
            client_id_col = next((col for col in df.columns if column_mapping.get(col) == 'client_id'), None)
            print(f"DEBUG: client_id column found: '{client_id_col}' - will check for existing clients with matching client_id + source to determine if update or new creation")
        else:
            print(f"DEBUG: client_id column NOT found - this will cause validation error")
        
        # Check if any row has a Client ID + Source combination that exists in the database - if so, we'll allow updates with partial data
        has_existing_client_ids = False
        for col in df.columns:
            if column_mapping.get(col) == 'client_id':
                print(f"DEBUG: Found client_id column: '{col}'")
                # Check if any of the client_ids + source combinations in the CSV actually exist in the database
                for index, row in df.iterrows():
                    client_id_value = row[col]
                    print(f"DEBUG: Row {index + 1}: Checking client_id value: '{client_id_value}' with source: '{source}'")
                    if pd.notna(client_id_value) and str(client_id_value).strip():
                        client_id_clean = str(client_id_value).strip()
                        print(f"DEBUG: Row {index + 1}: Looking up client_id '{client_id_clean}' with source '{source}' in database")
                        existing_client = Client.objects.filter(client_id=client_id_clean, source=source).first()
                        print(f"DEBUG: Row {index + 1}: Database lookup result: {existing_client}")
                        if existing_client:
                            has_existing_client_ids = True
                            print(f"DEBUG: Found existing client with ID '{client_id_value}' and source '{source}' - will allow updates")
                            break
                if has_existing_client_ids:
                    break
        
        print(f"DEBUG: Final has_existing_client_ids: {has_existing_client_ids}")
        
        # Check for required fields using case-insensitive mapping
        # Note: client_id is now required for ALL uploads (both new and updates)
        # For updates: only client_id is required
        # For new clients: client_id, first_name, last_name, and either phone or dob are required
        if has_existing_client_ids:
            # If we have existing clients, this is an update - only require client_id
            required_fields = ['client_id']
        else:
            # If no existing clients, this is new client creation - require full set
            required_fields = ['client_id', 'first_name', 'last_name']
        missing_fields = []
        
        # Debug logging
        debug_info = {
            'column_mapping': column_mapping,
            'has_existing_client_ids': has_existing_client_ids,
            'df_columns': list(df.columns)
        }
        
        # Enforce required fields for all uploads (client_id is now required for both new and updates)
        # Special handling for combined client field - if present, it can provide client_id, first_name, last_name
        has_combined_client_field = False
        for col in df.columns:
            if column_mapping.get(col) == 'client_combined':
                has_combined_client_field = True
                print(f"DEBUG: Found combined client field: '{col}' - can provide client_id, first_name, last_name")
                break
        
        for required_field in required_fields:
            found = False
            for col in df.columns:
                if column_mapping.get(col) == required_field:
                    found = True
                    break
            
            # If not found individually, check if combined client field can provide it
            if not found and has_combined_client_field:
                if required_field in ['client_id', 'first_name', 'last_name']:
                    found = True
                    print(f"DEBUG: Combined client field can provide '{required_field}'")
            
            if not found:
                missing_fields.append(required_field)
        
        if missing_fields:
            return JsonResponse({
                'success': False, 
                'error': f'Missing required columns. Please include columns for: {", ".join(missing_fields)}. Note: client_id is now required for all uploads.'
            }, status=400)
        
        # Check that at least one of phone OR dob is present (only for new clients)
        if not has_existing_client_ids:
            has_phone = any(column_mapping.get(col) == 'phone' for col in df.columns)
            has_dob = any(column_mapping.get(col) == 'dob' for col in df.columns)
            
            print(f"DEBUG: Has phone column: {has_phone}")
            print(f"DEBUG: Has dob column: {has_dob}")
            
            if not has_phone and not has_dob:
                return JsonResponse({
                    'success': False, 
                    'error': 'At least one of phone or DOB columns is required for new client creation. Please include either a phone number column or a date of birth (DOB) column.'
                }, status=400)
        
        # Check for intake-related columns using case-insensitive mapping
        has_intake_data = False
        for col in df.columns:
            if column_mapping.get(col) in ['program_name', 'intake_date']:
                has_intake_data = True
                break
        
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
        
        def parse_combined_client_field(client_field_value, client_id_field_value=None):
            """
            Parse client field that can be in two formats:
            1. Combined: 'Last, First (ID)' - everything in one field
            2. Separate: 'Last, First' + client_id from separate field
            
            Handles various name formats:
            - Abdul-Azim,  Safi
            - Abdirazaq Warsame,  Mohamed  
            - A. Hussein,  Mohamud
            - Abbakar,  Tagwa Seddig Adam
            - Abdoun Mohamed,  Sarah Hassan
            
            Returns: (first_name, last_name, client_id)
            """
            if not client_field_value or str(client_field_value).strip() == '':
                return None, None, None
            
            client_str = str(client_field_value).strip()
            client_id = None
            
            import re
            
            # Pattern 1: "Last, First (ID)" - Last, First with ID in parentheses
            pattern1 = r'^([A-Za-z\s.-]+),\s+([A-Za-z\s.-]+)\s*\((\d+)\)$'
            match1 = re.match(pattern1, client_str)
            if match1:
                last_name = match1.group(1).strip()    # "Abdul-Azim"
                first_name = match1.group(2).strip()   # "Safi"
                client_id = match1.group(3).strip()    # "12345"
                
                return first_name, last_name, client_id
            
            # Pattern 2: "Last, First" - Last, First without ID (ID from separate field)
            pattern2 = r'^([A-Za-z\s.-]+),\s+([A-Za-z\s.-]+)$'
            match2 = re.match(pattern2, client_str)
            if match2:
                last_name = match2.group(1).strip()    # "Abdul-Azim"
                first_name = match2.group(2).strip()   # "Safi"
                
                # Use client_id from separate field if provided
                if client_id_field_value and str(client_id_field_value).strip():
                    client_id = str(client_id_field_value).strip()
                    return first_name, last_name, client_id
                else:
                    # Return names but no client_id
                    return first_name, last_name, None
            
            # If no pattern matches, return None
            return None, None, None
        
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
        
        def process_intake_data(client, row, index, column_mapping, df_columns):
            """Process intake data for a client"""
            try:
                # Helper function to get data using field mapping
                def get_field_data(field_name, default=''):
                    """Get data from row using field mapping"""
                    for col in df_columns:
                        if column_mapping.get(col) == field_name:
                            value = row[col]
                            if pd.notna(value) and str(value).strip():
                                return str(value).strip()
                    return default
                
                # Helper function to parse boolean values safely
                def parse_boolean(value, default=False):
                    """Parse boolean value from string, handling empty values"""
                    if not value or value.strip() == '':
                        return default
                    return str(value).lower().strip() in ['true', '1', 'yes', 'y']
                
                # Helper function to parse integer values safely
                def parse_integer(value, default=None):
                    """Parse integer value from string, handling empty values"""
                    if not value or value.strip() == '':
                        return default
                    try:
                        return int(str(value).strip())
                    except (ValueError, TypeError):
                        return default
                
                # Helper function to parse date values safely
                def parse_date(value, default=None):
                    """Parse date value from string, handling empty values"""
                    if not value or value.strip() == '':
                        return default
                    try:
                        return pd.to_datetime(value).date()
                    except (ValueError, TypeError):
                        return default
                
                program_name = get_field_data('program_name')
                program_department = get_field_data('program_department')
                # Use the source from the form (upload type selection), not from CSV
                
                print(f"DEBUG: Program enrollment data - program_name: '{program_name}', source: '{source}'")
                intake_date_value = get_field_data('intake_date')
                if intake_date_value:
                    intake_date = pd.to_datetime(intake_date_value).date()
                else:
                    intake_date = datetime.now().date()
                intake_database = get_field_data('intake_database', 'CCD')
                referral_source = get_field_data('referral_source', source)
                intake_housing_status = get_field_data('intake_housing_status', 'unknown')
                
                if not program_name:
                    logger.warning(f"No program name provided for client {client.first_name} {client.last_name}")
                    return
                
                # Handle multiple programs in a single cell (separated by newlines)
                program_names = [name.strip() for name in str(program_name).split('\n') if name.strip()]
                print(f"DEBUG: Split program names: {program_names}")
                
                # Handle multiple dates in a single cell (separated by newlines)
                intake_dates = []
                if intake_date_value:
                    date_strings = [date.strip() for date in str(intake_date_value).split('\n') if date.strip()]
                    for date_str in date_strings:
                        try:
                            intake_dates.append(pd.to_datetime(date_str).date())
                        except:
                            intake_dates.append(intake_date)  # fallback to default
                else:
                    intake_dates = [intake_date]  # use default date
                
                print(f"DEBUG: Split intake dates: {intake_dates}")
                
                # Ensure we have the same number of programs and dates
                # If we have more programs than dates, repeat the last date
                # If we have more dates than programs, repeat the last program
                while len(intake_dates) < len(program_names):
                    intake_dates.append(intake_dates[-1] if intake_dates else intake_date)
                while len(program_names) < len(intake_dates):
                    program_names.append(program_names[-1] if program_names else program_name)
                
                print(f"DEBUG: Final program-date pairs: {list(zip(program_names, intake_dates))}")
                
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
                    # Default to NA if no department specified
                    department, created = Department.objects.get_or_create(
                        name='NA',
                        defaults={'owner': 'System'}
                    )
                
                # Get additional enrollment fields using field mapping (outside loop for efficiency)
                sub_program = get_field_data('sub_program')
                support_workers = get_field_data('support_workers')
                level_of_support = get_field_data('level_of_support')
                client_type = get_field_data('client_type')
                discharge_date_value = get_field_data('discharge_date')
                days_elapsed_value = get_field_data('days_elapsed')
                program_status = get_field_data('program_status', 'pending')
                reason_discharge = get_field_data('reason_discharge')
                receiving_services_value = get_field_data('receiving_services', 'false')
                
                # Parse dates
                discharge_date = parse_date(discharge_date_value)
                
                # Parse days elapsed
                days_elapsed = parse_integer(days_elapsed_value)
                
                # Parse receiving services
                receiving_services = parse_boolean(receiving_services_value)
                
                # Process each program-date pair
                for i, (current_program_name, current_intake_date) in enumerate(zip(program_names, intake_dates)):
                    print(f"DEBUG: Processing program {i+1}/{len(program_names)}: '{current_program_name}' with date {current_intake_date}")
                    
                    # Get or create program
                    program, created = Program.objects.get_or_create(
                        name=current_program_name,
                        department=department,
                        defaults={
                            'location': 'TBD',
                            'status': 'suggested' if created else 'active',
                            'description': f'Program created from intake data - {source}'
                        }
                    )
                    
                    if created:
                        logger.info(f"Created new program: {current_program_name} (status: suggested)")
                    else:
                        # If program exists but is suggested, keep it as suggested
                        if program.status == 'suggested':
                            logger.info(f"Program {current_program_name} already exists with suggested status")
                    
                    # Create intake record
                    intake, created = Intake.objects.get_or_create(
                        client=client,
                        program=program,
                        defaults={
                            'department': department,
                            'intake_date': current_intake_date,
                            'intake_database': intake_database,
                            'referral_source': referral_source,
                            'intake_housing_status': intake_housing_status,
                            'notes': f'Intake created from {source} upload (program {i+1})'
                        }
                    )
                    
                    if created:
                        logger.info(f"Created intake record for {client.first_name} {client.last_name} in {current_program_name}")
                    else:
                        logger.info(f"Intake record already exists for {client.first_name} {client.last_name} in {current_program_name}")
                    
                    # Create enrollment for this program
                    # Build notes with additional information
                    notes_parts = [f'Enrollment created from {source} intake']
                    if level_of_support:
                        notes_parts.append(f'Level of Support: {level_of_support}')
                    if client_type:
                        notes_parts.append(f'Client Type: {client_type}')
                    if referral_source:
                        notes_parts.append(f'Referral Source: {referral_source}')
                    if support_workers:
                        notes_parts.append(f'Support Workers: {support_workers}')
                    if reason_discharge:
                        notes_parts.append(f'Reason for Discharge: {reason_discharge}')
                    
                    enrollment, created = ClientProgramEnrollment.objects.get_or_create(
                        client=client,
                        program=program,
                        defaults={
                            'start_date': current_intake_date,  # Use current_intake_date instead of intake_date
                            'end_date': discharge_date,
                            'status': program_status,
                            'days_elapsed': days_elapsed,
                            'notes': ' | '.join(notes_parts),
                            'created_by': request.user.get_full_name() or request.user.username if request.user.is_authenticated else 'System'
                        }
                        )
                    
                    if created:
                        logger.info(f"Created pending enrollment for {client.first_name} {client.last_name} in {current_program_name}")
                        print(f"DEBUG: Successfully created enrollment for {client.first_name} {client.last_name} in {current_program_name}")
                        
                        # Create audit log entry for enrollment creation
                        try:
                            from core.models import create_audit_log
                            create_audit_log(
                                entity_name='Enrollment',
                                entity_id=enrollment.external_id,
                                action='create',
                                changed_by=None,  # Bulk import, no specific user
                                diff_data={
                                    'client': str(enrollment.client),
                                    'program': str(enrollment.program),
                                    'start_date': str(enrollment.start_date),
                                    'status': enrollment.status,
                                    'source': 'bulk_import'
                                }
                            )
                        except Exception as e:
                            logger.error(f"Error creating audit log for enrollment: {e}")
                    else:
                        print(f"DEBUG: Enrollment already exists for {client.first_name} {client.last_name} in {current_program_name}")
                        logger.info(f"Enrollment already exists for {client.first_name} {client.last_name} in {current_program_name}")
                    
            except Exception as e:
                logger.error(f"Error processing intake data for row {index + 2}: {str(e)}")
                errors.append(f"Row {index + 2} (Intake): {str(e)}")
        
        def find_duplicate_client(client_data):
            """Find duplicate client based on email, phone, and name similarity"""
            contact_info = client_data.get('contact_information', {})
            email = contact_info.get('email', '').strip()
            phone = contact_info.get('phone', '').strip()
            full_name = f"{client_data.get('first_name', '')} {client_data.get('last_name', '')}".strip()
            dob = client_data.get('dob', '')

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

            # Priority 5: Name + Date of Birth combination
            if full_name and dob and dob != datetime(1900, 1, 1).date():  # Skip default DOB
                name_dob_match = Client.objects.filter(
                    first_name__iexact=client_data.get('first_name', '').strip(),
                    last_name__iexact=client_data.get('last_name', '').strip(),
                    dob=dob
                ).first()
                if name_dob_match:
                    return name_dob_match, "name_dob_match"

            # Priority 6: Date of Birth + Name similarity (if DOB is valid and not default)
            if dob and dob != datetime(1900, 1, 1).date():
                dob_clients = Client.objects.filter(dob=dob)
                for client in dob_clients:
                    client_full_name = f"{client.first_name} {client.last_name}".strip()
                    similarity = calculate_name_similarity(full_name, client_full_name)
                    
                    # If names are similar (70%+ similarity) and DOB matches, consider it a duplicate
                    if similarity >= 0.7:
                        return client, f"dob_name_similarity_{similarity:.2f}"
            
            return None, None
        
        for index, row in df.iterrows():
            try:
                # Helper function to get data using field mapping
                def get_field_data(field_name, default=''):
                    """Get data from row using field mapping"""
                    for col in df.columns:
                        if column_mapping.get(col) == field_name:
                            value = row[col]
                            if pd.notna(value) and str(value).strip():
                                return str(value).strip()
                    return default
                
                # Helper function to parse boolean values safely
                def parse_boolean(value, default=False):
                    """Parse boolean value from string, handling empty values"""
                    if not value or value.strip() == '':
                        return default
                    return str(value).lower().strip() in ['true', '1', 'yes', 'y']
                
                # Helper function to parse integer values safely
                def parse_integer(value, default=None):
                    """Parse integer value from string, handling empty values"""
                    if not value or value.strip() == '':
                        return default
                    try:
                        return int(str(value).strip())
                    except (ValueError, TypeError):
                        return default
                
                # Helper function to parse date values safely
                def parse_date(value, default=None):
                    """Parse date value from string, handling empty values"""
                    if not value or value.strip() == '':
                        return default
                    try:
                        return pd.to_datetime(value).date()
                    except (ValueError, TypeError):
                        return default
                
                # Helper function to clean client_id and ensure it's a whole number string
                def clean_client_id(value):
                    """Clean client_id to ensure it's a whole number string without decimals"""
                    if not value or str(value).strip() == '':
                        return None
                    
                    try:
                        # Convert to string first
                        str_value = str(value).strip()
                        
                        # If it's a decimal number (like 2765.0), convert to integer then back to string
                        if '.' in str_value:
                            # Check if it's a whole number decimal (like 2765.0)
                            float_val = float(str_value)
                            if float_val.is_integer():
                                return str(int(float_val))
                            else:
                                # If it has actual decimal places, keep as is
                                return str_value
                        else:
                            # Already a whole number, return as string
                            return str_value
                    except (ValueError, TypeError):
                        return str(value).strip() if value else None

                # Clean and prepare data using field mapping
                email = get_field_data('email')  # Now optional
                phone = get_field_data('phone')
                client_id = get_field_data('client_id')
                
                # Debug: Log what we're getting for phone and client_id
                print(f"Row {index + 1}: phone value from get_field_data('phone'): '{phone}'")
                print(f"Row {index + 1}: client_id value from get_field_data('client_id'): '{client_id}'")
                
                # Debug: Log the actual row data for phone_number and client_id columns
                print(f"Row {index + 1}: Raw row data for phone_number column: '{row.get('phone_number', 'NOT_FOUND')}'")
                print(f"Row {index + 1}: Raw row data for client_id column: '{row.get('client_id', 'NOT_FOUND')}'")
                
                # Debug: Log the column mapping for phone-related fields
                print(f"Row {index + 1}: Column mapping for phone fields:")
                for col in df.columns:
                    if 'phone' in col.lower() or column_mapping.get(col) == 'phone':
                        print(f"  Column '{col}' -> Field '{column_mapping.get(col)}'")
                
                # Debug: Test get_field_data function directly
                print(f"Row {index + 1}: Testing get_field_data function:")
                for col in df.columns:
                    if column_mapping.get(col) == 'phone':
                        value = row[col]
                        print(f"  Found column '{col}' mapped to 'phone', value: '{value}', type: {type(value)}")
                        print(f"  pd.notna(value): {pd.notna(value)}")
                        print(f"  str(value).strip(): '{str(value).strip()}'")
                        if pd.notna(value) and str(value).strip():
                            print(f"  -> Would return: '{str(value).strip()}'")
                        else:
                            print(f"  -> Would return default: ''")
                
                # Debug: Log phone and client ID extraction
                debug_phone_info = f"Row {index + 1}: phone extracted = '{phone}'"
                debug_client_id_info = f"Row {index + 1}: client_id extracted = '{client_id}'"
                print(debug_phone_info)
                print(debug_client_id_info)
                
                # Debug: Log column mapping for phone
                phone_mapping_debug = f"Row {index + 1}: Column mapping for phone: {[(col, column_mapping.get(col)) for col in df.columns if 'phone' in col.lower() or 'Phone' in col]}"
                print(phone_mapping_debug)
                if not hasattr(debug_info, 'phone_debug'):
                    debug_info['phone_debug'] = []
                debug_info['phone_debug'].append(debug_phone_info)
                debug_info['phone_debug'].append(debug_client_id_info)
                
                # Handle date of birth - required for new clients, optional for updates
                dob = None
                try:
                    dob_value = get_field_data('dob')
                    print(f"DEBUG: Row {index + 1}: DOB value from get_field_data('dob'): {repr(dob_value)}")
                    if dob_value:
                        # Check if the value looks like a valid date format
                        dob_str = str(dob_value).strip().lower()
                        
                        # Skip values that are clearly not dates
                        if dob_str in ['yes', 'no', 'y', 'n', 'true', 'false', '1', '0', '']:
                            # These are not valid date values, treat as missing
                            dob_value = None
                        
                        if dob_value:
                            # Try to parse the date with multiple format attempts
                            try:
                                # First try pandas automatic parsing
                                dob = pd.to_datetime(dob_value).date()
                            except:
                                # If that fails, try specific date formats
                                dob_str = str(dob_value).strip()
                                try:
                                    # Try YYYY-MM-DD format
                                    dob = datetime.strptime(dob_str, '%Y-%m-%d').date()
                                except:
                                    # Try other common formats
                                    try:
                                        dob = datetime.strptime(dob_str, '%Y/%m/%d').date()
                                    except:
                                        try:
                                            dob = datetime.strptime(dob_str, '%m/%d/%Y').date()
                                        except:
                                            try:
                                                dob = datetime.strptime(dob_str, '%d/%m/%Y').date()
                                            except:
                                                # If all parsing attempts fail, raise the original error
                                                raise ValueError(f"Unable to parse date: {dob_str}")
                    else:
                        # Check if this is an update (has Client ID) - if so, DOB is optional
                        client_id = get_field_data('client_id')
                        if not client_id:
                            # This is a new client creation, DOB is required
                            errors.append(f"Row {index + 1}: Date of Birth is required for new client creation")
                            skipped_count += 1
                            continue
                        # For updates, we can proceed without DOB
                except Exception as e:
                    # If date parsing fails, check if this is a new client or update
                    client_id = get_field_data('client_id')
                    if not client_id:
                        # This is a new client creation, DOB is required
                        errors.append(f"Row {index + 1}: Invalid Date of Birth format - {str(e)}")
                        skipped_count += 1
                        continue
                    # For updates, we can proceed without DOB
                
                client_data = {
                    'first_name': get_field_data('first_name'),
                    'last_name': get_field_data('last_name'),
                    'middle_name': get_field_data('middle_name'),
                    'dob': dob,
                    'preferred_name': get_field_data('preferred_name'),
                    'alias': get_field_data('alias'),
                    'gender': get_field_data('gender', 'Unknown'),
                    'gender_identity': get_field_data('gender_identity'),
                    'pronoun': get_field_data('pronoun'),
                    'marital_status': get_field_data('marital_status'),
                    'citizenship_status': get_field_data('citizenship_status'),
                    'location_county': get_field_data('location_county'),
                    'province': get_field_data('province'),
                    'city': get_field_data('city'),
                    'postal_code': get_field_data('postal_code'),
                    'address': get_field_data('address'),
                    'address_2': get_field_data('address_2'),
                    'language': get_field_data('language'),
                    'preferred_language': get_field_data('preferred_language'),
                    'mother_tongue': get_field_data('mother_tongue'),
                    'official_language': get_field_data('official_language'),
                    'language_interpreter_required': parse_boolean(get_field_data('language_interpreter_required')),
                    'self_identification_race_ethnicity': get_field_data('self_identification_race_ethnicity'),
                    'lgbtq_status': get_field_data('lgbtq_status'),
                    'highest_level_education': get_field_data('highest_level_education'),
                    'children_home': parse_boolean(get_field_data('children_home')),
                    'children_number': parse_integer(get_field_data('children_number')),
                    'lhin': get_field_data('lhin'),
                    'client_id': clean_client_id(get_field_data('client_id')),
                    'phone': get_field_data('phone'),
                    'email': email,  # Add email to direct field
                    'source': source,  # Add the source field from the form
                    'level_of_support': get_field_data('level_of_support'),
                    'client_type': get_field_data('client_type'),
                    'referral_source': get_field_data('referral_source'),
                    'phone_work': get_field_data('phone_work'),
                    'phone_alt': get_field_data('phone_alt'),
                    'permission_to_phone': parse_boolean(get_field_data('permission_to_phone')),
                    'permission_to_email': parse_boolean(get_field_data('permission_to_email')),
                    'medical_conditions': get_field_data('medical_conditions'),
                    'primary_diagnosis': get_field_data('primary_diagnosis'),
                    'family_doctor': get_field_data('family_doctor'),
                    'health_card_number': get_field_data('health_card_number'),
                    'health_card_version': get_field_data('health_card_version'),
                    'health_card_exp_date': parse_date(get_field_data('health_card_exp_date')),
                    'health_card_issuing_province': get_field_data('health_card_issuing_province'),
                    'no_health_card_reason': get_field_data('no_health_card_reason'),
                    'next_of_kin': get_field_data('next_of_kin'),
                    'emergency_contact': get_field_data('emergency_contact'),
                    'comments': get_field_data('comments'),
                    'chart_number': get_field_data('chart_number'),
                    'contact_information': {
                        'email': email,
                        'phone': phone,
                    },
                    # Extended fields for ClientExtended model
                    'indigenous_identity': get_field_data('indigenous_identity'),
                    'military_status': get_field_data('military_status'),
                    'refugee_status': get_field_data('refugee_status'),
                    'household_size': parse_integer(get_field_data('household_size')),
                    'family_head_client_no': get_field_data('family_head_client_no'),
                    'relationship': get_field_data('relationship'),
                    'primary_worker': get_field_data('primary_worker'),
                    'chronically_homeless': parse_boolean(get_field_data('chronically_homeless')),
                    'num_bednights_current_stay': parse_integer(get_field_data('num_bednights_current_stay')),
                    'length_homeless_3yrs': parse_integer(get_field_data('length_homeless_3yrs')),
                    'income_source': get_field_data('income_source'),
                    'taxation_year_filed': get_field_data('taxation_year_filed'),
                    'status_id': get_field_data('status_id'),
                    'picture_id': get_field_data('picture_id'),
                    'other_id': get_field_data('other_id'),
                    'bnl_consent': parse_boolean(get_field_data('bnl_consent')),
                    'allergies': get_field_data('allergies'),
                    'harm_reduction_support': parse_boolean(get_field_data('harm_reduction_support')),
                    'medication_support': parse_boolean(get_field_data('medication_support')),
                    'pregnancy_support': parse_boolean(get_field_data('pregnancy_support')),
                    'mental_health_support': parse_boolean(get_field_data('mental_health_support')),
                    'physical_health_support': parse_boolean(get_field_data('physical_health_support')),
                    'daily_activities_support': parse_boolean(get_field_data('daily_activities_support')),
                    'other_health_supports': get_field_data('other_health_supports'),
                    'cannot_use_stairs': parse_boolean(get_field_data('cannot_use_stairs')),
                    'limited_mobility': parse_boolean(get_field_data('limited_mobility')),
                    'wheelchair_accessibility': parse_boolean(get_field_data('wheelchair_accessibility')),
                    'vision_hearing_speech_supports': get_field_data('vision_hearing_speech_supports'),
                    'english_translator': parse_boolean(get_field_data('english_translator')),
                    'reading_supports': parse_boolean(get_field_data('reading_supports')),
                    'other_accessibility_supports': get_field_data('other_accessibility_supports'),
                    'pet_owner': parse_boolean(get_field_data('pet_owner')),
                    'legal_support': parse_boolean(get_field_data('legal_support')),
                    'immigration_support': parse_boolean(get_field_data('immigration_support')),
                    'religious_cultural_supports': get_field_data('religious_cultural_supports'),
                    'safety_concerns': get_field_data('safety_concerns'),
                    'intimate_partner_violence_support': parse_boolean(get_field_data('intimate_partner_violence_support')),
                    'human_trafficking_support': parse_boolean(get_field_data('human_trafficking_support')),
                    'other_supports': get_field_data('other_supports'),
                    'access_to_housing_application': get_field_data('access_to_housing_application'),
                    'access_to_housing_no': get_field_data('access_to_housing_no'),
                    'access_point_application': get_field_data('access_point_application'),
                    'access_point_no': get_field_data('access_point_no'),
                    'cars': get_field_data('cars'),
                    'cars_no': parse_integer(get_field_data('cars_no')),
                    'discharge_disposition': get_field_data('discharge_disposition'),
                    'intake_status': get_field_data('intake_status'),
                    'lived_last_12_months': get_field_data('lived_last_12_months'),
                    'reason_for_service': get_field_data('reason_for_service'),
                    'intake_date': parse_date(get_field_data('intake_date')),
                    'service_end_date': parse_date(get_field_data('service_end_date')),
                    'rejection_date': parse_date(get_field_data('rejection_date')),
                    'rejection_reason': get_field_data('rejection_reason'),
                    'room': get_field_data('room'),
                    'bed': get_field_data('bed'),
                    'occupancy_status': get_field_data('occupancy_status'),
                    'bed_nights_historical': parse_integer(get_field_data('bed_nights_historical')),
                    'restriction_reason': get_field_data('restriction_reason'),
                    'restriction_date': parse_date(get_field_data('restriction_date')),
                    'restriction_duration_days': parse_integer(get_field_data('restriction_duration_days')),
                    'restriction_status': get_field_data('restriction_status'),
                    'early_termination_by': get_field_data('early_termination_by')
                }
                
                # OPTIONAL: Check for combined client field (only if present) - MUST happen before validation
                combined_client_value = None
                client_id_from_separate_field = None
                
                # Look for combined client field
                for col in df.columns:
                    if column_mapping.get(col) == 'client_combined':
                        combined_client_value = row[col]
                        break
                
                # Look for separate client_id field
                for col in df.columns:
                    if column_mapping.get(col) == 'client_id':
                        client_id_from_separate_field = row[col]
                        print(f"Row {index + 1}: Found separate client_id field '{col}' with value: '{client_id_from_separate_field}'")
                        break
                
                # Only parse if combined field exists AND has a value
                if combined_client_value and str(combined_client_value).strip():
                    print(f"Row {index + 1}: Parsing combined client field '{combined_client_value}' with separate client_id '{client_id_from_separate_field}'")
                    parsed_first, parsed_last, parsed_client_id = parse_combined_client_field(
                        combined_client_value, 
                        client_id_from_separate_field
                    )
                    print(f"Row {index + 1}: Parsing result - First: '{parsed_first}', Last: '{parsed_last}', ID: '{parsed_client_id}'")
                    
                    # Only override if parsing was successful
                    if parsed_first and parsed_last:
                        client_data['first_name'] = parsed_first
                        client_data['last_name'] = parsed_last
                        
                        # Only override client_id if we successfully parsed it
                        if parsed_client_id:
                            client_data['client_id'] = clean_client_id(parsed_client_id)
                        
                        print(f"Row {index + 1}: Parsed combined client field - First: '{parsed_first}', Last: '{parsed_last}', ID: '{parsed_client_id}'")
                    else:
                        print(f"Row {index + 1}: Combined client field found but parsing failed, using individual fields")
                
                # Handle languages_spoken (expect comma-separated string)
                languages = get_field_data('language')
                if languages:
                    client_data['languages_spoken'] = [lang.strip() for lang in languages.split(',') if lang.strip()]
                else:
                    client_data['languages_spoken'] = []
                
                # Handle ethnicity (expect comma-separated string)
                ethnicity = get_field_data('ethnicity')
                if ethnicity:
                    client_data['ethnicity'] = [eth.strip() for eth in ethnicity.split(',') if eth.strip()]
                else:
                    client_data['ethnicity'] = []
                
                # Handle support_workers (expect comma-separated string)
                support_workers = get_field_data('support_workers')
                if support_workers:
                    client_data['support_workers'] = [worker.strip() for worker in support_workers.split(',') if worker.strip()]
                # Don't set empty list if no support_workers column exists - this prevents overwriting existing data
                
                # Handle next_of_kin (expect JSON string or simple text)
                next_of_kin = get_field_data('next_of_kin')
                if next_of_kin:
                    try:
                        client_data['next_of_kin'] = json.loads(next_of_kin)
                    except json.JSONDecodeError:
                        # If JSON parsing fails, create a simple dict with the string
                        client_data['next_of_kin'] = {'name': next_of_kin}
                else:
                    client_data['next_of_kin'] = {}
                
                # Handle emergency_contact (expect JSON string or simple text)
                emergency_contact = get_field_data('emergency_contact')
                if emergency_contact:
                    try:
                        client_data['emergency_contact'] = json.loads(emergency_contact)
                    except json.JSONDecodeError:
                        # If JSON parsing fails, create a simple dict with the string
                        client_data['emergency_contact'] = {'name': emergency_contact}
                else:
                    client_data['emergency_contact'] = {}
                
                # Handle addresses (expect JSON string or individual address fields)
                addresses = []
                if 'addresses' in row and pd.notna(row['addresses']):
                    try:
                        addresses = json.loads(str(row['addresses']))
                    except:
                        addresses = []
                elif get_field_data('address'):
                    address = {
                        'type': get_field_data('address_type', 'Home'),
                        'street': get_field_data('address'),
                        'address_2': get_field_data('address_2'),
                        'city': get_field_data('city'),
                        'state': get_field_data('province'),
                        'zip': get_field_data('postal_code'),
                        'country': 'USA'  # Default country
                    }
                    if any(address.values()):
                        addresses = [address]
                
                client_data['addresses'] = addresses
                
                # Check for duplicates using our custom logic
                duplicate_client, match_type = find_duplicate_client(client_data)
                client = None  # Initialize client variable
                original_email = ''
                original_phone = ''
                original_client_id = ''
                
                # Check for existing client_id first - this is the primary update mechanism
                existing_client_id = None
                client = None
                is_update = False
                
                if client_data.get('client_id'):
                    try:
                        # Debug: Log Client ID + Source lookup
                        client_id_to_find = client_data['client_id']
                        print(f"Row {index + 1}: Looking for existing client with Client ID: '{client_id_to_find}' and Source: '{source}'")
                        
                        # Match by both client_id AND source - only update if both match
                        existing_client_id = Client.objects.filter(client_id=client_data['client_id'], source=source).first()
                        print(f"Row {index + 1}: Found existing client: {existing_client_id}")
                        
                        if existing_client_id:
                            # Found existing client by Client ID + Source combination - UPDATE instead of CREATE
                            client = existing_client_id
                            is_update = True
                            updated_count += 1
                            print(f"Row {index + 1}: Will UPDATE existing client (client_id + source match)")
                            
                            # Update the existing client with new data (only non-empty values)
                            # Filter out empty values to prevent overwriting existing data
                            
                            # Debug: Log what's in client_data before filtering
                            print(f"Row {index + 1}: client_data keys: {list(client_data.keys())}")
                            if 'gender' in client_data:
                                print(f"Row {index + 1}: gender in client_data: '{client_data['gender']}'")
                            if 'contact_information' in client_data:
                                print(f"Row {index + 1}: contact_information in client_data: {client_data['contact_information']}")
                            
                            # For updates, only include fields that are actually present in the CSV
                            filtered_data = {}
                            
                            # Get all fields that are mapped from CSV columns
                            csv_fields = set()
                            for col in df.columns:
                                field_name = column_mapping.get(col)
                                if field_name:
                                    csv_fields.add(field_name)
                            
                            # Only include fields that exist in the CSV and have non-empty values
                            for field, value in client_data.items():
                                # Skip if field is not in CSV
                                if field not in csv_fields:
                                    continue
                                    
                                # Skip if value is None, empty string, or empty dict
                                if value is None:
                                    continue
                                if isinstance(value, str) and value.strip() == '':
                                    continue
                                if isinstance(value, dict) and not value:
                                    continue
                                    
                                # Handle contact_information specially - only include if it has actual values
                                if field == 'contact_information' and isinstance(value, dict):
                                    has_values = False
                                    for key, val in value.items():
                                        if val and str(val).strip():
                                            has_values = True
                                            break
                                    if not has_values:
                                        continue
                                
                                # Handle other dictionary fields (addresses, etc.) - only include if they have actual values
                                if isinstance(value, dict) and field not in ['contact_information']:
                                    has_values = False
                                    for key, val in value.items():
                                        if val and str(val).strip():
                                            has_values = True
                                            break
                                    if not has_values:
                                        continue
                                
                                filtered_data[field] = value
                            
                            # Debug: Log what fields are being updated
                            print(f"Row {index + 1}: Updating client {client.first_name} {client.last_name}")
                            print(f"Row {index + 1}: Original gender: '{client.gender}'")
                            print(f"Row {index + 1}: Filtered data fields: {list(filtered_data.keys())}")
                            if 'gender' in filtered_data:
                                print(f"Row {index + 1}: Gender in filtered_data: '{filtered_data['gender']}'")
                            
                            # Apply only the filtered (non-empty) values, excluding extended fields
                            extended_fields_list = [
                                'indigenous_identity', 'military_status', 'refugee_status', 'household_size',
                                'family_head_client_no', 'relationship', 'primary_worker', 'chronically_homeless',
                                'num_bednights_current_stay', 'length_homeless_3yrs', 'income_source',
                                'taxation_year_filed', 'status_id', 'picture_id', 'other_id', 'bnl_consent',
                                'allergies', 'harm_reduction_support', 'medication_support', 'pregnancy_support',
                                'mental_health_support', 'physical_health_support', 'daily_activities_support',
                                'other_health_supports', 'cannot_use_stairs', 'limited_mobility',
                                'wheelchair_accessibility', 'vision_hearing_speech_supports', 'english_translator',
                                'reading_supports', 'other_accessibility_supports', 'pet_owner', 'legal_support',
                                'immigration_support', 'religious_cultural_supports', 'safety_concerns',
                                'intimate_partner_violence_support', 'human_trafficking_support', 'other_supports',
                                'access_to_housing_application', 'access_to_housing_no', 'access_point_application',
                                'access_point_no', 'cars', 'cars_no', 'discharge_disposition', 'intake_status',
                                'lived_last_12_months', 'reason_for_service', 'intake_date', 'service_end_date',
                                'rejection_date', 'rejection_reason', 'room', 'bed', 'occupancy_status',
                                'bed_nights_historical', 'restriction_reason', 'restriction_date',
                                'restriction_duration_days', 'restriction_status', 'early_termination_by'
                            ]
                            
                            for field, value in filtered_data.items():
                                if hasattr(client, field) and field not in extended_fields_list:
                                    setattr(client, field, value)
                            
                            # Save the updated client
                            client.save()
                            logger.info(f"Updated existing client by Client ID {client_data['client_id']}: {client.first_name} {client.last_name}")
                            
                            # Update or create ClientExtended record
                            from core.models import ClientExtended
                            extended_data = {}
                            
                            # Extract extended fields from filtered_data (only non-empty values)
                            for field in extended_fields_list:
                                if field in filtered_data:
                                    value = filtered_data[field]
                                    if value is not None and value != '':
                                        if isinstance(value, str) and value.strip() != '':
                                            extended_data[field] = value.strip()
                                        elif not isinstance(value, str):
                                            extended_data[field] = value
                            
                            # Update or create ClientExtended record
                            if extended_data:
                                extended_record, created = ClientExtended.objects.get_or_create(
                                    client=client,
                                    defaults=extended_data
                                )
                                if not created:
                                    # Update existing record
                                    for field, value in extended_data.items():
                                        setattr(extended_record, field, value)
                                    extended_record.save()
                                    logger.info(f"Updated ClientExtended record for client {client.client_id}")
                                else:
                                    logger.info(f"Created ClientExtended record for client {client.client_id}")
                        else:
                            # Client ID exists but with different source - CREATE new client
                            print(f"Row {index + 1}: Client ID '{client_id_to_find}' exists but with different source - will CREATE new client")
                            is_update = False  # Reset to False since we're creating a new client
                        
                    except Exception as e:
                        logger.error(f"Error updating client with ID {client_data['client_id']}: {e}")
                        # Continue to create new client if update fails
                
                # Validate required fields for all rows (client_id is now required for all uploads)
                if not is_update:
                    # For new client creation, validate required fields (including client_id)
                    # Either phone OR dob is required (not both)
                    required_fields = ['client_id', 'first_name', 'last_name']
                    missing_required = []
                    
                    for field in required_fields:
                        value = client_data.get(field)
                        if not value or (isinstance(value, str) and value.strip() == ''):
                            missing_required.append(field)
                    
                    # Check that at least one of phone OR dob is present (only for new clients)
                    has_phone = False
                    has_dob = False
                    
                    # Check phone number in both locations
                    phone_value = client_data.get('contact_information', {}).get('phone')
                    if phone_value and isinstance(phone_value, str) and phone_value.strip() != '':
                        has_phone = True
                    else:
                        # Also check the direct phone field
                        phone_value = client_data.get('phone')
                        if phone_value and isinstance(phone_value, str) and phone_value.strip() != '':
                            has_phone = True
                    
                    # Check DOB
                    dob_value = client_data.get('dob')
                    if dob_value:
                        has_dob = True
                    
                    if not has_phone and not has_dob:
                        missing_required.append('phone_or_dob')
                    
                    # Debug: Log what's in client_data for required fields
                    debug_fields = []
                    for f in required_fields:
                        debug_fields.append((f, client_data.get(f)))
                    
                    # Add phone/dob debug info
                    contact_phone = client_data.get('contact_information', {}).get('phone')
                    direct_phone = client_data.get('phone')
                    dob_value = client_data.get('dob')
                    debug_fields.append(('phone_or_dob', f"contact_phone='{contact_phone}', direct_phone='{direct_phone}', dob='{dob_value}'"))
                    
                    debug_row_info = f"Row {index + 1}: client_data for required fields: {debug_fields}"
                    print(debug_row_info)
                    if not hasattr(debug_info, 'row_debug'):
                        debug_info['row_debug'] = []
                    debug_info['row_debug'].append(debug_row_info)
                    
                    if missing_required:
                        # Handle special case for phone_or_dob
                        if 'phone_or_dob' in missing_required:
                            missing_required.remove('phone_or_dob')
                            if missing_required:
                                error_msg = f"Row {index + 1}: Missing required fields: {', '.join(missing_required)}. Also, at least one of phone or DOB is required."
                            else:
                                error_msg = f"Row {index + 1}: At least one of phone or DOB is required for client creation."
                        else:
                            error_msg = f"Row {index + 1}: Missing required fields for client creation: {', '.join(missing_required)}"
                        print(f"Row {index + 1}: VALIDATION FAILED - {error_msg}")
                        errors.append(error_msg)
                        skipped_count += 1
                        continue
                    else:
                        print(f"Row {index + 1}: VALIDATION PASSED - proceeding to client creation")
                    
                    # Check for duplicates using our custom logic (only for new clients)
                    print(f"Row {index + 1}: About to check for duplicates")
                    duplicate_client, match_type = find_duplicate_client(client_data)
                    print(f"Row {index + 1}: Duplicate check result: duplicate_client={duplicate_client}, match_type={match_type}")
                    
                    # Store original values for duplicate relationship creation
                    if duplicate_client:
                        original_email = client_data.get('contact_information', {}).get('email', '')
                        original_phone = client_data.get('contact_information', {}).get('phone', '')
                        original_client_id = client_data.get('client_id', '')
                        
                        # Don't modify email/phone - keep original values
                        # The client will be created with original contact information
                        # Duplicate detection will be handled through the ClientDuplicate relationship
                    
                    # Separate client fields from extended fields for new client creation
                    print(f"Row {index + 1}: About to separate client fields from extended fields")
                    client_fields = {}
                    extended_fields_list = [
                        'indigenous_identity', 'military_status', 'refugee_status', 'household_size',
                        'family_head_client_no', 'relationship', 'primary_worker', 'chronically_homeless',
                        'num_bednights_current_stay', 'length_homeless_3yrs', 'income_source',
                        'taxation_year_filed', 'status_id', 'picture_id', 'other_id', 'bnl_consent',
                        'allergies', 'harm_reduction_support', 'medication_support', 'pregnancy_support',
                        'mental_health_support', 'physical_health_support', 'daily_activities_support',
                        'other_health_supports', 'cannot_use_stairs', 'limited_mobility',
                        'wheelchair_accessibility', 'vision_hearing_speech_supports', 'english_translator',
                        'reading_supports', 'other_accessibility_supports', 'pet_owner', 'legal_support',
                        'immigration_support', 'religious_cultural_supports', 'safety_concerns',
                        'intimate_partner_violence_support', 'human_trafficking_support', 'other_supports',
                        'access_to_housing_application', 'access_to_housing_no', 'access_point_application',
                        'access_point_no', 'cars', 'cars_no', 'discharge_disposition', 'intake_status',
                        'lived_last_12_months', 'reason_for_service', 'intake_date', 'service_end_date',
                        'rejection_date', 'rejection_reason', 'room', 'bed', 'occupancy_status',
                        'bed_nights_historical', 'restriction_reason', 'restriction_date',
                        'restriction_duration_days', 'restriction_status', 'early_termination_by'
                    ]
                    
                    # Filter out extended fields from client_data
                    for field, value in client_data.items():
                        if field not in extended_fields_list:
                            client_fields[field] = value
                    
                    # Create the client with only client fields
                    print(f"Row {index + 1}: About to create client with fields: {list(client_fields.keys())}")
                    client = Client.objects.create(**client_fields)
                    created_count += 1
                    print(f"Row {index + 1}: Successfully created client: {client.first_name} {client.last_name}")
                    if duplicate_client:
                        logger.info(f"Created new client with duplicate flag: {client.email or client.phone}")
                    else:
                        logger.info(f"Created new client: {client.email or client.phone}")
                    
                    # Create ClientExtended record if there are extended fields
                    extended_data = {}
                    
                    # Extract extended fields from original client_data
                    for field in extended_fields_list:
                        if field in client_data:
                            value = client_data[field]
                            if value is not None and value != '':
                                if isinstance(value, str) and value.strip() != '':
                                    extended_data[field] = value.strip()
                                elif not isinstance(value, str):
                                    extended_data[field] = value
                    
                    # Create ClientExtended record if there's any extended data
                    if extended_data:
                        from core.models import ClientExtended
                        extended_data['client'] = client
                        ClientExtended.objects.create(**extended_data)
                        logger.info(f"Created ClientExtended record for client {client.client_id}")
                
                # If we have a client and found a potential duplicate, create duplicate relationship for review
                # Only do this for newly created clients, not updated ones
                if client and duplicate_client and not is_update:
                    client_name = f"{client_data.get('first_name', '')} {client_data.get('last_name', '')}".strip()
                    existing_name = f"{duplicate_client.first_name} {duplicate_client.last_name}".strip()
                    
                    # Always create duplicate relationship for review when potential duplicate is found
                    similarity = 1.0 if match_type in ["exact_email", "exact_phone", "email_phone"] else 0.8
                    confidence_level = fuzzy_matcher.get_duplicate_confidence_level(similarity)
                    
                    try:
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
                                    'primary_client_id': duplicate_client.client_id,
                                    'duplicate_original_email': original_email,
                                    'duplicate_original_phone': original_phone,
                                    'duplicate_original_client_id': original_client_id,
                                }
                            }
                        )
                        print(f"Created duplicate relationship: {duplicate_client} <-> {client}")
                        
                        duplicate_details.append({
                            'type': 'created_with_duplicate',
                            'reason': f'{match_type.replace("_", " ").title()} match - created with duplicate flag for review',
                            'client_name': client_name,
                            'existing_name': existing_name,
                            'match_field': f"Match: {match_type}"
                        })
                        logger.info(f"Created client with {match_type} duplicate flag")
                    except Exception as e:
                        print(f"Error creating duplicate relationship: {e}")
                
                # Process intake data if available and we have a client
                if has_intake_data and client is not None:
                    print(f"DEBUG: Processing intake data for client {client.first_name} {client.last_name}")
                    process_intake_data(client, row, index, column_mapping, df.columns)
                else:
                    print(f"DEBUG: Skipping intake data - has_intake_data: {has_intake_data}, client: {client is not None}")
                    
            except Exception as e:
                error_message = str(e)
                
                # Handle other types of errors
                if "NOT NULL constraint" in error_message:
                    errors.append(f"Row {index + 2}: Required information is missing. Please ensure all required fields are filled.")
                elif "invalid input syntax" in error_message:
                    errors.append(f"Row {index + 2}: Invalid data format. Please check the data in this row.")
                else:
                    # Generic user-friendly error
                    errors.append(f"Row {index + 2}: Unable to process this client. Please check the data and try again.")
                
                logger.error(f"Error processing row {index + 2}: {str(e)}")
        
        # Prepare response
        duplicate_created_count = len([d for d in duplicate_details if d['type'] == 'created_with_duplicate'])
        
        response_data = {
            'success': True,
            'message': f'Upload completed successfully! {created_count} clients created, {updated_count} clients updated.',
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
            'debug_info': debug_info,  # Add debug information
            'notes': [
                'Existing clients with matching Client ID were updated with new information',
                'New clients were created for records without existing Client ID matches',
                'Missing date of birth values were set to 1900-01-01',
                'Missing gender values were set to "Unknown"',
                f'{duplicate_created_count} clients were created with potential duplicate flags for review',
                'Review flagged duplicates in the "Probable Duplicate Clients" section'
            ] if created_count > 0 or updated_count > 0 or duplicate_created_count > 0 else []
        }
        
        return JsonResponse(response_data)
        
    except Exception as e:
        logger.error(f"Upload error: {str(e)}")
        # Provide user-friendly error message
        return JsonResponse({
            'success': False, 
            'error': 'Upload failed. Please check your file format and try again. If the problem persists, contact your system administrator.'
        }, status=500)

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
            'country': 'USA'
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
            'country': 'USA'
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
            'country': 'USA'
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
            'country': 'USA'
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
            'country': 'USA'
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
    
    def dispatch(self, request, *args, **kwargs):
        """Check if user has permission to access duplicate detection"""
        if request.user.is_authenticated:
            try:
                staff = request.user.staff_profile
                user_roles = staff.staffrole_set.select_related('role').all()
                role_names = [staff_role.role.name for staff_role in user_roles]
                
                # Staff role users cannot access duplicate detection
                if 'Staff' in role_names and not any(role in ['SuperAdmin', 'Admin', 'Manager', 'Leader'] for role in role_names):
                    messages.error(request, 'You do not have permission to access duplicate detection. Contact your administrator.')
                    return redirect('clients:list')
            except Exception:
                pass
        
        return super().dispatch(request, *args, **kwargs)
    
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


@require_http_methods(["GET", "POST"])
def mark_duplicate_action(request, duplicate_id, action):
    """Handle duplicate actions (confirm, not_duplicate, merge)"""
    try:
        print(f"mark_duplicate_action called with duplicate_id={duplicate_id}, action={action}")
        duplicate = get_object_or_404(ClientDuplicate, id=duplicate_id)
        print(f"Found duplicate: {duplicate}")
        
        # If this is a GET request with confirm=true, show confirmation page
        if request.method == 'GET' and request.GET.get('confirm') == 'true':
            action_names = {
                'not_duplicate': 'Mark as Not Duplicate',
                'merge_confirm': 'Confirm Merge Clients'
            }
            return render(request, 'clients/duplicate_confirm.html', {
                'duplicate': duplicate,
                'action': action,
                'action_name': action_names.get(action, action.title())
            })
        
        # Get the current user (you might need to adjust this based on your auth system)
        reviewed_by = None
        if hasattr(request, 'user') and request.user.is_authenticated:
            # Try to get staff profile
            try:
                reviewed_by = request.user.staff_profile
                print(f"Found staff profile: {reviewed_by}")
            except Exception as e:
                print(f"Could not get staff profile: {e}")
                pass
        
        # Get notes from request - handle both JSON and form data
        notes = ''
        if request.content_type == 'application/json':
            # Handle JSON data (from AJAX requests)
            data = json.loads(request.body) if request.body else {}
            notes = data.get('notes', '')
        else:
            # Handle form data (from regular form submissions)
            notes = request.POST.get('notes', '')
        print(f"Notes: {notes}")
        
        if action == 'confirm':
            # Redirect directly to comparison view without modal
            if request.content_type == 'application/json':
                return JsonResponse({
                    'success': True,
                    'redirect': f'/clients/dedupe/compare/{duplicate_id}/'
                })
            else:
                return redirect(f'/clients/dedupe/compare/{duplicate_id}/')
        elif action == 'merge':
            # Redirect to merge view
            if request.content_type == 'application/json':
                return JsonResponse({
                    'success': True,
                    'redirect': f'/clients/dedupe/merge/{duplicate_id}/'
                })
            else:
                return redirect(f'/clients/dedupe/merge/{duplicate_id}/')
        elif action == 'not_duplicate':
            # Mark as not duplicate and keep the client
            duplicate.mark_as_not_duplicate(reviewed_by, notes)
            message = f'Confirmed {duplicate.duplicate_client} is NOT a duplicate. Client kept in system and duplicate flag removed.'
            print(f"Marked as not duplicate: {message}")
            
            # Add success message
            messages.success(request, message)
            
            # Return JSON response for AJAX requests
            if request.content_type == 'application/json':
                return JsonResponse({
                    'success': True,
                    'message': message,
                    'redirect_url': reverse('clients:dedupe')
                })
            else:
                return redirect('clients:dedupe')
        elif action == 'merge_confirm':
            # Check if this is coming from the merge interface (POST request)
            if request.method == 'POST':
                # This is the actual merge processing
                print(f"Processing actual merge for duplicate {duplicate_id}")
                
                # Get the duplicate record
                duplicate = get_object_or_404(ClientDuplicate, id=duplicate_id)
                
                # Get the primary client (the one we want to keep)
                primary_client = duplicate.primary_client
                duplicate_client = duplicate.duplicate_client
                
                # Get the duplicate client name before deleting
                duplicate_client_name = f"{duplicate_client.first_name} {duplicate_client.last_name}"
                
                # Mark the duplicate as resolved BEFORE deleting the client
                duplicate.status = 'resolved'
                duplicate.resolved_by = reviewed_by
                duplicate.resolved_at = timezone.now()
                duplicate.resolution_notes = notes
                duplicate.save()
                
                # Now delete the duplicate client
                duplicate_client.delete()
                
                print(f"Merge completed: Deleted duplicate client {duplicate_client_name}, kept primary client")
                return redirect(f'/clients/dedupe/?success=merge&client={duplicate_client_name}')
            else:
                # This is the initial confirmation, redirect to merge interface
                print(f"Redirecting to merge page: /clients/dedupe/merge/{duplicate_id}/")
                return redirect(f'/clients/dedupe/merge/{duplicate_id}/')
        elif action == 'merge':
            # For merge, we'll keep the primary client and delete the duplicate
            duplicate_client_name = f"{duplicate.duplicate_client.first_name} {duplicate.duplicate_client.last_name}"
            duplicate_client_id = duplicate.duplicate_client.id
            
            # Delete the duplicate client
            duplicate.duplicate_client.delete()
            
            # Delete the duplicate relationship record
            duplicate.delete()
            
            message = f'Merged and deleted duplicate client {duplicate_client_name} (ID: {duplicate_client_id})'
            print(f"Merged and deleted duplicate client: {message}")
        else:
            print(f"Invalid action: {action}")
            if request.content_type == 'application/json':
                return JsonResponse({
                    'success': False,
                    'error': 'Invalid action'
                }, status=400)
            else:
                return redirect('/clients/dedupe/')
        
        print(f"Returning success response: {message}")
        if request.content_type == 'application/json':
            return JsonResponse({
                'success': True,
                'message': message
            })
        else:
            # For form submissions, redirect back to dedupe page with success message
            return redirect('/clients/dedupe/?success=resolved')
        
    except Exception as e:
        print(f"Error in mark_duplicate_action: {str(e)}")
        logger.error(f"Error in mark_duplicate_action: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': f'An error occurred: {str(e)}'
        }, status=500)


def client_duplicate_comparison(request, duplicate_id):
    """View for side-by-side comparison of duplicate clients with selection interface"""
    try:
        duplicate = get_object_or_404(ClientDuplicate, id=duplicate_id)
        
        # Get both clients
        primary_client = duplicate.primary_client
        duplicate_client = duplicate.duplicate_client
        
        # Get related data for both clients
        primary_enrollments = primary_client.clientprogramenrollment_set.select_related('program', 'program__department').all()
        duplicate_enrollments = duplicate_client.clientprogramenrollment_set.select_related('program', 'program__department').all()
        
        primary_restrictions = primary_client.servicerestriction_set.all()
        duplicate_restrictions = duplicate_client.servicerestriction_set.all()
        
        context = {
            'duplicate': duplicate,
            'primary_client': primary_client,
            'duplicate_client': duplicate_client,
            'primary_enrollments': primary_enrollments,
            'duplicate_enrollments': duplicate_enrollments,
            'primary_restrictions': primary_restrictions,
            'duplicate_restrictions': duplicate_restrictions,
            'similarity_score': duplicate.similarity_score,
            'match_type': duplicate.match_type,
            'confidence_level': duplicate.confidence_level,
        }
        
        return render(request, 'clients/client_duplicate_comparison.html', context)
        
    except Exception as e:
        messages.error(request, f'Error loading client comparison: {str(e)}')
        return redirect('clients:dedupe')


def client_not_duplicate_comparison(request, duplicate_id):
    """View for side-by-side comparison of clients to confirm they are NOT duplicates"""
    try:
        duplicate = get_object_or_404(ClientDuplicate, id=duplicate_id)
        
        # Get both clients
        primary_client = duplicate.primary_client
        duplicate_client = duplicate.duplicate_client
        
        context = {
            'duplicate': duplicate,
            'primary_client': primary_client,
            'duplicate_client': duplicate_client,
            'similarity_score': duplicate.similarity_score,
            'match_type': duplicate.match_type,
            'confidence_level': duplicate.confidence_level,
        }
        
        return render(request, 'clients/client_not_duplicate_comparison.html', context)
        
    except Exception as e:
        messages.error(request, f'Error loading client comparison: {str(e)}')
        return redirect('clients:dedupe')


@require_http_methods(["POST"])
def resolve_duplicate_selection(request, duplicate_id):
    """Handle the selection of which client to keep and which to delete"""
    try:
        duplicate = get_object_or_404(ClientDuplicate, id=duplicate_id)
        data = json.loads(request.body) if request.body else {}
        
        selected_client_id = data.get('selected_client_id')
        notes = data.get('notes', '')
        
        if not selected_client_id:
            return JsonResponse({
                'success': False,
                'error': 'No client selected'
            }, status=400)
        
        # Get the current user for audit trail
        reviewed_by = None
        if hasattr(request, 'user') and request.user.is_authenticated:
            try:
                reviewed_by = request.user.staff_profile
            except:
                pass
        
        # Determine which client to keep and which to delete
        if str(selected_client_id) == str(duplicate.primary_client.id):
            # Keep primary, delete duplicate
            client_to_delete = duplicate.duplicate_client
            client_to_keep = duplicate.primary_client
            kept_client_name = f"{duplicate.primary_client.first_name} {duplicate.primary_client.last_name}"
            deleted_client_name = f"{duplicate.duplicate_client.first_name} {duplicate.duplicate_client.last_name}"
        elif str(selected_client_id) == str(duplicate.duplicate_client.id):
            # Keep duplicate, delete primary
            client_to_delete = duplicate.primary_client
            client_to_keep = duplicate.duplicate_client
            kept_client_name = f"{duplicate.duplicate_client.first_name} {duplicate.duplicate_client.last_name}"
            deleted_client_name = f"{duplicate.primary_client.first_name} {duplicate.primary_client.last_name}"
        else:
            return JsonResponse({
                'success': False,
                'error': 'Invalid client selection'
            }, status=400)
        
        # Transfer related records to the kept client before deletion
        try:
            # Transfer enrollments
            from core.models import ClientProgramEnrollment
            enrollments = ClientProgramEnrollment.objects.filter(client=client_to_delete)
            for enrollment in enrollments:
                enrollment.client = client_to_keep
                enrollment.save()
            
            # Transfer restrictions
            from core.models import ServiceRestriction
            restrictions = ServiceRestriction.objects.filter(client=client_to_delete)
            for restriction in restrictions:
                restriction.client = client_to_keep
                restriction.save()
            
            # Delete the selected client
            client_to_delete.delete()
            
        except Exception as transfer_error:
            return JsonResponse({
                'success': False,
                'error': f'Error transferring related records: {str(transfer_error)}'
            }, status=500)
        
        # Delete the duplicate relationship record
        duplicate.delete()
        
        # Count transferred records
        enrollment_count = ClientProgramEnrollment.objects.filter(client=client_to_keep).count()
        restriction_count = ServiceRestriction.objects.filter(client=client_to_keep).count()
        
        message = f'Successfully resolved duplicate! Kept: {kept_client_name}, Deleted: {deleted_client_name}'
        if enrollment_count > 0 or restriction_count > 0:
            message += f' (Transferred {enrollment_count} enrollments and {restriction_count} restrictions)'
        
        # Add success message
        messages.success(request, message)
        
        return JsonResponse({
            'success': True,
            'message': message,
            'kept_client_name': kept_client_name,
            'deleted_client_name': deleted_client_name,
            'redirect_url': reverse('clients:dedupe')
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'An error occurred: {str(e)}'
        }, status=500)


@require_http_methods(["POST"])
def bulk_duplicate_action(request):
    """Handle bulk actions on duplicates"""
    try:
        print(f"bulk_duplicate_action called")
        data = json.loads(request.body)
        duplicate_ids = data.get('duplicate_ids', [])
        action = data.get('action', '')
        notes = data.get('notes', '')
        
        print(f"Bulk action data: duplicate_ids={duplicate_ids}, action={action}, notes={notes}")
        
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
                print(f"Found staff profile for bulk action: {reviewed_by}")
            except Exception as e:
                print(f"Could not get staff profile for bulk action: {e}")
                pass
        
        # Get duplicates
        duplicates = ClientDuplicate.objects.filter(id__in=duplicate_ids)
        print(f"Found {duplicates.count()} duplicates to process")
        updated_count = 0
        
        for duplicate in duplicates:
            print(f"Processing duplicate {duplicate.id}: {duplicate}")
            if action == 'confirm':
                # Delete the duplicate client completely
                duplicate_client_name = f"{duplicate.duplicate_client.first_name} {duplicate.duplicate_client.last_name}"
                duplicate.duplicate_client.delete()
                duplicate.delete()
                print(f"Deleted duplicate client: {duplicate_client_name}")
            elif action == 'not_duplicate':
                # Mark as not duplicate and keep the client
                duplicate.mark_as_not_duplicate(reviewed_by, notes)
            elif action == 'merge':
                # Delete the duplicate client (keep primary)
                duplicate_client_name = f"{duplicate.duplicate_client.first_name} {duplicate.duplicate_client.last_name}"
                duplicate.duplicate_client.delete()
                duplicate.delete()
                print(f"Merged and deleted duplicate client: {duplicate_client_name}")
            else:
                continue
            updated_count += 1
        
        print(f"Updated {updated_count} duplicates")
        return JsonResponse({
            'success': True,
            'message': f'Updated {updated_count} duplicate(s)',
            'updated_count': updated_count
        })
        
    except json.JSONDecodeError as e:
        print(f"JSON decode error: {e}")
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON data'
        }, status=400)
    except Exception as e:
        print(f"Error in bulk_duplicate_action: {str(e)}")
        logger.error(f"Error in bulk_duplicate_action: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': f'An error occurred: {str(e)}'
        }, status=500)


# Update the update_profile_picture view
@method_decorator(csrf_exempt, name='dispatch')
@require_http_methods(["POST"])
def update_profile_picture(request, external_id):
    """Update client profile picture"""
    try:
        client = get_object_or_404(Client, external_id=external_id)
        
        # Handle file upload
        if 'profile_picture' in request.FILES:
            file = request.FILES['profile_picture']
            
            # Check file size (5MB = 5 * 1024 * 1024 bytes)
            max_size = 5 * 1024 * 1024  # 5MB in bytes
            if file.size > max_size:
                return JsonResponse({
                    'success': False,
                    'error': 'File size must be less than 5MB'
                }, status=400)
            
            # Check file type
            if not file.content_type.startswith('image/'):
                return JsonResponse({
                    'success': False,
                    'error': 'Please upload an image file'
                }, status=400)
            
            client.profile_picture = file
            client.save()
            return JsonResponse({
                'success': True,
                'profile_image_url': client.profile_picture.url,
                'message': 'Profile picture updated successfully'
            })
        
        # Handle URL update
        elif 'image' in request.POST and request.POST['image']:
            client.image = request.POST['image']
            client.save()
            return JsonResponse({
                'success': True,
                'profile_image_url': client.image,
                'message': 'Profile picture URL updated successfully'
            })
        
        else:
            return JsonResponse({
                'success': False,
                'error': 'No file or URL provided'
            }, status=400)
            
    except Exception as e:
        logger.error(f"Error updating profile picture: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': f'An error occurred: {str(e)}'
        }, status=500)


# Add this view for removing profile pictures
@method_decorator(csrf_exempt, name='dispatch')
@require_http_methods(["POST"])
def remove_profile_picture(request, external_id):
    """Remove client profile picture"""
    try:
        client = get_object_or_404(Client, external_id=external_id)
        
        # Remove the profile picture
        if client.profile_picture:
            client.profile_picture.delete()  # Delete the file from storage
            client.profile_picture = None
        
        # Also clear the image URL
        client.image = None
        client.save()
        
        return JsonResponse({
            'success': True,
            'message': 'Profile picture removed successfully'
        })
        
    except Exception as e:
        logger.error(f"Error removing profile picture: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': f'An error occurred: {str(e)}'
        }, status=500)


def client_merge_view(request, duplicate_id):
    """View for merging duplicate clients with field selection"""
    try:
        duplicate = get_object_or_404(ClientDuplicate, id=duplicate_id)
        
        # Get both clients
        primary_client = duplicate.primary_client
        duplicate_client = duplicate.duplicate_client
        
        # Define all possible fields to check
        all_fields = {
            # 🧍 CLIENT PERSONAL DETAILS
            'client_id': 'Client ID',
            'first_name': 'First Name',
            'last_name': 'Last Name',
            'middle_name': 'Middle Name',
            'preferred_name': 'Preferred Name',
            'alias': 'Alias',
            'dob': 'Date of Birth',
            'age': 'Age',
            'gender': 'Gender',
            'gender_identity': 'Gender Identity',
            'pronoun': 'Pronoun',
            'marital_status': 'Marital Status',
            'citizenship_status': 'Citizenship Status',
            'location_county': 'Location/County',
            'province': 'Province',
            'city': 'City',
            'postal_code': 'Postal Code',
            'address': 'Address',
            'address_2': 'Address Line 2',
            
            # 🌍 CULTURAL & DEMOGRAPHIC INFO
            'language': 'Language',
            'preferred_language': 'Preferred Language',
            'mother_tongue': 'Mother Tongue',
            'official_language': 'Official Language',
            'language_interpreter_required': 'Language Interpreter Required',
            'self_identification_race_ethnicity': 'Self-Identification as Race/Ethnicity',
            'ethnicity': 'Ethnicity',
            'aboriginal_status': 'Aboriginal Status',
            'lgbtq_status': 'LGBTQ+ Status',
            'highest_level_education': 'Highest Level of Education',
            'children_home': 'Children at Home',
            'children_number': 'Number of Children',
            'lhin': 'LHIN (Local Health Integration Network)',
            
            # 💊 MEDICAL & HEALTH INFORMATION
            'medical_conditions': 'Medical Conditions',
            'primary_diagnosis': 'Primary Diagnosis',
            'family_doctor': 'Family Doctor',
            'health_card_number': 'Health Card Number',
            'health_card_version': 'Health Card Version',
            'health_card_exp_date': 'Health Card Exp Date',
            'health_card_issuing_province': 'Health Card Issuing Province',
            'no_health_card_reason': 'No Health Card Reason',
            
            # 👥 CONTACT & PERMISSIONS
            'permission_to_phone': 'Permission to Phone',
            'permission_to_email': 'Permission to Email',
            'phone': 'Phone',
            'phone_work': 'Work Phone',
            'phone_alt': 'Alternative Phone',
            'email': 'Email',
            'next_of_kin': 'Next of Kin',
            'emergency_contact': 'Emergency Contact',
            'comments': 'Comments',
            
            # 🧑‍💼 PROGRAM / ENROLLMENT DETAILS
            'program': 'Program',
            'sub_program': 'Sub Program',
            'support_workers': 'Support Workers',
            'level_of_support': 'Level of Support',
            'client_type': 'Client Type',
            'admission_date': 'Admission Date',
            'discharge_date': 'Discharge Date',
            'days_elapsed': 'Days Elapsed',
            'program_status': 'Program Status',
            'reason_discharge': 'Reason for Discharge/Program Status',
            'receiving_services': 'Receiving Services',
            'receiving_services_date': 'Receiving Services Date',
            'referral_source': 'Referral Source',
            
            # 🧾 ADMINISTRATIVE / SYSTEM FIELDS
            'chart_number': 'Chart Number',
            'source': 'Source System',
            
            # Legacy fields
            'image': 'Image URL',
            'profile_picture': 'Profile Picture',
            'contact_information': 'Contact Information',
            'addresses': 'Addresses',
            'uid_external': 'External UID',
            'languages_spoken': 'Languages Spoken',
            'indigenous_status': 'Indigenous Status',
            'country_of_birth': 'Country of Birth',
            'sexual_orientation': 'Sexual Orientation',
            
            # Audit fields
            'updated_by': 'Updated By',
        }
        
        # Check which fields have values in either client
        fields_with_values = {}
        for field_name, field_label in all_fields.items():
            primary_value = getattr(primary_client, field_name, None)
            duplicate_value = getattr(duplicate_client, field_name, None)
            
            # More comprehensive check for values
            def has_value(value):
                if value is None:
                    return False
                if isinstance(value, str):
                    return value.strip() != ''
                if isinstance(value, list):
                    return len(value) > 0
                if isinstance(value, dict):
                    return len(value) > 0
                if isinstance(value, bool):
                    return True  # Include boolean fields even if False
                return True
            
            has_primary_value = has_value(primary_value)
            has_duplicate_value = has_value(duplicate_value)
            
            # Always include the field if either client has a value
            # Also always include important fields even if empty
            important_fields = [
                'level_of_support', 'client_type', 'referral_source', 'receiving_services',
                'receiving_services_date', 'days_elapsed', 'reason_discharge', 'support_workers'
            ]
            
            if has_primary_value or has_duplicate_value or field_name in important_fields:
                fields_with_values[field_name] = {
                    'label': field_label,
                    'primary_value': primary_value,
                    'duplicate_value': duplicate_value,
                    'has_primary': has_primary_value,
                    'has_duplicate': has_duplicate_value,
                }
        
        # Debug: Print field information
        print(f"DEBUG: Total fields in all_fields: {len(all_fields)}")
        print(f"DEBUG: Fields with values: {len(fields_with_values)}")
        print(f"DEBUG: Important fields check:")
        for field_name in ['level_of_support', 'client_type', 'referral_source', 'receiving_services', 'receiving_services_date', 'days_elapsed', 'reason_discharge']:
            if field_name in fields_with_values:
                print(f"  {field_name}: FOUND in fields_with_values")
            else:
                print(f"  {field_name}: NOT FOUND in fields_with_values")
                # Check if field exists in all_fields
                if field_name in all_fields:
                    print(f"    - Field exists in all_fields")
                    primary_val = getattr(primary_client, field_name, None)
                    duplicate_val = getattr(duplicate_client, field_name, None)
                    print(f"    - Primary value: {primary_val}")
                    print(f"    - Duplicate value: {duplicate_val}")
                else:
                    print(f"    - Field NOT in all_fields")
        
        context = {
            'duplicate': duplicate,
            'primary_client': primary_client,
            'duplicate_client': duplicate_client,
            'similarity_score': duplicate.similarity_score,
            'match_type': duplicate.match_type,
            'confidence_level': duplicate.confidence_level,
            'fields_with_values': fields_with_values,
        }
        
        return render(request, 'clients/client_merge.html', context)
        
    except Exception as e:
        messages.error(request, f'Error loading client merge: {str(e)}')
        return redirect('clients:dedupe')


@require_http_methods(["POST"])
def merge_clients(request, duplicate_id):
    """Handle the merging of duplicate clients with selected fields"""
    try:
        print(f"Merge clients called with duplicate_id: {duplicate_id}")
        duplicate = get_object_or_404(ClientDuplicate, id=duplicate_id)
        data = json.loads(request.body) if request.body else {}
        
        print(f"Request data: {data}")
        selected_fields = data.get('selected_fields', {})
        notes = data.get('notes', '')
        
        print(f"Selected fields: {selected_fields}")
        print(f"Number of selected fields: {len(selected_fields)}")
        print(f"Selected fields keys: {list(selected_fields.keys())}")
        
        if not selected_fields:
            return JsonResponse({
                'success': False,
                'error': 'No fields selected for merge'
            }, status=400)
        
        # Get both clients
        primary_client = duplicate.primary_client
        duplicate_client = duplicate.duplicate_client
        
        print(f"Primary client: {primary_client.first_name} {primary_client.last_name}")
        print(f"Duplicate client: {duplicate_client.first_name} {duplicate_client.last_name}")
        
        # Use the primary client as the base and update it with selected fields
        merged_client = primary_client
        
        # Process each field and update the primary client
        print(f"Processing {len(selected_fields)} fields for merge")
        for field_name, field_data in selected_fields.items():
            print(f"Processing field: {field_name} with data: {field_data}")
            # Handle both old format (string) and new format (dict)
            if isinstance(field_data, dict):
                source = field_data.get('source')
                custom_value = field_data.get('value')
            else:
                # Backward compatibility with old format
                source = field_data
                custom_value = None
            
            if source == 'primary':
                value = getattr(primary_client, field_name, '')
                print(f"Using primary {field_name}: {value}")
            elif source == 'duplicate':
                value = getattr(duplicate_client, field_name, '')
                print(f"Using duplicate {field_name}: {value}")
            elif source == 'custom' and custom_value:
                value = custom_value
                print(f"Using custom {field_name}: {value}")
            else:
                continue
                
            # Handle special fields that need special processing
            if field_name in ['addresses', 'next_of_kin', 'emergency_contact', 'support_workers', 'languages_spoken']:
                # Handle JSON fields - copy the entire structure
                setattr(merged_client, field_name, value)
            elif field_name in ['permission_to_phone', 'permission_to_email']:
                # Handle boolean fields
                if value == 'true':
                    setattr(merged_client, field_name, True)
                elif value == 'false':
                    setattr(merged_client, field_name, False)
                else:
                    setattr(merged_client, field_name, value)
            else:
                # Update regular fields (including email, phone, phone_work, phone_alt)
                setattr(merged_client, field_name, value)
        
        # Save the updated primary client
        merged_client.save()
        print(f"Updated merged client: {merged_client}")
        
        # Delete only the duplicate client (keep the primary one)
        duplicate_client.delete()
        
        # Delete the duplicate relationship
        duplicate.delete()
        
        merged_client_name = f"{merged_client.first_name} {merged_client.last_name}"
        
        return JsonResponse({
            'success': True,
            'message': f'Clients merged successfully into {merged_client_name}',
            'merged_client_name': merged_client_name
        })
        
    except Exception as e:
        print(f"Error in merge_clients: {str(e)}")
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False,
            'error': f'An error occurred: {str(e)}'
        }, status=500)


def export_clients(request):
    """Export clients to CSV with current filters applied"""
    try:
        # Get the same queryset as the list view
        queryset = Client.objects.all()
        
        # Apply role-based filtering (same as ClientListView)
        if request.user.is_authenticated:
            try:
                staff = request.user.staff_profile
                user_roles = staff.staffrole_set.select_related('role').all()
                role_names = [staff_role.role.name for staff_role in user_roles]
                
                if 'Staff' in role_names and not any(role in ['SuperAdmin', 'Manager', 'Leader'] for role in role_names):
                    # Staff-only users see clients from both assigned programs AND directly assigned clients
                    from staff.models import StaffProgramAssignment, StaffClientAssignment
                    
                    # Create a Q object to combine both types of assignments
                    relationship_filters = Q()
                    
                    # 1. Clients enrolled in their assigned programs
                    assigned_program_ids = StaffProgramAssignment.objects.filter(
                        staff=staff,
                        is_active=True
                    ).values_list('program_id', flat=True)
                    if assigned_program_ids:
                        relationship_filters |= Q(
                            clientprogramenrollment__program_id__in=assigned_program_ids
                        )
                    
                    # 2. Directly assigned clients
                    assigned_client_ids = StaffClientAssignment.objects.filter(
                        staff=staff,
                        is_active=True
                    ).values_list('client_id', flat=True)
                    if assigned_client_ids:
                        relationship_filters |= Q(
                            id__in=assigned_client_ids
                        )
                    
                    # Apply the combined filter
                    if relationship_filters:
                        queryset = queryset.filter(relationship_filters).distinct()
                    else:
                        # If no assignments, show no clients
                        queryset = queryset.none()
            except Exception:
                pass
        
        # Apply the same filters as the list view
        search_query = request.GET.get('search', '')
        program_filter = request.GET.get('program', '')
        department_filter = request.GET.get('department', '')
        status_filter = request.GET.get('status', '')
        manager_filter = request.GET.get('manager', '')
        
        # Apply search filter
        if search_query:
            queryset = queryset.filter(
                Q(first_name__icontains=search_query) |
                Q(last_name__icontains=search_query) |
                Q(email__icontains=search_query) |
                Q(phone__icontains=search_query) |
                Q(client_id__icontains=search_query)
            )
        
        # Apply program filter
        if program_filter:
            queryset = queryset.filter(clientprogramenrollment__program__id=program_filter).distinct()
        
        # Apply department filter
        if department_filter:
            queryset = queryset.filter(clientprogramenrollment__program__department__id=department_filter).distinct()
        
        # Apply status filter
        if status_filter:
            if status_filter == 'enrolled':
                queryset = queryset.filter(clientprogramenrollment__status='active').distinct()
            elif status_filter == 'not_enrolled':
                queryset = queryset.exclude(clientprogramenrollment__status='active').distinct()
        
        # Apply gender filter
        gender_filter = request.GET.get('gender', '')
        if gender_filter:
            queryset = queryset.filter(gender=gender_filter)
        
        # Apply program manager filter
        if manager_filter:
            queryset = queryset.filter(
                clientprogramenrollment__program__manager_assignments__staff_id=manager_filter,
                clientprogramenrollment__program__manager_assignments__is_active=True
            ).distinct()
        
        # Create CSV response
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="clients_export.csv"'
        
        writer = csv.writer(response)
        
        # Write header row with all fields from client detail view
        writer.writerow([
            'First Name',
            'Last Name',
            'Preferred Name',
            'Alias',
            'Date of Birth',
            'Gender',
            'Sexual Orientation',
            'Citizenship Status',
            'Indigenous Status',
            'Country of Birth',
            'Languages Spoken',
            'Ethnicity',
            'Phone',
            'Work Phone',
            'Alternative Phone',
            'Email',
            'Permission to Phone',
            'Permission to Email',
            'Address Line 2',
            'Addresses (JSON)',
            'Contact Information (JSON)',
            'Primary Diagnosis',
            'Medical Conditions',
            'Support Workers (JSON)',
            'Next of Kin (JSON)',
            'Emergency Contact (JSON)',
            'Program Enrollments',
            'Program Status',
            'Program Start Dates',
            'Program End Dates',
            'Comments',
            'Profile Picture URL',
            'Image URL',
            'External UID',
            'Updated By',
            'Created Date',
            'Updated Date'
        ])
        
        # Write data rows
        for client in queryset:
            # Get contact information from JSON field
            contact_info = client.contact_information or {}
            phone = contact_info.get('phone', '') if contact_info else ''
            email = contact_info.get('email', '') if contact_info else ''
            
            # Get program enrollment information
            enrollments = client.clientprogramenrollment_set.all()
            program_names = []
            program_statuses = []
            start_dates = []
            end_dates = []
            
            for enrollment in enrollments:
                program_names.append(enrollment.program.name if enrollment.program else 'Unknown Program')
                program_statuses.append(enrollment.status)
                start_dates.append(enrollment.start_date.strftime('%Y-%m-%d') if enrollment.start_date else 'null')
                end_dates.append(enrollment.end_date.strftime('%Y-%m-%d') if enrollment.end_date else 'null')
            
            writer.writerow([
                client.first_name or 'null',
                client.last_name or 'null',
                client.preferred_name or 'null',
                client.alias or 'null',
                client.dob.strftime('%Y-%m-%d') if client.dob else 'null',
                client.gender or 'null',
                client.sexual_orientation or 'null',
                client.citizenship_status or 'null',
                client.indigenous_status or 'null',
                client.country_of_birth or 'null',
                ', '.join(client.languages_spoken) if client.languages_spoken else 'null',
                ', '.join(client.ethnicity) if client.ethnicity else 'null',
                phone or 'null',
                client.phone_work or 'null',
                client.phone_alt or 'null',
                email or 'null',
                'Yes' if client.permission_to_phone else 'No',
                'Yes' if client.permission_to_email else 'No',
                client.address_2 or 'null',
                str(client.addresses) if client.addresses else 'null',
                str(client.contact_information) if client.contact_information else 'null',
                client.primary_diagnosis or 'null',
                client.medical_conditions or 'null',
                str(client.support_workers) if client.support_workers else 'null',
                str(client.next_of_kin) if client.next_of_kin else 'null',
                str(client.emergency_contact) if client.emergency_contact else 'null',
                '; '.join(program_names) if program_names else 'null',
                '; '.join(program_statuses) if program_statuses else 'null',
                '; '.join(start_dates) if start_dates else 'null',
                '; '.join(end_dates) if end_dates else 'null',
                client.comments or 'null',
                str(client.profile_picture) if client.profile_picture else 'null',
                client.image or 'null',
                client.uid_external or 'null',
                client.updated_by or 'null',
                client.created_at.strftime('%Y-%m-%d %H:%M:%S') if client.created_at else 'null',
                client.updated_at.strftime('%Y-%m-%d %H:%M:%S') if client.updated_at else 'null'
            ])
        
        return response
        
    except Exception as e:
        print(f"Error in export_clients: {str(e)}")
        return HttpResponse(f"Error exporting clients: {str(e)}", status=500)


@require_http_methods(["GET"])
@csrf_protect
@require_permission('manage_email_subscriptions')
def get_email_recipients(request):
    """Get all active email recipients"""
    try:
        from core.models import EmailRecipient
        
        recipients = EmailRecipient.objects.for_user(request.user).filter(is_active=True).values(
            'id', 'email', 'name', 'frequency', 'created_at'
        )
        
        return JsonResponse({
            'success': True,
            'recipients': list(recipients)
        })
        
    except Exception as e:
        logger.error(f'Error in get_email_recipients: {str(e)}')
        return JsonResponse({'success': False, 'error': str(e)})


@require_http_methods(["POST"])
@csrf_protect
@require_permission('manage_email_subscriptions')
def save_email_subscriptions(request):
    """Save new email subscriptions"""
    try:
        from core.models import EmailRecipient
        
        data = json.loads(request.body)
        frequency = data.get('frequency', 'daily')
        recipients = data.get('recipients', [])
        
        if not recipients:
            return JsonResponse({'success': False, 'error': 'No recipients specified'})
        
        added_count = 0
        for email in recipients:
            # Check if recipient already exists
            recipient, created = EmailRecipient.objects.get_or_create(
                email=email,
                defaults={
                    'name': email.split('@')[0],  # Use email prefix as name
                    'frequency': frequency,
                    'is_active': True
                }
            )
            
            if created:
                added_count += 1
            else:
                # Update existing recipient
                recipient.frequency = frequency
                recipient.is_active = True
                recipient.save()
        
        return JsonResponse({
            'success': True,
            'added_count': added_count,
            'total_recipients': len(recipients)
        })
        
    except Exception as e:
        logger.error(f'Error in save_email_subscriptions: {str(e)}')
        return JsonResponse({'success': False, 'error': str(e)})


@require_http_methods(["DELETE"])
@csrf_protect
@require_permission('manage_email_subscriptions')
def remove_email_recipient(request, recipient_id):
    """Remove an email recipient"""
    try:
        from core.models import EmailRecipient
        
        recipient = get_object_or_404(EmailRecipient.objects.for_user(request.user), id=recipient_id)
        recipient.is_active = False
        recipient.save()
        
        return JsonResponse({
            'success': True,
            'message': 'Recipient removed successfully'
        })
        
    except Exception as e:
        logger.error(f'Error in remove_email_recipient: {str(e)}')
        return JsonResponse({'success': False, 'error': str(e)})


def generate_csv_data(clients):
    """Generate CSV data for the clients"""
    output = io.StringIO()
    writer = csv.writer(output)
    
    # CSV headers
    headers = [
        'Client ID', 'First Name', 'Last Name', 'Preferred Name', 'Date of Birth', 'Age',
        'Gender', 'Phone', 'Email', 'Address', 'City', 'Province', 'Postal Code',
        'Program', 'Program Status', 'Admission Date', 'Discharge Date',
        'Health Card Number', 'Referral Source', 'Created At', 'Created By'
    ]
    writer.writerow(headers)
    
    # CSV data rows
    for client in clients:
        row = [
            client.client_id or '',
            client.first_name or '',
            client.last_name or '',
            client.preferred_name or '',
            client.dob.strftime('%Y-%m-%d') if client.dob else '',
            client.age or client.calculated_age or '',
            client.gender or '',
            client.phone or '',
            client.email or '',
            client.address or '',
            client.city or '',
            client.province or '',
            client.postal_code or '',
            client.program or '',
            client.program_status or '',
            client.admission_date.strftime('%Y-%m-%d') if client.admission_date else '',
            client.discharge_date.strftime('%Y-%m-%d') if client.discharge_date else '',
            client.health_card_number or '',
            client.referral_source or '',
            client.created_at.strftime('%Y-%m-%d %H:%M:%S') if client.created_at else '',
            client.updated_by or ''
        ]
        writer.writerow(row)
    
    return output.getvalue()


def generate_html_content(clients, start_date, end_date, custom_message=''):
    """Generate HTML content for the email"""
    context = {
        'clients': clients,
        'start_date': start_date,
        'end_date': end_date,
        'client_count': clients.count(),
        'report_date': timezone.now().date(),
        'custom_message': custom_message
    }
    
    return render_to_string('emails/daily_client_report.html', context)


def send_single_email(recipient_email, clients, csv_data, html_content, start_date, end_date, custom_message=''):
    """Send email to a specific recipient"""
    subject = f'Daily New Client Report - {timezone.now().strftime("%B %d, %Y")}'
    
    # Create email message
    msg = EmailMultiAlternatives(
        subject=subject,
        body=f'Daily new client report for {start_date} to {end_date}. Please see attached CSV file.',
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[recipient_email]
    )
    
    # Attach HTML content
    msg.attach_alternative(html_content, "text/html")
    
    # Attach CSV file
    csv_filename = f'new_clients_report_{start_date}_{end_date}.csv'
    msg.attach(csv_filename, csv_data, 'text/csv')
    
    # Send email
    msg.send()

