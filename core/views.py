from django.shortcuts import render, redirect
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
from .models import Client, Program, Staff, PendingChange, ClientProgramEnrollment

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
    return render(request, 'core/departments.html')


@jwt_required
def enrollments(request):
    """Enrollments management view"""
    return render(request, 'core/enrollments.html')


@jwt_required
def restrictions(request):
    """Service restrictions management view"""
    return render(request, 'core/restrictions.html')


@jwt_required
def approvals(request):
    """Pending approvals management view"""
    return render(request, 'core/approvals.html')


@jwt_required
def audit_log(request):
    """Audit log view"""
    return render(request, 'core/audit_log.html')
