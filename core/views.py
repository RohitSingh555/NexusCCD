from django.shortcuts import render, redirect
from django.db.models import Count, Q
from django.http import JsonResponse
from django.contrib.auth import get_user_model
from functools import wraps
import json
from django.contrib import messages
from django.urls import reverse_lazy
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils.decorators import method_decorator
from datetime import datetime
from .models import Client, Program, Staff, PendingChange, ClientProgramEnrollment, Department, ServiceRestriction
from .forms import EnrollmentForm
from .forms import UserProfileForm, StaffProfileForm, PasswordChangeForm, ServiceRestrictionForm


User = get_user_model()


class ProgramManagerAccessMixin:
    """Mixin to filter data for Program Managers based on their assigned programs"""
    
    def get_queryset(self):
        """Filter queryset based on user's assigned programs"""
        # Start with the base queryset with proper ordering and select_related
        queryset = super().get_queryset().order_by('-created_at')
        
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
            
            # Program Manager can only see assigned programs
            if staff.is_program_manager():
                assigned_programs = staff.get_assigned_programs()
                # Filter based on model type
                if hasattr(self.model, 'program'):
                    # For models with program field (like ServiceRestriction)
                    return queryset.filter(program__in=assigned_programs)
                else:
                    # For models without program field (like Program)
                    return queryset.filter(id__in=assigned_programs)
            
            # Other roles see everything (Staff, etc.)
            return queryset
            
        except Exception:
            # For superadmin, return all programs even if there's an exception
            if self.request.user.is_superuser:
                return queryset
            return queryset.none()
    
    def get_context_data(self, **kwargs):
        """Add program manager context"""
        context = super().get_context_data(**kwargs)
        
        if self.request.user.is_authenticated:
            try:
                staff = self.request.user.staff_profile
                if staff.is_program_manager():
                    context['assigned_programs'] = staff.get_assigned_programs()
                    context['is_program_manager'] = True
            except Exception:
                pass
        
        return context

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
        has_permissions = any(role in ['SuperAdmin', 'Staff','Program Manager'] for role in role_names)
        
        if not has_permissions:
            # User doesn't have proper permissions, redirect to profile
            return redirect('core:profile')
            
    except Staff.DoesNotExist:
        # User doesn't have staff profile, redirect to profile
        return redirect('core:profile')
    
    # User has proper permissions, show dashboard
    # Get basic statistics
    total_clients = Client.objects.count()
    active_programs = Program.objects.count()
    total_staff = Staff.objects.count()
    pending_approvals = PendingChange.objects.filter(status='pending').count()
    
    # Get recent clients (last 5)
    recent_clients = Client.objects.order_by('-created_at')[:5]
    
    # Get program status with enrollment counts and capacity information
    # Filter programs for Program Managers
    if request.user.is_authenticated:
        try:
            staff = request.user.staff_profile
            if staff.is_program_manager():
                # Program Manager can only see their assigned programs
                programs = staff.get_assigned_programs()
            else:
                # SuperAdmin and Staff can see all programs
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
        'pending_approvals': pending_approvals,
        'recent_clients': recent_clients,
        'program_status': program_status,
        'pending_approvals_count': pending_approvals,
    }
    
    return render(request, 'dashboard.html', context)


@jwt_required
def departments(request):
    """Departments management view"""
    # Get departments - filter for Program Managers
    if request.user.is_authenticated:
        try:
            staff = request.user.staff_profile
            if staff.is_program_manager():
                # Program Manager can only see departments of their assigned programs
                departments = staff.get_assigned_departments()
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
    
    # Get statistics
    total_departments = departments.count()
    total_programs = Program.objects.count()
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
    # Get all enrollments with related data
    enrollments = ClientProgramEnrollment.objects.select_related(
        'client', 'program', 'program__department'
    ).order_by('-start_date')
    
    # Calculate statistics
    total_enrollments = enrollments.count()
    active_enrollments = enrollments.filter(end_date__isnull=True).count()
    completed_enrollments = enrollments.filter(end_date__isnull=False).count()
    
    # Calculate success rate
    success_rate = 0
    if total_enrollments > 0:
        success_rate = round((completed_enrollments / total_enrollments) * 100, 1)
    
    context = {
        'enrollments': enrollments,
        'total_enrollments': total_enrollments,
        'active_enrollments': active_enrollments,
        'completed_enrollments': completed_enrollments,
        'success_rate': success_rate,
    }
    
    return render(request, 'core/enrollments.html', context)


@jwt_required
def restrictions(request):
    """Service restrictions management view"""
    from django.utils import timezone as django_timezone
    
    # Get all restrictions with related data
    restrictions = ServiceRestriction.objects.select_related(
        'client', 'program', 'program__department'
    ).order_by('-start_date')
    
    # Calculate statistics
    total_restrictions = restrictions.count()
    active_restrictions = restrictions.filter(
        end_date__isnull=True
    ).count()
    org_restrictions = restrictions.filter(scope='org').count()
    program_restrictions = restrictions.filter(scope='program').count()
    
    context = {
        'restrictions': restrictions,
        'total_restrictions': total_restrictions,
        'active_restrictions': active_restrictions,
        'org_restrictions': org_restrictions,
        'program_restrictions': program_restrictions,
        'today': django_timezone.now().date(),
    }
    
    return render(request, 'core/restrictions.html', context)


@jwt_required
def approvals(request):
    """Pending approvals management view"""
    return render(request, 'core/approvals.html')


@jwt_required
def audit_log(request):
    """Audit log view"""
    from .models import AuditLog
    
    # Get all audit logs ordered by most recent first
    audit_logs = AuditLog.objects.select_related('changed_by').order_by('-changed_at')
    
    # Get statistics
    total_events = audit_logs.count()
    create_events = audit_logs.filter(action='create').count()
    update_events = audit_logs.filter(action='update').count()
    delete_events = audit_logs.filter(action='delete').count()
    
    context = {
        'audit_logs': audit_logs,
        'total_events': total_events,
        'create_events': create_events,
        'update_events': update_events,
        'delete_events': delete_events,
    }
    
    return render(request, 'core/audit_log.html', context)


# Department CRUD Views
class DepartmentListView(ListView):
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


class DepartmentDetailView(DetailView):
    model = Department
    template_name = 'core/department_detail.html'
    context_object_name = 'department'
    slug_field = 'external_id'
    slug_url_kwarg = 'external_id'


class DepartmentCreateView(CreateView):
    model = Department
    template_name = 'core/department_form.html'
    fields = ['name', 'owner']
    success_url = reverse_lazy('core:departments')
    
    def form_valid(self, form):
        messages.success(self.request, 'Department created successfully.')
        return super().form_valid(form)


class DepartmentUpdateView(UpdateView):
    model = Department
    template_name = 'core/department_form.html'
    fields = ['name', 'owner']
    slug_field = 'external_id'
    slug_url_kwarg = 'external_id'
    success_url = reverse_lazy('core:departments')
    
    def form_valid(self, form):
        messages.success(self.request, 'Department updated successfully.')
        return super().form_valid(form)


class DepartmentDeleteView(DeleteView):
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
class EnrollmentListView(ProgramManagerAccessMixin, ListView):
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
        
        if department_filter:
            queryset = queryset.filter(program__department__name=department_filter)
        
        if status_filter:
            if status_filter == 'active':
                queryset = queryset.filter(end_date__isnull=True)
            elif status_filter == 'completed':
                queryset = queryset.filter(end_date__isnull=False)
            elif status_filter == 'future':
                from django.utils import timezone
                queryset = queryset.filter(start_date__gt=timezone.now().date())
        
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
        context['total_enrollments'] = enrollments.count()
        context['active_enrollments'] = enrollments.filter(end_date__isnull=True).count()
        context['completed_enrollments'] = enrollments.filter(end_date__isnull=False).count()
        
        # Calculate success rate
        success_rate = 0
        if context['total_enrollments'] > 0:
            success_rate = round((context['completed_enrollments'] / context['total_enrollments']) * 100, 1)
        context['success_rate'] = success_rate
        
        # Add filter options to context
        context['departments'] = Department.objects.all().order_by('name')
        context['status_choices'] = [
            ('', 'All Statuses'),
            ('active', 'Active'),
            ('completed', 'Completed'),
            ('future', 'Future Start'),
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
class EnrollmentDetailView(ProgramManagerAccessMixin, DetailView):
    model = ClientProgramEnrollment
    template_name = 'core/enrollment_detail.html'
    context_object_name = 'enrollment'
    slug_field = 'external_id'
    slug_url_kwarg = 'external_id'


@method_decorator(jwt_required, name='dispatch')
class EnrollmentCreateView(ProgramManagerAccessMixin, CreateView):
    model = ClientProgramEnrollment
    form_class = EnrollmentForm
    template_name = 'core/enrollment_form.html'
    success_url = reverse_lazy('core:enrollments')
    
    def form_valid(self, form):
        """Override form_valid to add audit logging"""
        response = super().form_valid(form)
        
        # Create audit log entry
        try:
            from .models import create_audit_log
            create_audit_log(
                entity_name='Enrollment',
                entity_id=self.object.external_id,
                action='create',
                changed_by=self.request.user,
                diff_data={
                    'client': str(self.object.client),
                    'program': str(self.object.program),
                    'start_date': str(self.object.start_date),
                    'status': self.object.status
                }
            )
        except Exception as e:
            # Log error but don't break the enrollment creation
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error creating audit log for enrollment: {e}")
        
        return response
    
    def get_form_kwargs(self):
        """Filter programs and clients to only assigned ones for Program Managers"""
        kwargs = super().get_form_kwargs()
        if self.request.user.is_authenticated:
            try:
                staff = self.request.user.staff_profile
                if staff.is_program_manager():
                    # Filter programs to only assigned ones
                    assigned_programs = staff.get_assigned_programs()
                    kwargs['program_queryset'] = assigned_programs
                    
                    # For now, show all clients - program managers can enroll any client
                    # In the future, you might want to filter clients based on some criteria
                    kwargs['client_queryset'] = Client.objects.all()
            except Exception:
                pass
        return kwargs
    
    def form_invalid(self, form):
        """Handle form validation errors"""
        return super().form_invalid(form)
    
    def form_valid(self, form):
        """Handle successful form submission"""
        return super().form_valid(form)


@method_decorator(jwt_required, name='dispatch')
class EnrollmentUpdateView(ProgramManagerAccessMixin, UpdateView):
    model = ClientProgramEnrollment
    form_class = EnrollmentForm
    template_name = 'core/enrollment_form.html'
    slug_field = 'external_id'
    slug_url_kwarg = 'external_id'
    success_url = reverse_lazy('core:enrollments')
    
    def get_form_kwargs(self):
        """Filter programs and clients to only assigned ones for Program Managers"""
        kwargs = super().get_form_kwargs()
        if self.request.user.is_authenticated:
            try:
                staff = self.request.user.staff_profile
                if staff.is_program_manager():
                    # Filter programs to only assigned ones
                    assigned_programs = staff.get_assigned_programs()
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
class EnrollmentDeleteView(ProgramManagerAccessMixin, DeleteView):
    model = ClientProgramEnrollment
    template_name = 'core/enrollment_confirm_delete.html'
    slug_field = 'external_id'
    slug_url_kwarg = 'external_id'
    success_url = reverse_lazy('core:enrollments')
    
    def get_context_data(self, **kwargs):
        """Add enrollment object to context"""
        context = super().get_context_data(**kwargs)
        context['enrollment'] = self.get_object()
        return context
    
    def delete(self, request, *args, **kwargs):
        """Override to handle confirmation text validation"""
        try:
            # Get the enrollment object first
            enrollment = self.get_object()
            
            # Check confirmation text
            confirmation = request.POST.get('confirmation_text', '').strip().upper()
            if confirmation != 'DELETE':
                messages.error(request, 'Please type "DELETE" to confirm deletion.')
                return redirect('core:enrollments_detail', external_id=enrollment.external_id)
            
            client_name = f"{enrollment.client.first_name} {enrollment.client.last_name}"
            program_name = enrollment.program.name
            
            # Create audit log entry before deletion
            from .models import create_audit_log
            create_audit_log(
                entity_name='Enrollment',
                entity_id=enrollment.external_id,
                action='delete',
                changed_by=request.user,
                diff_data={
                    'client': str(enrollment.client),
                    'program': str(enrollment.program),
                    'start_date': str(enrollment.start_date),
                    'end_date': str(enrollment.end_date) if enrollment.end_date else None,
                    'status': enrollment.status
                }
            )
            
            # Delete the enrollment
            enrollment.delete()
            print(f"Deleted enrollment: {client_name} - {program_name}")
            
            messages.success(
                request, 
                f'Enrollment for {client_name} in {program_name} has been deleted successfully.'
            )
            return redirect(self.success_url)
            
        except Exception as e:
            print(f"Error deleting enrollment: {str(e)}")
            messages.error(request, f'Error deleting enrollment: {str(e)}')
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
class RestrictionListView(ProgramManagerAccessMixin, ListView):
    model = ServiceRestriction
    template_name = 'core/restrictions.html'
    context_object_name = 'restrictions'
    paginate_by = 10
    
    def get_queryset(self):
        return ServiceRestriction.objects.select_related(
            'client', 'program', 'program__department'
        ).order_by('-created_at')
    
    def get_context_data(self, **kwargs):
        from django.utils import timezone as django_timezone
        context = super().get_context_data(**kwargs)
        restrictions = self.get_queryset()
        context['total_restrictions'] = restrictions.count()
        context['active_restrictions'] = restrictions.filter(end_date__isnull=True).count()
        context['org_restrictions'] = restrictions.filter(scope='org').count()
        context['program_restrictions'] = restrictions.filter(scope='program').count()
        context['today'] = django_timezone.now().date()
        return context


class RestrictionDetailView(ProgramManagerAccessMixin, DetailView):
    model = ServiceRestriction
    template_name = 'core/restriction_detail.html'
    context_object_name = 'restriction'
    slug_field = 'external_id'
    slug_url_kwarg = 'external_id'


class RestrictionCreateView(ProgramManagerAccessMixin, CreateView):
    model = ServiceRestriction
    template_name = 'core/restriction_form.html'
    form_class = ServiceRestrictionForm
    success_url = reverse_lazy('core:restrictions')
    
    def get_form_kwargs(self):
        """Filter programs to only assigned ones for Program Managers"""
        kwargs = super().get_form_kwargs()
        if self.request.user.is_authenticated:
            try:
                staff = self.request.user.staff_profile
                if staff.is_program_manager():
                    # Filter programs to only assigned ones
                    assigned_programs = staff.get_assigned_programs()
                    kwargs['program_queryset'] = assigned_programs
            except Exception:
                pass
        return kwargs
    
    def form_valid(self, form):
        print("RestrictionCreateView.form_valid called")
        print(f"Form is valid: {form.is_valid()}")
        print(f"Form errors: {form.errors}")
        print(f"Form cleaned_data: {form.cleaned_data}")
        
        try:
            # Set the created_by and updated_by fields before saving
            restriction = form.save(commit=False)
            user_name = self.request.user.get_full_name() or self.request.user.username
            restriction.created_by = user_name
            restriction.updated_by = user_name
            restriction.save()
            
            messages.success(self.request, 'Service restriction created successfully.')
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


class RestrictionUpdateView(ProgramManagerAccessMixin, UpdateView):
    model = ServiceRestriction
    template_name = 'core/restriction_form.html'
    form_class = ServiceRestrictionForm
    slug_field = 'external_id'
    slug_url_kwarg = 'external_id'
    success_url = reverse_lazy('core:restrictions')
    
    def get_form_kwargs(self):
        """Filter programs to only assigned ones for Program Managers"""
        kwargs = super().get_form_kwargs()
        if self.request.user.is_authenticated:
            try:
                staff = self.request.user.staff_profile
                if staff.is_program_manager():
                    # Filter programs to only assigned ones
                    assigned_programs = staff.get_assigned_programs()
                    kwargs['program_queryset'] = assigned_programs
            except Exception:
                pass
        return kwargs
    
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
    
    def form_valid(self, form):
        # Set the updated_by field before saving
        restriction = form.save(commit=False)
        restriction.updated_by = self.request.user.get_full_name() or self.request.user.username
        restriction.save()
        
        messages.success(self.request, 'Service restriction updated successfully.')
        return redirect(self.success_url)


class RestrictionDeleteView(ProgramManagerAccessMixin, DeleteView):
    model = ServiceRestriction
    template_name = 'core/restriction_confirm_delete.html'
    slug_field = 'external_id'
    slug_url_kwarg = 'external_id'
    success_url = reverse_lazy('core:restrictions')
    
    def get_context_data(self, **kwargs):
        """Add restriction object to context"""
        context = super().get_context_data(**kwargs)
        context['restriction'] = self.get_object()
        return context
    
    def delete(self, request, *args, **kwargs):
        """Override to handle confirmation text validation"""
        try:
            # Get the restriction object first
            restriction = self.get_object()
            
            # Check confirmation text
            confirmation = request.POST.get('confirmation_text', '').strip().upper()
            if confirmation != 'DELETE':
                messages.error(request, 'Please type "DELETE" to confirm deletion.')
                return redirect('core:restrictions_detail', external_id=restriction.external_id)
            
            client_name = f"{restriction.client.first_name} {restriction.client.last_name}"
            restriction_type = restriction.get_restriction_type_display()
            
            # Delete the restriction
            restriction.delete()
            print(f"Deleted restriction: {client_name} - {restriction_type}")
            
            messages.success(
                request, 
                f'Service restriction for {client_name} has been deleted successfully.'
            )
            return redirect(self.success_url)
            
        except Exception as e:
            print(f"Error deleting restriction: {str(e)}")
            messages.error(request, f'Error deleting restriction: {str(e)}')
            return redirect(self.success_url)


@csrf_exempt
@require_http_methods(["POST"])
def bulk_delete_restrictions(request):
    """Bulk delete service restrictions"""
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
                'error': 'No restrictions selected for deletion'
            }, status=400)
        
        # Get the restrictions to delete
        restrictions_to_delete = ServiceRestriction.objects.filter(id__in=restriction_ids)
        deleted_count = restrictions_to_delete.count()
        
        if deleted_count == 0:
            return JsonResponse({
                'success': False,
                'error': 'No restrictions found with the provided IDs'
            }, status=404)
        
        # Delete the restrictions
        restrictions_to_delete.delete()
        
        return JsonResponse({
            'success': True,
            'deleted_count': deleted_count,
            'message': f'Successfully deleted {deleted_count} restriction(s)'
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON data'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Error deleting restrictions: {str(e)}'
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
        
        # Create audit log entries for each enrollment before deletion
        from .models import create_audit_log
        for enrollment in enrollments_to_delete:
            create_audit_log(
                entity_name='Enrollment',
                entity_id=enrollment.external_id,
                action='delete',
                changed_by=request.user,
                diff_data={
                    'client': str(enrollment.client),
                    'program': str(enrollment.program),
                    'start_date': str(enrollment.start_date),
                    'end_date': str(enrollment.end_date) if enrollment.end_date else None,
                    'status': enrollment.status
                }
            )
        
        # Delete the enrollments
        enrollments_to_delete.delete()
        
        return JsonResponse({
            'success': True,
            'deleted_count': deleted_count,
            'message': f'Successfully deleted {deleted_count} enrollment(s)'
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
        print(f"POST data: {request.POST}")
        print(f"FILES data: {request.FILES}")
        user_form = UserProfileForm(request.POST, request.FILES, instance=request.user)
        staff_form = StaffProfileForm(request.POST, instance=staff_profile)
        
        print(f"User form is valid: {user_form.is_valid()}")
        print(f"User form errors: {user_form.errors}")
        print(f"Staff form is valid: {staff_form.is_valid()}")
        print(f"Staff form errors: {staff_form.errors}")
        
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