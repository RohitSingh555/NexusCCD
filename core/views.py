from django.shortcuts import render, redirect
from django.db.models import Count, Q
from django.db import models
from django.http import JsonResponse, HttpResponse
from django.contrib.auth import get_user_model
from functools import wraps
import json
import csv
from django.contrib import messages
from .message_utils import success_message, error_message, warning_message, info_message, create_success, update_success, delete_success, validation_error, permission_error, not_found_error
from django.urls import reverse_lazy
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils.decorators import method_decorator
from datetime import datetime
from django.utils import timezone
from .models import Client, Program, Staff, ClientProgramEnrollment, Department, ServiceRestriction, AuditLog
from .forms import EnrollmentForm
from .forms import UserProfileForm, StaffProfileForm, PasswordChangeForm, ServiceRestrictionForm


User = get_user_model()


class AnalystAccessMixin:
    """Mixin to block Analyst users from accessing individual pages"""
    
    def dispatch(self, request, *args, **kwargs):
        """Check if user is Analyst and block access to individual pages"""
        if request.user.is_authenticated:
            try:
                staff = request.user.staff_profile
                user_roles = staff.staffrole_set.select_related('role').all()
                role_names = [staff_role.role.name for staff_role in user_roles]
                
                # Block Analyst users from accessing individual pages
                if 'Analyst' in role_names and not any(role in ['SuperAdmin', 'Manager', 'Leader', 'Staff'] for role in role_names):
                    messages.error(request, 'Analyst users can only access Dashboard and Reports. Individual pages are not accessible.')
                    return redirect('dashboard')
            except Exception:
                pass
        
        return super().dispatch(request, *args, **kwargs)


class ProgramManagerAccessMixin:
    """Mixin to filter data for Managers based on their assigned programs"""
    
    def get_queryset(self):
        """Filter queryset based on user's assigned programs"""
        # Start with the base queryset with proper ordering and select_related
        queryset = self.model.objects.all().order_by('-created_at')
        
        # Add appropriate select_related based on model
        if hasattr(self.model, 'department'):
            queryset = queryset.select_related('department')
        elif hasattr(self.model, 'client') and hasattr(self.model, 'program'):
            queryset = queryset.select_related('client', 'program')
        elif hasattr(self.model, 'client'):
            queryset = queryset.select_related('client')
        elif hasattr(self.model, 'program'):
            queryset = queryset.select_related('program')
        
        if not self.request.user.is_authenticated:
            return queryset.none()
        
        # Superadmin can see everything - bypass all filtering
        if self.request.user.is_superuser:
            return queryset
        
        try:
            staff = self.request.user.staff_profile
            user_roles = staff.staffrole_set.select_related('role').all()
            role_names = [staff_role.role.name for staff_role in user_roles]
            
            # Manager can see all data - no filtering for managers
            if staff.is_program_manager():
                # Managers see all restrictions without any filtering
                if self.model.__name__ == 'ServiceRestriction':
                    return queryset
                else:
                    # For other models, managers see only their assigned programs
                    assigned_programs = staff.get_assigned_programs()
                    if hasattr(self.model, 'program'):
                        return queryset.filter(program__in=assigned_programs)
                    else:
                        return queryset.filter(id__in=assigned_programs)
            
            # Leader can see data for their assigned departments
            elif staff.is_leader():
                # Use direct queries since the methods aren't working
                assigned_departments = Department.objects.filter(
                    leader_assignments__staff=staff,
                    leader_assignments__is_active=True
                ).distinct()
                assigned_programs = Program.objects.filter(
                    department__in=assigned_departments
                ).distinct()
                
                if self.model.__name__ == 'ServiceRestriction':
                    # Leaders see ALL restrictions (like Staff users)
                    return queryset
                elif hasattr(self.model, 'program'):
                    return queryset.filter(program__in=assigned_programs)
                elif hasattr(self.model, 'department'):
                    return queryset.filter(department__in=assigned_departments)
                elif hasattr(self.model, 'client'):
                    # For client models, show clients enrolled in assigned programs
                    assigned_clients = Client.objects.filter(
                        clientprogramenrollment__program__in=assigned_programs
                    ).distinct()
                    return queryset.filter(id__in=assigned_clients)
                else:
                    return queryset.filter(id__in=assigned_programs)
            
            # Staff users (including those with multiple roles) see limited access to data
            elif 'Staff' in role_names:
                from staff.models import StaffClientAssignment
                # Get programs where assigned clients are enrolled
                assigned_client_ids = StaffClientAssignment.objects.filter(
                    staff=staff,
                    is_active=True
                ).values_list('client_id', flat=True)
                assigned_programs = Program.objects.filter(
                    clientprogramenrollment__client_id__in=assigned_client_ids
                ).distinct()
                
                # Filter based on model type - special handling for different models
                if self.model.__name__ == 'ServiceRestriction':
                    # Staff users see ALL restrictions regardless of program or client assignments
                    return queryset
                elif hasattr(self.model, 'program') and self.model.__name__ == 'ClientProgramEnrollment':
                    # For ClientProgramEnrollment - Staff users see only enrollments for their assigned programs
                    return queryset.filter(program__in=assigned_programs)
                elif hasattr(self.model, 'program'):
                    # For other models with program field (like ServiceRestriction) - show all
                    return queryset
                elif hasattr(self.model, 'client') and not hasattr(self.model, 'program'):
                    # For models with only client field (like Client)
                    # Staff users see only clients enrolled in their assigned programs
                    assigned_clients = Client.objects.filter(
                        clientprogramenrollment__program__in=assigned_programs
                    ).distinct()
                    return queryset.filter(id__in=assigned_clients)
                else:
                    # For models without program field (like Program)
                    return queryset.filter(id__in=assigned_programs)
            
            # Other roles see everything (SuperAdmin, etc.)
            return queryset
            
        except Exception as e:
            # For superadmin, return all programs even if there's an exception
            if self.request.user.is_superuser:
                return queryset
            return queryset.none()
    

def jwt_required(view_func):
    """Decorator to require authentication (JWT or Django session)"""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        # Check if user is authenticated (either JWT via middleware or Django session)
        if request.user.is_authenticated:
            return view_func(request, *args, **kwargs)
        
        # If no authentication at all, redirect to home
        return redirect('home')
    
    return wrapper


def home(request):
    """Home view that redirects authenticated users to dashboard"""
    # Check if user is authenticated (either JWT via middleware or Django session)
    if request.user.is_authenticated:
        return redirect('dashboard')
    
    return render(request, 'home.html')


def dashboard(request):
    """Dashboard view - redirects to profile for users without proper permissions"""
    # Check if user is authenticated (either JWT via middleware or Django session)
    if not request.user.is_authenticated:
        return redirect('home')
    
    # Check if user has proper permissions to access dashboard
    try:
        staff_profile = request.user.staff_profile
        user_roles = staff_profile.staffrole_set.select_related('role').all()
        role_names = [staff_role.role.name for staff_role in user_roles]
        
        # Check if user has any meaningful permissions
        has_permissions = any(role in ['SuperAdmin', 'Admin', 'Staff', 'Manager', 'Leader', 'Analyst'] for role in role_names)
        
        if not has_permissions:
            # User doesn't have proper permissions, redirect to profile
            return redirect('core:profile')
            
    except Staff.DoesNotExist:
        # User doesn't have staff profile, redirect to profile
        return redirect('core:profile')
    
    # User has proper permissions, show dashboard
    # Check if user is a program manager, staff-only, leader, or analyst to filter data accordingly
    is_program_manager = False
    is_staff_only = False
    is_leader = False
    is_analyst = False
    assigned_programs = None
    assigned_clients = None
    staff_assigned_clients = None
    
    try:
        staff_profile = request.user.staff_profile
        user_roles = staff_profile.staffrole_set.select_related('role').all()
        role_names = [staff_role.role.name for staff_role in user_roles]
        
        if staff_profile.is_program_manager():
            is_program_manager = True
            assigned_programs = staff_profile.get_assigned_programs()
        elif staff_profile.is_leader():
            is_leader = True
            # Get assigned programs for leader users via departments using direct queries
            assigned_departments = Department.objects.filter(
                leader_assignments__staff=staff_profile,
                leader_assignments__is_active=True
            ).distinct()
            assigned_programs = Program.objects.filter(
                department__in=assigned_departments
            ).distinct()
            # Get clients enrolled in assigned programs
            assigned_clients = Client.objects.filter(
                clientprogramenrollment__program__in=assigned_programs
            ).distinct()
        elif 'Analyst' in role_names:
            is_analyst = True
            # Analysts see all data - no filtering needed
            assigned_programs = None
            assigned_clients = None
        elif staff_profile.is_staff_only():
                is_staff_only = True
                # Get directly assigned clients for staff users
                from staff.models import StaffClientAssignment
                staff_assigned_clients = Client.objects.filter(
                    staff_assignments__staff=staff_profile,
                    staff_assignments__is_active=True
                ).distinct()
                # Get programs where assigned clients are enrolled
                assigned_programs = Program.objects.filter(
                    clientprogramenrollment__client__in=staff_assigned_clients
                ).distinct()
                # Get clients enrolled in assigned programs (same as staff_assigned_clients for staff users)
                assigned_clients = staff_assigned_clients
    except Exception:
        pass
    
    # Get basic statistics - filter for program managers and staff-only users
    if is_program_manager and assigned_programs:
        # Program managers see only clients enrolled in their assigned programs
        total_clients = Client.objects.filter(
            clientprogramenrollment__program__in=assigned_programs
        ).distinct().count()
        active_programs = assigned_programs.count()
        total_staff = Staff.objects.count()  # Staff count is same for all
        
        # Get active restrictions count - Managers see ALL restrictions
        from django.utils import timezone
        today = timezone.now().date()
        active_restrictions = ServiceRestriction.objects.filter(
            is_archived=False,
            start_date__lte=today
        ).filter(
            Q(end_date__isnull=True) | Q(end_date__gte=today)
        ).count()
        
        # Get recent clients (last 5) from assigned programs
        recent_clients = Client.objects.filter(
            clientprogramenrollment__program__in=assigned_programs
        ).distinct().order_by('-created_at')[:5]
        
        # Get recent restrictions (last 5) - Managers see ALL restrictions
        recent_restrictions = ServiceRestriction.objects.filter(
            is_archived=False
        ).select_related('client', 'program').order_by('-created_at')[:5]
        
        # Get restricted clients (Bill 168 and No Trespass) - Managers see ALL restrictions
        restricted_clients = ServiceRestriction.objects.filter(
            is_archived=False
        ).filter(
            Q(is_bill_168=True) | Q(is_no_trespass=True)
        ).select_related('client', 'program').order_by('-created_at')[:10]
    elif is_leader and assigned_programs:
        # Leader users see data for their assigned departments
        total_clients = Client.objects.filter(
            clientprogramenrollment__program__in=assigned_programs
        ).distinct().count()
        active_programs = assigned_programs.count()
        total_staff = Staff.objects.count()  # Staff count is same for all
        
        # Get active restrictions count - Leaders see ALL restrictions
        from django.utils import timezone
        today = timezone.now().date()
        active_restrictions = ServiceRestriction.objects.filter(
            is_archived=False,
            start_date__lte=today
        ).filter(
            Q(end_date__isnull=True) | Q(end_date__gte=today)
        ).count()
        
        # Get recent clients (last 5) from assigned programs
        recent_clients = Client.objects.filter(
            clientprogramenrollment__program__in=assigned_programs
        ).distinct().order_by('-created_at')[:5]
        
        # Get recent restrictions (last 5) - Leaders see ALL restrictions
        recent_restrictions = ServiceRestriction.objects.filter(
            is_archived=False
        ).select_related('client', 'program').order_by('-created_at')[:5]
        
        # Get restricted clients (Bill 168 and No Trespass) - Leaders see ALL restrictions
        restricted_clients = ServiceRestriction.objects.filter(
            is_archived=False
        ).filter(
            Q(is_bill_168=True) | Q(is_no_trespass=True)
        ).select_related('client', 'program').order_by('-created_at')[:10]
    elif is_staff_only:
        # Staff users now see ALL data across all clients and programs (same as analysts)
        total_clients = Client.objects.count()
        active_programs = Program.objects.count()
        total_staff = Staff.objects.count()
        
        # Get active restrictions count - Staff users see ALL restrictions
        from django.utils import timezone
        today = timezone.now().date()
        active_restrictions = ServiceRestriction.objects.filter(
            is_archived=False,
            start_date__lte=today
        ).filter(
            Q(end_date__isnull=True) | Q(end_date__gte=today)
        ).count()
        
        # Get recent clients (last 5) - Staff users see ALL clients
        recent_clients = Client.objects.all().order_by('-created_at')[:5]
        
        # Get recent restrictions (last 5) - Staff users see ALL restrictions
        recent_restrictions = ServiceRestriction.objects.filter(
            is_archived=False
        ).select_related('client', 'program').order_by('-created_at')[:5]
        
        # Get restricted clients (Bill 168 and No Trespass) - Staff users see ALL restrictions
        restricted_clients = ServiceRestriction.objects.filter(
            is_archived=False
        ).filter(
            Q(is_bill_168=True) | Q(is_no_trespass=True)
        ).select_related('client', 'program').order_by('-created_at')[:10]
    elif is_analyst:
        # Analysts see ALL data across all clients and programs
        total_clients = Client.objects.count()
        active_programs = Program.objects.count()
        total_staff = Staff.objects.count()
        
        # Get active restrictions count - Analysts see ALL restrictions
        from django.utils import timezone
        today = timezone.now().date()
        active_restrictions = ServiceRestriction.objects.filter(
            is_archived=False,
            start_date__lte=today
        ).filter(
            Q(end_date__isnull=True) | Q(end_date__gte=today)
        ).count()
        
        # Get recent clients (last 5) - Analysts see ALL clients
        recent_clients = Client.objects.all().order_by('-created_at')[:5]
        
        # Get recent restrictions (last 5) - Analysts see ALL restrictions
        recent_restrictions = ServiceRestriction.objects.filter(
            is_archived=False
        ).select_related('client', 'program').order_by('-created_at')[:5]
        
        # Get restricted clients (Bill 168 and No Trespass) - Analysts see ALL restrictions
        restricted_clients = ServiceRestriction.objects.filter(
            is_archived=False
        ).filter(
            Q(is_bill_168=True) | Q(is_no_trespass=True)
        ).select_related('client', 'program').order_by('-created_at')[:10]
    else:
        # SuperAdmin and other roles see all data
        total_clients = Client.objects.count()
        active_programs = Program.objects.count()
        total_staff = Staff.objects.count()
        
        # Get active restrictions count
        from django.utils import timezone
        today = timezone.now().date()
        active_restrictions = ServiceRestriction.objects.filter(
            is_archived=False,
            start_date__lte=today
        ).filter(
            Q(end_date__isnull=True) | Q(end_date__gte=today)
        ).count()
        
        # Get recent clients (last 5)
        recent_clients = Client.objects.order_by('-created_at')[:5]
        
        # Get recent restrictions (last 5)
        recent_restrictions = ServiceRestriction.objects.filter(
            is_archived=False
        ).select_related('client', 'program').order_by('-created_at')[:5]
        
        # Get restricted clients (Bill 168 and No Trespass)
        restricted_clients = ServiceRestriction.objects.filter(
            is_archived=False
        ).filter(
            Q(is_bill_168=True) | Q(is_no_trespass=True)
        ).select_related('client', 'program').order_by('-created_at')[:10]
    
    # Get program status with enrollment counts and capacity information
    # Filter programs based on user role
    if request.user.is_authenticated:
        try:
            staff = request.user.staff_profile
            if staff.is_program_manager():
                # Manager can only see their assigned programs
                programs = staff.get_assigned_programs()
            elif is_staff_only:
                # Staff-only users see only programs where their assigned clients are enrolled
                programs = assigned_programs if assigned_programs else Program.objects.none()
            else:
                # SuperAdmin and other roles can see all programs
                programs = Program.objects.all()
        except Exception:
            programs = Program.objects.none()
    else:
        programs = Program.objects.none()
    
    program_status = []
    
    # Limit to first 5 programs
    programs_limited = programs[:5]
    
    for program in programs_limited:
        current_enrollments = program.get_current_enrollments_count()
        available_capacity = program.get_available_capacity()
        capacity_percentage = program.get_capacity_percentage()
        is_at_capacity = program.is_at_capacity()
        
        program_status.append({
            'name': program.name,
            'department': program.department,
            'capacity_current': program.capacity_current,
            'current_enrollments': current_enrollments,
            'available_capacity': available_capacity,
            'capacity_percentage': round(capacity_percentage, 1),
            'is_at_capacity': is_at_capacity
        })
    
    context = {
        'total_clients': total_clients,
        'active_programs': active_programs,
        'total_staff': total_staff,
        'active_restrictions': active_restrictions,
        'recent_clients': recent_clients,
        'recent_restrictions': recent_restrictions,
        'restricted_clients': restricted_clients,
        'program_status': program_status,
        'is_program_manager': is_program_manager,
        'is_staff_only': is_staff_only,
        'assigned_programs': assigned_programs,
        'staff_assigned_clients': staff_assigned_clients,
    }
    
    return render(request, 'dashboard.html', context)


@jwt_required
def departments(request):
    """Departments management view"""
    # Check if user is Analyst and block access
    if request.user.is_authenticated:
        try:
            staff = request.user.staff_profile
            user_roles = staff.staffrole_set.select_related('role').all()
            role_names = [staff_role.role.name for staff_role in user_roles]
            
            # Block Analyst users from accessing departments page
            if 'Analyst' in role_names and not any(role in ['SuperAdmin', 'Manager', 'Leader', 'Staff'] for role in role_names):
                messages.error(request, 'Analyst users can only access Dashboard and Reports. Individual pages are not accessible.')
                return redirect('dashboard')
        except Exception:
            pass
    
    # Get departments - filter for Managers and Leaders
    if request.user.is_authenticated:
        try:
            staff = request.user.staff_profile
            if staff.is_program_manager():
                # Manager can only see departments of their assigned programs
                # Get assigned departments and add proper annotations
                assigned_departments = staff.get_assigned_departments()
                assigned_programs = staff.get_assigned_programs()
                departments = Department.objects.filter(
                    id__in=assigned_departments.values_list('id', flat=True)
                ).annotate(
                    program_count=Count('program', filter=Q(program__in=assigned_programs), distinct=True),
                    staff_count=Count('program__programstaff__staff', distinct=True)
                ).order_by('name')
            elif staff.is_leader():
                # Leader can only see their assigned departments
                assigned_departments = Department.objects.filter(
                    leader_assignments__staff=staff,
                    leader_assignments__is_active=True
                ).distinct()
                assigned_programs = Program.objects.filter(
                    department__in=assigned_departments
                ).distinct()
                departments = assigned_departments.annotate(
                    program_count=Count('program', filter=Q(program__in=assigned_programs), distinct=True),
                    staff_count=Count('program__programstaff__staff', distinct=True)
                ).order_by('name')
            else:
                # SuperAdmin and Staff can see all departments
                departments = Department.objects.annotate(
                    program_count=Count('program', distinct=True),
                    staff_count=Count('program__programstaff__staff', distinct=True)
                ).order_by('name')
        except Exception:
            departments = Department.objects.none()
    else:
        departments = Department.objects.none()
    
    # Get statistics based on filtered departments
    total_departments = departments.count()
    
    # Calculate total programs based on filtered departments
    if request.user.is_authenticated:
        try:
            staff = request.user.staff_profile
            if staff.is_program_manager():
                # Manager sees only programs they are assigned to manage
                total_programs = staff.get_assigned_programs().count()
            elif staff.is_leader():
                # Leader sees only programs from their assigned departments
                assigned_departments = Department.objects.filter(
                    leader_assignments__staff=staff,
                    leader_assignments__is_active=True
                ).distinct()
                total_programs = Program.objects.filter(
                    department__in=assigned_departments
                ).distinct().count()
            else:
                # SuperAdmin and Staff see all programs
                total_programs = Program.objects.count()
        except Exception:
            total_programs = Program.objects.count()
    else:
        total_programs = Program.objects.count()
    
    # Calculate total staff based on user role
    if request.user.is_authenticated:
        try:
            staff = request.user.staff_profile
            if staff.is_program_manager():
                # Manager sees only staff from their assigned programs
                total_staff = Staff.objects.filter(
                    program_assignments__program__in=staff.get_assigned_programs(),
                    program_assignments__is_active=True
                ).distinct().count()
            elif staff.is_leader():
                # Leader sees only staff from their assigned departments
                assigned_departments = Department.objects.filter(
                    leader_assignments__staff=staff,
                    leader_assignments__is_active=True
                ).distinct()
                assigned_programs = Program.objects.filter(
                    department__in=assigned_departments
                ).distinct()
                total_staff = Staff.objects.filter(
                    program_assignments__program__in=assigned_programs,
                    program_assignments__is_active=True
                ).distinct().count()
            else:
                # SuperAdmin and Staff see all staff
                total_staff = Staff.objects.count()
        except Exception:
            total_staff = Staff.objects.count()
    else:
        total_staff = Staff.objects.count()
    
    context = {
        'departments': departments,
        'total_departments': total_departments,
        'total_programs': total_programs,
        'total_staff': total_staff,
    }
    
    return render(request, 'core/departments.html', context)


@jwt_required
def enrollments(request):
    """Enrollments management view"""
    # Check if user is Analyst and block access
    if request.user.is_authenticated:
        try:
            staff = request.user.staff_profile
            user_roles = staff.staffrole_set.select_related('role').all()
            role_names = [staff_role.role.name for staff_role in user_roles]
            
            # Block Analyst users from accessing enrollments page
            if 'Analyst' in role_names and not any(role in ['SuperAdmin', 'Manager', 'Leader', 'Staff'] for role in role_names):
                messages.error(request, 'Analyst users can only access Dashboard and Reports. Individual pages are not accessible.')
                return redirect('dashboard')
        except Exception:
            pass
    
    # Get all enrollments with related data
    enrollments = ClientProgramEnrollment.objects.select_related(
        'client', 'program', 'program__department'
    ).order_by('-start_date')
    
    # Calculate statistics using date-based logic
    from django.utils import timezone
    today = timezone.now().date()
    
    total_enrollments = enrollments.count()
    active_count = 0
    completed_count = 0
    pending_count = 0
    
    for enrollment in enrollments:
        if today < enrollment.start_date:
            pending_count += 1
        elif enrollment.end_date:
            if today > enrollment.end_date:
                completed_count += 1
            else:
                active_count += 1
        else:
            active_count += 1
    
    # Calculate success rate
    success_rate = 0
    if total_enrollments > 0:
        success_rate = round((completed_count / total_enrollments) * 100, 1)
    
    context = {
        'enrollments': enrollments,
        'total_enrollments': total_enrollments,
        'active_enrollments': active_count,
        'completed_enrollments': completed_count,
        'pending_enrollments': pending_count,
        'success_rate': success_rate,
    }
    
    return render(request, 'core/enrollments.html', context)


@method_decorator(jwt_required, name='dispatch')
class RestrictionListView(AnalystAccessMixin, ProgramManagerAccessMixin, ListView):
    model = ServiceRestriction
    template_name = 'core/restrictions.html'
    context_object_name = 'restrictions'
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
        # First apply the ProgramManagerAccessMixin filtering
        queryset = super().get_queryset()
        
        # Apply additional filters
        restriction_type_filter = self.request.GET.get('restriction_type', '')
        scope_filter = self.request.GET.get('scope', '')
        status_filter = self.request.GET.get('status', '')
        bill_168_filter = self.request.GET.get('bill_168', '')
        no_trespass_filter = self.request.GET.get('no_trespass', '')
        search_query = self.request.GET.get('search', '').strip()
        
        if restriction_type_filter:
            queryset = queryset.filter(restriction_type=restriction_type_filter)
        
        if scope_filter:
            queryset = queryset.filter(scope=scope_filter)
        
        if bill_168_filter:
            if bill_168_filter == 'true':
                queryset = queryset.filter(is_bill_168=True)
            elif bill_168_filter == 'false':
                queryset = queryset.filter(is_bill_168=False)
        
        if no_trespass_filter:
            if no_trespass_filter == 'true':
                queryset = queryset.filter(is_no_trespass=True)
            elif no_trespass_filter == 'false':
                queryset = queryset.filter(is_no_trespass=False)
        
        if status_filter and status_filter != 'all':
            if status_filter == 'active':
                # Use the model's is_active method logic
                today = timezone.now().date()
                queryset = queryset.filter(
                    is_archived=False,
                    start_date__lte=today
                ).filter(
                    Q(is_indefinite=True) | 
                    Q(end_date__isnull=True) | 
                    Q(end_date__gte=today)
                )
            elif status_filter == 'expired':
                # Use the model's is_expired method logic
                today = timezone.now().date()
                queryset = queryset.filter(
                    is_archived=False,
                    is_indefinite=False,
                    end_date__isnull=False,
                    end_date__lt=today
                )
            elif status_filter == 'archived':
                queryset = queryset.filter(is_archived=True)
        
        if search_query:
            queryset = queryset.filter(
                Q(client__first_name__icontains=search_query) |
                Q(client__last_name__icontains=search_query) |
                Q(notes__icontains=search_query)
            )
        
        # Apply client search
        client_search_query = self.request.GET.get('client_search', '').strip()
        if client_search_query:
            queryset = queryset.filter(
                Q(client__first_name__icontains=client_search_query) |
                Q(client__last_name__icontains=client_search_query)
            )
        
        # Apply program search
        program_search_query = self.request.GET.get('program_search', '').strip()
        if program_search_query:
            queryset = queryset.filter(
                Q(program__name__icontains=program_search_query)
            )
        
        return queryset.select_related('client', 'program', 'program__department').order_by('-start_date')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        print(f"DEBUG: Context keys after super(): {list(context.keys())}")
        if 'restrictions' in context:
            print(f"DEBUG: Restrictions in context: {len(context['restrictions'])}")
        else:
            print("DEBUG: No 'restrictions' key in context!")
        
        # Get the total count of filtered restrictions (not just current page)
        total_filtered_count = self.get_queryset().count()
        
        # Get filtered restrictions for statistics (not paginated)
        # Use the same base queryset as the main queryset but without pagination
        base_queryset = super().get_queryset()
        
        # Apply the same filters as the main queryset but without search filters
        restriction_type_filter = self.request.GET.get('restriction_type', '')
        scope_filter = self.request.GET.get('scope', '')
        status_filter = self.request.GET.get('status', '')
        bill_168_filter = self.request.GET.get('bill_168', '')
        no_trespass_filter = self.request.GET.get('no_trespass', '')
        
        if restriction_type_filter:
            base_queryset = base_queryset.filter(restriction_type=restriction_type_filter)
        
        if scope_filter:
            base_queryset = base_queryset.filter(scope=scope_filter)
        
        if bill_168_filter:
            if bill_168_filter == 'true':
                base_queryset = base_queryset.filter(is_bill_168=True)
            elif bill_168_filter == 'false':
                base_queryset = base_queryset.filter(is_bill_168=False)
        
        if no_trespass_filter:
            if no_trespass_filter == 'true':
                base_queryset = base_queryset.filter(is_no_trespass=True)
            elif no_trespass_filter == 'false':
                base_queryset = base_queryset.filter(is_no_trespass=False)
        
        if status_filter:
            if status_filter == 'active':
                base_queryset = base_queryset.filter(end_date__isnull=True) | base_queryset.filter(end_date__gt=timezone.now().date())
            elif status_filter == 'expired':
                base_queryset = base_queryset.filter(end_date__lt=timezone.now().date())
        
        # Get all filtered restrictions for statistics
        all_restrictions = base_queryset.select_related(
            'client', 'program', 'program__department'
        )
        
        # Calculate statistics
        context['total_restrictions'] = all_restrictions.count()
        
        # Calculate active restrictions using the model's is_active method
        active_count = 0
        expired_count = 0
        archived_count = 0
        
        for restriction in all_restrictions:
            if restriction.is_archived:
                archived_count += 1
            elif restriction.is_expired():
                expired_count += 1
            elif restriction.is_active():
                active_count += 1
        
        context['active_restrictions'] = active_count
        context['expired_restrictions'] = expired_count
        context['archived_restrictions'] = archived_count
        context['org_restrictions'] = all_restrictions.filter(scope='org').count()
        context['program_restrictions'] = all_restrictions.filter(scope='program').count()
        context['total_filtered_count'] = total_filtered_count
        from django.utils import timezone as django_timezone
        context['today'] = django_timezone.now().date()
        
        # Add filter options to context
        context['restriction_type_choices'] = [
            ('', 'All Types'),
            ('bill_168', 'Bill 168 (Violence Against Staff)'),
            ('no_trespass', 'No Trespass Order'),
            ('behaviors', 'Behavioral Restrictions'),
        ]
        
        context['scope_choices'] = [
            ('', 'All Scopes'),
            ('org', 'Organization'),
            ('program', 'Program'),
        ]
        
        context['status_choices'] = [
            ('all', 'All'),
            ('active', 'Active'),
            ('expired', 'Expired'),
            ('archived', 'Archived'),
        ]
        
        # Add current filter values
        context['current_restriction_type'] = self.request.GET.get('restriction_type', '')
        context['current_scope'] = self.request.GET.get('scope', '')
        context['current_status'] = self.request.GET.get('status', 'all')
        context['current_bill_168'] = self.request.GET.get('bill_168', '')
        context['current_no_trespass'] = self.request.GET.get('no_trespass', '')
        context['current_search'] = self.request.GET.get('search', '')
        context['per_page'] = self.request.GET.get('per_page', '10')
        
        # Add search parameters
        context['client_search'] = self.request.GET.get('client_search', '')
        context['program_search'] = self.request.GET.get('program_search', '')
        
        # Override pagination context
        context['is_paginated'] = True  # Always show pagination controls
        context['per_page'] = str(self.get_paginate_by(self.get_queryset()))
        
        return context




@method_decorator(jwt_required, name='dispatch')
class AuditLogListView(ListView):
    """Audit log list view with pagination - SuperAdmin only"""
    model = AuditLog
    template_name = 'core/audit_log.html'
    context_object_name = 'audit_logs'
    paginate_by = 10  # Default: Show 10 audit logs per page
    
    def dispatch(self, request, *args, **kwargs):
        """Check if user has permission to view audit logs"""
        # Only SuperAdmin can view audit logs
        if not request.user.is_superuser:
            try:
                staff = request.user.staff_profile
                user_roles = staff.staffrole_set.select_related('role').all()
                role_names = [staff_role.role.name for staff_role in user_roles]
                
                if not any(role in ['SuperAdmin', 'Admin'] for role in role_names):
                    messages.error(request, 'You do not have permission to view audit logs.')
                    return redirect('dashboard')
            except:
                messages.error(request, 'You do not have permission to view audit logs.')
                return redirect('dashboard')
        
        return super().dispatch(request, *args, **kwargs)
    
    def get_paginate_by(self, queryset):
        """Get number of items to paginate by from request parameter"""
        per_page = self.request.GET.get('per_page', self.paginate_by)
        try:
            return int(per_page)
        except (ValueError, TypeError):
            return self.paginate_by
    
    def get_queryset(self):
        """Get audit logs ordered by most recent first"""
        return AuditLog.objects.select_related('changed_by').order_by('-changed_at')
    
    def get_context_data(self, **kwargs):
        """Add statistics to context"""
        context = super().get_context_data(**kwargs)
        
        # Get all audit logs for statistics (not just current page)
        all_audit_logs = AuditLog.objects.all()
        
        context['total_events'] = all_audit_logs.count()
        context['create_events'] = all_audit_logs.filter(action='create').count()
        context['update_events'] = all_audit_logs.filter(action='update').count()
        context['delete_events'] = all_audit_logs.filter(action='delete').count()
        
        # Add per_page to context for the template
        context['per_page'] = str(self.get_paginate_by(self.get_queryset()))
        
        return context


# Department CRUD Views
class DepartmentListView(AnalystAccessMixin, ListView):
    model = Department
    template_name = 'core/departments.html'
    context_object_name = 'departments'
    paginate_by = 10
    
    def get_queryset(self):
        return Department.objects.annotate(
            program_count=Count('program', distinct=True),
            staff_count=Count('program__programstaff__staff', distinct=True)
        ).order_by('name')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['total_departments'] = self.get_queryset().count()
        context['total_programs'] = Program.objects.count()
        context['total_staff'] = Staff.objects.count()
        return context


class DepartmentDetailView(AnalystAccessMixin, DetailView):
    model = Department
    template_name = 'core/department_detail.html'
    context_object_name = 'department'
    slug_field = 'external_id'
    slug_url_kwarg = 'external_id'


class DepartmentCreateView(AnalystAccessMixin, CreateView):
    model = Department
    template_name = 'core/department_form.html'
    fields = ['name', 'owner']
    success_url = reverse_lazy('core:departments')
    
    def form_valid(self, form):
        messages.success(self.request, 'Department created successfully.')
        return super().form_valid(form)


class DepartmentUpdateView(AnalystAccessMixin, UpdateView):
    model = Department
    template_name = 'core/department_form.html'
    fields = ['name', 'owner']
    slug_field = 'external_id'
    slug_url_kwarg = 'external_id'
    success_url = reverse_lazy('core:departments')
    
    def form_valid(self, form):
        messages.success(self.request, 'Department updated successfully.')
        return super().form_valid(form)


class DepartmentDeleteView(AnalystAccessMixin, DeleteView):
    model = Department
    template_name = 'core/department_confirm_delete.html'
    slug_field = 'external_id'
    slug_url_kwarg = 'external_id'
    success_url = reverse_lazy('core:departments')
    
    def delete(self, request, *args, **kwargs):
        messages.success(self.request, 'Department deleted successfully.')
        return super().delete(request, *args, **kwargs)


# Enrollment CRUD Views
@method_decorator(jwt_required, name='dispatch')
class EnrollmentListView(AnalystAccessMixin, ProgramManagerAccessMixin, ListView):
    model = ClientProgramEnrollment
    template_name = 'core/enrollments.html'
    context_object_name = 'enrollments'
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
        # First apply the ProgramManagerAccessMixin filtering
        queryset = super().get_queryset()
        
        # Apply additional filters
        department_filter = self.request.GET.get('department', '')
        status_filter = self.request.GET.get('status', '')
        client_search = self.request.GET.get('client_search', '').strip()
        program_search = self.request.GET.get('program_search', '').strip()
        
        # Handle department filter first
        if department_filter:
            queryset = queryset.filter(program__department__name=department_filter)
        
        # Handle status filtering
        if status_filter:
            if status_filter == 'active_only':
                # Show only non-archived enrollments
                queryset = queryset.filter(is_archived=False)
            elif status_filter == 'pending':
                # Show enrollments with status='pending' and not archived
                queryset = queryset.filter(status='pending', is_archived=False)
            elif status_filter == 'active':
                # Show enrollments with status='active' and not archived
                queryset = queryset.filter(status='active', is_archived=False)
            elif status_filter == 'completed':
                # Show enrollments with status='completed' and not archived
                queryset = queryset.filter(status='completed', is_archived=False)
            elif status_filter == 'future':
                # Show future enrollments (start date in future and not archived)
                from django.utils import timezone
                queryset = queryset.filter(start_date__gt=timezone.now().date(), is_archived=False)
            elif status_filter == 'archived':
                # Show only archived enrollments
                queryset = queryset.filter(is_archived=True)
        
        if client_search:
            queryset = queryset.filter(
                Q(client__first_name__icontains=client_search) |
                Q(client__last_name__icontains=client_search) |
                Q(client__preferred_name__icontains=client_search) |
                Q(client__alias__icontains=client_search)
            ).distinct()
        
        if program_search:
            queryset = queryset.filter(
                Q(program__name__icontains=program_search) |
                Q(program__department__name__icontains=program_search) |
                Q(program__location__icontains=program_search)
            ).distinct()
        
        return queryset.order_by('-start_date')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        enrollments = self.get_queryset()
        
        # Get the total count of filtered enrollments (not just current page)
        total_filtered_count = self.get_queryset().count()
        
        # Calculate statistics using date-based logic
        from django.utils import timezone
        today = timezone.now().date()
        
        total_enrollments = enrollments.count()
        active_count = 0
        completed_count = 0
        pending_count = 0
        
        for enrollment in enrollments:
            if today < enrollment.start_date:
                pending_count += 1
            elif enrollment.end_date:
                if today > enrollment.end_date:
                    completed_count += 1
                else:
                    active_count += 1
            else:
                active_count += 1
        
        context['total_enrollments'] = total_enrollments
        context['active_enrollments'] = active_count
        context['completed_enrollments'] = completed_count
        context['pending_enrollments'] = pending_count
        context['total_filtered_count'] = total_filtered_count
        
        # Calculate success rate
        success_rate = 0
        if total_enrollments > 0:
            success_rate = round((completed_count / total_enrollments) * 100, 1)
        context['success_rate'] = success_rate
        
        # Add filter options to context
        context['departments'] = Department.objects.all().order_by('name')
        context['status_choices'] = [
            ('', 'All Statuses'),
            ('pending', 'Pending'),
            ('active', 'Active'),
            ('completed', 'Completed'),
            ('future', 'Future Start'),
            ('archived', 'Archived'),
            ('active_only', 'All Non-Archived'),
        ]
        
        # Add current filter values
        context['current_department'] = self.request.GET.get('department', '')
        context['current_status'] = self.request.GET.get('status', '')
        context['client_search'] = self.request.GET.get('client_search', '')
        context['program_search'] = self.request.GET.get('program_search', '')
        context['per_page'] = self.request.GET.get('per_page', '10')
        
        # Force pagination to be enabled if there are any results
        if context.get('paginator') and context['paginator'].count > 0:
            context['is_paginated'] = True
        
        return context


@method_decorator(jwt_required, name='dispatch')
class EnrollmentDetailView(AnalystAccessMixin, ProgramManagerAccessMixin, DetailView):
    model = ClientProgramEnrollment
    template_name = 'core/enrollment_detail.html'
    context_object_name = 'enrollment'
    slug_field = 'external_id'
    slug_url_kwarg = 'external_id'


@method_decorator(jwt_required, name='dispatch')
class EnrollmentCreateView(AnalystAccessMixin, ProgramManagerAccessMixin, CreateView):
    model = ClientProgramEnrollment
    form_class = EnrollmentForm
    template_name = 'core/enrollment_form.html'
    success_url = reverse_lazy('core:enrollments')
    
    def dispatch(self, request, *args, **kwargs):
        """Check if user has permission to create enrollments"""
        if request.user.is_authenticated:
            try:
                staff = request.user.staff_profile
                user_roles = staff.staffrole_set.select_related('role').all()
                role_names = [staff_role.role.name for staff_role in user_roles]
                
                # Staff role users cannot create enrollments
                if 'Staff' in role_names and not any(role in ['SuperAdmin', 'Admin', 'Manager'] for role in role_names):
                    messages.error(request, 'You do not have permission to create enrollments. Contact your administrator.')
                    return redirect('core:enrollments')
            except Exception:
                pass
        
        return super().dispatch(request, *args, **kwargs)
    
    def post(self, request, *args, **kwargs):
        """Override post method to handle form validation"""
        form = self.get_form()
        
        if form.is_valid():
            return self.form_valid(form)
        else:
            return self.form_invalid(form)
    
    def form_valid(self, form):
        """Override form_valid to set created_by and add audit logging"""
        try:
            enrollment = form.save(commit=False)
            enrollment.created_by = self.request.user.get_full_name() or self.request.user.username
            enrollment.save()
            
            # Create audit log entry
            try:
                from .models import create_audit_log
                create_audit_log(
                    entity_name='Enrollment',
                    entity_id=enrollment.external_id,
                    action='create',
                    changed_by=self.request.user,
                    diff_data={
                        'client': str(enrollment.client),
                        'program': str(enrollment.program),
                        'start_date': str(enrollment.start_date),
                        'status': enrollment.status
                    }
                )
            except Exception as e:
                # Log error but don't break the enrollment creation
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Error creating audit log for enrollment: {e}")
            
            messages.success(self.request, 'Enrollment created successfully.')
            return super().form_valid(form)
            
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error in form_valid method: {e}")
            # Still call super to maintain normal behavior
            return super().form_valid(form)
    
    def get_form_kwargs(self):
        """Filter programs and clients to only assigned ones for Managers"""
        kwargs = super().get_form_kwargs()
        if self.request.user.is_authenticated:
            try:
                staff = self.request.user.staff_profile
                if staff.is_program_manager():
                    # Filter programs to only assigned ones
                    assigned_programs = staff.get_assigned_programs()
                    kwargs['program_queryset'] = assigned_programs
                elif staff.is_leader():
                    # Filter programs to only assigned ones via departments
                    assigned_departments = Department.objects.filter(
                        leader_assignments__staff=staff,
                        leader_assignments__is_active=True
                    ).distinct()
                    assigned_programs = Program.objects.filter(
                        department__in=assigned_departments
                    ).distinct()
                    kwargs['program_queryset'] = assigned_programs
                    
                    # For now, show all clients - program managers can enroll any client
                    # In the future, you might want to filter clients based on some criteria
                    kwargs['client_queryset'] = Client.objects.all()
            except Exception:
                pass
        return kwargs
    
    def form_invalid(self, form):
        """Handle form validation errors"""
        print("=== ENROLLMENT FORM_INVALID CALLED ===")
        print(f"Form errors: {form.errors}")
        
        # Add error messages to the form
        for field, errors in form.errors.items():
            for error in errors:
                if field == '__all__':
                    messages.error(self.request, str(error))
                else:
                    messages.error(self.request, f"{field}: {error}")
        
        # Get context data without calling the problematic parent method
        context = {
            'form': form,
            'view': self,
        }
        
        # Add program manager context if needed
        if self.request.user.is_authenticated:
            try:
                staff = self.request.user.staff_profile
                if staff.is_program_manager():
                    context['assigned_programs'] = staff.get_assigned_programs()
                    context['is_program_manager'] = True
            except Exception:
                pass
        
        # Return the form with errors
        return self.render_to_response(context)


@method_decorator(jwt_required, name='dispatch')
class EnrollmentUpdateView(AnalystAccessMixin, ProgramManagerAccessMixin, UpdateView):
    model = ClientProgramEnrollment
    form_class = EnrollmentForm
    template_name = 'core/enrollment_form.html'
    slug_field = 'external_id'
    slug_url_kwarg = 'external_id'
    success_url = reverse_lazy('core:enrollments')
    
    def dispatch(self, request, *args, **kwargs):
        """Check if user has permission to edit enrollments"""
        if request.user.is_authenticated:
            try:
                staff = request.user.staff_profile
                user_roles = staff.staffrole_set.select_related('role').all()
                role_names = [staff_role.role.name for staff_role in user_roles]
                
                # Staff role users cannot edit enrollments
                if 'Staff' in role_names and not any(role in ['SuperAdmin', 'Admin', 'Manager'] for role in role_names):
                    messages.error(request, 'You do not have permission to edit enrollments. Contact your administrator.')
                    return redirect('core:enrollments')
            except Exception:
                pass
        
        return super().dispatch(request, *args, **kwargs)
    
    def get_form_kwargs(self):
        """Filter programs and clients to only assigned ones for Managers"""
        kwargs = super().get_form_kwargs()
        if self.request.user.is_authenticated:
            try:
                staff = self.request.user.staff_profile
                if staff.is_program_manager():
                    # Filter programs to only assigned ones
                    assigned_programs = staff.get_assigned_programs()
                    kwargs['program_queryset'] = assigned_programs
                elif staff.is_leader():
                    # Filter programs to only assigned ones via departments
                    assigned_departments = Department.objects.filter(
                        leader_assignments__staff=staff,
                        leader_assignments__is_active=True
                    ).distinct()
                    assigned_programs = Program.objects.filter(
                        department__in=assigned_departments
                    ).distinct()
                    kwargs['program_queryset'] = assigned_programs
                    
                    # For now, show all clients - program managers can enroll any client
                    # In the future, you might want to filter clients based on some criteria
                    kwargs['client_queryset'] = Client.objects.all()
            except Exception:
                pass
        return kwargs
    
    def get_context_data(self, **kwargs):
        """Add client and program data for edit mode"""
        context = super().get_context_data(**kwargs)
        if self.object:
            # Add client data for JavaScript
            context['client_data'] = json.dumps({
                'id': self.object.client.id,
                'external_id': str(self.object.client.external_id),
                'name': f"{self.object.client.first_name} {self.object.client.last_name}",
                'first_name': self.object.client.first_name,
                'last_name': self.object.client.last_name,
            })
            # Add program data for JavaScript
            context['program_data'] = json.dumps({
                'id': self.object.program.id,
                'external_id': str(self.object.program.external_id),
                'name': self.object.program.name,
                'department': self.object.program.department.name,
                'location': self.object.program.location,
                'capacity': self.object.program.capacity_current,
                'description': self.object.program.description or '',
            })
        return context
    
    def form_valid(self, form):
        """Set the updated_by field before saving and add audit logging"""
        enrollment = form.save(commit=False)
        enrollment.updated_by = self.request.user.get_full_name() or self.request.user.username
        enrollment.save()
        
        # Create audit log entry
        from .models import create_audit_log
        create_audit_log(
            entity_name='Enrollment',
            entity_id=enrollment.external_id,
            action='update',
            changed_by=self.request.user,
            diff_data={
                'client': str(enrollment.client),
                'program': str(enrollment.program),
                'start_date': str(enrollment.start_date),
                'end_date': str(enrollment.end_date) if enrollment.end_date else None,
                'status': enrollment.status
            }
        )
        
        messages.success(self.request, 'Enrollment updated successfully.')
        return redirect(self.success_url)


@method_decorator(jwt_required, name='dispatch')
class EnrollmentDeleteView(AnalystAccessMixin, ProgramManagerAccessMixin, DeleteView):
    model = ClientProgramEnrollment
    template_name = 'core/enrollment_confirm_delete.html'
    slug_field = 'external_id'
    slug_url_kwarg = 'external_id'
    success_url = reverse_lazy('core:enrollments')
    
    def dispatch(self, request, *args, **kwargs):
        """Check if user has permission to archive enrollments"""
        if request.user.is_authenticated:
            try:
                staff = request.user.staff_profile
                user_roles = staff.staffrole_set.select_related('role').all()
                role_names = [staff_role.role.name for staff_role in user_roles]
                
                # Staff role users cannot archive enrollments
                if 'Staff' in role_names and not any(role in ['SuperAdmin', 'Admin', 'Manager'] for role in role_names):
                    messages.error(request, 'You do not have permission to archive enrollments. Contact your administrator.')
                    return redirect('core:enrollments')
            except Exception:
                pass
        
        return super().dispatch(request, *args, **kwargs)
    
    def get_context_data(self, **kwargs):
        """Add enrollment object to context"""
        context = super().get_context_data(**kwargs)
        context['enrollment'] = self.get_object()
        return context
    
    def form_valid(self, form):
        """Override to archive enrollment instead of deleting"""
        try:
            print(f"Form valid method called for enrollment archiving")
            print(f"Request method: {self.request.method}")
            print(f"Request POST data: {self.request.POST}")
            
            # Get the enrollment object first
            enrollment = self.get_object()
            print(f"Found enrollment: {enrollment.client.first_name} {enrollment.client.last_name}")
            
            client_name = f"{enrollment.client.first_name} {enrollment.client.last_name}"
            program_name = enrollment.program.name
            
            # Archive the enrollment instead of deleting
            enrollment.is_archived = True
            enrollment.status = 'archived'
            enrollment.updated_by = self.request.user.get_full_name() or self.request.user.username
            enrollment.save()
            
            print(f"Enrollment archived successfully: {client_name} - {program_name}")
            print(f"is_archived: {enrollment.is_archived}, status: {enrollment.status}")
            
            # Create audit log entry for archiving
            from .models import create_audit_log
            create_audit_log(
                entity_name='Enrollment',
                entity_id=enrollment.external_id,
                action='update',
                changed_by=self.request.user,
                diff_data={
                    'client': str(enrollment.client),
                    'program': str(enrollment.program),
                    'start_date': str(enrollment.start_date),
                    'end_date': str(enrollment.end_date) if enrollment.end_date else None,
                    'status': 'archived',
                    'is_archived': True
                }
            )
            
            print(f"Archived enrollment: {client_name} - {program_name}")
            
            messages.success(
                self.request, 
                f'Enrollment for {client_name} in {program_name} has been archived successfully.'
            )
            return redirect(self.success_url)
            
        except Exception as e:
            print(f"Error archiving enrollment: {str(e)}")
            messages.error(self.request, f'Error archiving enrollment: {str(e)}')
            return redirect(self.success_url)


@csrf_exempt
@require_http_methods(["POST"])
def check_program_capacity(request):
    """API endpoint to check program capacity for a specific date"""
    try:
        data = json.loads(request.body)
        program_id = data.get('program_id')
        start_date_str = data.get('start_date')
        
        if not program_id or not start_date_str:
            return JsonResponse({
                'success': False,
                'error': 'Program ID and start date are required'
            }, status=400)
        
        # Parse the date
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        except ValueError:
            return JsonResponse({
                'success': False,
                'error': 'Invalid date format. Use YYYY-MM-DD'
            }, status=400)
        
        # Get the program
        try:
            program = Program.objects.get(id=program_id)
        except Program.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'Program not found'
            }, status=404)
        
        # Get capacity information for the specific date
        enrollments_on_date = program.get_enrollments_count_for_date(start_date)
        available_capacity = program.get_available_capacity(start_date)
        is_at_capacity = program.is_at_capacity(start_date)
        capacity_percentage = program.get_capacity_percentage(start_date)
        
        return JsonResponse({
            'success': True,
            'program_name': program.name,
            'capacity': program.capacity_current,
            'enrollments_on_date': enrollments_on_date,
            'available_capacity': available_capacity,
            'is_at_capacity': is_at_capacity,
            'capacity_percentage': round(capacity_percentage, 1),
            'start_date_formatted': start_date.strftime('%B %d, %Y')
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON data'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Server error: {str(e)}'
        }, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def search_clients(request):
    """Search clients by name via AJAX with priority ordering"""
    try:
        query = request.GET.get('q', '').strip()
        
        if not query:
            # If no query, return all clients (limit to 20 for performance)
            clients = Client.objects.all()[:20]
        else:
            # First get clients that start with the query (highest priority)
            starts_with_clients = Client.objects.filter(
                Q(first_name__istartswith=query) |
                Q(last_name__istartswith=query)
            )
            
            # Then get clients that contain the query anywhere (lower priority)
            contains_clients = Client.objects.filter(
                Q(first_name__icontains=query) |
                Q(last_name__icontains=query)
            ).exclude(
                Q(first_name__istartswith=query) |
                Q(last_name__istartswith=query)
            )
            
            # Combine and limit results
            clients = list(starts_with_clients) + list(contains_clients)
            clients = clients[:50]  # Limit to 50 results for performance
        
        # Format results for the frontend
        results = []
        for client in clients:
            results.append({
                'id': client.id,
                'external_id': str(client.external_id),
                'client_id': client.client_id,  # Add the actual client_id field
                'name': f"{client.first_name} {client.last_name}",
                'first_name': client.first_name,
                'last_name': client.last_name,
                'date_of_birth': client.dob.strftime('%Y-%m-%d') if client.dob else None,
                'display_text': f"{client.first_name} {client.last_name} ({client.dob.strftime('%m/%d/%Y') if client.dob else 'No DOB'})"
            })
        
        return JsonResponse({
            'success': True,
            'clients': results,
            'count': len(results)
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Error searching clients: {str(e)}'
        }, status=500)


# Service Restriction CRUD Views
# Note: RestrictionListView is defined earlier in the file (line 255) with full pagination support


class RestrictionDetailView(AnalystAccessMixin, ProgramManagerAccessMixin, DetailView):
    model = ServiceRestriction
    template_name = 'core/restriction_detail.html'
    context_object_name = 'restriction'
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
            return redirect(f"{reverse('core:permission_error')}?type=restriction_not_found&resource=restriction")
        
        # Check if user has access to this restriction
        if not request.user.is_superuser:
            try:
                staff = request.user.staff_profile
                user_roles = staff.staffrole_set.select_related('role').all()
                role_names = [staff_role.role.name for staff_role in user_roles]
                
                if staff.is_program_manager():
                    # Managers can view ALL restrictions (no access restriction for viewing)
                    pass
                
                elif 'Staff' in role_names and not any(role in ['SuperAdmin', 'Admin', 'Manager', 'Leader'] for role in role_names):
                    # Staff users can view all restrictions (no additional filtering needed)
                    pass
                
                elif staff.is_leader():
                    # Leaders can view ALL restrictions (like Staff users)
                    # They can only edit restrictions for their assigned clients
                    pass
                        
            except Exception:
                from django.shortcuts import redirect
                from django.urls import reverse
                return redirect(f"{reverse('core:permission_error')}?type=access_denied&resource=restriction")
        
        # If we get here, user has access, proceed with normal rendering
        context = self.get_context_data(object=self.object)
        return self.render_to_response(context)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        restriction = self.get_object()
        
        # Check if user can edit this restriction
        can_edit = False
        if self.request.user.is_authenticated:
            try:
                staff = self.request.user.staff_profile
                if staff.is_program_manager():
                    # Managers can edit restrictions for their assigned clients
                    assigned_programs = staff.get_assigned_programs()
                    assigned_clients = Client.objects.filter(
                        clientprogramenrollment__program__in=assigned_programs
                    ).distinct()
                    can_edit = restriction.client in assigned_clients
                elif staff.is_leader():
                    # Leaders can edit restrictions for their assigned clients
                    assigned_departments = Department.objects.filter(
                        leader_assignments__staff=staff,
                        leader_assignments__is_active=True
                    ).distinct()
                    assigned_programs = Program.objects.filter(
                        department__in=assigned_departments
                    ).distinct()
                    assigned_clients = Client.objects.filter(
                        clientprogramenrollment__program__in=assigned_programs
                    ).distinct()
                    can_edit = restriction.client in assigned_clients
                elif staff.is_staff_only():
                    # Staff users can view all restrictions but cannot edit them
                    can_edit = False
                elif self.request.user.is_superuser:
                    # SuperAdmin can edit all restrictions
                    can_edit = True
            except Exception:
                pass
        
        context['can_edit_restriction'] = can_edit
        return context


class RestrictionCreateView(AnalystAccessMixin, ProgramManagerAccessMixin, CreateView):
    model = ServiceRestriction
    template_name = 'core/restriction_form.html'
    form_class = ServiceRestrictionForm
    success_url = reverse_lazy('core:restrictions')
    
    def dispatch(self, request, *args, **kwargs):
        """Check if user has permission to create restrictions"""
        if request.user.is_authenticated:
            try:
                staff = request.user.staff_profile
                user_roles = staff.staffrole_set.select_related('role').all()
                role_names = [staff_role.role.name for staff_role in user_roles]
                
                # Staff role users cannot create restrictions
                if 'Staff' in role_names and not any(role in ['SuperAdmin', 'Admin', 'Manager'] for role in role_names):
                    messages.error(request, 'You do not have permission to create restrictions. Contact your administrator.')
                    return redirect('core:restrictions')
            except Exception:
                pass
        
        return super().dispatch(request, *args, **kwargs)
    
    def get_form_kwargs(self):
        """Filter programs to only assigned ones for Managers"""
        kwargs = super().get_form_kwargs()
        if self.request.user.is_authenticated:
            try:
                staff = self.request.user.staff_profile
                if staff.is_program_manager():
                    # Filter programs to only assigned ones
                    assigned_programs = staff.get_assigned_programs()
                    kwargs['program_queryset'] = assigned_programs
                elif staff.is_leader():
                    # Filter programs to only assigned ones via departments
                    assigned_departments = Department.objects.filter(
                        leader_assignments__staff=staff,
                        leader_assignments__is_active=True
                    ).distinct()
                    assigned_programs = Program.objects.filter(
                        department__in=assigned_departments
                    ).distinct()
                    kwargs['program_queryset'] = assigned_programs
            except Exception:
                pass
        return kwargs
    
    def form_valid(self, form):
        try:
            # Set the created_by and updated_by fields before saving
            restriction = form.save(commit=False)
            user_name = self.request.user.get_full_name() or self.request.user.username
            restriction.created_by = user_name
            restriction.updated_by = user_name
            restriction.save()
            
            # Create audit log entry for restriction creation
            try:
                from .models import create_audit_log
                create_audit_log(
                    entity_name='Restriction',
                    entity_id=restriction.external_id,
                    action='create',
                    changed_by=self.request.user,
                    diff_data={
                        'client': str(restriction.client),
                        'scope': restriction.scope,
                        'program': str(restriction.program) if restriction.program else None,
                        'restriction_type': restriction.restriction_type,
                        'is_bill_168': restriction.is_bill_168,
                        'is_no_trespass': restriction.is_no_trespass,
                        'start_date': str(restriction.start_date),
                        'end_date': str(restriction.end_date) if restriction.end_date else None,
                        'is_indefinite': restriction.is_indefinite,
                        'behaviors': restriction.behaviors,
                        'notes': restriction.notes or '',
                        'created_by': restriction.created_by
                    }
                )
            except Exception as e:
                print(f"Error creating audit log for restriction: {e}")
            
            create_success(self.request, 'Service restriction')
            return redirect(self.success_url)
        except Exception as e:
            print(f"Error saving form: {e}")
            messages.error(self.request, f'Error creating restriction: {e}')
            return self.form_invalid(form)
    
    def form_invalid(self, form):
        print("RestrictionCreateView.form_invalid called")
        print(f"Form is valid: {form.is_valid()}")
        print(f"Form errors: {form.errors}")
        print(f"Form non_field_errors: {form.non_field_errors()}")
        for field_name, errors in form.errors.items():
            print(f"Field '{field_name}' errors: {errors}")
        return super().form_invalid(form)


class RestrictionUpdateView(AnalystAccessMixin, ProgramManagerAccessMixin, UpdateView):
    model = ServiceRestriction
    template_name = 'core/restriction_form.html'
    form_class = ServiceRestrictionForm
    slug_field = 'external_id'
    slug_url_kwarg = 'external_id'
    success_url = reverse_lazy('core:restrictions')
    
    def dispatch(self, request, *args, **kwargs):
        """Check if user has permission to edit restrictions"""
        if request.user.is_authenticated:
            try:
                staff = request.user.staff_profile
                user_roles = staff.staffrole_set.select_related('role').all()
                role_names = [staff_role.role.name for staff_role in user_roles]
                
                # Staff role users cannot edit restrictions
                if 'Staff' in role_names and not any(role in ['SuperAdmin', 'Manager', 'Leader'] for role in role_names):
                    messages.error(request, 'You do not have permission to edit restrictions. Contact your administrator.')
                    return redirect('core:restrictions')
            except Exception:
                pass
        
        return super().dispatch(request, *args, **kwargs)
    
    def get_form_kwargs(self):
        """Filter programs to only assigned ones for Managers"""
        kwargs = super().get_form_kwargs()
        if self.request.user.is_authenticated:
            try:
                staff = self.request.user.staff_profile
                if staff.is_program_manager():
                    # Filter programs to only assigned ones
                    assigned_programs = staff.get_assigned_programs()
                    kwargs['program_queryset'] = assigned_programs
                elif staff.is_leader():
                    # Filter programs to only assigned ones via departments
                    assigned_departments = Department.objects.filter(
                        leader_assignments__staff=staff,
                        leader_assignments__is_active=True
                    ).distinct()
                    assigned_programs = Program.objects.filter(
                        department__in=assigned_departments
                    ).distinct()
                    kwargs['program_queryset'] = assigned_programs
            except Exception:
                pass
        return kwargs
    
    def form_valid(self, form):
        """Handle restriction updates with audit logging"""
        # Get the original restriction data before saving
        original_restriction = self.get_object()
        
        # Set the updated_by field before saving
        restriction = form.save(commit=False)
        user_name = self.request.user.get_full_name() or self.request.user.username
        restriction.updated_by = user_name
        restriction.save()
        
        # Create audit log entry for restriction update
        try:
            from .models import create_audit_log
            
            # Compare original and updated values to detect changes
            changes = {}
            
            # Check each field for changes
            if original_restriction.scope != restriction.scope:
                changes['scope'] = f"{original_restriction.scope} → {restriction.scope}"
            
            if original_restriction.program != restriction.program:
                changes['program'] = f"{str(original_restriction.program) if original_restriction.program else 'None'} → {str(restriction.program) if restriction.program else 'None'}"
            
            if original_restriction.restriction_type != restriction.restriction_type:
                changes['restriction_type'] = f"{original_restriction.restriction_type} → {restriction.restriction_type}"
            
            if original_restriction.is_bill_168 != restriction.is_bill_168:
                changes['is_bill_168'] = f"{original_restriction.is_bill_168} → {restriction.is_bill_168}"
            
            if original_restriction.is_no_trespass != restriction.is_no_trespass:
                changes['is_no_trespass'] = f"{original_restriction.is_no_trespass} → {restriction.is_no_trespass}"
            
            if original_restriction.start_date != restriction.start_date:
                changes['start_date'] = f"{original_restriction.start_date} → {restriction.start_date}"
            
            if original_restriction.end_date != restriction.end_date:
                changes['end_date'] = f"{original_restriction.end_date} → {restriction.end_date}"
            
            if original_restriction.is_indefinite != restriction.is_indefinite:
                changes['is_indefinite'] = f"{original_restriction.is_indefinite} → {restriction.is_indefinite}"
            
            if original_restriction.behaviors != restriction.behaviors:
                changes['behaviors'] = f"{original_restriction.behaviors} → {restriction.behaviors}"
            
            if original_restriction.notes != restriction.notes:
                changes['notes'] = f"{original_restriction.notes or ''} → {restriction.notes or ''}"
            
            # Only create audit log if there were changes
            if changes:
                create_audit_log(
                    entity_name='Restriction',
                    entity_id=restriction.external_id,
                    action='update',
                    changed_by=self.request.user,
                    diff_data=changes
                )
        except Exception as e:
            print(f"Error creating audit log for restriction update: {e}")
        
        update_success(self.request, 'Service restriction')
        return redirect(self.success_url)
    
    def get_context_data(self, **kwargs):
        """Add client data for pre-population in edit mode"""
        context = super().get_context_data(**kwargs)
        if self.object:
            # Add client data for JavaScript pre-population
            context['client_data'] = json.dumps({
                'id': self.object.client.id,
                'external_id': str(self.object.client.external_id),
                'name': f"{self.object.client.first_name} {self.object.client.last_name}",
                'first_name': self.object.client.first_name,
                'last_name': self.object.client.last_name,
            })
        return context


class RestrictionDeleteView(AnalystAccessMixin, ProgramManagerAccessMixin, DeleteView):
    model = ServiceRestriction
    template_name = 'core/restriction_confirm_delete.html'
    slug_field = 'external_id'
    slug_url_kwarg = 'external_id'
    success_url = reverse_lazy('core:restrictions')
    
    def dispatch(self, request, *args, **kwargs):
        """Check if user has permission to archive restrictions"""
        if request.user.is_authenticated:
            try:
                staff = request.user.staff_profile
                user_roles = staff.staffrole_set.select_related('role').all()
                role_names = [staff_role.role.name for staff_role in user_roles]
                
                # Staff role users cannot archive restrictions
                if 'Staff' in role_names and not any(role in ['SuperAdmin', 'Manager', 'Leader'] for role in role_names):
                    messages.error(request, 'You do not have permission to archive restrictions. Contact your administrator.')
                    return redirect('core:restrictions')
            except Exception:
                pass
        
        return super().dispatch(request, *args, **kwargs)
    
    def get_context_data(self, **kwargs):
        """Add restriction object to context"""
        context = super().get_context_data(**kwargs)
        context['restriction'] = self.get_object()
        return context
    
    def form_valid(self, form):
        """Handle restriction archiving with audit logging"""
        print("RestrictionDeleteView.form_valid called")
        
        # Get the restriction object first
        restriction = self.get_object()
        print(f"Restriction to archive: {restriction}")
        
        # Check confirmation text
        confirmation = self.request.POST.get('confirmation_text', '').strip().upper()
        if confirmation != 'ARCHIVE':
            messages.error(self.request, 'Please type "ARCHIVE" to confirm archiving.')
            return redirect('core:restrictions_detail', external_id=restriction.external_id)
        
        client_name = f"{restriction.client.first_name} {restriction.client.last_name}"
        restriction_type = restriction.get_restriction_type_display()
        
        # Create audit log entry before archiving
        print("Creating audit log for restriction archiving...")
        try:
            from .models import create_audit_log
            create_audit_log(
                entity_name='Restriction',
                entity_id=restriction.external_id,
                action='archive',
                changed_by=self.request.user,
                diff_data={
                    'client': str(restriction.client),
                    'scope': restriction.scope,
                    'program': str(restriction.program) if restriction.program else None,
                    'restriction_type': restriction.restriction_type,
                    'start_date': str(restriction.start_date),
                    'end_date': str(restriction.end_date) if restriction.end_date else None,
                    'is_indefinite': restriction.is_indefinite,
                    'behaviors': restriction.behaviors,
                    'notes': restriction.notes or '',
                    'is_archived': f"{restriction.is_archived} → True",
                    'archived_by': f"{self.request.user.first_name} {self.request.user.last_name}".strip() or self.request.user.username
                }
            )
            print("Audit log created for restriction archiving")
        except Exception as e:
            print(f"Error creating audit log for restriction archiving: {e}")
        
        # Archive the restriction instead of deleting
        print("Archiving restriction...")
        restriction.is_archived = True
        restriction.updated_by = f"{self.request.user.first_name} {self.request.user.last_name}".strip() or self.request.user.username
        restriction.save()
        print("Restriction archived successfully")
        
        messages.success(self.request, f'Service restriction for {client_name} has been archived successfully.')
        return redirect(self.success_url)


@csrf_exempt
@require_http_methods(["POST"])
def bulk_delete_restrictions(request):
    """Bulk archive service restrictions"""
    # Check if user is authenticated
    if not request.user.is_authenticated:
        return JsonResponse({
            'success': False,
            'error': 'Authentication required'
        }, status=401)
    
    try:
        data = json.loads(request.body)
        restriction_ids = data.get('restriction_ids', [])
        
        if not restriction_ids:
            return JsonResponse({
                'success': False,
                'error': 'No restrictions selected for archiving'
            }, status=400)
        
        # Get the restrictions to archive
        restrictions_to_archive = ServiceRestriction.objects.filter(id__in=restriction_ids)
        archived_count = restrictions_to_archive.count()
        
        if archived_count == 0:
            return JsonResponse({
                'success': False,
                'error': 'No restrictions found with the provided IDs'
            }, status=404)
        
        # Archive the restrictions instead of deleting
        updated_by = f"{request.user.first_name} {request.user.last_name}".strip() or request.user.username
        restrictions_to_archive.update(is_archived=True, updated_by=updated_by)
        
        return JsonResponse({
            'success': True,
            'archived_count': archived_count,
            'message': f'Successfully archived {archived_count} restriction(s)'
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON data'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Error archiving restrictions: {str(e)}'
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def bulk_delete_enrollments(request):
    """Bulk delete client program enrollments"""
    # Check if user is authenticated
    if not request.user.is_authenticated:
        return JsonResponse({
            'success': False,
            'error': 'Authentication required'
        }, status=401)
    
    try:
        data = json.loads(request.body)
        enrollment_ids = data.get('enrollment_ids', [])
        
        if not enrollment_ids:
            return JsonResponse({
                'success': False,
                'error': 'No enrollments selected for deletion'
            }, status=400)
        
        # Get the enrollments to delete
        enrollments_to_delete = ClientProgramEnrollment.objects.filter(id__in=enrollment_ids)
        deleted_count = enrollments_to_delete.count()
        
        if deleted_count == 0:
            return JsonResponse({
                'success': False,
                'error': 'No enrollments found with the provided IDs'
            }, status=404)
        
        # Archive the enrollments instead of deleting
        from .models import create_audit_log
        for enrollment in enrollments_to_delete:
            # Archive the enrollment
            enrollment.is_archived = True
            enrollment.status = 'archived'
            enrollment.updated_by = request.user.get_full_name() or request.user.username
            enrollment.save()
            
            # Create audit log entry for archiving
            create_audit_log(
                entity_name='Enrollment',
                entity_id=enrollment.external_id,
                action='update',
                changed_by=request.user,
                diff_data={
                    'client': str(enrollment.client),
                    'program': str(enrollment.program),
                    'start_date': str(enrollment.start_date),
                    'end_date': str(enrollment.end_date) if enrollment.end_date else None,
                    'status': 'archived',
                    'is_archived': True
                }
            )
        
        return JsonResponse({
            'success': True,
            'deleted_count': deleted_count,
            'message': f'Successfully archived {deleted_count} enrollment(s)'
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON data'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Error deleting enrollments: {str(e)}'
        }, status=500)


@jwt_required
def profile(request):
    """User profile view"""
    try:
        staff_profile = request.user.staff_profile
    except Staff.DoesNotExist:
        staff_profile = None

    context = {
        'user': request.user,
        'staff_profile': staff_profile,
    }
    
    return render(request, 'core/profile.html', context)


@jwt_required
def edit_profile(request):
    """Edit user profile view"""
    try:
        staff_profile = request.user.staff_profile
    except Staff.DoesNotExist:
        # Create a staff profile if it doesn't exist
        staff_profile = Staff.objects.create(
            user=request.user,
            first_name=request.user.first_name,
            last_name=request.user.last_name,
        )

    if request.method == 'POST':
        user_form = UserProfileForm(request.POST, request.FILES, instance=request.user)
        staff_form = StaffProfileForm(request.POST, instance=staff_profile)
        
        if user_form.is_valid() and staff_form.is_valid():
            user = user_form.save()
            staff = staff_form.save(commit=False)
            
            # Update staff name fields from user
            staff.first_name = user.first_name
            staff.last_name = user.last_name
            staff.save()
            
            messages.success(request, 'Profile updated successfully!')
            return redirect('core:profile')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        user_form = UserProfileForm(instance=request.user)
        staff_form = StaffProfileForm(instance=staff_profile)

    context = {
        'user_form': user_form,
        'staff_form': staff_form,
        'user': request.user,
        'staff_profile': staff_profile,
    }
    
    return render(request, 'core/edit_profile.html', context)


@jwt_required
def test_messages(request):
    """Test page for message system"""
    return render(request, 'test_messages.html')


@jwt_required
def test_success(request):
    """Test success message"""
    success_message(request, "This is a test success message!")
    return redirect('core:test_messages')


@jwt_required
def test_error(request):
    """Test error message"""
    error_message(request, "This is a test error message!")
    return redirect('core:test_messages')


@jwt_required
def test_warning(request):
    """Test warning message"""
    warning_message(request, "This is a test warning message!")
    return redirect('core:test_messages')


@jwt_required
def test_info(request):
    """Test info message"""
    info_message(request, "This is a test info message!")
    return redirect('core:test_messages')


@jwt_required
def test_create_success(request):
    """Test create success message"""
    create_success(request, 'Test Entity', 'Sample Item')
    return redirect('core:test_messages')


@jwt_required
def test_update_success(request):
    """Test update success message"""
    update_success(request, 'Test Entity', 'Sample Item')
    return redirect('core:test_messages')


@jwt_required
def test_delete_success(request):
    """Test delete success message"""
    delete_success(request, 'Test Entity', 'Sample Item')
    return redirect('core:test_messages')


@jwt_required
def test_validation_error(request):
    """Test validation error message"""
    validation_error(request, "This field is required.")
    return redirect('core:test_messages')


@jwt_required
def test_permission_error(request):
    """Test permission error message"""
    permission_error(request, "delete this item")
    return redirect('core:test_messages')


@jwt_required
def test_not_found_error(request):
    """Test not found error message"""
    not_found_error(request, 'Test Entity')
    return redirect('core:test_messages')


@jwt_required
def test_bulk_operation_success(request):
    """Test bulk operation success message"""
    from .message_utils import bulk_operation_success
    bulk_operation_success(request, 'Client', 5, 'processed')
    return redirect('core:test_messages')


@jwt_required
def test_bulk_operation_error(request):
    """Test bulk operation error message"""
    from .message_utils import bulk_operation_error
    bulk_operation_error(request, 'Client', ['Invalid email', 'Missing phone'])
    return redirect('core:test_messages')


@jwt_required
def change_password(request):
    """Change password view"""
    if request.method == 'POST':
        form = PasswordChangeForm(request.user, request.POST)
        
        if form.is_valid():
            new_password = form.cleaned_data['new_password']
            request.user.set_password(new_password)
            request.user.save()
            
            messages.success(request, 'Password changed successfully! Please log in again with your new password.')
            return redirect('home')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = PasswordChangeForm(request.user)

    context = {
        'form': form,
    }
    
    return render(request, 'core/change_password.html', context)




@csrf_exempt
@require_http_methods(["GET"])
def search_programs(request):
    """AJAX endpoint for searching programs with priority ordering"""
    if request.method == 'GET':
        search_term = request.GET.get('q', '').strip()
        
        if not search_term:
            # If no query, return all active programs (limit to 20 for performance)
            queryset = Program.objects.filter(status='active')
            
            # Apply program manager filtering for empty search too
            if request.user.is_authenticated and not request.user.is_superuser:
                try:
                    staff = request.user.staff_profile
                    if staff.is_program_manager():
                        assigned_programs = staff.get_assigned_programs()
                        queryset = queryset.filter(id__in=assigned_programs.values_list('id', flat=True))
                except:
                    pass
            
            programs = queryset[:20]
            programs_data = []
            for program in programs:
                programs_data.append({
                    'id': program.id,
                    'external_id': str(program.external_id),
                    'name': program.name,
                    'department': program.department.name,
                    'location': program.location,
                    'capacity': program.capacity_current,
                    'description': program.description or '',
                })
            return JsonResponse({'success': True, 'programs': programs_data})
        
        # Filter programs based on user's access level
        queryset = Program.objects.filter(status='active')
        
        # Apply program manager filtering
        if request.user.is_authenticated and not request.user.is_superuser:
            try:
                staff = request.user.staff_profile
                if staff.is_program_manager():
                    assigned_programs = staff.get_assigned_programs()
                    queryset = queryset.filter(id__in=assigned_programs.values_list('id', flat=True))
            except:
                pass
        
        # First get programs that start with the search term (highest priority)
        starts_with_programs = queryset.filter(
            Q(name__istartswith=search_term) |
            Q(department__name__istartswith=search_term) |
            Q(location__istartswith=search_term)
        ).select_related('department')
        
        # Then get programs that contain the search term anywhere (lower priority)
        contains_programs = queryset.filter(
            Q(name__icontains=search_term) |
            Q(department__name__icontains=search_term) |
            Q(location__icontains=search_term) |
            Q(description__icontains=search_term)
        ).exclude(
            Q(name__istartswith=search_term) |
            Q(department__name__istartswith=search_term) |
            Q(location__istartswith=search_term)
        ).select_related('department')
        
        # Combine and limit results
        programs = list(starts_with_programs) + list(contains_programs)
        programs = programs[:20]  # Limit to 20 results
        
        programs_data = []
        for program in programs:
            programs_data.append({
                'id': program.id,
                'external_id': str(program.external_id),
                'name': program.name,
                'department': program.department.name,
                'location': program.location,
                'capacity': program.capacity_current,
                'description': program.description or '',
            })
        
        return JsonResponse({'success': True, 'programs': programs_data})
    
    return JsonResponse({'error': 'Invalid request method'}, status=405)


@method_decorator(jwt_required, name='dispatch')
class EnrollmentCSVExportView(AnalystAccessMixin, ProgramManagerAccessMixin, ListView):
    """Export enrollments to CSV with filtering support"""
    model = ClientProgramEnrollment
    template_name = 'core/enrollments.html'
    
    def get_queryset(self):
        # Use the same filtering logic as EnrollmentListView
        queryset = super().get_queryset()
        
        # Apply additional filters
        department_filter = self.request.GET.get('department', '')
        status_filter = self.request.GET.get('status', '')
        client_search = self.request.GET.get('client_search', '').strip()
        program_search = self.request.GET.get('program_search', '').strip()
        
        # Handle department filter first
        if department_filter:
            queryset = queryset.filter(program__department__name=department_filter)
        
        # Handle status filtering
        if status_filter:
            if status_filter == 'active_only':
                # Show only non-archived enrollments
                queryset = queryset.filter(is_archived=False)
            elif status_filter == 'pending':
                # Show enrollments with status='pending' and not archived
                queryset = queryset.filter(status='pending', is_archived=False)
            elif status_filter == 'active':
                # Show enrollments with status='active' and not archived
                queryset = queryset.filter(status='active', is_archived=False)
            elif status_filter == 'completed':
                # Show enrollments with status='completed' and not archived
                queryset = queryset.filter(status='completed', is_archived=False)
            elif status_filter == 'future':
                # Show future enrollments (start date in future and not archived)
                from django.utils import timezone
                queryset = queryset.filter(start_date__gt=timezone.now().date(), is_archived=False)
            elif status_filter == 'archived':
                # Show only archived enrollments
                queryset = queryset.filter(is_archived=True)
        
        if client_search:
            queryset = queryset.filter(
                Q(client__first_name__icontains=client_search) |
                Q(client__last_name__icontains=client_search) |
                Q(client__preferred_name__icontains=client_search) |
                Q(client__alias__icontains=client_search)
            )
        
        if program_search:
            queryset = queryset.filter(
                Q(program__name__icontains=program_search) |
                Q(program__department__name__icontains=program_search)
            )
        
        return queryset.order_by('-created_at')
    
    def get(self, request, *args, **kwargs):
        # Create CSV response
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="enrollments_export.csv"'
        
        # Create CSV writer
        writer = csv.writer(response)
        
        # Write header row
        writer.writerow([
            'Client Name',
            'Client ID',
            'Program Name',
            'Department',
            'Start Date',
            'End Date',
            'Status',
            'Notes',
            'Created By',
            'Created At',
            'Updated By',
            'Updated At',
            'Is Archived'
        ])
        
        # Get filtered enrollments
        enrollments = self.get_queryset()
        
        # Write data rows
        from django.utils import timezone
        today = timezone.now().date()
        
        for enrollment in enrollments:
            # Calculate status based on current date
            if today < enrollment.start_date:
                status = "Pending"
            elif enrollment.end_date:
                if today > enrollment.end_date:
                    status = "Completed"
                else:
                    status = "Active"
            else:
                status = "Active"
            
            writer.writerow([
                f"{enrollment.client.first_name} {enrollment.client.last_name}",
                enrollment.client.client_id,
                enrollment.program.name,
                enrollment.program.department.name,
                enrollment.start_date.strftime('%Y-%m-%d') if enrollment.start_date else '',
                enrollment.end_date.strftime('%Y-%m-%d') if enrollment.end_date else '',
                status,
                enrollment.notes or '',
                enrollment.created_by or '',
                enrollment.created_at.strftime('%Y-%m-%d %H:%M:%S') if enrollment.created_at else '',
                enrollment.updated_by or '',
                enrollment.updated_at.strftime('%Y-%m-%d %H:%M:%S') if enrollment.updated_at else '',
                'Yes' if enrollment.is_archived else 'No'
            ])
        
        return response


@method_decorator(jwt_required, name='dispatch')
class RestrictionCSVExportView(AnalystAccessMixin, ProgramManagerAccessMixin, ListView):
    """Export restrictions to CSV with filtering support"""
    model = ServiceRestriction
    template_name = 'core/restrictions.html'
    
    def get_queryset(self):
        # Use the same filtering logic as the restrictions view
        queryset = super().get_queryset()
        
        # Apply additional filters if any
        restriction_type_filter = self.request.GET.get('restriction_type', '')
        scope_filter = self.request.GET.get('scope', '')
        status_filter = self.request.GET.get('status', '')
        bill_168_filter = self.request.GET.get('bill_168', '')
        no_trespass_filter = self.request.GET.get('no_trespass', '')
        search_query = self.request.GET.get('search', '').strip()
        
        if restriction_type_filter:
            queryset = queryset.filter(restriction_type=restriction_type_filter)
        
        if scope_filter:
            queryset = queryset.filter(scope=scope_filter)
        
        if bill_168_filter:
            if bill_168_filter == 'true':
                queryset = queryset.filter(is_bill_168=True)
            elif bill_168_filter == 'false':
                queryset = queryset.filter(is_bill_168=False)
        
        if no_trespass_filter:
            if no_trespass_filter == 'true':
                queryset = queryset.filter(is_no_trespass=True)
            elif no_trespass_filter == 'false':
                queryset = queryset.filter(is_no_trespass=False)
        
        if status_filter:
            if status_filter == 'active':
                queryset = queryset.filter(end_date__isnull=True) | queryset.filter(end_date__gt=timezone.now().date())
            elif status_filter == 'expired':
                queryset = queryset.filter(end_date__lt=timezone.now().date())
        
        if search_query:
            queryset = queryset.filter(
                Q(client__first_name__icontains=search_query) |
                Q(client__last_name__icontains=search_query) |
                Q(notes__icontains=search_query)
            )
        
        return queryset.order_by('-created_at')
    
    def get(self, request, *args, **kwargs):
        # Create CSV response
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="restrictions_export.csv"'
        
        # Create CSV writer
        writer = csv.writer(response)
        
        # Write header row
        writer.writerow([
            'Client Name',
            'Client ID',
            'Restriction Type',
            'Scope',
            'Program',
            'Duration',
            'Start Date',
            'End Date',
            'Is Indefinite',
            'Status',
            'Notes',
            'Created By',
            'Created At',
            'Updated By',
            'Updated At'
        ])
        
        # Get filtered restrictions
        restrictions = self.get_queryset()
        
        # Write data rows
        for restriction in restrictions:
            # Determine status
            status = 'Active'
            if restriction.end_date and restriction.end_date < timezone.now().date():
                status = 'Expired'
            elif restriction.is_indefinite:
                status = 'Indefinite'
            
            writer.writerow([
                f"{restriction.client.first_name} {restriction.client.last_name}",
                restriction.client.client_id,
                restriction.get_restriction_type_display(),
                restriction.get_scope_display(),
                restriction.program.name if restriction.program else 'All Programs',
                restriction.get_duration_display() if not restriction.is_indefinite else 'Indefinite',
                restriction.start_date.strftime('%Y-%m-%d') if restriction.start_date else '',
                restriction.end_date.strftime('%Y-%m-%d') if restriction.end_date else '',
                'Yes' if restriction.is_indefinite else 'No',
                status,
                restriction.notes or '',
                restriction.created_by or '',
                restriction.created_at.strftime('%Y-%m-%d %H:%M:%S') if restriction.created_at else '',
                restriction.updated_by or '',
                restriction.updated_at.strftime('%Y-%m-%d %H:%M:%S') if restriction.updated_at else ''
            ])
        
        return response