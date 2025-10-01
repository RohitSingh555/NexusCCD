from django.shortcuts import render, redirect
from django.db.models import Count
from django.http import JsonResponse
from django.contrib.auth import get_user_model
from functools import wraps
import json
from django.contrib import messages
from django.urls import reverse_lazy
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from datetime import datetime
from .models import Client, Program, Staff, PendingChange, ClientProgramEnrollment, Department, ServiceRestriction
from .forms import EnrollmentForm
from .forms import UserProfileForm, StaffProfileForm, PasswordChangeForm


User = get_user_model()


class ProgramManagerAccessMixin:
    """Mixin to filter data for Program Managers based on their assigned programs"""
    
    def get_queryset(self):
        """Filter queryset based on user's assigned programs"""
        queryset = super().get_queryset()
        
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
    
    # Get recent clients (last 10)
    recent_clients = Client.objects.order_by('-created_at')[:10]
    
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
    
    for program in programs:
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
    return render(request, 'core/audit_log.html')


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
class EnrollmentListView(ProgramManagerAccessMixin, ListView):
    model = ClientProgramEnrollment
    template_name = 'core/enrollments.html'
    context_object_name = 'enrollments'
    paginate_by = 10
    
    def get_queryset(self):
        return ClientProgramEnrollment.objects.select_related(
            'client', 'program', 'program__department'
        ).order_by('-start_date')
    
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
        
        return context


class EnrollmentDetailView(ProgramManagerAccessMixin, DetailView):
    model = ClientProgramEnrollment
    template_name = 'core/enrollment_detail.html'
    context_object_name = 'enrollment'
    slug_field = 'external_id'
    slug_url_kwarg = 'external_id'


class EnrollmentCreateView(ProgramManagerAccessMixin, CreateView):
    model = ClientProgramEnrollment
    form_class = EnrollmentForm
    template_name = 'core/enrollment_form.html'
    success_url = reverse_lazy('core:enrollments')
    
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


class EnrollmentUpdateView(ProgramManagerAccessMixin, UpdateView):
    model = ClientProgramEnrollment
    form_class = EnrollmentForm
    template_name = 'core/enrollment_form.html'
    slug_field = 'external_id'
    slug_url_kwarg = 'external_id'
    success_url = reverse_lazy('core:enrollments')
    
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


class EnrollmentDeleteView(ProgramManagerAccessMixin, DeleteView):
    model = ClientProgramEnrollment
    template_name = 'core/enrollment_confirm_delete.html'
    slug_field = 'external_id'
    slug_url_kwarg = 'external_id'
    success_url = reverse_lazy('core:enrollments')


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
    fields = ['client', 'scope', 'program', 'start_date', 'end_date', 'reason']
    success_url = reverse_lazy('core:restrictions')
    
    def form_valid(self, form):
        messages.success(self.request, 'Service restriction created successfully.')
        return super().form_valid(form)


class RestrictionUpdateView(ProgramManagerAccessMixin, UpdateView):
    model = ServiceRestriction
    template_name = 'core/restriction_form.html'
    slug_field = 'external_id'
    slug_url_kwarg = 'external_id'
    success_url = reverse_lazy('core:restrictions')
    
    def form_valid(self, form):
        messages.success(self.request, 'Service restriction updated successfully.')
        return super().form_valid(form)


class RestrictionDeleteView(ProgramManagerAccessMixin, DeleteView):
    model = ServiceRestriction
    template_name = 'core/restriction_confirm_delete.html'
    slug_field = 'external_id'
    slug_url_kwarg = 'external_id'
    success_url = reverse_lazy('core:restrictions')
    
    def delete(self, request, *args, **kwargs):
        messages.success(self.request, 'Service restriction deleted successfully.')
        return super().delete(request, *args, **kwargs)


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