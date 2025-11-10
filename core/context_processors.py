from django.contrib.auth import get_user_model
from core.models import Staff, Role

User = get_user_model()

def user_permissions(request):
    """Add user permissions and roles to template context"""
    if request.user.is_authenticated:
        try:
            staff = request.user.staff_profile
            user_roles = staff.staffrole_set.select_related('role').all()
            role_names = [staff_role.role.name for staff_role in user_roles]
            
            # Check if user has only "User" role or no roles - if so, no permissions
            if role_names == ['User'] or not role_names:
                return {
                    'user_roles': role_names,
                    'user_permissions': {
                        'is_superadmin': False,
                        'is_staff': False,
                        'is_user': True,
                        'can_view_clients': False,
                        'can_manage_clients': False,
                        'can_view_programs': False,
                        'can_manage_programs': False,
                        'can_view_departments': False,
                        'can_manage_departments': False,
                        'can_view_enrollments': False,
                        'can_manage_enrollments': False,
                        'can_view_restrictions': False,
                        'can_manage_restrictions': False,
                        'can_view_reports': False,
                        'can_manage_reports': False,
                        'can_manage_email_subscriptions': False,
                        'can_view_audit_log': False,
                        'can_manage_users': False,
                        'can_manage_staff': False,
                    }
                }
            
            # Check specific permissions for other roles
            permissions = {
                'is_superadmin': 'SuperAdmin' in role_names or request.user.is_superuser,
                'is_staff': 'Staff' in role_names,
                'is_user': 'User' in role_names,
                'can_view_clients': any(role in ['SuperAdmin', 'Admin', 'Staff', 'Manager', 'Leader'] for role in role_names),
                'can_manage_clients': any(role in ['SuperAdmin', 'Admin'] for role in role_names),
                'can_create_clients': any(role in ['SuperAdmin', 'Admin', 'Manager', 'Leader'] for role in role_names),
                'can_view_programs': any(role in ['SuperAdmin', 'Admin', 'Manager', 'Leader'] for role in role_names),
                'can_manage_programs': any(role in ['SuperAdmin', 'Admin'] for role in role_names),
                'can_create_programs': any(role in ['SuperAdmin', 'Admin', 'Manager', 'Leader'] for role in role_names),
                'can_view_departments': any(role in ['SuperAdmin', 'Admin', 'Manager', 'Leader'] for role in role_names),
                'can_manage_departments': any(role in ['SuperAdmin', 'Admin'] for role in role_names),
                'can_view_enrollments': any(role in ['SuperAdmin', 'Admin', 'Manager', 'Leader'] for role in role_names),
                'can_manage_enrollments': any(role in ['SuperAdmin', 'Admin', 'Manager', 'Leader'] for role in role_names),
                'can_create_enrollments': any(role in ['SuperAdmin', 'Admin', 'Manager', 'Leader'] for role in role_names),
                'can_view_restrictions': any(role in ['SuperAdmin', 'Admin', 'Staff', 'Manager', 'Leader'] for role in role_names),
                'can_manage_restrictions': any(role in ['SuperAdmin', 'Admin', 'Manager', 'Leader'] for role in role_names),
                'can_create_restrictions': any(role in ['SuperAdmin', 'Admin', 'Manager', 'Leader'] for role in role_names),
                'can_view_reports': any(role in ['SuperAdmin', 'Admin', 'Manager', 'Leader', 'Analyst'] for role in role_names),
                'can_manage_reports': any(role in ['SuperAdmin', 'Admin'] for role in role_names),
                'can_manage_email_subscriptions': any(role in ['SuperAdmin', 'Admin'] for role in role_names),
                'can_view_audit_log': any(role in ['SuperAdmin', 'Admin'] for role in role_names),
                'can_manage_users': any(role in ['SuperAdmin', 'Admin'] for role in role_names),
                'can_manage_staff': any(role in ['SuperAdmin', 'Admin'] for role in role_names),
                'can_view_dashboard': any(role in ['SuperAdmin', 'Admin', 'Staff', 'Manager', 'Leader', 'Analyst'] for role in role_names),
                'is_program_manager': 'Manager' in role_names,
                'is_leader': 'Leader' in role_names,
                'is_analyst': 'Analyst' in role_names,
                'is_staff_only': 'Staff' in role_names and not any(role in ['SuperAdmin', 'Admin', 'Manager', 'Leader', 'Analyst'] for role in role_names),
            }
            
            return {
                'user_roles': role_names,
                'user_permissions': permissions,
            }
        except Staff.DoesNotExist:
            # User doesn't have staff profile yet - no permissions
            return {
                'user_roles': [],
                'user_permissions': {
                    'is_superadmin': False,
                    'is_staff': False,
                    'is_user': True,
                    'can_view_clients': False,
                    'can_manage_clients': False,
                    'can_view_programs': False,
                    'can_manage_programs': False,
                    'can_view_departments': False,
                    'can_manage_departments': False,
                    'can_view_enrollments': False,
                    'can_manage_enrollments': False,
                    'can_view_restrictions': False,
                    'can_manage_restrictions': False,
                    'can_view_reports': False,
                    'can_manage_reports': False,
                    'can_manage_email_subscriptions': False,
                    'can_view_audit_log': False,
                    'can_manage_users': False,
                    'can_manage_staff': False,
                }
            }
    
    return {
        'user_roles': [],
        'user_permissions': {}
    }



def program_manager_context(request):
    """Add program manager context to all templates"""
    context = {}
    
    if request.user.is_authenticated:
        try:
            staff = request.user.staff_profile
            context['is_program_manager'] = staff.is_program_manager()
            
            if context['is_program_manager']:
                context['assigned_programs'] = staff.get_assigned_programs()
                context['assigned_services'] = staff.get_assigned_services()
                context['assigned_departments'] = staff.get_assigned_departments()
                context['assigned_programs_count'] = context['assigned_programs'].count()
        except:
            context['is_program_manager'] = False
    else:
        context['is_program_manager'] = False
    
    return context