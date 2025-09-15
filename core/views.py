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
from .models import Client, Program, Staff, PendingChange, ClientProgramEnrollment, Department, ServiceRestriction
from .forms import EnrollmentForm

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
    """Dashboard view with statistics and recent data"""
    # Get basic statistics
    total_clients = Client.objects.count()
    active_programs = Program.objects.count()
    total_staff = Staff.objects.count()
    pending_approvals = PendingChange.objects.filter(status='pending').count()
    
    # Get recent clients (last 10)
    recent_clients = Client.objects.order_by('-created_at')[:10]
    
    # Get program status with enrollment counts
    programs = Program.objects.all()
    program_status = []
    
    for program in programs:
        current_enrollments = ClientProgramEnrollment.objects.filter(
            program=program,
            start_date__lte=timezone.now().date(),
            end_date__isnull=True
        ).count()
        
        occupancy_percentage = 0
        if program.capacity_current > 0:
            occupancy_percentage = min((current_enrollments / program.capacity_current) * 100, 100)
        
        program_status.append({
            'name': program.name,
            'department': program.department,
            'capacity_current': program.capacity_current,
            'current_enrollments': current_enrollments,
            'occupancy_percentage': occupancy_percentage
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
