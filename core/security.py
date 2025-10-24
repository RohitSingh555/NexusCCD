"""
Comprehensive Role-Based Access Control System
Ensures security at both UI and database/backend levels
"""

from functools import wraps
from django.http import JsonResponse, HttpResponseForbidden
from django.contrib import messages
from django.shortcuts import redirect
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from core.models import Staff, Role, StaffRole

User = get_user_model()


class SecurityManager:
    """Centralized security management for role-based access control"""
    
    # Define role hierarchy and permissions
    ROLE_HIERARCHY = {
        'SuperAdmin': 100,
        'Admin': 90,
        'Manager': 80,
        'Leader': 70,
        'Staff': 60,
        'Analyst': 50,
        'User': 10,
    }
    
    # Define permissions for each role
    ROLE_PERMISSIONS = {
        'SuperAdmin': [
            'view_all', 'manage_all', 'delete_all', 'export_all',
            'manage_users', 'manage_staff', 'manage_departments',
            'manage_programs', 'manage_clients', 'manage_enrollments',
            'manage_restrictions', 'view_audit_log', 'manage_email_subscriptions',
            'view_reports', 'manage_reports'
        ],
        'Admin': [
            'view_all', 'manage_all', 'delete_all', 'export_all',
            'manage_users', 'manage_staff', 'manage_departments',
            'manage_programs', 'manage_clients', 'manage_enrollments',
            'manage_restrictions', 'view_audit_log', 'manage_email_subscriptions',
            'view_reports', 'manage_reports'
        ],
        'Manager': [
            'view_department', 'manage_department', 'export_department',
            'manage_staff', 'manage_programs', 'manage_clients',
            'manage_enrollments', 'manage_restrictions', 'view_reports'
        ],
        'Leader': [
            'view_department', 'manage_department', 'export_department',
            'manage_programs', 'manage_clients', 'manage_enrollments',
            'manage_restrictions', 'view_reports'
        ],
        'Staff': [
            'view_clients', 'edit_clients', 'view_programs',
            'view_enrollments', 'view_restrictions', 'view_reports'
        ],
        'Analyst': [
            'view_reports', 'export_reports', 'view_dashboard'
        ],
        'User': [
            'view_own_profile'
        ]
    }
    
    @classmethod
    def get_user_roles(cls, user):
        """Get all roles for a user"""
        if not user.is_authenticated:
            return []
        
        try:
            staff = user.staff_profile
            user_roles = staff.staffrole_set.select_related('role').all()
            return [staff_role.role.name for staff_role in user_roles]
        except Exception:
            return []
    
    @classmethod
    def get_user_permissions(cls, user):
        """Get all permissions for a user based on their roles"""
        if not user.is_authenticated:
            return []
        
        # Superuser has all permissions
        if user.is_superuser:
            return list(set().union(*cls.ROLE_PERMISSIONS.values()))
        
        user_roles = cls.get_user_roles(user)
        permissions = set()
        
        for role in user_roles:
            if role in cls.ROLE_PERMISSIONS:
                permissions.update(cls.ROLE_PERMISSIONS[role])
        
        return list(permissions)
    
    @classmethod
    def has_permission(cls, user, permission):
        """Check if user has a specific permission"""
        return permission in cls.get_user_permissions(user)
    
    @classmethod
    def has_role(cls, user, role):
        """Check if user has a specific role"""
        return role in cls.get_user_roles(user)
    
    @classmethod
    def has_any_role(cls, user, roles):
        """Check if user has any of the specified roles"""
        user_roles = cls.get_user_roles(user)
        return any(role in user_roles for role in roles)
    
    @classmethod
    def has_higher_role(cls, user, min_role):
        """Check if user has a role higher than or equal to min_role"""
        if user.is_superuser:
            return True
        
        user_roles = cls.get_user_roles(user)
        if not user_roles:
            return False
        
        min_level = cls.ROLE_HIERARCHY.get(min_role, 0)
        user_level = max(cls.ROLE_HIERARCHY.get(role, 0) for role in user_roles)
        
        return user_level >= min_level
    
    @classmethod
    def filter_queryset_by_role(cls, user, queryset, model_name):
        """Filter queryset based on user's role and permissions"""
        if not user.is_authenticated:
            return queryset.none()
        
        # Superuser sees everything
        if user.is_superuser:
            return queryset
        
        user_roles = cls.get_user_roles(user)
        
        # SuperAdmin and Admin see everything
        if any(role in ['SuperAdmin', 'Admin'] for role in user_roles):
            return queryset
        
        # Manager and Leader see department data
        if any(role in ['Manager', 'Leader'] for role in user_roles):
            try:
                staff = user.staff_profile
                # Filter by department assignments
                if hasattr(queryset.model, 'department'):
                    return queryset.filter(department__in=staff.departments.all())
                elif hasattr(queryset.model, 'staff'):
                    return queryset.filter(staff__departments__in=staff.departments.all())
            except Exception:
                pass
        
        # Staff and Analyst see limited data
        if any(role in ['Staff', 'Analyst'] for role in user_roles):
            try:
                staff = user.staff_profile
                # Filter by staff assignments
                if hasattr(queryset.model, 'staff'):
                    return queryset.filter(staff=staff)
                elif hasattr(queryset.model, 'created_by'):
                    return queryset.filter(created_by=user)
            except Exception:
                pass
        
        # Default: no access
        return queryset.none()


def require_permission(permission):
    """Decorator to require specific permission"""
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not SecurityManager.has_permission(request.user, permission):
                if request.headers.get('Accept') == 'application/json':
                    return JsonResponse({
                        'success': False,
                        'error': f'Permission denied. Required permission: {permission}'
                    }, status=403)
                else:
                    messages.error(request, f'You do not have permission to access this page. Required permission: {permission}')
                    return redirect('dashboard')
            
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def require_role(role):
    """Decorator to require specific role"""
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not SecurityManager.has_role(request.user, role):
                if request.headers.get('Accept') == 'application/json':
                    return JsonResponse({
                        'success': False,
                        'error': f'Access denied. Required role: {role}'
                    }, status=403)
                else:
                    messages.error(request, f'You do not have permission to access this page. Required role: {role}')
                    return redirect('dashboard')
            
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def require_any_role(*roles):
    """Decorator to require any of the specified roles"""
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not SecurityManager.has_any_role(request.user, roles):
                if request.headers.get('Accept') == 'application/json':
                    return JsonResponse({
                        'success': False,
                        'error': f'Access denied. Required roles: {", ".join(roles)}'
                    }, status=403)
                else:
                    messages.error(request, f'You do not have permission to access this page. Required roles: {", ".join(roles)}')
                    return redirect('dashboard')
            
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def require_minimum_role(min_role):
    """Decorator to require minimum role level"""
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not SecurityManager.has_higher_role(request.user, min_role):
                if request.headers.get('Accept') == 'application/json':
                    return JsonResponse({
                        'success': False,
                        'error': f'Access denied. Required minimum role: {min_role}'
                    }, status=403)
                else:
                    messages.error(request, f'You do not have permission to access this page. Required minimum role: {min_role}')
                    return redirect('dashboard')
            
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def secure_queryset(view_func):
    """Decorator to automatically filter querysets based on user role"""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        response = view_func(request, *args, **kwargs)
        
        # If response has a queryset, filter it
        if hasattr(response, 'context_data') and 'object_list' in response.context_data:
            queryset = response.context_data['object_list']
            if hasattr(queryset, 'model'):
                filtered_queryset = SecurityManager.filter_queryset_by_role(
                    request.user, queryset, queryset.model.__name__
                )
                response.context_data['object_list'] = filtered_queryset
        
        return response
    return wrapper


class SecureModelMixin:
    """Mixin for model views to automatically apply security filters"""
    
    def get_queryset(self):
        """Override to apply role-based filtering"""
        queryset = super().get_queryset()
        return SecurityManager.filter_queryset_by_role(
            self.request.user, queryset, self.model.__name__
        )
    
    def dispatch(self, request, *args, **kwargs):
        """Check permissions before dispatching"""
        # Check if user has permission to access this view
        required_permission = getattr(self, 'required_permission', None)
        if required_permission and not SecurityManager.has_permission(request.user, required_permission):
            if request.headers.get('Accept') == 'application/json':
                return JsonResponse({
                    'success': False,
                    'error': f'Permission denied. Required permission: {required_permission}'
                }, status=403)
            else:
                messages.error(request, f'You do not have permission to access this page.')
                return redirect('dashboard')
        
        return super().dispatch(request, *args, **kwargs)
