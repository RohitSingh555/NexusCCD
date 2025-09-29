from functools import wraps
from django.http import HttpResponseForbidden
from django.shortcuts import redirect
from django.contrib import messages

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