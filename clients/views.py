from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, TemplateView
from django.urls import reverse_lazy, reverse
from django.contrib import messages
from core.message_utils import success_message, error_message, warning_message, info_message, create_success, update_success, delete_success, validation_error, permission_error, not_found_error
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt, csrf_protect
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from django.db.models import Q
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import IntegrityError, transaction
from core.models import Client, Program, Department, Intake, ClientProgramEnrollment, ClientDuplicate, ClientUploadLog, ServiceRestrictionNotificationSubscription
from datetime import datetime, date, timedelta
from core.views import ProgramManagerAccessMixin, AnalystAccessMixin, jwt_required
from core.fuzzy_matching import fuzzy_matcher
from .forms import ClientForm
import pandas as pd
import json
import uuid
import logging
import csv
import io
from django.core.mail import EmailMultiAlternatives
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.template.loader import render_to_string
from django.conf import settings
from functools import wraps
from core.security import require_permission, SecurityManager

logger = logging.getLogger(__name__)


def get_date_range_filter(request):
    """Helper function to get date range filter parameters from request"""
    start_date = request.GET.get('start_date', '').strip()
    end_date = request.GET.get('end_date', '').strip()
    
    # Parse dates if provided
    parsed_start_date = None
    parsed_end_date = None
    
    if start_date:
        try:
            parsed_start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        except ValueError:
            parsed_start_date = None
    
    if end_date:
        try:
            parsed_end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        except ValueError:
            parsed_end_date = None
    
    return start_date, end_date, parsed_start_date, parsed_end_date


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
    
    def paginate_queryset(self, queryset, page_size):
        """Override pagination to handle empty pages gracefully"""
        result = super().paginate_queryset(queryset, page_size)
        
        # super().paginate_queryset returns a tuple: (page, paginator, is_paginated, object_list)
        if result is None:
            return None
        
        # Handle case where result might not be a tuple
        if not isinstance(result, tuple) or len(result) != 4:
            return result
            
        page, paginator, is_paginated, object_list = result
        
        # If the current page is empty and we're not on page 1, redirect to the last valid page
        if paginator and hasattr(paginator, 'num_pages') and paginator.num_pages > 0:
            current_page = self.request.GET.get('page', 1)
            try:
                current_page = int(current_page)
                if current_page > paginator.num_pages:
                    # Redirect to the last valid page
                    from django.http import HttpResponseRedirect
                    
                    # Get current URL parameters
                    params = self.request.GET.copy()
                    params['page'] = paginator.num_pages
                    
                    # Build redirect URL
                    redirect_url = f"{self.request.path}?{params.urlencode()}"
                    return HttpResponseRedirect(redirect_url)
            except (ValueError, TypeError):
                pass
        
        return result
    
    def get_queryset(self):
        from django.db.models import Q
        from datetime import date
        
        # Start with base queryset - exclude archived clients by default
        # Don't use ProgramManagerAccessMixin's get_queryset because it tries to select_related('program') 
        # which doesn't exist on Client model
        queryset = Client.objects.filter(is_archived=False).order_by('-created_at')
        
        # Exclude clients that are marked as duplicates (i.e., they are duplicate_client in a pending ClientDuplicate record)
        queryset = queryset.exclude(
            duplicate_of__status='pending'
        )
        
        # Apply date range filtering
        start_date, end_date, parsed_start_date, parsed_end_date = get_date_range_filter(self.request)
        
        if parsed_start_date:
            queryset = queryset.filter(created_at__date__gte=parsed_start_date)
        if parsed_end_date:
            queryset = queryset.filter(created_at__date__lte=parsed_end_date)
        
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
        status_filter = self.request.GET.get('status', '').strip()
        
        # Filter by status (active vs inactive)
        if status_filter == 'active':
            # Show only active clients (is_inactive=False)
            queryset = queryset.filter(is_inactive=False)
        elif status_filter == 'inactive':
            # Show only inactive clients (is_inactive=True)
            queryset = queryset.filter(is_inactive=True)
        # If status is empty or 'all', show all clients
        
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
        
        # Sorting (case-insensitive by name)
        from django.db.models.functions import Lower, Coalesce
        from django.db.models import Value, Count
        from django.db.models.query import Prefetch
        
        # Annotate enrollment count to avoid N+1 queries in template
        # Count only non-archived enrollments
        queryset = queryset.annotate(
            last_name_ci=Lower(Coalesce('last_name', Value(''))),
            first_name_ci=Lower(Coalesce('first_name', Value(''))),
            enrollment_count=Count('clientprogramenrollment', filter=Q(clientprogramenrollment__is_archived=False), distinct=True),
        )
        
        # Prefetch related objects to optimize queries
        queryset = queryset.select_related('extended').prefetch_related(
            Prefetch(
                'clientprogramenrollment_set',
                queryset=ClientProgramEnrollment.objects.select_related('program', 'sub_program').filter(is_archived=False),
                to_attr='active_enrollments'
            )
        )
        
        sort_key = self.request.GET.get('sort', 'name_asc')
        sort_mapping = {
            'name_asc': ['first_name_ci', 'last_name_ci'],
            'name_desc': ['-first_name_ci', '-last_name_ci'],
            'created_desc': ['-created_at'],
            'created_asc': ['created_at'],
            'updated_desc': ['-updated_at'],
            'updated_asc': ['updated_at'],
            'dob_asc': ['dob', 'first_name_ci', 'last_name_ci'],
            'dob_desc': ['-dob', 'first_name_ci', 'last_name_ci'],
        }
        order_by_fields = sort_mapping.get(sort_key, ['first_name_ci', 'last_name_ci'])
        return queryset.order_by(*order_by_fields)
    
    def get_accessible_programs(self):
        """Get all programs that the current user has access to based on their roles"""
        if not self.request.user or not self.request.user.is_authenticated:
            return Program.objects.filter(status='active').order_by('name')
        
        try:
            staff = self.request.user.staff_profile
            user_roles = staff.staffrole_set.select_related('role').all()
            role_names = [staff_role.role.name for staff_role in user_roles]
            
            # SuperAdmin and Admin see all programs
            if any(role in ['SuperAdmin', 'Admin'] for role in role_names):
                return Program.objects.filter(status='active').order_by('name')
            
            # Analyst sees all programs (for reporting purposes)
            elif 'Analyst' in role_names and not any(role in ['SuperAdmin', 'Manager', 'Leader', 'Staff'] for role in role_names):
                return Program.objects.filter(status='active').order_by('name')
            
            # Manager sees programs they're assigned to
            elif staff.is_program_manager():
                return staff.get_assigned_programs().filter(status='active').order_by('name')
            
            # Leader sees programs in departments they lead
            elif staff.is_leader():
                assigned_departments = staff.get_assigned_departments()
                return Program.objects.filter(
                    department__in=assigned_departments,
                    status='active'
                ).distinct().order_by('name')
            
            # Staff sees programs where their assigned clients are enrolled
            elif 'Staff' in role_names:
                from staff.models import StaffClientAssignment
                assigned_client_ids = StaffClientAssignment.objects.filter(
                    staff=staff,
                    is_active=True
                ).values_list('client_id', flat=True)
                return Program.objects.filter(
                    clientprogramenrollment__client_id__in=assigned_client_ids,
                    status='active'
                ).distinct().order_by('name')
            
            # Default: show all active programs
            else:
                return Program.objects.filter(status='active').order_by('name')
                
        except Exception:
            # If there's any error, show all active programs
            return Program.objects.filter(status='active').order_by('name')
    
    def get_context_data(self, **kwargs):
        # Don't use ProgramManagerAccessMixin's get_context_data to avoid conflicts
        context = super(ProgramManagerAccessMixin, self).get_context_data(**kwargs)
        context['search_query'] = self.request.GET.get('search', '')
        context['program_filter'] = self.request.GET.get('program', '')
        context['age_range'] = self.request.GET.get('age_range', '')
        context['gender_filter'] = self.request.GET.get('gender', '')
        context['manager_filter'] = self.request.GET.get('manager', '')
        context['per_page'] = self.request.GET.get('per_page', '10')
        context['sort'] = self.request.GET.get('sort', 'name_asc')
        
        # Add date range filter parameters
        start_date, end_date, parsed_start_date, parsed_end_date = get_date_range_filter(self.request)
        context['start_date'] = start_date
        context['end_date'] = end_date
        
        # Add gender choices for the filter dropdown
        from .forms import GENDER_CHOICES
        context['gender_choices'] = GENDER_CHOICES
        
        # Get programs based on user's access level
        context['programs'] = self.get_accessible_programs()
        
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
        context['current_status'] = self.request.GET.get('status', '')
        
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
        
        # Prefetch duplicate information for efficient badge display
        # Get all clients that have pending duplicates (primary_duplicates with status='pending')
        # Use select_related and only fetch primary_client_id for efficiency
        client_ids = [client.id for client in context['clients']]
        if client_ids:
            clients_with_duplicates = ClientDuplicate.objects.filter(
                status='pending',
                primary_client_id__in=client_ids
            ).only('primary_client_id').values_list('primary_client_id', flat=True)
            context['clients_with_duplicates'] = set(clients_with_duplicates)
        else:
            context['clients_with_duplicates'] = set()
        
        # Calculate client status counts for the cards
        # Get base queryset WITHOUT date filters or other GET parameter filters
        # This ensures counts show totals, not filtered results
        from django.db.models import Count, Exists, OuterRef
        from django.utils import timezone
        from datetime import date
        today = timezone.now().date()
        
        base_queryset = Client.objects.filter(is_archived=False)
        
        # Exclude clients marked as duplicates
        base_queryset = base_queryset.exclude(duplicate_of__status='pending')
        
        # Apply the same permission filters as get_queryset (but NOT date/search/filter params)
        if self.request.user.is_authenticated:
            try:
                staff = self.request.user.staff_profile
                user_roles = staff.staffrole_set.select_related('role').all()
                role_names = [staff_role.role.name for staff_role in user_roles]
                
                if staff.is_program_manager():
                    assigned_programs = staff.get_assigned_programs()
                    relationship_filters = Q()
                    relationship_filters |= Q(clientprogramenrollment__program__in=assigned_programs)
                    staff_name = f"{staff.user.first_name} {staff.user.last_name}".strip() or staff.user.username
                    relationship_filters |= Q(clientprogramenrollment__created_by=staff_name)
                    relationship_filters |= Q(servicerestriction__created_by=staff_name)
                    relationship_filters |= Q(updated_by=staff_name)
                    base_queryset = base_queryset.filter(relationship_filters)
                elif 'Staff' in role_names and not any(role in ['SuperAdmin', 'Manager', 'Leader'] for role in role_names):
                    from staff.models import StaffProgramAssignment, StaffClientAssignment
                    relationship_filters = Q()
                    assigned_program_ids = StaffProgramAssignment.objects.filter(
                        staff=staff,
                        is_active=True
                    ).values_list('program_id', flat=True)
                    if assigned_program_ids:
                        relationship_filters |= Q(clientprogramenrollment__program_id__in=assigned_program_ids)
                    assigned_client_ids = StaffClientAssignment.objects.filter(
                        staff=staff,
                        is_active=True
                    ).values_list('client_id', flat=True)
                    if assigned_client_ids:
                        relationship_filters |= Q(id__in=assigned_client_ids)
                    if relationship_filters:
                        base_queryset = base_queryset.filter(relationship_filters)
                    else:
                        base_queryset = base_queryset.none()
                elif staff.is_leader():
                    from core.models import Department
                    assigned_departments = Department.objects.filter(
                        leader_assignments__staff=staff,
                        leader_assignments__is_active=True
                    ).distinct()
                    assigned_programs = Program.objects.filter(
                        department__in=assigned_departments
                    ).distinct()
                    base_queryset = base_queryset.filter(
                        clientprogramenrollment__program__in=assigned_programs
                    )
            except Exception:
                pass
        
        # Optimize count queries by using a single queryset with annotations
        # This reduces the number of database queries from 3 to 1
        base_ids = base_queryset.values('id').distinct()
        context['total_clients_count'] = base_ids.count()
        
        # Active: clients with at least one active enrollment
        # Use Exists subquery for better performance
        active_enrollments = ClientProgramEnrollment.objects.filter(
            client=OuterRef('pk'),
            is_archived=False,
            start_date__lte=today
        ).filter(
            Q(end_date__isnull=True) | Q(end_date__gt=today)
        )
        active_queryset = base_queryset.annotate(has_active_enrollment=Exists(active_enrollments))
        context['active_clients_count'] = active_queryset.filter(has_active_enrollment=True).values('id').distinct().count()
        
        # Inactive: clients with is_inactive=True (uses the is_inactive field from the model)
        inactive_ids = base_queryset.filter(is_inactive=True).values('id').distinct()
        context['inactive_clients_count'] = inactive_ids.count()
        
        # Duplicate: clients that have been marked as duplicates (duplicate_of with status='pending' or 'confirmed_duplicate')
        duplicate_clients = Client.objects.filter(
            is_archived=False,
            duplicate_of__status__in=['pending', 'confirmed_duplicate']
        ).distinct()
        # Apply the same permission filters
        if self.request.user.is_authenticated:
            try:
                staff = self.request.user.staff_profile
                user_roles = staff.staffrole_set.select_related('role').all()
                role_names = [staff_role.role.name for staff_role in user_roles]
                
                if staff.is_program_manager():
                    assigned_programs = staff.get_assigned_programs()
                    relationship_filters = Q()
                    relationship_filters |= Q(clientprogramenrollment__program__in=assigned_programs)
                    staff_name = f"{staff.user.first_name} {staff.user.last_name}".strip() or staff.user.username
                    relationship_filters |= Q(clientprogramenrollment__created_by=staff_name)
                    relationship_filters |= Q(servicerestriction__created_by=staff_name)
                    relationship_filters |= Q(updated_by=staff_name)
                    duplicate_clients = duplicate_clients.filter(relationship_filters)
                elif 'Staff' in role_names and not any(role in ['SuperAdmin', 'Manager', 'Leader'] for role in role_names):
                    from staff.models import StaffProgramAssignment, StaffClientAssignment
                    relationship_filters = Q()
                    assigned_program_ids = StaffProgramAssignment.objects.filter(
                        staff=staff,
                        is_active=True
                    ).values_list('program_id', flat=True)
                    if assigned_program_ids:
                        relationship_filters |= Q(clientprogramenrollment__program_id__in=assigned_program_ids)
                    assigned_client_ids = StaffClientAssignment.objects.filter(
                        staff=staff,
                        is_active=True
                    ).values_list('client_id', flat=True)
                    if assigned_client_ids:
                        relationship_filters |= Q(id__in=assigned_client_ids)
                    if relationship_filters:
                        duplicate_clients = duplicate_clients.filter(relationship_filters)
                    else:
                        duplicate_clients = duplicate_clients.none()
                elif staff.is_leader():
                    from core.models import Department
                    assigned_departments = Department.objects.filter(
                        leader_assignments__staff=staff,
                        leader_assignments__is_active=True
                    ).distinct()
                    assigned_programs = Program.objects.filter(
                        department__in=assigned_departments
                    ).distinct()
                    duplicate_clients = duplicate_clients.filter(
                        clientprogramenrollment__program__in=assigned_programs
                    )
            except Exception:
                pass
        
        context['duplicate_clients_count'] = duplicate_clients.values('id').distinct().count()
        
        return context

@csrf_protect
@require_http_methods(["POST"])
@login_required
def toggle_client_status(request, external_id):
    """Toggle client inactive status (only for SuperAdmin/Admin)"""
    try:
        client = Client.objects.get(external_id=external_id, is_archived=False)
    except Client.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Client not found'}, status=404)
    
    # Check if user is SuperAdmin or Admin
    if not request.user.is_authenticated:
        return JsonResponse({'success': False, 'error': 'Authentication required'}, status=401)
    
    try:
        staff = request.user.staff_profile
        user_roles = staff.staffrole_set.select_related('role').all()
        role_names = [staff_role.role.name for staff_role in user_roles]
        
        if 'SuperAdmin' not in role_names and 'Admin' not in role_names:
            return JsonResponse({'success': False, 'error': 'Permission denied. Only SuperAdmin and Admin can change client status.'}, status=403)
    except Exception:
        return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)
    
    # Get the new status from request
    import json
    data = json.loads(request.body)
    new_status = data.get('is_inactive', False)
    
    # Update client status
    client.is_inactive = new_status
    user_name = request.user.get_full_name() or request.user.username
    client.updated_by = user_name
    client.save()
    
    return JsonResponse({
        'success': True,
        'message': f'Client status updated to {"inactive" if new_status else "active"}',
        'is_inactive': client.is_inactive
    })

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
    
    def get_queryset(self):
        """Optimize queryset to prefetch related enrollments and their relationships"""
        return Client.objects.select_related(
            'extended'
        ).prefetch_related(
            'clientprogramenrollment_set__program__department',
            'clientprogramenrollment_set__sub_program',
            'servicerestriction_set__program'
        )
    
    def get_context_data(self, **kwargs):
        """Add optimized enrollments to context"""
        context = super().get_context_data(**kwargs)
        client = context['client']
        
        # Get enrollments with optimized queries, ordered by start_date descending
        # Exclude archived (soft-deleted) enrollments from the main view
        enrollments = client.clientprogramenrollment_set.select_related(
            'program__department',
            'sub_program'
        ).filter(is_archived=False).order_by('-start_date', 'program__name')
        
        # Also get archived enrollments for restore functionality
        archived_enrollments = client.clientprogramenrollment_set.select_related(
            'program__department',
            'sub_program'
        ).filter(is_archived=True).order_by('-start_date', 'program__name')
        
        context['enrollments'] = enrollments
        context['archived_enrollments'] = archived_enrollments
        context['archived_count'] = archived_enrollments.count()
        return context

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
        
        # Set created_by and updated_by fields
        if self.request.user.is_authenticated:
            user_name = f"{self.request.user.first_name} {self.request.user.last_name}".strip()
            if not user_name or user_name == ' ':
                user_name = self.request.user.username or self.request.user.email or 'System'
            
            client.created_by = user_name
            client.updated_by = user_name
        else:
            client.created_by = 'System'
            client.updated_by = 'System'
        
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
        
        # Always check for duplicates based on names (regardless of email/phone)
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
    
    def get_success_url(self):
        """Redirect to the client detail page after successful update"""
        return reverse('clients:detail', kwargs={'external_id': self.object.external_id})
    
    def form_valid(self, form):
        try:
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
        except Exception as e:
            logger.error(f"Error in ClientUpdateView.form_valid: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            messages.error(self.request, f'Error updating client: {str(e)}')
            return self.form_invalid(form)
    
    def form_invalid(self, form):
        """Handle form validation errors"""
        logger.warning(f"Client update form is invalid: {form.errors}")
        for field, errors in form.errors.items():
            for error in errors:
                messages.error(self.request, f'{field}: {error}')
        return super().form_invalid(form)
    
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
    
    def get_context_data(self, **kwargs):
        """Add enrollment and restriction counts to context"""
        context = super().get_context_data(**kwargs)
        client = context['client']
        
        # Get counts of non-archived enrollments and restrictions
        from core.models import ServiceRestriction
        enrollment_count = ClientProgramEnrollment.objects.filter(client=client, is_archived=False).count()
        restriction_count = ServiceRestriction.objects.filter(client=client, is_archived=False).count()
        
        context['enrollment_count'] = enrollment_count
        context['restriction_count'] = restriction_count
        
        return context
    
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
        
        # Create audit log entry before archiving
        try:
            from core.models import create_audit_log
            create_audit_log(
                entity_name='Client',
                entity_id=client.external_id,
                action='archive',
                changed_by=self.request.user,
                diff_data=client_data
            )
        except Exception as e:
            logger.error(f"Error creating audit log for client archiving: {e}")
        
        # Soft delete: set is_archived=True and archived_at timestamp
        from django.utils import timezone
        from core.models import ServiceRestriction
        
        archived_at = timezone.now()
        user_name = self.request.user.get_full_name() or self.request.user.username if self.request.user.is_authenticated else 'System'
        
        # Archive all enrollments associated with this client
        enrollments = ClientProgramEnrollment.objects.filter(client=client, is_archived=False)
        enrollment_count = enrollments.count()
        for enrollment in enrollments:
            enrollment.is_archived = True
            enrollment.archived_at = archived_at
            enrollment.updated_by = user_name
            enrollment.save()
        
        # Archive all restrictions associated with this client
        restrictions = ServiceRestriction.objects.filter(client=client, is_archived=False)
        restriction_count = restrictions.count()
        for restriction in restrictions:
            restriction.is_archived = True
            restriction.archived_at = archived_at
            restriction.updated_by = user_name
            restriction.save()
        
        # Archive the client
        client.is_archived = True
        client.archived_at = archived_at
        client.updated_by = user_name
        client.save()
        
        # Create success message with details about what was archived
        message_parts = [f'Client {client.first_name} {client.last_name} has been archived.']
        if enrollment_count > 0:
            message_parts.append(f'{enrollment_count} enrollment(s) have been archived.')
        if restriction_count > 0:
            message_parts.append(f'{restriction_count} restriction(s) have been archived.')
        message_parts.append('You can restore them from the archived clients section.')
        
        messages.success(
            self.request, 
            ' '.join(message_parts)
        )
        return redirect(self.success_url)

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
@transaction.atomic
def upload_clients(request):
    """Handle CSV/Excel file upload and process client data"""
    
    # Start timing the upload
    upload_start_time = timezone.now()
    upload_log = None
    
    # Check for load test mode - skip database writes if X-Load-Test header is present
    is_load_test = request.headers.get('X-Load-Test', '').lower() == 'true'
    
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
            logger.error("Upload failed: No file in request.FILES")
            return JsonResponse({'success': False, 'error': 'No file provided'}, status=400)
        
        # Get the source parameter
        source = request.POST.get('source', 'SMIMS')  # Default to SMIMS if not provided
        logger.info(f"Upload request - source: {source}, file: {request.FILES.get('file', {}).name if 'file' in request.FILES else 'None'}")
        if source not in ['SMIMS', 'EMHware']:
            logger.error(f"Upload failed: Invalid source '{source}'")
            return JsonResponse({'success': False, 'error': 'Invalid source. Must be SMIMS or EMHware.'}, status=400)
        
        file = request.FILES['file']
        file_extension = file.name.split('.')[-1].lower()
        
        # Get staff profile for upload log
        staff_profile = None
        if request.user.is_authenticated:
            try:
                staff_profile = request.user.staff_profile
            except Exception:
                pass
        
        # Create upload log entry
        try:
            upload_log = ClientUploadLog.objects.create(
                file_name=file.name,
                file_size=file.size,
                file_type=file_extension,
                source=source,
                started_at=upload_start_time,
                uploaded_by=staff_profile,
                status='success',
                upload_details={}
            )
        except Exception as e:
            logger.warning(f"Failed to create upload log: {e}")
            upload_log = None
        
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
                        except (UnicodeDecodeError, UnicodeError):
                            decoded_content = content.decode('utf-8', errors='replace')
                        
                        # Create StringIO object and read with pandas
                        string_io = io.StringIO(decoded_content)
                        df = pd.read_csv(string_io)
                    except Exception as e:
                        return JsonResponse({'success': False, 'error': f'Could not read CSV file with any supported encoding. Last error: {last_error}. Fallback error: {str(e)}'}, status=400)
            
            else:
                df = pd.read_excel(file)
        except Exception as e:
            logger.error(f"Error reading file: {str(e)}")
            return JsonResponse({'success': False, 'error': f'Error reading file: {str(e)}'}, status=400)
        
        # Check if dataframe is empty
        if df.empty:
            logger.error("Upload failed: Dataframe is empty after reading file")
            return JsonResponse({'success': False, 'error': 'The uploaded file is empty or contains no data.'}, status=400)
        
        # Check if dataframe has no columns
        if len(df.columns) == 0:
            logger.error("Upload failed: Dataframe has no columns")
            return JsonResponse({'success': False, 'error': 'The uploaded file has no columns. Please check the file format.'}, status=400)
        
        logger.info(f"Successfully read file with {len(df)} rows and {len(df.columns)} columns")
        
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
                logger.info(f"Loaded field mapping from {json_file_path}")
            except (FileNotFoundError, json.JSONDecodeError) as e:
                logger.error(f"Error loading field mapping from JSON: {e}")
                # Fallback to basic mapping if JSON file is not found or corrupted
                field_mapping = {
                    'client_id': ['client_no', 'client no', 'ID', 'client_id', 'client id', 'clientno', 'id', 'client number', 'Client No.', 'Client No', 'Client ID', 'CLIENT ID'],
                    'client_combined': ['client', 'Client', 'client_name', 'client name', 'full_name', 'full name', 'name', 'Name'],
                    'first_name': ['first_name', 'first name', 'firstname', 'fname', 'given name', 'First Name', 'FIRST NAME'],
                    'last_name': ['last_name', 'last name', 'lastname', 'lname', 'surname', 'family name', 'Last Name', 'LAST NAME'],
                    'email': ['email', 'e-mail', 'email address', 'e_mail'],
                    'phone': ['phone_number', 'phone number', 'phone', 'telephone', 'tel', 'mobile', 'cell', 'Phone', 'PHONE'],
                    'dob': ['dob', 'date of birth', 'birthdate', 'birth date', 'dateofbirth', 'DOB', 'DOB'],
                    'discharge_date': ['discharge_date', 'discharge date', 'dischargedate', 'Discharge Date', 'DISCHARGE DATE'],
                    'reason_discharge': ['reason (for discharge/program status)', 'reason for discharge', 'discharge reason', 'reason', 'Reason'],
                }
                logger.warning(f"Using fallback field mapping")
            
            # Create reverse mapping from column names to standardized names
            column_mapping = {}
            df_columns_lower = [col.lower().strip() for col in df_columns]
            
            logger.info(f"Creating field mapping for columns: {list(df_columns)}")
            
            for standard_name, variations in field_mapping.items():
                for variation in variations:
                    variation_lower = variation.lower().strip()
                    if variation_lower in df_columns_lower:
                        # Find the original column name (case-sensitive)
                        original_col = df_columns[df_columns_lower.index(variation_lower)]
                        column_mapping[original_col] = standard_name
                        logger.debug(f"Mapped column '{original_col}' -> '{standard_name}'")
                        break
            
            logger.info(f"Final column mapping: {column_mapping}")
            return column_mapping
        
        # Create field mapping
        column_mapping = create_field_mapping(df.columns)
        
        # Check if we have client_id column (now required for all uploads)
        # Check if any column maps to client_id (not just exact column name)
        has_client_id = any(column_mapping.get(col) == 'client_id' for col in df.columns)
        
        # Check if any row has a Client ID + Source combination that exists in the database - if so, we'll allow updates with partial data
        has_existing_client_ids = False
        for col in df.columns:
            if column_mapping.get(col) == 'client_id':
                # Check if any of the client_ids + source combinations in the CSV actually exist in the database
                for index, row in df.iterrows():
                    client_id_value = row[col]
                    if pd.notna(client_id_value) and str(client_id_value).strip():
                        client_id_clean = str(client_id_value).strip()
                        existing_client = Client.objects.filter(client_id=client_id_clean, source=source).first()
                        if existing_client:
                            has_existing_client_ids = True
                            break
                if has_existing_client_ids:
                    break
        
        
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
            
            if not found:
                missing_fields.append(required_field)
        
        if missing_fields:
            logger.error(f"Upload validation failed - Missing fields: {missing_fields}. Column mapping: {column_mapping}. DF columns: {list(df.columns)}")
            return JsonResponse({
                'success': False, 
                'error': f'Missing required columns. Please include columns for: {", ".join(missing_fields)}. Note: client_id is now required for all uploads.'
            }, status=400)
        
        # Phone and DOB are both optional - no requirement check needed
        
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
        duplicates_flagged = 0  # Track duplicates flagged during processing
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
            Parse client field that can be in various formats:
            1. Combined: 'Last, First (ID)' - everything in one field
            2. Separate: 'Last, First' + client_id from separate field
            3. Complex: 'Last, First (Preferred)' - with preferred names
            4. Complex: 'First (Previous), Last' - with previous names
            
            Handles various name formats:
            - Abdul-Azim,  Safi
            - Abdirazaq Warsame,  Mohamed  
            - A. Hussein,  Mohamud
            - Abbakar,  Tagwa Seddig Adam
            - Abdoun Mohamed,  Sarah Hassan
            - Adeshigbin,  Babatunde (Ganiu)
            - Adeware,  Olubunni (Elizabeth)
            - Adrian (Prev. Langton),  Naomi
            - Ahmed,  Tasaddhuque (Duke)
            - Archibald_2,  Reina
            - Al-Khair,  A'shafie
            
            Returns: (first_name, last_name, client_id)
            """
            if not client_field_value or str(client_field_value).strip() == '':
                return None, None, None
            
            client_str = str(client_field_value).strip()
            client_id = None
            
            import re
            
            # Pattern 1: "Last, First (ID)" - Last, First with ID in parentheses
            pattern1 = r'^([A-Za-z0-9\s._\'-]+),\s*([A-Za-z0-9\s._\'-]+)\s*\((\d+)\)$'
            match1 = re.match(pattern1, client_str)
            if match1:
                last_name = match1.group(1).strip()    # "Abdul-Azim"
                first_name = match1.group(2).strip()   # "Safi"
                client_id = match1.group(3).strip()    # "12345"
                
                return first_name, last_name, client_id
            
            # Pattern 2: "Last, First (Preferred)" - Last, First with preferred name in parentheses
            pattern2 = r'^([A-Za-z0-9\s._\'-]+),\s*([A-Za-z0-9\s._\'-]+)\s*\(([A-Za-z0-9\s._\'-]+)\)$'
            match2 = re.match(pattern2, client_str)
            if match2:
                last_name = match2.group(1).strip()    # "Adeshigbin"
                first_name = match2.group(2).strip()   # "Babatunde"
                preferred_name = match2.group(3).strip()  # "Ganiu"
                
                # Use client_id from separate field if provided
                if client_id_field_value and str(client_id_field_value).strip():
                    client_id = str(client_id_field_value).strip()
                    return first_name, last_name, client_id
                else:
                    # Return names but no client_id
                    return first_name, last_name, None
            
            # Pattern 3: "First (Previous), Last" - First with previous name, Last
            pattern3 = r'^([A-Za-z0-9\s._\'-]+)\s*\(([A-Za-z0-9\s._\'-]+)\)\s*,\s*([A-Za-z0-9\s._\'-]+)$'
            match3 = re.match(pattern3, client_str)
            if match3:
                first_name = match3.group(1).strip()    # "Adrian"
                previous_name = match3.group(2).strip()  # "Prev. Langton"
                last_name = match3.group(3).strip()     # "Naomi"
                
                # Use client_id from separate field if provided
                if client_id_field_value and str(client_id_field_value).strip():
                    client_id = str(client_id_field_value).strip()
                    return first_name, last_name, client_id
                else:
                    # Return names but no client_id
                    return first_name, last_name, None
            
            # Pattern 4: "Last, First" - Simple Last, First without parentheses
            pattern4 = r'^([A-Za-z0-9\s._\'-]+),\s*([A-Za-z0-9\s._\'-]+)$'
            match4 = re.match(pattern4, client_str)
            if match4:
                last_name = match4.group(1).strip()    # "Abdul-Azim"
                first_name = match4.group(2).strip()   # "Safi"
                
                # Use client_id from separate field if provided
                if client_id_field_value and str(client_id_field_value).strip():
                    client_id = str(client_id_field_value).strip()
                    return first_name, last_name, client_id
                else:
                    # Return names but no client_id
                    return first_name, last_name, None
            
            # Pattern 5: "First Last" - Simple space-separated First Last format (no comma)
            # This handles cases like "John Doe" or "Mary Jane Smith"
            pattern5 = r'^([A-Za-z0-9._\'-]+(?:\s+[A-Za-z0-9._\'-]+)*)\s+([A-Za-z0-9\s._\'-]+)$'
            match5 = re.match(pattern5, client_str)
            if match5:
                # First group might be just first name or first + middle name(s)
                name_parts = match5.group(1).strip().split()
                if len(name_parts) >= 1:
                    first_name = name_parts[0].strip()  # First part is first name
                    last_name = match5.group(2).strip()  # Second group is last name
                    
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
        
        def process_intake_data(client, row, index, column_mapping, df_columns, departments_cache, programs_by_department):
            """Process intake data for a client - optimized with pre-loaded caches"""
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
                
                # Helper function to ensure proper defaults for optional fields (convert empty strings to None)
                def get_field_with_default(field_name, default=None):
                    """Get field data and ensure empty strings become None for optional fields"""
                    value = get_field_data(field_name, '')
                    if value == '' or value is None:
                        return default
                    return value
                
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
                    """Parse date value from string, handling empty values, multiple formats, Excel serial numbers, and various date formats"""
                    if not value or (isinstance(value, str) and value.strip() == ''):
                        return default
                    
                    # Handle pandas Timestamp or datetime objects directly
                    if hasattr(value, 'date'):
                        try:
                            return value.date()
                        except (AttributeError, TypeError):
                            pass
                    
                    # Handle date objects directly
                    if hasattr(value, 'year') and hasattr(value, 'month') and hasattr(value, 'day'):
                        try:
                            from datetime import date
                            if isinstance(value, date):
                                return value
                        except (AttributeError, TypeError):
                            pass
                    
                    try:
                        # Check if it's an Excel serial number (numeric value between 1 and 1000000)
                        # Excel dates are days since 1900-01-01 (but Excel incorrectly treats 1900 as a leap year)
                        try:
                            numeric_value = float(value)
                            # Excel serial numbers for dates are typically between 1 (Jan 1, 1900) and ~45000+ (modern dates)
                            if 1 <= numeric_value <= 1000000:
                                from datetime import datetime, timedelta
                                # Excel epoch is 1899-12-30 (not 1900-01-01 due to Excel's 1900 leap year bug)
                                excel_epoch = datetime(1899, 12, 30)
                                parsed_date = excel_epoch + timedelta(days=int(numeric_value))
                                logger.debug(f"Converted Excel serial {numeric_value} to date: {parsed_date.date()}")
                                return parsed_date.date()
                        except (ValueError, TypeError):
                            pass
                        
                        # Try pandas automatic parsing first (handles most standard formats)
                        try:
                            parsed = pd.to_datetime(value, errors='coerce', infer_datetime_format=True)
                            if pd.notna(parsed):
                                return parsed.date() if hasattr(parsed, 'date') else parsed
                        except (ValueError, TypeError, OverflowError):
                            pass
                    except (ValueError, TypeError):
                        pass
                    
                    # If pandas fails, try manual parsing for common formats
                    try:
                        from datetime import datetime
                        value_str = str(value).strip()
                        
                        # Remove time components if present (e.g., "2024-12-05 00:00:00" -> "2024-12-05")
                        if ' ' in value_str:
                            value_str = value_str.split(' ')[0]
                        
                        # Try various date formats
                        date_formats = [
                            '%Y-%m-%d',           # 2024-12-05
                            '%Y/%m/%d',           # 2024/12/05
                            '%m/%d/%Y',           # 12/05/2024 (US format)
                            '%d/%m/%Y',           # 05/12/2024 (European format)
                            '%m-%d-%Y',           # 12-05-2024
                            '%d-%m-%Y',           # 05-12-2024
                            '%Y.%m.%d',           # 2024.12.05
                            '%m.%d.%Y',           # 12.05.2024
                            '%d.%m.%Y',           # 05.12.2024
                            '%B %d, %Y',          # December 5, 2024
                            '%b %d, %Y',          # Dec 5, 2024
                            '%d %B %Y',           # 5 December 2024
                            '%d %b %Y',           # 5 Dec 2024
                            '%Y%m%d',             # 20241205
                            '%m/%d/%y',           # 12/05/24 (2-digit year)
                            '%d/%m/%y',           # 05/12/24 (2-digit year, European)
                        ]
                        
                        for date_format in date_formats:
                            try:
                                parsed = datetime.strptime(value_str, date_format)
                                return parsed.date()
                            except (ValueError, TypeError):
                                continue
                        
                        # Try parsing with slash separator (handle both MM/DD/YYYY and DD/MM/YYYY)
                        if '/' in value_str:
                            parts = value_str.split('/')
                            if len(parts) == 3:
                                try:
                                    # Try MM/DD/YYYY first (US format)
                                    month, day, year = parts
                                    if len(year) == 4 and 1 <= int(month) <= 12 and 1 <= int(day) <= 31:
                                        return datetime(int(year), int(month), int(day)).date()
                                except (ValueError, TypeError):
                                    try:
                                        # Try DD/MM/YYYY (European format)
                                        day, month, year = parts
                                        if len(year) == 4 and 1 <= int(month) <= 12 and 1 <= int(day) <= 31:
                                            return datetime(int(year), int(month), int(day)).date()
                                    except (ValueError, TypeError):
                                        pass
                        
                        # Try parsing with dash separator
                        if '-' in value_str:
                            parts = value_str.split('-')
                            if len(parts) == 3:
                                try:
                                    # Try YYYY-MM-DD first (ISO format)
                                    year, month, day = parts
                                    if len(year) == 4 and 1 <= int(month) <= 12 and 1 <= int(day) <= 31:
                                        return datetime(int(year), int(month), int(day)).date()
                                except (ValueError, TypeError):
                                    try:
                                        # Try MM-DD-YYYY (US format)
                                        month, day, year = parts
                                        if len(year) == 4 and 1 <= int(month) <= 12 and 1 <= int(day) <= 31:
                                            return datetime(int(year), int(month), int(day)).date()
                                    except (ValueError, TypeError):
                                        try:
                                            # Try DD-MM-YYYY (European format)
                                            day, month, year = parts
                                            if len(year) == 4 and 1 <= int(month) <= 12 and 1 <= int(day) <= 31:
                                                return datetime(int(year), int(month), int(day)).date()
                                        except (ValueError, TypeError):
                                            pass
                    except (ValueError, TypeError, AttributeError) as e:
                        logger.debug(f"Failed to parse date '{value}': {e}")
                        pass
                    
                    return default
                
                # Helper function to parse multi-line date values safely
                def parse_multiline_dates(value, default=None):
                    """Parse multiple dates from a single cell (separated by newlines)"""
                    if not value or value.strip() == '':
                        return [default] if default else []
                    
                    date_strings = [date.strip() for date in str(value).split('\n') if date.strip()]
                    parsed_dates = []
                    
                    for date_str in date_strings:
                        try:
                            parsed_dates.append(pd.to_datetime(date_str).date())
                        except (ValueError, TypeError):
                            if default:
                                parsed_dates.append(default)
                    
                    return parsed_dates if parsed_dates else ([default] if default else [])
                
                program_name = get_field_data('program_name')
                program_department = get_field_data('program_department')
                # Use the source from the form (upload type selection), not from CSV
                
                print(f"DEBUG: Program enrollment data - program_name: '{program_name}', source: '{source}'")
                intake_date_value = get_field_data('intake_date')
                # Set default intake date - will be overridden by split logic below
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
                intake_dates = parse_multiline_dates(intake_date_value, intake_date)
                
                print(f"DEBUG: Split intake dates: {intake_dates}")
                
                # Ensure we have the same number of programs and dates
                # If we have more programs than dates, repeat the last date
                # If we have more dates than programs, repeat the last program
                while len(intake_dates) < len(program_names):
                    intake_dates.append(intake_dates[-1] if intake_dates else intake_date)
                while len(program_names) < len(intake_dates):
                    program_names.append(program_names[-1] if program_names else program_name)
                
                print(f"DEBUG: Final program-date pairs: {list(zip(program_names, intake_dates))}")
                
                # Get or create department (use cache)
                department = None
                dept_name = program_department if program_department else 'NA'
                if dept_name in departments_cache:
                    department = departments_cache[dept_name]
                else:
                    # Create new department and add to cache
                    department, created = Department.objects.get_or_create(
                        name=dept_name,
                        defaults={'owner': 'System'}
                    )
                    departments_cache[dept_name] = department
                    if created:
                        logger.info(f"Created new department: {dept_name}")
                
                # Get additional enrollment fields using field mapping (outside loop for efficiency)
                sub_program = get_field_data('sub_program')
                support_workers = get_field_data('support_workers')
                level_of_support = get_field_data('level_of_support')
                client_type = get_field_data('client_type')
                discharge_date_value = get_field_data('discharge_date')
                days_elapsed_value = get_field_data('days_elapsed')
                program_status = get_field_data('program_status', 'active')
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
                    
                    # Find existing program by name matching (DO NOT CREATE NEW PROGRAMS)
                    # Search across ALL programs, not just within department
                    normalized_name = (current_program_name or '').strip()
                    program = None
                    
                    if not normalized_name:
                        logger.warning(f"Skipping enrollment: empty program name for client {client.first_name} {client.last_name}")
                        continue
                    
                    # First, try exact match (case-insensitive) across all departments
                    program = Program.objects.filter(name__iexact=normalized_name).first()
                    
                    # If no exact match, try fuzzy matching across ALL programs
                    # Use the best match found, regardless of score
                    if not program:
                        best_match = None
                        best_score = 0
                        # Search all programs (load them if not already cached globally)
                        all_programs_list = []
                        for dept_programs in programs_by_department.values():
                            if isinstance(dept_programs, dict) and '_all' in dept_programs:
                                all_programs_list.extend(dept_programs['_all'])
                        
                        # If cache doesn't have all programs, query database
                        if not all_programs_list:
                            all_programs_list = list(Program.objects.select_related('department').all())
                        
                        # Find the best matching program
                        for p in all_programs_list:
                            score = calculate_name_similarity(normalized_name, p.name or '')
                            if score > best_score:
                                best_score = score
                                best_match = p
                        
                        # Use the best match found (even if score is low)
                        if best_match and best_score > 0:
                            program = best_match
                            logger.info(f"Fuzzy matched program '{current_program_name}' to existing program '{program.name}' (score: {best_score:.2f})")
                        else:
                            # No match found at all
                            logger.warning(
                                f"Skipping enrollment for client {client.first_name} {client.last_name}: "
                                f"Program '{current_program_name}' not found. Please create the program first or check the name spelling."
                            )
                            continue
                    
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
                    
                    # Check if enrollment exists for this client-program combination
                    # Logic: Find client by ID, then check if enrollment exists for the program
                    # If exists: update enrollment with discharge_date
                    # If not exists: create new enrollment with discharge_date
                    enrollment = None
                    created = False
                    
                    # Try to get existing enrollment first - look for any enrollment for this client-program combination
                    existing_enrollment = ClientProgramEnrollment.objects.filter(
                        client=client,
                        program=program
                    ).order_by('-start_date').first()
                    
                    if existing_enrollment:
                        # Update existing enrollment
                        enrollment = existing_enrollment
                        created = False
                        
                        # If discharge_date is present, update end_date and add discharge reason to notes
                        if discharge_date:
                            enrollment.end_date = discharge_date
                            
                            # Ensure end_date >= start_date constraint is satisfied
                            if enrollment.end_date < enrollment.start_date:
                                # If discharge_date is before start_date, adjust start_date
                                # If we have days_elapsed, calculate start_date from discharge_date
                                if days_elapsed and days_elapsed > 0:
                                    from datetime import timedelta
                                    enrollment.start_date = discharge_date - timedelta(days=days_elapsed)
                                else:
                                    # No days_elapsed, use discharge_date as start_date (same-day enrollment/discharge)
                                    enrollment.start_date = discharge_date
                            
                            # Update status to 'completed' if discharge date is set and no specific status provided
                            if not program_status:
                                enrollment.status = 'completed'
                            else:
                                enrollment.status = program_status
                            
                            # Format discharge note consistently
                            if reason_discharge:
                                discharge_note = f'Discharge Date: {discharge_date.strftime("%Y-%m-%d")} | Reason: {reason_discharge}'
                            else:
                                discharge_note = f'Discharge Date: {discharge_date.strftime("%Y-%m-%d")}'
                            
                            # Append discharge note to existing notes
                            existing_notes = enrollment.notes or ''
                            if existing_notes:
                                enrollment.notes = f'{existing_notes} | {discharge_note}'
                            else:
                                enrollment.notes = discharge_note
                            
                            if days_elapsed:
                                enrollment.days_elapsed = days_elapsed
                            
                            enrollment.updated_by = request.user.get_full_name() or request.user.username if request.user.is_authenticated else 'System'
                            enrollment.save()
                            logger.info(f"Updated enrollment end_date for {client.first_name} {client.last_name} in {program.name} with discharge date {discharge_date}")
                        else:
                            # No discharge date, just update other fields
                            enrollment.status = program_status if program_status else enrollment.status
                            if days_elapsed:
                                enrollment.days_elapsed = days_elapsed
                            enrollment.updated_by = request.user.get_full_name() or request.user.username if request.user.is_authenticated else 'System'
                            enrollment.save()
                    else:
                        # Create new enrollment - client is not enrolled in this program yet
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
                        
                        # If discharge_date is present, format it consistently with update logic
                        if discharge_date:
                            if reason_discharge:
                                discharge_note = f'Discharge Date: {discharge_date.strftime("%Y-%m-%d")} | Reason: {reason_discharge}'
                            else:
                                discharge_note = f'Discharge Date: {discharge_date.strftime("%Y-%m-%d")}'
                            notes_parts.append(discharge_note)
                        
                        # Determine status - if discharge_date is present, default to 'completed'
                        final_status = program_status if program_status else ('completed' if discharge_date else 'active')
                        
                        # Calculate proper start_date to ensure end_date >= start_date constraint
                        enrollment_start_date = current_intake_date
                        if discharge_date:
                            # If discharge_date is before start_date, we need to adjust
                            if discharge_date < current_intake_date:
                                # If we have days_elapsed, calculate start_date from discharge_date
                                if days_elapsed and days_elapsed > 0:
                                    from datetime import timedelta
                                    enrollment_start_date = discharge_date - timedelta(days=days_elapsed)
                                else:
                                    # No days_elapsed, use discharge_date as start_date (same-day enrollment/discharge)
                                    enrollment_start_date = discharge_date
                            # Ensure start_date is not after end_date
                            if enrollment_start_date > discharge_date:
                                enrollment_start_date = discharge_date
                        
                        # Create new enrollment
                        enrollment, created = ClientProgramEnrollment.objects.get_or_create(
                            client=client,
                            program=program,
                            defaults={
                                'start_date': enrollment_start_date,
                                'end_date': discharge_date,  # Set discharge_date as end_date
                                'status': final_status,
                                'days_elapsed': days_elapsed,
                                'notes': ' | '.join(notes_parts),
                                'created_by': request.user.get_full_name() or request.user.username if request.user.is_authenticated else 'System'
                            }
                        )
                        
                        if not created:
                            # Enrollment was found during get_or_create (race condition), update it instead
                            if discharge_date:
                                enrollment.end_date = discharge_date
                                
                                # Ensure end_date >= start_date constraint is satisfied
                                if enrollment.end_date < enrollment.start_date:
                                    # If discharge_date is before start_date, adjust start_date
                                    # If we have days_elapsed, calculate start_date from discharge_date
                                    if days_elapsed and days_elapsed > 0:
                                        from datetime import timedelta
                                        enrollment.start_date = discharge_date - timedelta(days=days_elapsed)
                                    else:
                                        # No days_elapsed, use discharge_date as start_date (same-day enrollment/discharge)
                                        enrollment.start_date = discharge_date
                                
                                if reason_discharge:
                                    discharge_note = f'Discharge Date: {discharge_date.strftime("%Y-%m-%d")} | Reason: {reason_discharge}'
                                else:
                                    discharge_note = f'Discharge Date: {discharge_date.strftime("%Y-%m-%d")}'
                                existing_notes = enrollment.notes or ''
                                if existing_notes:
                                    enrollment.notes = f'{existing_notes} | {discharge_note}'
                                else:
                                    enrollment.notes = discharge_note
                            enrollment.status = final_status
                            enrollment.updated_by = request.user.get_full_name() or request.user.username if request.user.is_authenticated else 'System'
                            enrollment.save()
                            logger.info(f"Updated existing enrollment (found during get_or_create) for {client.first_name} {client.last_name} in {program.name}")
                    
                    if created:
                        logger.info(f"Created {final_status} enrollment for {client.first_name} {client.last_name} in {current_program_name}")
                        print(f"DEBUG: Successfully created enrollment for {client.first_name} {client.last_name} in {current_program_name}")
                        
                        # Skip audit log for bulk imports to improve performance
                        # Audit logs can be created separately if needed for specific tracking
                        # For 10k+ records, creating individual audit logs adds significant overhead
                        pass
                    else:
                        print(f"DEBUG: Enrollment already exists for {client.first_name} {client.last_name} in {current_program_name}")
                        logger.info(f"Enrollment already exists for {client.first_name} {client.last_name} in {current_program_name}")
                    
            except Exception as e:
                logger.error(f"Error processing intake data for row {index + 2}: {str(e)}")
                errors.append(f"Row {index + 2} (Intake): {str(e)}")
        
        
        # Load test mode: process data but skip database writes
        if is_load_test:
            # Simulate processing without database writes
            processed_count = len(df)
            
            # Return load test response
            return JsonResponse({
                'success': True,
                'message': f'Load test mode: {processed_count} clients processed (no DB writes)',
                'load_test_mode': True,
                'processed_count': processed_count,
                'stats': {
                    'total_rows': processed_count,
                    'created': 0,
                    'updated': 0,
                    'skipped': 0,
                    'duplicates_flagged': 0,
                    'errors': 0
                },
                'notes': [
                    'Load test mode: Data was processed but not saved to database',
                    'This is a safe test run with no data persistence'
                ]
            })
        
        # ===== BATCH OPTIMIZATION: Pre-load existing data =====
        # Collect all client_ids, emails, phones from the upload first
        all_client_ids = []
        all_emails = []
        all_phones = []
        row_data_map = {}  # Store row data by index for later processing
        
        # Pre-load all departments and programs for intake processing optimization
        logger.info("Pre-loading departments and programs for batch processing")
        departments_cache = {dept.name: dept for dept in Department.objects.all()}
        # Pre-load all programs grouped by department for fast lookup
        programs_by_department = {}
        all_programs = Program.objects.select_related('department').all()
        for program in all_programs:
            dept_name = program.department.name if program.department else 'NA'
            # Initialize department entry if not exists
            if dept_name not in programs_by_department:
                programs_by_department[dept_name] = {'_all': []}
            # Store program by name (case-insensitive key) for direct lookup
            programs_by_department[dept_name][program.name.lower()] = program
            # Store in '_all' list for fuzzy matching
            programs_by_department[dept_name]['_all'].append(program)
        
        logger.info(f"Pre-loaded {len(departments_cache)} departments and {len(all_programs)} programs")
        logger.info("Starting batch data collection phase")
        for index, row in df.iterrows():
            try:
                # Helper function to get data using field mapping (inline version for collection phase)
                def get_field_data_inline(field_name, default=''):
                    for col in df.columns:
                        if column_mapping.get(col) == field_name:
                            value = row[col]
                            if pd.notna(value) and str(value).strip():
                                return str(value).strip()
                    return default
                
                # Helper function to clean client_id
                def clean_client_id_inline(value):
                    if pd.isna(value) or value is None:
                        return None
                    try:
                        str_value = str(value).strip()
                        if not str_value or str_value.lower() in ['nan', 'none', 'null', '']:
                            return None
                        if '.' in str_value:
                            float_val = float(str_value)
                            if float_val.is_integer():
                                return str(int(float_val))
                            return str_value
                        return str_value
                    except (ValueError, TypeError):
                        return None
                
                client_id = clean_client_id_inline(get_field_data_inline('client_id'))
                email = get_field_data_inline('email', '').strip()
                phone = get_field_data_inline('phone', '').strip()
                
                # Store row data for later processing
                row_data_map[index] = {
                    'client_id': client_id,
                    'email': email,
                    'phone': phone,
                    'first_name': get_field_data_inline('first_name', ''),
                    'last_name': get_field_data_inline('last_name', ''),
                }
                
                if client_id:
                    all_client_ids.append(client_id)
                if email:
                    all_emails.append(email.lower())
                if phone:
                    all_phones.append(phone)
            except Exception as e:
                logger.warning(f"Error collecting data from row {index + 1}: {str(e)}")
                continue
        
        # Batch query existing clients by client_id + source
        existing_clients_by_id = {}
        if all_client_ids:
            existing_clients = Client.objects.filter(
                client_id__in=all_client_ids,
                source=source
            ).select_related().only(
                'id', 'client_id', 'source', 'first_name', 'last_name', 
                'email', 'phone', 'contact_information', 'dob'
            )
            for client in existing_clients:
                existing_clients_by_id[client.client_id] = client
        
        logger.info(f"Found {len(existing_clients_by_id)} existing clients by client_id+source")
        
        # Batch query potential duplicates by email
        # Note: Email/phone matching should check all sources (including same source) as exact matches indicate true duplicates
        potential_duplicates_by_email = {}
        if all_emails:
            duplicate_email_clients = Client.objects.filter(
                contact_information__email__in=all_emails
            ).only('id', 'first_name', 'last_name', 'email', 'phone', 'contact_information', 'dob', 'client_id', 'source')
            for client in duplicate_email_clients:
                email_key = client.contact_information.get('email', '').lower() if client.contact_information else ''
                if email_key:
                    if email_key not in potential_duplicates_by_email:
                        potential_duplicates_by_email[email_key] = []
                    potential_duplicates_by_email[email_key].append(client)
        
        # Batch query potential duplicates by phone
        # Note: Email/phone matching should check all sources (including same source) as exact matches indicate true duplicates
        potential_duplicates_by_phone = {}
        if all_phones:
            duplicate_phone_clients = Client.objects.filter(
                contact_information__phone__in=all_phones
            ).only('id', 'first_name', 'last_name', 'email', 'phone', 'contact_information', 'dob', 'client_id', 'source')
            for client in duplicate_phone_clients:
                phone_key = client.contact_information.get('phone', '') if client.contact_information else ''
                if phone_key:
                    if phone_key not in potential_duplicates_by_phone:
                        potential_duplicates_by_phone[phone_key] = []
                    potential_duplicates_by_phone[phone_key].append(client)
        
        logger.info(f"Pre-loaded {len(potential_duplicates_by_email)} email-based potential duplicates")
        logger.info(f"Pre-loaded {len(potential_duplicates_by_phone)} phone-based potential duplicates")
        # ===== END BATCH OPTIMIZATION =====
        
        # Optimized find_duplicate_client function using pre-loaded data
        def find_duplicate_client_optimized(client_data, row_index):
            """Find duplicate client using pre-loaded batch data"""
            contact_info = client_data.get('contact_information', {}) or {}
            email_val = contact_info.get('email') or ''
            email = email_val.strip().lower() if isinstance(email_val, str) else ''
            phone_val = contact_info.get('phone') or ''
            phone = phone_val.strip() if isinstance(phone_val, str) else ''
            first_name_val = client_data.get('first_name') or ''
            last_name_val = client_data.get('last_name') or ''
            first_name_str = first_name_val.strip() if isinstance(first_name_val, str) else str(first_name_val)
            last_name_str = last_name_val.strip() if isinstance(last_name_val, str) else str(last_name_val)
            full_name = f"{first_name_str} {last_name_str}".strip()
            dob = client_data.get('dob', '')

            # Priority 1: Exact email match (from batch data)
            if email:
                email_matches = potential_duplicates_by_email.get(email, [])
                if email_matches:
                    return email_matches[0], "exact_email"
            
            # Priority 2: Exact phone match (from batch data)
            if phone:
                phone_matches = potential_duplicates_by_phone.get(phone, [])
                if phone_matches:
                    return phone_matches[0], "exact_phone"
            
            # Priority 3: Email and phone combination (from batch data)
            if email and phone:
                email_matches = potential_duplicates_by_email.get(email, [])
                for match in email_matches:
                    match_phone = match.contact_information.get('phone', '').strip() if match.contact_information else ''
                    if match_phone == phone:
                        return match, "email_phone"
            
            # Priority 4: Name similarity check (only check against pre-loaded duplicates, not all clients)
            if full_name:
                # Check name similarity against potential duplicates we already found
                candidates = []
                if email:
                    candidates.extend(potential_duplicates_by_email.get(email, []))
                if phone:
                    candidates.extend(potential_duplicates_by_phone.get(phone, []))
                
                # Also check existing clients with same client_id but different source (potential duplicates)
                client_id = client_data.get('client_id')
                if client_id and client_id in existing_clients_by_id:
                    candidates.append(existing_clients_by_id[client_id])
                
                for client in candidates:
                    client_full_name = f"{client.first_name} {client.last_name}".strip()
                    similarity = calculate_name_similarity(full_name, client_full_name)
                    if similarity >= 0.9:
                        return client, f"name_similarity_{similarity:.2f}"
            
            # Priority 5: Name + Date of Birth combination (limited query)
            # Only check against clients from different sources when source is SMIMS or EMHware
            if full_name and dob and dob != datetime(1900, 1, 1).date():
                first_name_val = client_data.get('first_name') or ''
                last_name_val = client_data.get('last_name') or ''
                first_name_clean = first_name_val.strip() if isinstance(first_name_val, str) else str(first_name_val)
                last_name_clean = last_name_val.strip() if isinstance(last_name_val, str) else str(last_name_val)
                name_dob_query = Client.objects.filter(
                    first_name__iexact=first_name_clean,
                    last_name__iexact=last_name_clean,
                    dob=dob
                )
                # Exclude same source for SMIMS/EMHware cross-source duplicate detection
                if source in ['SMIMS', 'EMHware']:
                    name_dob_query = name_dob_query.exclude(source=source)
                name_dob_match = name_dob_query.first()
                if name_dob_match:
                    return name_dob_match, "name_dob_match"
            
            # Priority 6: Date of Birth + Name similarity (limited query)
            # Only check against clients from different sources when source is SMIMS or EMHware
            if dob and dob != datetime(1900, 1, 1).date():
                # Build query with exclude before slicing
                dob_query = Client.objects.filter(dob=dob).only('id', 'first_name', 'last_name')
                # Exclude same source for SMIMS/EMHware cross-source duplicate detection
                if source in ['SMIMS', 'EMHware']:
                    dob_query = dob_query.exclude(source=source)
                # Apply limit after all filters
                dob_query = dob_query[:100]  # Limit to 100
                for client in dob_query:
                    client_full_name = f"{client.first_name} {client.last_name}".strip()
                    similarity = calculate_name_similarity(full_name, client_full_name)
                    if similarity >= 0.7:
                        return client, f"dob_name_similarity_{similarity:.2f}"
            
            return None, None
        
        # Initialize lists for bulk operations
        clients_to_create = []
        clients_to_update = []  # NEW: List for bulk updates
        extended_records_to_create = []
        duplicate_relationships_to_create = []
        
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
                
                # Helper function to ensure proper defaults for optional fields (convert empty strings to None)
                def get_field_with_default(field_name, default=None):
                    """Get field data and ensure empty strings become None for optional fields"""
                    value = get_field_data(field_name, '')
                    if value == '' or value is None:
                        return default
                    return value
                
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
                    """Parse date value from string, handling empty values, multiple formats, Excel serial numbers, and various date formats"""
                    if not value or (isinstance(value, str) and value.strip() == ''):
                        return default
                    
                    # Handle pandas Timestamp or datetime objects directly
                    if hasattr(value, 'date'):
                        try:
                            return value.date()
                        except (AttributeError, TypeError):
                            pass
                    
                    # Handle date objects directly
                    if hasattr(value, 'year') and hasattr(value, 'month') and hasattr(value, 'day'):
                        try:
                            from datetime import date
                            if isinstance(value, date):
                                return value
                        except (AttributeError, TypeError):
                            pass
                    
                    try:
                        # Check if it's an Excel serial number (numeric value between 1 and 1000000)
                        # Excel dates are days since 1900-01-01 (but Excel incorrectly treats 1900 as a leap year)
                        try:
                            numeric_value = float(value)
                            # Excel serial numbers for dates are typically between 1 (Jan 1, 1900) and ~45000+ (modern dates)
                            if 1 <= numeric_value <= 1000000:
                                from datetime import datetime, timedelta
                                # Excel epoch is 1899-12-30 (not 1900-01-01 due to Excel's 1900 leap year bug)
                                excel_epoch = datetime(1899, 12, 30)
                                parsed_date = excel_epoch + timedelta(days=int(numeric_value))
                                logger.debug(f"Converted Excel serial {numeric_value} to date: {parsed_date.date()}")
                                return parsed_date.date()
                        except (ValueError, TypeError):
                            pass
                        
                        # Try pandas automatic parsing first (handles most standard formats)
                        try:
                            parsed = pd.to_datetime(value, errors='coerce', infer_datetime_format=True)
                            if pd.notna(parsed):
                                return parsed.date() if hasattr(parsed, 'date') else parsed
                        except (ValueError, TypeError, OverflowError):
                            pass
                    except (ValueError, TypeError):
                        pass
                    
                    # If pandas fails, try manual parsing for common formats
                    try:
                        from datetime import datetime
                        value_str = str(value).strip()
                        
                        # Remove time components if present (e.g., "2024-12-05 00:00:00" -> "2024-12-05")
                        if ' ' in value_str:
                            value_str = value_str.split(' ')[0]
                        
                        # Try various date formats
                        date_formats = [
                            '%Y-%m-%d',           # 2024-12-05
                            '%Y/%m/%d',           # 2024/12/05
                            '%m/%d/%Y',           # 12/05/2024 (US format)
                            '%d/%m/%Y',           # 05/12/2024 (European format)
                            '%m-%d-%Y',           # 12-05-2024
                            '%d-%m-%Y',           # 05-12-2024
                            '%Y.%m.%d',           # 2024.12.05
                            '%m.%d.%Y',           # 12.05.2024
                            '%d.%m.%Y',           # 05.12.2024
                            '%B %d, %Y',          # December 5, 2024
                            '%b %d, %Y',          # Dec 5, 2024
                            '%d %B %Y',           # 5 December 2024
                            '%d %b %Y',           # 5 Dec 2024
                            '%Y%m%d',             # 20241205
                            '%m/%d/%y',           # 12/05/24 (2-digit year)
                            '%d/%m/%y',           # 05/12/24 (2-digit year, European)
                        ]
                        
                        for date_format in date_formats:
                            try:
                                parsed = datetime.strptime(value_str, date_format)
                                return parsed.date()
                            except (ValueError, TypeError):
                                continue
                        
                        # Try parsing with slash separator (handle both MM/DD/YYYY and DD/MM/YYYY)
                        if '/' in value_str:
                            parts = value_str.split('/')
                            if len(parts) == 3:
                                try:
                                    # Try MM/DD/YYYY first (US format)
                                    month, day, year = parts
                                    if len(year) == 4 and 1 <= int(month) <= 12 and 1 <= int(day) <= 31:
                                        return datetime(int(year), int(month), int(day)).date()
                                except (ValueError, TypeError):
                                    try:
                                        # Try DD/MM/YYYY (European format)
                                        day, month, year = parts
                                        if len(year) == 4 and 1 <= int(month) <= 12 and 1 <= int(day) <= 31:
                                            return datetime(int(year), int(month), int(day)).date()
                                    except (ValueError, TypeError):
                                        pass
                        
                        # Try parsing with dash separator
                        if '-' in value_str:
                            parts = value_str.split('-')
                            if len(parts) == 3:
                                try:
                                    # Try YYYY-MM-DD first (ISO format)
                                    year, month, day = parts
                                    if len(year) == 4 and 1 <= int(month) <= 12 and 1 <= int(day) <= 31:
                                        return datetime(int(year), int(month), int(day)).date()
                                except (ValueError, TypeError):
                                    try:
                                        # Try MM-DD-YYYY (US format)
                                        month, day, year = parts
                                        if len(year) == 4 and 1 <= int(month) <= 12 and 1 <= int(day) <= 31:
                                            return datetime(int(year), int(month), int(day)).date()
                                    except (ValueError, TypeError):
                                        try:
                                            # Try DD-MM-YYYY (European format)
                                            day, month, year = parts
                                            if len(year) == 4 and 1 <= int(month) <= 12 and 1 <= int(day) <= 31:
                                                return datetime(int(year), int(month), int(day)).date()
                                        except (ValueError, TypeError):
                                            pass
                    except (ValueError, TypeError, AttributeError) as e:
                        logger.debug(f"Failed to parse date '{value}': {e}")
                        pass
                    
                    return default
                
                # Helper function to clean client_id and ensure it's a whole number string
                def clean_client_id(value):
                    """Clean client_id to ensure it's a whole number string without decimals"""
                    # Check for pandas NaN/None/null values first
                    if pd.isna(value) or value is None:
                        return None
                    
                    # Convert to string and check if it's empty or 'nan'
                    try:
                        str_value = str(value).strip()
                        if not str_value or str_value.lower() in ['nan', 'none', 'null', '']:
                            return None
                        
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
                        return None

                # Clean and prepare data using field mapping
                email = get_field_data('email')  # Now optional
                phone = get_field_data('phone')
                client_id = get_field_data('client_id')
                
                
                # Handle date of birth - required for new clients, optional for updates
                dob = None
                try:
                    dob_value = get_field_data('dob')
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
                            except (ValueError, TypeError, OverflowError):
                                # If that fails, try specific date formats
                                dob_str = str(dob_value).strip()
                                try:
                                    # Try YYYY-MM-DD format
                                    dob = datetime.strptime(dob_str, '%Y-%m-%d').date()
                                except (ValueError, TypeError):
                                    # Try other common formats
                                    try:
                                        dob = datetime.strptime(dob_str, '%Y/%m/%d').date()
                                    except (ValueError, TypeError):
                                        try:
                                            dob = datetime.strptime(dob_str, '%m/%d/%Y').date()
                                        except (ValueError, TypeError):
                                            try:
                                                dob = datetime.strptime(dob_str, '%d/%m/%Y').date()
                                            except (ValueError, TypeError):
                                                # If all parsing attempts fail, raise the original error
                                                raise ValueError(f"Unable to parse date: {dob_str}")
                    else:
                        # DOB is optional - no error needed
                        pass
                except Exception as e:
                    # If date parsing fails, DOB is optional - just set to None
                    dob = None
                
                client_data = {
                    'first_name': get_field_data('first_name'),
                    'last_name': get_field_data('last_name'),
                    'middle_name': get_field_with_default('middle_name'),
                    'dob': dob,
                    'preferred_name': get_field_with_default('preferred_name'),
                    'alias': get_field_with_default('alias'),
                    'gender': get_field_with_default('gender'),
                    'gender_identity': get_field_with_default('gender_identity'),
                    'pronoun': get_field_with_default('pronoun'),
                    'marital_status': get_field_with_default('marital_status'),
                    'citizenship_status': get_field_with_default('citizenship_status'),
                    'location_county': get_field_with_default('location_county'),
                    'province': get_field_with_default('province'),
                    'city': get_field_with_default('city'),
                    'postal_code': get_field_with_default('postal_code'),
                    'address': get_field_with_default('address'),
                    'address_2': get_field_with_default('address_2'),
                    'language': get_field_with_default('language'),
                    'preferred_language': get_field_with_default('preferred_language'),
                    'mother_tongue': get_field_with_default('mother_tongue'),
                    'official_language': get_field_with_default('official_language'),
                    'language_interpreter_required': parse_boolean(get_field_data('language_interpreter_required')),
                    'self_identification_race_ethnicity': get_field_with_default('self_identification_race_ethnicity'),
                    'indigenous_status': get_field_with_default('indigenous_status'),
                    'lgbtq_status': get_field_with_default('lgbtq_status'),
                    'highest_level_education': get_field_with_default('highest_level_education'),
                    'children_home': parse_boolean(get_field_data('children_home')),
                    'children_number': parse_integer(get_field_data('children_number')),
                    'lhin': get_field_with_default('lhin'),
                    'client_id': clean_client_id(get_field_data('client_id')),
                    'phone': get_field_with_default('phone'),
                    'email': email if email else None,  # Add email to direct field, None if empty
                    'source': source,  # Add the source field from the form
                    'level_of_support': get_field_with_default('level_of_support'),
                    'client_type': get_field_with_default('client_type'),
                    'referral_source': get_field_with_default('referral_source'),
                    'phone_work': get_field_with_default('phone_work'),
                    'phone_alt': get_field_with_default('phone_alt'),
                    'permission_to_phone': parse_boolean(get_field_data('permission_to_phone')),
                    'permission_to_email': parse_boolean(get_field_data('permission_to_email')),
                    'medical_conditions': get_field_with_default('medical_conditions'),
                    'primary_diagnosis': get_field_with_default('primary_diagnosis'),
                    'family_doctor': get_field_with_default('family_doctor'),
                    'health_card_number': get_field_with_default('health_card_number'),
                    'health_card_version': get_field_with_default('health_card_version'),
                    'health_card_exp_date': parse_date(get_field_data('health_card_exp_date')),
                    'health_card_issuing_province': get_field_with_default('health_card_issuing_province'),
                    'no_health_card_reason': get_field_with_default('no_health_card_reason'),
                    'next_of_kin': get_field_with_default('next_of_kin'),
                    'emergency_contact': get_field_with_default('emergency_contact'),
                    'comments': get_field_with_default('comments'),
                    'chart_number': get_field_with_default('chart_number'),
                    'contact_information': {
                        'email': email if email else None,
                        'phone': phone if phone else None,
                    },
                    # Extended fields for ClientExtended model
                    'indigenous_identity': get_field_with_default('indigenous_identity'),
                    'military_status': get_field_with_default('military_status'),
                    'refugee_status': get_field_with_default('refugee_status'),
                    'household_size': parse_integer(get_field_data('household_size')),
                    'family_head_client_no': get_field_with_default('family_head_client_no'),
                    'relationship': get_field_with_default('relationship'),
                    'primary_worker': get_field_with_default('primary_worker'),
                    'chronically_homeless': parse_boolean(get_field_data('chronically_homeless')),
                    'num_bednights_current_stay': parse_integer(get_field_data('num_bednights_current_stay')),
                    'length_homeless_3yrs': parse_integer(get_field_data('length_homeless_3yrs')),
                    'income_source': get_field_with_default('income_source'),
                    'taxation_year_filed': get_field_with_default('taxation_year_filed'),
                    'status_id': get_field_with_default('status_id'),
                    'picture_id': get_field_with_default('picture_id'),
                    'other_id': get_field_with_default('other_id'),
                    'bnl_consent': parse_boolean(get_field_data('bnl_consent')),
                    'allergies': get_field_with_default('allergies'),
                    'harm_reduction_support': parse_boolean(get_field_data('harm_reduction_support')),
                    'medication_support': parse_boolean(get_field_data('medication_support')),
                    'pregnancy_support': parse_boolean(get_field_data('pregnancy_support')),
                    'mental_health_support': parse_boolean(get_field_data('mental_health_support')),
                    'physical_health_support': parse_boolean(get_field_data('physical_health_support')),
                    'daily_activities_support': parse_boolean(get_field_data('daily_activities_support')),
                    'other_health_supports': get_field_with_default('other_health_supports'),
                    'cannot_use_stairs': parse_boolean(get_field_data('cannot_use_stairs')),
                    'limited_mobility': parse_boolean(get_field_data('limited_mobility')),
                    'wheelchair_accessibility': parse_boolean(get_field_data('wheelchair_accessibility')),
                    'vision_hearing_speech_supports': get_field_with_default('vision_hearing_speech_supports'),
                    'english_translator': parse_boolean(get_field_data('english_translator')),
                    'reading_supports': parse_boolean(get_field_data('reading_supports')),
                    'other_accessibility_supports': get_field_with_default('other_accessibility_supports'),
                    'pet_owner': parse_boolean(get_field_data('pet_owner')),
                    'legal_support': parse_boolean(get_field_data('legal_support')),
                    'immigration_support': parse_boolean(get_field_data('immigration_support')),
                    'religious_cultural_supports': get_field_with_default('religious_cultural_supports'),
                    'safety_concerns': get_field_with_default('safety_concerns'),
                    'intimate_partner_violence_support': parse_boolean(get_field_data('intimate_partner_violence_support')),
                    'human_trafficking_support': parse_boolean(get_field_data('human_trafficking_support')),
                    'other_supports': get_field_with_default('other_supports'),
                    'access_to_housing_application': get_field_with_default('access_to_housing_application'),
                    'access_to_housing_no': get_field_with_default('access_to_housing_no'),
                    'access_point_application': get_field_with_default('access_point_application'),
                    'access_point_no': get_field_with_default('access_point_no'),
                    'cars': get_field_with_default('cars'),
                    'cars_no': parse_integer(get_field_data('cars_no')),
                    'discharge_disposition': get_field_with_default('discharge_disposition'),
                    'intake_status': get_field_with_default('intake_status'),
                    'lived_last_12_months': get_field_with_default('lived_last_12_months'),
                    'reason_for_service': get_field_with_default('reason_for_service'),
                    'intake_date': parse_date(get_field_data('intake_date')),
                    'service_end_date': parse_date(get_field_data('service_end_date')),
                    'rejection_date': parse_date(get_field_data('rejection_date')),
                    'rejection_reason': get_field_with_default('rejection_reason'),
                    'room': get_field_with_default('room'),
                    'bed': get_field_with_default('bed'),
                    'occupancy_status': get_field_with_default('occupancy_status'),
                    'bed_nights_historical': parse_integer(get_field_data('bed_nights_historical')),
                    'restriction_reason': get_field_with_default('restriction_reason'),
                    'restriction_date': parse_date(get_field_data('restriction_date')),
                    'restriction_duration_days': parse_integer(get_field_data('restriction_duration_days')),
                    'restriction_status': get_field_with_default('restriction_status'),
                    'early_termination_by': get_field_with_default('early_termination_by')
                }
                
                # OPTIONAL: Check for combined client field (only if present) - MUST happen before validation
                combined_client_value = None
                client_id_from_separate_field = None
                
                # Look for combined client field via mapping first
                for col in df.columns:
                    if column_mapping.get(col) == 'client_combined':
                        combined_client_value = row[col]
                        break
                
                # If not found via mapping, check for "Client" or "client" column directly (case-insensitive)
                if not combined_client_value or pd.isna(combined_client_value) or not str(combined_client_value).strip():
                    for col in df.columns:
                        col_lower = col.lower().strip()
                        # Check if column name is "client" (but not already mapped to client_id or something else)
                        if col_lower == 'client' and column_mapping.get(col) not in ['client_id', 'first_name', 'last_name']:
                            combined_client_value = row[col]
                            break
                
                # Look for separate client_id field via mapping
                for col in df.columns:
                    if column_mapping.get(col) == 'client_id':
                        client_id_from_separate_field = row[col]
                        break
                
                # If not found via mapping, check for "Client ID" or "client id" column directly (case-insensitive)
                if not client_id_from_separate_field or pd.isna(client_id_from_separate_field) or (str(client_id_from_separate_field).strip() == '' or str(client_id_from_separate_field).strip().lower() in ['nan', 'none', '']):
                    for col in df.columns:
                        col_lower = col.lower().strip()
                        # Check if column name contains "client" and "id" (like "Client ID", "client id", etc.)
                        if ('client' in col_lower and 'id' in col_lower) and column_mapping.get(col) not in ['first_name', 'last_name', 'client_combined']:
                            potential_client_id = row[col]
                            if potential_client_id and not pd.isna(potential_client_id) and str(potential_client_id).strip() and str(potential_client_id).strip().lower() not in ['nan', 'none', '']:
                                client_id_from_separate_field = potential_client_id
                                break
                
                # Try to extract names and client_id from combined field
                if combined_client_value and not pd.isna(combined_client_value) and str(combined_client_value).strip():
                    parsed_first, parsed_last, parsed_client_id = parse_combined_client_field(
                        combined_client_value, 
                        client_id_from_separate_field
                    )
                    
                    # Override names if parsing was successful
                    if parsed_first and parsed_last:
                        if not client_data.get('first_name') or (isinstance(client_data.get('first_name'), str) and client_data.get('first_name', '').strip() == ''):
                            client_data['first_name'] = parsed_first
                        if not client_data.get('last_name') or (isinstance(client_data.get('last_name'), str) and client_data.get('last_name', '').strip() == ''):
                            client_data['last_name'] = parsed_last
                        
                        # Override client_id if we successfully parsed it and it's missing
                        if parsed_client_id and (not client_data.get('client_id') or (isinstance(client_data.get('client_id'), str) and client_data.get('client_id', '').strip() == '')):
                            client_data['client_id'] = clean_client_id(parsed_client_id)
                
                # If client_id is still missing, try to get it from Client ID column
                client_id_value = client_data.get('client_id')
                if (not client_id_value or (isinstance(client_id_value, str) and client_id_value.strip() == '')) and client_id_from_separate_field:
                    try:
                        if not pd.isna(client_id_from_separate_field):
                            cleaned_id = clean_client_id(client_id_from_separate_field)
                            if cleaned_id:
                                client_data['client_id'] = cleaned_id
                    except Exception:
                        pass
                
                # If names are still missing, try to extract from a simple "name" column (First Last format)
                first_name_val = client_data.get('first_name')
                last_name_val = client_data.get('last_name')
                first_name_empty = not first_name_val or (isinstance(first_name_val, str) and first_name_val.strip() == '')
                last_name_empty = not last_name_val or (isinstance(last_name_val, str) and last_name_val.strip() == '')
                
                if first_name_empty or last_name_empty:
                    # Check for a "name" column that might contain "First Last" format
                    name_field_value = None
                    for col in df.columns:
                        col_lower = col.lower().strip()
                        # Check if column is "name" (but not already mapped to something else)
                        if col_lower in ['name'] and column_mapping.get(col) not in ['first_name', 'last_name', 'client_combined']:
                            name_field_value = row[col]
                            break
                    
                    if name_field_value and str(name_field_value).strip():
                        name_str = str(name_field_value).strip()
                        # Try to parse as "First Last" format (simple space-separated)
                        # Only split if we have at least one space and the result has 2+ parts
                        name_parts = name_str.split()
                        if len(name_parts) >= 2:
                            # First part is first name, rest is last name
                            if first_name_empty:
                                client_data['first_name'] = name_parts[0]
                            if last_name_empty:
                                client_data['last_name'] = ' '.join(name_parts[1:])
                
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
                    except (json.JSONDecodeError, ValueError, TypeError):
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
                
                # Early validation: Check if we have at least client_id, first_name, or last_name before processing
                # This helps catch errors early and provide better error messages
                def safe_check_field(field_value):
                    """Safely check if a field has a non-empty value"""
                    if field_value is None:
                        return False
                    if isinstance(field_value, str):
                        return bool(field_value.strip())
                    return bool(field_value)
                
                has_client_id = safe_check_field(client_data.get('client_id'))
                has_first_name = safe_check_field(client_data.get('first_name'))
                has_last_name = safe_check_field(client_data.get('last_name'))
                
                # If we're missing all three required fields, skip early with a clear error
                if not has_client_id and not has_first_name and not has_last_name:
                    errors.append(f"Row {index + 2}: Missing all required fields (client_id, first_name, last_name). Row appears to be empty or invalid.")
                    skipped_count += 1
                    continue
                
                # Parse discharge_date and reason_discharge early to check if we should update instead of create
                discharge_date_value = get_field_data('discharge_date')
                discharge_date_parsed = parse_date(discharge_date_value)
                reason_discharge_value = get_field_data('reason_discharge')
                program_name = get_field_data('program_name')
                
                # Debug logging for discharge date parsing
                if discharge_date_value:
                    logger.info(f"Row {index + 2}: Found discharge_date_value: '{discharge_date_value}', parsed: {discharge_date_parsed}")
                if reason_discharge_value:
                    logger.info(f"Row {index + 2}: Found reason_discharge_value: '{reason_discharge_value}'")
                
                # Check if discharge_date is present - if so, we should update existing clients, not create new ones
                has_discharge_date = discharge_date_parsed is not None
                
                if has_discharge_date:
                    logger.info(f"Row {index + 2}: has_discharge_date=True, will update existing client")
                
                # Check for existing client_id first - this is the primary update mechanism (using batch lookup)
                client = None
                is_update = False
                original_email = ''
                original_phone = ''
                original_client_id = ''
                
                if client_data.get('client_id'):
                    try:
                        # Use batch-loaded existing clients instead of querying
                        client_id_to_find = client_data['client_id']
                        existing_client = existing_clients_by_id.get(client_id_to_find)
                        
                        if existing_client:
                            # Found existing client by Client ID + Source combination - UPDATE instead of CREATE
                            client = existing_client
                            is_update = True
                            updated_count += 1
                            
                            # If discharge_date is present, ensure it's handled
                            if has_discharge_date:
                                # Check if program is specified
                                if not program_name or not program_name.strip():
                                    # No program specified - store at client level
                                    client.discharge_date = discharge_date_parsed
                                    if reason_discharge_value:
                                        client.reason_discharge = reason_discharge_value
                                    # Also add to client_data so it's included in filtered_data
                                    client_data['discharge_date'] = discharge_date_parsed
                                    if reason_discharge_value:
                                        client_data['reason_discharge'] = reason_discharge_value
                                    logger.info(f"Prepared client-level discharge update for {client.first_name} {client.last_name}")
                                # If program is specified, we'll handle it later in enrollment processing
                            
                            # Collect update data instead of updating immediately
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
                            
                            # Define extended fields list
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
                            
                            # Apply filtered values to client object for bulk update
                            for field, value in filtered_data.items():
                                if hasattr(client, field) and field not in extended_fields_list:
                                    setattr(client, field, value)
                            
                            # Ensure discharge_date and reason_discharge are set if they exist (even if not in filtered_data)
                            # BUT only if NO program is specified - if program is present, discharge is enrollment-level only
                            # Also add them to filtered_data so they're included in the update
                            if has_discharge_date and discharge_date_parsed:
                                # Only set client-level discharge if NO program is specified
                                if not program_name or not program_name.strip():
                                    client.discharge_date = discharge_date_parsed
                                    # Add to filtered_data so it gets saved
                                    if 'discharge_date' not in filtered_data:
                                        filtered_data['discharge_date'] = discharge_date_parsed
                            if reason_discharge_value:
                                # Only set client-level discharge reason if NO program is specified
                                if not program_name or not program_name.strip():
                                    client.reason_discharge = reason_discharge_value
                                    # Add to filtered_data so it gets saved
                                    if 'reason_discharge' not in filtered_data:
                                        filtered_data['reason_discharge'] = reason_discharge_value
                            
                            # Set updated_by field
                            if request.user.is_authenticated:
                                first_name = request.user.first_name or ''
                                last_name = request.user.last_name or ''
                                user_name = f"{first_name} {last_name}".strip()
                                if not user_name or user_name == ' ':
                                    user_name = request.user.username or request.user.email or 'System'
                                client.updated_by = user_name
                            else:
                                client.updated_by = 'System'
                            
                            # Store client and extended data for bulk update
                            extended_data = {}
                            for field in extended_fields_list:
                                if field in filtered_data:
                                    value = filtered_data[field]
                                    if value is not None and value != '':
                                        if isinstance(value, str) and value.strip() != '':
                                            extended_data[field] = value.strip()
                                        elif not isinstance(value, str):
                                            extended_data[field] = value
                            
                            # Ensure discharge_date and reason_discharge are preserved
                            # BUT only if NO program is specified - if program is present, discharge is enrollment-level only
                            if has_discharge_date and discharge_date_parsed:
                                # Only set client-level discharge if NO program is specified
                                if not program_name or not program_name.strip():
                                    client.discharge_date = discharge_date_parsed
                            if reason_discharge_value:
                                # Only set client-level discharge reason if NO program is specified
                                if not program_name or not program_name.strip():
                                    client.reason_discharge = reason_discharge_value
                            
                            clients_to_update.append({
                                'client': client,
                                'extended_data': extended_data,
                                'row_index': index
                            })
                            
                            logger.info(f"Prepared update for client by Client ID {client_data['client_id']}: {client.first_name} {client.last_name}")
                        else:
                            # Client ID exists but with different source - CREATE new client
                            is_update = False  # Reset to False since we're creating a new client
                        
                    except Exception as e:
                        logger.error(f"Error updating client with ID {client_data['client_id']}: {e}")
                        # Continue to create new client if update fails
                
                # If discharge_date is present but we haven't found a client yet, try to find existing client
                # This ensures we update existing clients instead of creating new ones when discharge_date is present
                if has_discharge_date and not is_update:
                    # Try to find existing client by client_id first
                    if client_data.get('client_id'):
                        try:
                            client_id_to_find = client_data['client_id']
                            existing_client = existing_clients_by_id.get(client_id_to_find)
                            if existing_client:
                                client = existing_client
                                is_update = True
                                updated_count += 1
                                logger.info(f"Found existing client by Client ID for discharge update: {client_data['client_id']}")
                        except Exception as e:
                            logger.error(f"Error finding client by ID for discharge: {e}")
                    
                    # If still not found, try to find by name + DOB matching
                    first_name_val = client_data.get('first_name')
                    last_name_val = client_data.get('last_name')
                    if not is_update and first_name_val and last_name_val:
                        try:
                            first_name = first_name_val.strip() if isinstance(first_name_val, str) else str(first_name_val or '')
                            last_name = last_name_val.strip() if isinstance(last_name_val, str) else str(last_name_val or '')
                            dob = client_data.get('dob')
                            
                            # Search for matching client
                            query = Client.objects.filter(
                                first_name__iexact=first_name,
                                last_name__iexact=last_name
                            )
                            if dob:
                                query = query.filter(dob=dob)
                            
                            existing_client = query.first()
                            if existing_client:
                                client = existing_client
                                is_update = True
                                updated_count += 1
                                logger.info(f"Found existing client by name+DOB for discharge update: {first_name} {last_name}")
                        except Exception as e:
                            logger.error(f"Error finding client by name+DOB for discharge: {e}")
                    
                    # If we found a client for discharge update, prepare the update data
                    if is_update and client:
                        # Prepare discharge data
                        if not program_name or not program_name.strip():
                            # No program specified - store at client level
                            client.discharge_date = discharge_date_parsed
                            if reason_discharge_value:
                                client.reason_discharge = reason_discharge_value
                            logger.info(f"Prepared client-level discharge update for {client.first_name} {client.last_name}")
                        # If program is specified, we'll handle it later in the enrollment processing
                        # Only add discharge_date and reason_discharge to client_data if NO program is specified
                        # (If program is present, discharge is enrollment-level only, not client-level)
                        if not program_name or not program_name.strip():
                            if discharge_date_parsed:
                                client_data['discharge_date'] = discharge_date_parsed
                            if reason_discharge_value:
                                client_data['reason_discharge'] = reason_discharge_value
                
                # Validate required fields for all rows (client_id is now required for all uploads)
                if not is_update:
                    # If discharge_date is present BUT NO program is specified, we must have found an existing client
                    # (You can't create a new client that's already discharged at the client level)
                    # However, if a program IS present, discharge_date is enrollment-level only, so creating a new client is fine
                    if has_discharge_date and (not program_name or not program_name.strip()):
                        error_msg = f"Row {index + 2}: Discharge date present (without program) but no existing client found. Cannot create new client with client-level discharge date."
                        errors.append(error_msg)
                        skipped_count += 1
                        continue
                    
                    # For new client creation, validate required fields.
                    # client_id is optional for new records (blank IDs should create fresh clients),
                    # but first_name and last_name are still required.
                    required_fields = ['first_name', 'last_name']
                    missing_required = []
                    
                    for field in required_fields:
                        value = client_data.get(field)
                        if not value or (isinstance(value, str) and value.strip() == '') or value is None:
                            missing_required.append(field)
                    
                    # Phone and DOB are both optional - no requirement check needed
                    
                    if missing_required:
                        error_msg = f"Row {index + 2}: Missing required fields for client creation: {', '.join(missing_required)}"
                        errors.append(error_msg)
                        skipped_count += 1
                        continue
                    
                    # For SMIMS and EMHware sources: Check for name-based duplicates if no ID match found
                    duplicate_client = None
                    match_type = None
                    name_duplicate_similarity = None
                    
                    if source in ['SMIMS', 'EMHware']:
                        # Check for name-based duplicates using fuzzy matching
                        first_name_str = str(client_data.get('first_name') or '')
                        last_name_str = str(client_data.get('last_name') or '')
                        client_name = f"{first_name_str} {last_name_str}".strip()
                        
                        if client_name:
                            # Get all existing clients (excluding those from the same source to avoid cross-source duplicates)
                            # We want to check against clients from other sources or no source
                            existing_clients = Client.objects.exclude(id=client_data.get('id', -1)).exclude(source=source)
                            
                            logger.debug(f"Checking for duplicates for {client_name} from source {source}. Checking against {existing_clients.count()} clients from other sources.")
                            
                            # Use fuzzy_matcher to find potential duplicates by name
                            potential_duplicates = fuzzy_matcher.find_potential_duplicates(
                                client_data, existing_clients, similarity_threshold=0.9
                            )
                            
                            if potential_duplicates:
                                # Found name-based duplicate - mark it for duplicate record creation
                                # Only mark as duplicate if similarity is >= 0.9 (90%)
                                duplicate_client, match_type, similarity = potential_duplicates[0]  # Take the first/highest match
                                if similarity >= 0.9:
                                    name_duplicate_similarity = similarity
                                    duplicates_flagged += 1
                                    
                                    logger.info(f"Name duplicate found for {client_name} (similarity: {similarity:.2f}). Will mark as duplicate after client creation.")
                                else:
                                    # Similarity below 90%, don't mark as duplicate
                                    duplicate_client = None
                                    match_type = None
                                    logger.info(f"Name similarity found for {client_name} (similarity: {similarity:.2f}) but below 90% threshold, not marking as duplicate.")
                    
                    # If no name duplicate found, check for other types of duplicates using optimized batch function
                    if not duplicate_client:
                        duplicate_client, match_type = find_duplicate_client_optimized(client_data, index)
                    
                    # Store original values for duplicate relationship creation
                    original_email = ''
                    original_phone = ''
                    original_client_id = ''
                    
                    if duplicate_client:
                        original_email = client_data.get('contact_information', {}).get('email', '')
                        original_phone = client_data.get('contact_information', {}).get('phone', '')
                        original_client_id = client_data.get('client_id', '')
                        
                        # Don't modify email/phone - keep original values
                        # The client will be created with original contact information
                        # Duplicate detection will be handled through the ClientDuplicate relationship
                        
                        # If this was a name-based duplicate, use the similarity score from fuzzy matching
                        if name_duplicate_similarity is not None:
                            # Store the similarity for use when creating ClientDuplicate record
                            match_type = f"name_similarity_{name_duplicate_similarity:.2f}"
                    
                    # Separate client fields from extended fields for new client creation
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
                    
                    # Set user fields for created_by and updated_by
                    if request.user.is_authenticated:
                        # Try to get user's full name
                        first_name = request.user.first_name or ''
                        last_name = request.user.last_name or ''
                        user_name = f"{first_name} {last_name}".strip()
                        
                        # If no full name, fall back to username or email
                        if not user_name or user_name == ' ':
                            user_name = request.user.username or request.user.email or 'System'
                        
                        client_fields['created_by'] = user_name
                        client_fields['updated_by'] = user_name
                    else:
                        client_fields['created_by'] = 'System'
                        client_fields['updated_by'] = 'System'
                    
                    # Add client to bulk create list instead of creating immediately
                    clients_to_create.append({
                        'client_fields': client_fields,
                        'extended_data': {},
                        'duplicate_info': {
                            'is_duplicate': duplicate_client is not None,
                            'duplicate_client': duplicate_client,
                            'match_type': match_type,
                            'similarity_score': name_duplicate_similarity if name_duplicate_similarity is not None else None,
                            'original_email': original_email,
                            'original_phone': original_phone,
                            'original_client_id': original_client_id,
                            'client_data': client_data
                        },
                        'row_index': index
                    })
                    
                    # Extract extended fields from original client_data
                    for field in extended_fields_list:
                        if field in client_data:
                            value = client_data[field]
                            if value is not None and value != '':
                                if isinstance(value, str) and value.strip() != '':
                                    clients_to_create[-1]['extended_data'][field] = value.strip()
                                elif not isinstance(value, str):
                                    clients_to_create[-1]['extended_data'][field] = value
                
                # Note: Duplicate relationships and intake data will be created after bulk client creation
                    
            except Exception as e:
                error_message = str(e)
                import traceback
                error_traceback = traceback.format_exc()
                
                # Log full error details for debugging
                logger.error(f"Error processing row {index + 2}: {error_message}")
                logger.debug(f"Full traceback for row {index + 2}:\n{error_traceback}")
                
                # Handle specific types of errors with more detailed messages
                if "NOT NULL constraint" in error_message:
                    # Extract field name from error if possible
                    field_match = None
                    if "column" in error_message.lower():
                        import re
                        field_match = re.search(r"column ['\"]?(\w+)['\"]?", error_message, re.IGNORECASE)
                    if field_match:
                        field_name = field_match.group(1)
                        errors.append(f"Row {index + 2}: Required field '{field_name}' is missing. Please ensure this field is filled.")
                    else:
                        errors.append(f"Row {index + 2}: Required information is missing. Please ensure all required fields are filled.")
                elif "invalid input syntax" in error_message or "invalid literal" in error_message:
                    errors.append(f"Row {index + 2}: Invalid data format. Please check the data in this row.")
                elif "duplicate key" in error_message.lower() or "unique constraint" in error_message.lower():
                    errors.append(f"Row {index + 2}: Duplicate entry detected. This client may already exist in the system.")
                elif "foreign key constraint" in error_message.lower():
                    errors.append(f"Row {index + 2}: Invalid reference. Please check related data (program, department, etc.).")
                elif "value too long" in error_message.lower() or "string too long" in error_message.lower():
                    errors.append(f"Row {index + 2}: Data value is too long. Please shorten the value.")
                elif "missing required" in error_message.lower() or "required field" in error_message.lower():
                    errors.append(f"Row {index + 2}: {error_message}")
                else:
                    # Show actual error message but make it user-friendly
                    # Truncate very long error messages
                    if len(error_message) > 200:
                        error_message = error_message[:200] + "..."
                    errors.append(f"Row {index + 2}: {error_message}")
        
        # Bulk update existing clients first
        if clients_to_update:
            try:
                logger.info(f"Bulk updating {len(clients_to_update)} clients")
                clients_to_bulk_update = [update_data['client'] for update_data in clients_to_update]
                
                # Define fields that can be bulk updated
                # Note: updated_at is auto-managed by Django, don't include it
                update_fields = [
                    'first_name', 'last_name', 'middle_name', 'dob', 'preferred_name', 'alias',
                    'gender', 'gender_identity', 'pronoun', 'marital_status', 'citizenship_status',
                    'location_county', 'province', 'city', 'postal_code', 'address', 'address_2',
                    'language', 'preferred_language', 'mother_tongue', 'official_language',
                    'language_interpreter_required', 'self_identification_race_ethnicity', 'lgbtq_status',
                    'highest_level_education', 'children_home', 'children_number', 'lhin',
                    'email', 'phone', 'source', 'level_of_support', 'client_type', 'referral_source',
                    'phone_work', 'phone_alt', 'permission_to_phone', 'permission_to_email',
                    'medical_conditions', 'primary_diagnosis', 'family_doctor', 'health_card_number',
                    'health_card_version', 'health_card_exp_date', 'health_card_issuing_province',
                    'no_health_card_reason', 'next_of_kin', 'emergency_contact', 'comments',
                    'chart_number', 'contact_information', 'addresses', 'languages_spoken',
                    'ethnicity', 'support_workers', 'discharge_date', 'reason_discharge', 'updated_by'
                ]
                
                # Use bulk_update - Django will only update fields that are set on the objects
                # We've already set the fields we want to update on each client object above
                Client.objects.bulk_update(clients_to_bulk_update, update_fields, batch_size=1000)
                logger.info(f"Bulk updated {len(clients_to_bulk_update)} clients successfully")
                
                # Update or create ClientExtended records
                from core.models import ClientExtended
                for update_data in clients_to_update:
                    client = update_data['client']
                    extended_data = update_data['extended_data']
                    
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
                
                # Process intake data for updated clients (optimized with pre-loaded caches)
                if has_intake_data:
                    for update_data in clients_to_update:
                        try:
                            client = update_data['client']
                            row_index = update_data['row_index']
                            row = df.iloc[row_index]
                            # Pass pre-loaded caches to avoid repeated database queries
                            process_intake_data(client, row, row_index, column_mapping, df.columns, departments_cache, programs_by_department)
                        except Exception as e:
                            logger.error(f"Error processing intake data for updated client {update_data['client'].client_id}: {str(e)}")
                            errors.append(f"Row {update_data['row_index'] + 2}: Error processing intake data - {str(e)}")
                
            except Exception as e:
                logger.error(f"Error in bulk update: {str(e)}")
                raise
        
        # Bulk create all clients
        created_clients = []  # Initialize outside the if block to track created clients
        if clients_to_create:
            try:
                # Extract just the client fields for bulk creation
                client_objects = []
                for client_data in clients_to_create:
                    client_objects.append(Client(**client_data['client_fields']))
                
                # Bulk create clients
                created_clients = Client.objects.bulk_create(client_objects, batch_size=1000)
                created_count = len(created_clients)
                
                # Create ClientExtended records
                from core.models import ClientExtended
                extended_objects = []
                for i, client_data in enumerate(clients_to_create):
                    if client_data['extended_data']:
                        extended_data = client_data['extended_data'].copy()
                        extended_data['client'] = created_clients[i]
                        extended_objects.append(ClientExtended(**extended_data))
                
                if extended_objects:
                    ClientExtended.objects.bulk_create(extended_objects, batch_size=1000)
                
                # Create duplicate relationships
                from core.models import ClientDuplicate
                duplicate_objects = []
                for i, client_data in enumerate(clients_to_create):
                    duplicate_info = client_data['duplicate_info']
                    if duplicate_info['is_duplicate'] and not is_update:
                        duplicate_client = duplicate_info['duplicate_client']
                        match_type = duplicate_info['match_type']
                        client = created_clients[i]
                        
                        # Use stored similarity score if available (from name-based matching), otherwise calculate
                        if duplicate_info.get('similarity_score') is not None:
                            similarity = duplicate_info['similarity_score']
                        elif match_type in ["exact_email", "exact_phone", "email_phone"]:
                            similarity = 1.0
                        elif match_type and match_type.startswith('name_similarity_'):
                            # Extract similarity from match_type string like "name_similarity_0.85"
                            try:
                                similarity = float(match_type.replace('name_similarity_', ''))
                                # Only mark as duplicate if similarity >= 0.9 (90%)
                                if similarity < 0.9:
                                    # Skip creating duplicate record if similarity is below 90%
                                    continue
                            except (ValueError, AttributeError):
                                # Default similarity below threshold, skip duplicate creation
                                continue
                        else:
                            # Default similarity below threshold, skip duplicate creation
                            continue
                        
                        confidence_level = fuzzy_matcher.get_duplicate_confidence_level(similarity)
                        
                        duplicate_objects.append(ClientDuplicate(
                            primary_client=duplicate_client,
                            duplicate_client=client,
                            similarity_score=similarity,
                            match_type=match_type,
                            confidence_level=confidence_level,
                            match_details={
                                'primary_name': f"{duplicate_client.first_name} {duplicate_client.last_name}",
                                'duplicate_name': f"{client.first_name} {client.last_name}",
                                'primary_email': duplicate_client.email,
                                'primary_phone': duplicate_client.phone,
                                'primary_client_id': duplicate_client.client_id,
                                'duplicate_original_email': duplicate_info['original_email'],
                                'duplicate_original_phone': duplicate_info['original_phone'],
                                'duplicate_original_client_id': duplicate_info['original_client_id'],
                            }
                        ))
                        
                        # Add to duplicate details for response
                        client_name = f"{duplicate_info['client_data'].get('first_name', '')} {duplicate_info['client_data'].get('last_name', '')}".strip()
                        existing_name = f"{duplicate_client.first_name} {duplicate_client.last_name}".strip()
                        
                        duplicate_details.append({
                            'type': 'created_with_duplicate',
                            'reason': f'{match_type.replace("_", " ").title()} match - created with duplicate flag for review',
                            'client_name': client_name,
                            'existing_name': existing_name,
                            'match_field': f"Match: {match_type}"
                        })
                
                if duplicate_objects:
                    ClientDuplicate.objects.bulk_create(duplicate_objects, batch_size=1000)
                
                logger.info(f"Bulk created {created_count} clients successfully")
                
                # Process intake data for all created clients (optimized with pre-loaded caches)
                if has_intake_data and created_clients:
                    logger.info(f"Processing intake data for {len(created_clients)} created clients")
                    for i, client in enumerate(created_clients):
                        try:
                            # Get the original row data for this client
                            client_data = clients_to_create[i]
                            row_index = client_data['row_index']
                            row = df.iloc[row_index]
                            
                            # Pass pre-loaded caches to avoid repeated database queries
                            process_intake_data(client, row, row_index, column_mapping, df.columns, departments_cache, programs_by_department)
                        except Exception as e:
                            logger.error(f"Error processing intake data for client {client.first_name} {client.last_name}: {str(e)}")
                            errors.append(f"Row {row_index + 2}: Error processing intake data - {str(e)}")
                
            except Exception as e:
                logger.error(f"Error in bulk creation: {str(e)}")
                # Force rollback of the entire upload by raising the error to the outer handler
                raise
        
        # Update inactive status for all processed clients based on active enrollments
        # This is done after all clients and enrollments have been processed
        try:
            all_processed_client_ids = []
            
            # Collect IDs from updated clients
            if clients_to_update:
                for update_data in clients_to_update:
                    client = update_data['client']
                    all_processed_client_ids.append(client.id)
            
            # Collect IDs from created clients
            if created_clients:
                for client in created_clients:
                    all_processed_client_ids.append(client.id)
            
            # Update inactive status for all processed clients
            if all_processed_client_ids:
                logger.info(f"Updating inactive status for {len(all_processed_client_ids)} processed clients")
                inactive_count = 0
                
                # Get all processed clients with their enrollments prefetched
                processed_clients = Client.objects.filter(
                    id__in=all_processed_client_ids
                ).prefetch_related('clientprogramenrollment_set')
                
                clients_to_update_status = []
                for client in processed_clients:
                    status_changed = client.update_inactive_status()
                    if status_changed:
                        clients_to_update_status.append(client)
                        if client.is_inactive:
                            inactive_count += 1
                
                # Bulk update inactive status
                if clients_to_update_status:
                    Client.objects.bulk_update(
                        clients_to_update_status,
                        ['is_inactive'],
                        batch_size=1000
                    )
                    logger.info(f"Updated inactive status for {len(clients_to_update_status)} clients ({inactive_count} marked as inactive)")
        except Exception as e:
            # Don't fail the upload if inactive status update fails
            logger.error(f"Error updating inactive status for processed clients: {str(e)}")
        
        # Calculate completion time and update upload log
        upload_completed_time = timezone.now()
        duplicate_created_count = len([d for d in duplicate_details if d['type'] == 'created_with_duplicate'])
        
        # Determine status
        if len(errors) > 0 and (created_count == 0 and updated_count == 0):
            status = 'failed'
        elif len(errors) > 0:
            status = 'partial'
        else:
            status = 'success'
        
        # Update upload log
        if upload_log:
            try:
                upload_log.completed_at = upload_completed_time
                upload_log.total_rows = len(df)
                upload_log.records_created = created_count
                upload_log.records_updated = updated_count
                upload_log.records_skipped = skipped_count
                upload_log.duplicates_flagged = duplicate_created_count
                upload_log.errors_count = len(errors)
                upload_log.status = status
                upload_log.error_details = errors[:50]  # Store first 50 errors
                upload_log.upload_details = {
                    'has_intake_data': has_intake_data,
                    'source': source,
                    'file_extension': file_extension
                }
                upload_log.save()
                logger.info(f"Upload log updated: {upload_log.id} - Duration: {upload_log.duration_seconds:.2f}s")
            except Exception as e:
                logger.error(f"Failed to update upload log: {e}")
        
        response_data = {
            'success': True,
            'message': f'Upload completed successfully! {created_count} clients created, {updated_count} clients updated.',
            'stats': {
                'total_rows': len(df),
                'created': created_count,
                'updated': updated_count,
                'skipped': skipped_count,
                'duplicates_flagged': duplicate_created_count,
                'errors': len(errors),
                'duration_seconds': upload_log.duration_seconds if upload_log else None
            },
            'duplicate_details': duplicate_details[:20],  # Limit to first 20 duplicates for display
            'errors': errors[:10] if errors else [],  # Limit to first 10 errors
            'debug_info': debug_info,  # Add debug information
            'notes': [
                'Existing clients with matching Client ID were updated with new information',
                'New clients were created for records without existing Client ID matches',
                'Missing date of birth values were set to 1900-01-01',
                'Missing gender values were set to null',
                f'{duplicate_created_count} clients were created with potential duplicate flags for review',
                'Review flagged duplicates in the "Probable Duplicate Clients" section'
            ] if created_count > 0 or updated_count > 0 or duplicate_created_count > 0 else []
        }
        
        return JsonResponse(response_data)
        
    except Exception as e:
        logger.error(f"Upload error: {str(e)}")
        
        # Update upload log with error
        if upload_log:
            try:
                upload_log.completed_at = timezone.now()
                upload_log.status = 'failed'
                upload_log.error_message = str(e)
                if 'file' in locals():
                    upload_log.file_name = file.name if hasattr(file, 'name') else 'Unknown'
                    upload_log.file_size = file.size if hasattr(file, 'size') else 0
                upload_log.save()
            except Exception as log_error:
                logger.error(f"Failed to update upload log with error: {log_error}")
        
        # Provide user-friendly error message
        return JsonResponse({
            'success': False, 
            'error': 'Upload failed. Please check your file format and try again. If the problem persists, contact your system administrator.'
        }, status=500)

@require_http_methods(["GET"])
@login_required
def get_upload_logs(request):
    """API endpoint to get client upload logs"""
    try:
        # Check permissions - same as upload permission
        if request.user.is_authenticated:
            try:
                staff = request.user.staff_profile
                user_roles = staff.staffrole_set.select_related('role').all()
                role_names = [staff_role.role.name for staff_role in user_roles]
                
                # Staff role users cannot view upload logs
                if 'Staff' in role_names and not any(role in ['SuperAdmin', 'Admin', 'Manager', 'Leader'] for role in role_names):
                    return JsonResponse({'success': False, 'error': 'You do not have permission to view upload logs.'}, status=403)
            except Exception:
                pass
        
        # Get pagination parameters
        page = int(request.GET.get('page', 1))
        per_page = int(request.GET.get('per_page', 20))
        
        # Get all upload logs ordered by most recent
        logs = ClientUploadLog.objects.select_related('uploaded_by').order_by('-started_at')
        
        # Paginate
        from django.core.paginator import Paginator
        paginator = Paginator(logs, per_page)
        page_obj = paginator.get_page(page)
        
        # Serialize logs
        logs_data = []
        for log in page_obj:
            logs_data.append({
                'id': str(log.external_id),
                'file_name': log.file_name,
                'file_size': log.file_size,
                'file_type': log.file_type,
                'source': log.source,
                'total_rows': log.total_rows,
                'records_created': log.records_created,
                'records_updated': log.records_updated,
                'records_skipped': log.records_skipped,
                'duplicates_flagged': log.duplicates_flagged,
                'errors_count': log.errors_count,
                'started_at': log.started_at.strftime('%Y-%m-%d %H:%M:%S') if log.started_at else None,
                'completed_at': log.completed_at.strftime('%Y-%m-%d %H:%M:%S') if log.completed_at else None,
                'duration_seconds': round(log.duration_seconds, 2) if log.duration_seconds else None,
                'status': log.status,
                'error_message': log.error_message,
                'uploaded_by': f"{log.uploaded_by.first_name} {log.uploaded_by.last_name}".strip() if log.uploaded_by else 'System',
                'upload_details': log.upload_details
            })
        
        return JsonResponse({
            'success': True,
            'logs': logs_data,
            'pagination': {
                'page': page_obj.number,
                'per_page': per_page,
                'total_pages': paginator.num_pages,
                'total_count': paginator.count,
                'has_next': page_obj.has_next(),
                'has_previous': page_obj.has_previous(),
            }
        })
        
    except Exception as e:
        logger.error(f"Error fetching upload logs: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

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
@jwt_required
def bulk_delete_clients(request):
    """Bulk delete clients"""
    try:
        import json
        logger.info(f"Bulk delete request from user: {request.user}")
        
        data = json.loads(request.body)
        client_ids = data.get('client_ids', [])
        logger.info(f"Client IDs to delete: {client_ids}")
        
        if not client_ids:
            logger.warning("No client IDs provided for bulk delete")
            return JsonResponse({
                'success': False, 
                'error': 'No client IDs provided'
            }, status=400)
        
        # Get clients to delete
        clients_to_delete = Client.objects.filter(external_id__in=client_ids)
        deleted_count = clients_to_delete.count()
        logger.info(f"Found {deleted_count} clients to delete")
        
        if deleted_count == 0:
            logger.warning(f"No clients found with provided IDs: {client_ids}")
            return JsonResponse({
                'success': False, 
                'error': 'No clients found with provided IDs'
            }, status=404)
        
        # Soft delete: archive clients instead of actually deleting them
        from django.utils import timezone
        from core.models import create_audit_log, ServiceRestriction
        user_name = request.user.get_full_name() or request.user.username if request.user.is_authenticated else 'System'
        archived_at = timezone.now()
        
        total_enrollments_archived = 0
        total_restrictions_archived = 0
        
        for client in clients_to_delete:
            # Create audit log entry before archiving
            try:
                create_audit_log(
                    entity_name='Client',
                    entity_id=client.external_id,
                    action='archive',
                    changed_by=request.user,
                    diff_data={
                        'first_name': client.first_name,
                        'last_name': client.last_name,
                        'client_id': client.client_id or '',
                        'archived_by': user_name
                    }
                )
            except Exception as e:
                logger.error(f"Error creating audit log for client archiving: {e}")
            
            # Archive all enrollments associated with this client
            enrollments = ClientProgramEnrollment.objects.filter(client=client, is_archived=False)
            enrollment_count = enrollments.count()
            total_enrollments_archived += enrollment_count
            for enrollment in enrollments:
                enrollment.is_archived = True
                enrollment.archived_at = archived_at
                enrollment.updated_by = user_name
                enrollment.save()
            
            # Archive all restrictions associated with this client
            restrictions = ServiceRestriction.objects.filter(client=client, is_archived=False)
            restriction_count = restrictions.count()
            total_restrictions_archived += restriction_count
            for restriction in restrictions:
                restriction.is_archived = True
                restriction.archived_at = archived_at
                restriction.updated_by = user_name
                restriction.save()
            
            # Soft delete: set is_archived=True and archived_at timestamp
            client.is_archived = True
            client.archived_at = archived_at
            client.updated_by = user_name
            client.save()
        
        logger.info(f"Bulk archived {deleted_count} clients: {client_ids}")
        logger.info(f"Archived {total_enrollments_archived} enrollments and {total_restrictions_archived} restrictions")
        
        # Create message with details
        message_parts = [f'Successfully archived {deleted_count} client(s).']
        if total_enrollments_archived > 0:
            message_parts.append(f'{total_enrollments_archived} enrollment(s) have been archived.')
        if total_restrictions_archived > 0:
            message_parts.append(f'{total_restrictions_archived} restriction(s) have been archived.')
        message_parts.append('You can restore them from the archived clients section.')
        
        return JsonResponse({
            'success': True,
            'deleted_count': deleted_count,
            'enrollments_archived': total_enrollments_archived,
            'restrictions_archived': total_restrictions_archived,
            'message': ' '.join(message_parts)
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


@csrf_protect
@require_http_methods(["POST"])
@jwt_required
def bulk_restore_clients(request):
    """Bulk restore archived clients"""
    if not request.user.is_authenticated:
        return JsonResponse({
            'success': False,
            'error': 'Authentication required'
        }, status=401)
    
    try:
        import json
        data = json.loads(request.body)
        client_ids = data.get('client_ids', [])
        
        if not client_ids:
            return JsonResponse({
                'success': False,
                'error': 'No clients selected for restoration'
            }, status=400)
        
        # Get the archived clients to restore
        clients_to_restore = Client.objects.filter(
            external_id__in=client_ids,
            is_archived=True
        )
        restored_count = clients_to_restore.count()
        
        if restored_count == 0:
            return JsonResponse({
                'success': False,
                'error': 'No archived clients found with the provided IDs'
            }, status=404)
        
        # Restore clients: set is_archived=False and clear archived_at
        from django.utils import timezone
        from core.models import create_audit_log
        user_name = request.user.get_full_name() or request.user.username if request.user.is_authenticated else 'System'
        
        for client in clients_to_restore:
            # Create audit log entry for restoration
            try:
                create_audit_log(
                    entity_name='Client',
                    entity_id=client.external_id,
                    action='restore',
                    changed_by=request.user,
                    diff_data={
                        'first_name': client.first_name,
                        'last_name': client.last_name,
                        'client_id': client.client_id or '',
                        'restored_by': user_name
                    }
                )
            except Exception as e:
                logger.error(f"Error creating audit log for client restoration: {e}")
            
            # Restore: set is_archived=False and clear archived_at
            client.is_archived = False
            client.archived_at = None
            client.updated_by = user_name
            client.save()
        
        return JsonResponse({
            'success': True,
            'restored_count': restored_count,
            'message': f'Successfully restored {restored_count} client(s)'
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON data'
        }, status=400)
    except Exception as e:
        logger.error(f"Error restoring clients: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': f'Error restoring clients: {str(e)}'
        }, status=500)


class ClientDedupeView(TemplateView):
    """View for managing client duplicates"""
    template_name = 'clients/client_dedupe.html'
    paginate_by = 20  # Number of duplicate groups per page
    
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
        from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
        
        context = super().get_context_data(**kwargs)
        
        # Get filter parameters
        status_filter = self.request.GET.get('status', 'pending')
        confidence_filter = self.request.GET.get('confidence', '')
        
        # Build optimized query with select_related and only necessary fields
        duplicates_query = ClientDuplicate.objects.select_related(
            'primary_client', 'duplicate_client'
        ).only(
            'id', 'status', 'confidence_level', 'similarity_score', 'created_at',
            'primary_client__id', 'primary_client__first_name', 'primary_client__last_name',
            'primary_client__external_id', 'primary_client__client_id',
            'duplicate_client__id', 'duplicate_client__first_name', 'duplicate_client__last_name',
            'duplicate_client__external_id', 'duplicate_client__client_id'
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
        
        # Convert to list for pagination
        grouped_duplicates_list = list(grouped_duplicates.values())
        
        # Paginate the grouped duplicates
        paginator = Paginator(grouped_duplicates_list, self.paginate_by)
        page = self.request.GET.get('page', 1)
        
        try:
            paginated_groups = paginator.page(page)
        except PageNotAnInteger:
            paginated_groups = paginator.page(1)
        except EmptyPage:
            paginated_groups = paginator.page(paginator.num_pages)
        
        # Get statistics (optimized with single queries)
        total_duplicates = ClientDuplicate.objects.count()
        pending_duplicates = ClientDuplicate.objects.filter(status='pending').count()
        high_confidence_duplicates = ClientDuplicate.objects.filter(
            confidence_level='high', status='pending'
        ).count()
        
        context.update({
            'grouped_duplicates': {i: group for i, group in enumerate(paginated_groups)},
            'paginated_groups': paginated_groups,
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
            except Exception:
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
            
            # Mark the duplicate as confirmed before deletion (for audit trail)
            duplicate.mark_as_duplicate(reviewed_by, notes)
            
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
            
            # Check file type - allow PNG, JPEG, GIF, WebP
            allowed_types = ['image/jpeg', 'image/jpg', 'image/png', 'image/gif', 'image/webp']
            if file.content_type not in allowed_types:
                return JsonResponse({
                    'success': False,
                    'error': 'Please upload a valid image file (JPEG, PNG, GIF, or WebP)'
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
@login_required
def get_service_restriction_notifications(request):
    """Return the current user's service restriction notification preferences."""
    staff = getattr(request.user, 'staff_profile', None)
    if not staff:
        return JsonResponse({'success': False, 'error': 'Staff profile not found'}, status=400)

    default_email = staff.email or request.user.email or ''

    subscription, _ = ServiceRestrictionNotificationSubscription.objects.get_or_create(
        staff=staff,
        defaults={
            'email': default_email,
            'notify_new': True,
            'notify_expiring': True,
        }
    )

    return JsonResponse({
        'success': True,
        'subscription': {
            'email': subscription.email or '',
            'default_email': default_email,
            'notify_new': subscription.notify_new,
            'notify_expiring': subscription.notify_expiring,
        }
    })


@require_http_methods(["POST"])
@csrf_protect
@login_required
def save_service_restriction_notifications(request):
    """Persist the current user's notification preferences for service restriction alerts."""
    staff = getattr(request.user, 'staff_profile', None)
    if not staff:
        return JsonResponse({'success': False, 'error': 'Staff profile not found'}, status=400)

    try:
        data = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid request payload'}, status=400)

    notify_new = bool(data.get('notify_new', False))
    notify_expiring = bool(data.get('notify_expiring', False))
    email_input = (data.get('email') or '').strip()

    default_email = staff.email or request.user.email or ''
    effective_email = email_input or default_email

    # Validate email when subscribing to notifications
    if notify_new or notify_expiring:
        if not effective_email:
            return JsonResponse({
                'success': False,
                'error': 'Please provide an email address to receive alerts.'
            }, status=400)
        try:
            validate_email(effective_email)
        except ValidationError:
            return JsonResponse({
                'success': False,
                'error': 'Please provide a valid email address.'
            }, status=400)
    elif email_input:
        # If they provide a custom email while unsubscribed, still validate it
        try:
            validate_email(email_input)
        except ValidationError:
            return JsonResponse({
                'success': False,
                'error': 'Please provide a valid email address.'
            }, status=400)

    subscription, _ = ServiceRestrictionNotificationSubscription.objects.get_or_create(staff=staff)
    subscription.email = email_input or None
    subscription.notify_new = notify_new
    subscription.notify_expiring = notify_expiring
    subscription.save()

    return JsonResponse({
        'success': True,
        'subscription': {
            'email': subscription.email or '',
            'default_email': default_email,
            'notify_new': subscription.notify_new,
            'notify_expiring': subscription.notify_expiring,
        }
    })


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

