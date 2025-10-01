from functools import wraps
from django.http import HttpResponseForbidden
from django.shortcuts import redirect
from django.contrib import messages
from django.core.exceptions import PermissionDenied

def require_permission(permission_name):
    """Decorator to require specific permission"""
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('home')
            
            # Check if user has the required permission
            if hasattr(request, 'user_permissions') and request.user_permissions.get(permission_name, False):
                return view_func(request, *args, **kwargs)
            
            # Fallback: check Django superuser status
            if request.user.is_superuser:
                return view_func(request, *args, **kwargs)
            
            messages.error(request, 'You do not have permission to access this page.')
            return HttpResponseForbidden('Access denied')
        return wrapper
    return decorator

def require_role(role_name):
    """Decorator to require specific role"""
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('home')
            
            # Check if user has the required role
            if hasattr(request, 'user_roles') and role_name in request.user_roles:
                return view_func(request, *args, **kwargs)
            
            # Fallback: check Django superuser status
            if request.user.is_superuser:
                return view_func(request, *args, **kwargs)
            
            messages.error(request, 'You do not have the required role to access this page.')
            return HttpResponseForbidden('Access denied')
        return wrapper
    return decorator


def program_manager_required(view_func):
    """Decorator to check if user is a program manager"""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.error(request, 'You must be logged in to access this page.')
            return redirect('login')
        
        try:
            staff = request.user.staff_profile
            if not staff.is_program_manager():
                messages.error(request, 'You must be a Program Manager to access this page.')
                return redirect('dashboard')
        except:
            messages.error(request, 'You do not have staff access.')
            return redirect('dashboard')
        
        return view_func(request, *args, **kwargs)
    return wrapper


def can_access_program(view_func):
    """Decorator to check if program manager can access a specific program"""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.error(request, 'You must be logged in to access this page.')
            return redirect('login')
        
        try:
            staff = request.user.staff_profile
            
            # Superadmin can access everything
            if request.user.is_superuser:
                return view_func(request, *args, **kwargs)
            
            # Check if program manager
            if staff.is_program_manager():
                # Get program from kwargs
                program_id = kwargs.get('program_id') or kwargs.get('external_id')
                if program_id:
                    from core.models import Program
                    try:
                        program = Program.objects.get(external_id=program_id)
                        if not staff.can_access_program(program):
                            messages.error(request, 'You do not have access to this program.')
                            return redirect('programs:list')
                    except Program.DoesNotExist:
                        messages.error(request, 'Program not found.')
                        return redirect('programs:list')
            
        except:
            messages.error(request, 'Access denied.')
            return redirect('dashboard')
        
        return view_func(request, *args, **kwargs)
    return wrapper


def can_access_enrollment(view_func):
    """Decorator to check if program manager can access a specific enrollment"""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.error(request, 'You must be logged in to access this page.')
            return redirect('login')
        
        try:
            staff = request.user.staff_profile
            
            # Superadmin can access everything
            if request.user.is_superuser:
                return view_func(request, *args, **kwargs)
            
            # Check if program manager
            if staff.is_program_manager():
                # Get enrollment from kwargs
                enrollment_id = kwargs.get('enrollment_id') or kwargs.get('external_id')
                if enrollment_id:
                    from core.models import ClientProgramEnrollment
                    try:
                        enrollment = ClientProgramEnrollment.objects.get(external_id=enrollment_id)
                        if not staff.can_manage_enrollment(enrollment):
                            messages.error(request, 'You do not have access to this enrollment.')
                            return redirect('core:enrollments')
                    except ClientProgramEnrollment.DoesNotExist:
                        messages.error(request, 'Enrollment not found.')
                        return redirect('core:enrollments')
            
        except:
            messages.error(request, 'Access denied.')
            return redirect('dashboard')
        
        return view_func(request, *args, **kwargs)
    return wrapper