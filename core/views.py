from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.utils import timezone
from datetime import timedelta
from rest_framework_simplejwt.tokens import AccessToken
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
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


def jwt_required(view_func):
    """Decorator to require JWT authentication"""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        # Check for JWT token in Authorization header
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        if auth_header.startswith('Bearer '):
            token = auth_header.split(' ')[1]
            try:
                access_token = AccessToken(token)
                user_id = access_token['user_id']
                request.user = User.objects.get(id=user_id)
                return view_func(request, *args, **kwargs)
            except (InvalidToken, TokenError, User.DoesNotExist):
                pass
        
        # Check for JWT token in cookies
        token = request.COOKIES.get('access_token')
        if token:
            try:
                access_token = AccessToken(token)
                user_id = access_token['user_id']
                request.user = User.objects.get(id=user_id)
                return view_func(request, *args, **kwargs)
            except (InvalidToken, TokenError, User.DoesNotExist):
                pass
        
        # If no valid JWT token, redirect to home
        return redirect('home')
    
    return wrapper


def home(request):
    """Home view that redirects authenticated users to dashboard"""
    # Check for JWT token in Authorization header
    auth_header = request.META.get('HTTP_AUTHORIZATION', '')
    if auth_header.startswith('Bearer '):
        token = auth_header.split(' ')[1]
        try:
            # Validate the token
            AccessToken(token)
            # If token is valid, redirect to dashboard
            return redirect('dashboard')
        except (InvalidToken, TokenError):
            pass
    
    # Check for JWT token in cookies (for web requests)
    token = request.COOKIES.get('access_token')
    if token:
        try:
            AccessToken(token)
            return redirect('dashboard')
        except (InvalidToken, TokenError):
            pass
    
    # Check Django session authentication as fallback
    if request.user.is_authenticated:
        return redirect('dashboard')
    
    return render(request, 'home.html')


@jwt_required
def dashboard(request):
    """Dashboard view - redirects to profile for users without proper permissions"""
    # Check if user has proper permissions to access dashboard
    try:
        staff_profile = request.user.staff_profile
        user_roles = staff_profile.staffrole_set.select_related('role').all()
        role_names = [staff_role.role.name for staff_role in user_roles]
        
        # Check if user has any meaningful permissions
        has_permissions = any(role in ['SuperAdmin', 'Admin', 'Manager', 'Staff'] for role in role_names)
        
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
    programs = Program.objects.all()
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
    # Get all departments with related counts
    departments = Department.objects.annotate(
        program_count=Count('program', distinct=True),
        staff_count=Count('program__programstaff__staff', distinct=True)
    ).order_by('name')
    
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
    from django.utils import timezone
    
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
        'today': timezone.now().date(),
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
class EnrollmentListView(ListView):
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


class EnrollmentDetailView(DetailView):
    model = ClientProgramEnrollment
    template_name = 'core/enrollment_detail.html'
    context_object_name = 'enrollment'
    slug_field = 'external_id'
    slug_url_kwarg = 'external_id'


class EnrollmentCreateView(CreateView):
    model = ClientProgramEnrollment
    form_class = EnrollmentForm
    template_name = 'core/enrollment_form.html'
    success_url = reverse_lazy('core:enrollments')
    
    def form_valid(self, form):
        messages.success(self.request, 'Enrollment created successfully.')
        return super().form_valid(form)
    
    def form_invalid(self, form):
        messages.error(self.request, 'Please correct the errors below.')
        return super().form_invalid(form)


class EnrollmentUpdateView(UpdateView):
    model = ClientProgramEnrollment
    form_class = EnrollmentForm
    template_name = 'core/enrollment_form.html'
    slug_field = 'external_id'
    slug_url_kwarg = 'external_id'
    success_url = reverse_lazy('core:enrollments')
    
    def form_valid(self, form):
        messages.success(self.request, 'Enrollment updated successfully.')
        return super().form_valid(form)
    
    def form_invalid(self, form):
        messages.error(self.request, 'Please correct the errors below.')
        return super().form_invalid(form)


class EnrollmentDeleteView(DeleteView):
    model = ClientProgramEnrollment
    template_name = 'core/enrollment_confirm_delete.html'
    slug_field = 'external_id'
    slug_url_kwarg = 'external_id'
    success_url = reverse_lazy('core:enrollments')
    
    def delete(self, request, *args, **kwargs):
        messages.success(self.request, 'Enrollment deleted successfully.')
        return super().delete(request, *args, **kwargs)


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
class RestrictionListView(ListView):
    model = ServiceRestriction
    template_name = 'core/restrictions.html'
    context_object_name = 'restrictions'
    paginate_by = 10
    
    def get_queryset(self):
        return ServiceRestriction.objects.select_related(
            'client', 'program', 'program__department'
        ).order_by('-start_date')
    
    def get_context_data(self, **kwargs):
        from django.utils import timezone
        context = super().get_context_data(**kwargs)
        restrictions = self.get_queryset()
        context['total_restrictions'] = restrictions.count()
        context['active_restrictions'] = restrictions.filter(end_date__isnull=True).count()
        context['org_restrictions'] = restrictions.filter(scope='org').count()
        context['program_restrictions'] = restrictions.filter(scope='program').count()
        context['today'] = timezone.now().date()
        return context


class RestrictionDetailView(DetailView):
    model = ServiceRestriction
    template_name = 'core/restriction_detail.html'
    context_object_name = 'restriction'
    slug_field = 'external_id'
    slug_url_kwarg = 'external_id'


class RestrictionCreateView(CreateView):
    model = ServiceRestriction
    template_name = 'core/restriction_form.html'
    fields = ['client', 'scope', 'program', 'start_date', 'end_date', 'reason']
    success_url = reverse_lazy('core:restrictions')
    
    def form_valid(self, form):
        messages.success(self.request, 'Service restriction created successfully.')
        return super().form_valid(form)


class RestrictionUpdateView(UpdateView):
    model = ServiceRestriction
    template_name = 'core/restriction_form.html'
    fields = ['client', 'scope', 'program', 'start_date', 'end_date', 'reason']
    slug_field = 'external_id'
    slug_url_kwarg = 'external_id'
    success_url = reverse_lazy('core:restrictions')
    
    def form_valid(self, form):
        messages.success(self.request, 'Service restriction updated successfully.')
        return super().form_valid(form)


class RestrictionDeleteView(DeleteView):
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