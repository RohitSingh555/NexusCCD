from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.utils.decorators import method_decorator
from django.views import View
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
import json

class PermissionErrorView(View):
    """Custom view to handle permission errors with user-friendly messages"""
    
    def get(self, request):
        error_type = request.GET.get('type', 'access_denied')
        resource_type = request.GET.get('resource', 'resource')
        resource_name = request.GET.get('name', '')
        
        # Determine the appropriate message based on error type
        messages = {
            'access_denied': f"You don't have permission to access this {resource_type}.",
            'program_not_assigned': f"You don't have access to this program. Only programs assigned to you are accessible.",
            'client_not_related': f"You don't have access to this client. You can only view clients you have a relationship with.",
            'client_not_assigned': f"You don't have access to this client. You can only view clients enrolled in your assigned programs or departments.",
            'restriction_not_related': f"You don't have access to this restriction. You can only view restrictions for clients you manage.",
            'restriction_not_found': f"The requested restriction could not be found.",
            'enrollment_not_related': f"You don't have access to this enrollment. You can only view enrollments for clients you manage.",
        }
        
        message = messages.get(error_type, messages['access_denied'])
        
        if resource_name:
            message = f"You don't have access to {resource_name}. {message}"
        
        # If it's an AJAX request, return JSON
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'error': True,
                'message': message,
                'type': 'permission_error',
                'redirect_url': '/dashboard/'
            }, status=403)
        
        # Otherwise, render a user-friendly error page
        context = {
            'error_message': message,
            'error_type': error_type,
            'resource_type': resource_type,
            'resource_name': resource_name,
            'can_go_back': True,
        }
        
        return render(request, 'core/permission_error.html', context, status=403)

@require_http_methods(["GET"])
def permission_error_ajax(request):
    """AJAX endpoint for permission errors"""
    error_type = request.GET.get('type', 'access_denied')
    resource_type = request.GET.get('resource', 'resource')
    resource_name = request.GET.get('name', '')
    
    messages = {
        'access_denied': f"You don't have permission to access this {resource_type}.",
        'program_not_assigned': f"You don't have access to this program. Only programs assigned to you are accessible.",
        'client_not_related': f"You don't have access to this client. You can only view clients you have a relationship with.",
        'client_not_assigned': f"You don't have access to this client. You can only view clients enrolled in your assigned programs or departments.",
        'restriction_not_related': f"You don't have access to this restriction. You can only view restrictions for clients you manage.",
        'restriction_not_found': f"The requested restriction could not be found.",
        'enrollment_not_related': f"You don't have access to this enrollment. You can only view enrollments for clients you manage.",
    }
    
    message = messages.get(error_type, messages['access_denied'])
    
    if resource_name:
        message = f"You don't have access to {resource_name}. {message}"
    
    return JsonResponse({
        'error': True,
        'message': message,
        'type': 'permission_error',
        'redirect_url': '/dashboard/'
    }, status=403)
