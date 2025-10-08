"""
Django Messages utility functions for consistent alert messaging
"""
from django.contrib import messages
from django.utils.html import format_html


def success_message(request, message, title=None):
    """Add a success message with optional title"""
    if title:
        formatted_message = format_html('<strong>{}</strong><br>{}', title, message)
    else:
        formatted_message = message
    messages.success(request, formatted_message)


def error_message(request, message, title=None):
    """Add an error message with optional title"""
    if title:
        formatted_message = format_html('<strong>{}</strong><br>{}', title, message)
    else:
        formatted_message = message
    messages.error(request, formatted_message)


def warning_message(request, message, title=None):
    """Add a warning message with optional title"""
    if title:
        formatted_message = format_html('<strong>{}</strong><br>{}', title, message)
    else:
        formatted_message = message
    messages.warning(request, formatted_message)


def info_message(request, message, title=None):
    """Add an info message with optional title"""
    if title:
        formatted_message = format_html('<strong>{}</strong><br>{}', title, message)
    else:
        formatted_message = message
    messages.info(request, formatted_message)


def debug_message(request, message, title=None):
    """Add a debug message with optional title"""
    if title:
        formatted_message = format_html('<strong>{}</strong><br>{}', title, message)
    else:
        formatted_message = message
    messages.debug(request, formatted_message)


# Specific message types for common operations
def create_success(request, entity_name, entity_title=None):
    """Success message for entity creation"""
    if entity_title:
        success_message(request, f'{entity_name} "{entity_title}" has been created successfully.')
    else:
        success_message(request, f'{entity_name} has been created successfully.')


def update_success(request, entity_name, entity_title=None):
    """Success message for entity updates"""
    if entity_title:
        success_message(request, f'{entity_name} "{entity_title}" has been updated successfully.')
    else:
        success_message(request, f'{entity_name} has been updated successfully.')


def delete_success(request, entity_name, entity_title=None):
    """Success message for entity deletion"""
    if entity_title:
        success_message(request, f'{entity_name} "{entity_title}" has been deleted successfully.')
    else:
        success_message(request, f'{entity_name} has been deleted successfully.')


def validation_error(request, message):
    """Error message for validation failures"""
    error_message(request, message, "Validation Error")


def permission_error(request, action="perform this action"):
    """Error message for permission failures"""
    error_message(request, f'You do not have permission to {action}.', "Access Denied")


def not_found_error(request, entity_name):
    """Error message for entity not found"""
    error_message(request, f'{entity_name} not found or has been deleted.', "Not Found")


def bulk_operation_success(request, entity_name, count, operation="processed"):
    """Success message for bulk operations"""
    success_message(request, f'{count} {entity_name}(s) have been {operation} successfully.')


def bulk_operation_error(request, entity_name, errors):
    """Error message for bulk operations with specific errors"""
    error_message(request, f'Some {entity_name}(s) could not be processed: {", ".join(errors)}', "Partial Success")


# Form validation helpers
def form_validation_error(request, form):
    """Display form validation errors"""
    if form.errors:
        error_count = len(form.errors)
        if error_count == 1:
            error_message(request, "Please correct the error below.", "Form Validation Error")
        else:
            error_message(request, f"Please correct the {error_count} errors below.", "Form Validation Error")


def field_validation_error(request, field_name, message):
    """Display field-specific validation error"""
    error_message(request, f'{field_name}: {message}', "Validation Error")
