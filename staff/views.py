from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy
from django.contrib import messages
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from functools import wraps
from core.models import Staff, Role, StaffRole, User, ProgramManagerAssignment, Program, Department, DepartmentLeaderAssignment, Client
from .forms import StaffRoleForm, ProgramManagerAssignmentForm, StaffProgramAssignmentForm, StaffClientAssignmentForm
from .models import StaffClientAssignment, StaffProgramAssignment


def require_roles(*allowed_roles):
    """
    Decorator to require specific roles for access to views.
    Usage: @require_roles('Staff', 'Manager', 'Leader')
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                messages.error(request, 'You must be logged in to access this page.')
                return redirect('login')
            
            # Check if user is superuser (always allowed)
            if request.user.is_superuser:
                return view_func(request, *args, **kwargs)
            
            try:
                staff = request.user.staff_profile
                user_roles = staff.staffrole_set.select_related('role').all()
                role_names = [staff_role.role.name for staff_role in user_roles]
                
                # Check if user has any of the allowed roles
                has_allowed_role = any(role in allowed_roles for role in role_names)
                
                if not has_allowed_role:
                    messages.error(request, f'You do not have permission to access this page. Required roles: {", ".join(allowed_roles)}')
                    return redirect('staff:list')
                
                return view_func(request, *args, **kwargs)
                
            except Exception:
                messages.error(request, 'You do not have permission to access this page.')
                return redirect('staff:list')
        
        return wrapper
    return decorator


@method_decorator(require_roles('SuperAdmin', 'Admin'), name='dispatch')
class StaffListView(ListView):
    model = Staff
    template_name = 'staff/staff_list.html'
    context_object_name = 'staff'
    paginate_by = 10

    def get_paginate_by(self, queryset):
        """Get the number of items to paginate by from request parameters"""
        per_page = self.request.GET.get('per_page', '10')
        try:
            per_page = int(per_page)
            # Limit to reasonable values
            if per_page < 5:
                per_page = 5
            elif per_page > 100:
                per_page = 100
        except (ValueError, TypeError):
            per_page = 10
        return per_page

    def get_queryset(self):
        # Only show staff members who have a linked user account (can be converted to staff or already are staff)
        queryset = Staff.objects.filter(user__isnull=False).select_related('user')
        
        # Apply search filter
        search_query = self.request.GET.get('search', '').strip()
        if search_query:
            from django.db.models import Q
            queryset = queryset.filter(
                Q(first_name__icontains=search_query) |
                Q(last_name__icontains=search_query) |
                Q(email__icontains=search_query) |
                Q(user__first_name__icontains=search_query) |
                Q(user__last_name__icontains=search_query) |
                Q(user__email__icontains=search_query)
            ).distinct()
        
        # Apply status filter
        status_filter = self.request.GET.get('status', '')
        if status_filter == 'active':
            queryset = queryset.filter(active=True)
        elif status_filter == 'inactive':
            queryset = queryset.filter(active=False)
        
        return queryset.order_by('-created_at')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get the queryset and add role information to each staff member
        staff_list = list(context['staff'])
        for staff in staff_list:
            staff.current_roles = staff.staffrole_set.select_related('role').all()
            # Create a set of role IDs for easy lookup
            role_ids = []
            for staff_role in staff.current_roles:
                role_ids.append(staff_role.role.id)
            staff.role_ids = set(role_ids)
        
        # Update the context with the modified staff list
        context['staff'] = staff_list
        
        # Get the total count of filtered staff (not just current page)
        total_filtered_count = self.get_queryset().count()
        
        # Calculate statistics
        all_staff = Staff.objects.filter(user__isnull=False)
        context['total_staff'] = all_staff.count()
        context['active_staff'] = all_staff.filter(active=True).count()
        context['inactive_staff'] = all_staff.filter(active=False).count()
        context['total_filtered_count'] = total_filtered_count
        
        # Add all available roles to the context for the toggle buttons
        context['available_roles'] = Role.objects.all()
        
        # Add current filter values
        context['current_search'] = self.request.GET.get('search', '')
        context['current_status'] = self.request.GET.get('status', '')
        context['per_page'] = self.request.GET.get('per_page', '10')
        
        # Force pagination to be enabled if there are any results
        if context.get('paginator') and context['paginator'].count > 0:
            context['is_paginated'] = True
        
        return context

@method_decorator(require_roles('SuperAdmin', 'Admin'), name='dispatch')
class StaffDetailView(DetailView):
    model = Staff
    template_name = 'staff/staff_detail.html'
    context_object_name = 'staff_member'
    slug_field = 'external_id'
    slug_url_kwarg = 'external_id'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        staff = self.get_object()
        context['current_roles'] = staff.staffrole_set.select_related('role').all()

        # Check the viewing user's role to determine which assignment sections to show
        viewing_user_is_admin = False
        viewing_user_is_superadmin = False
        viewing_user_is_staff = False
        viewing_user_is_manager = False
        viewing_user_is_leader = False
        
        if self.request.user.is_authenticated:
            try:
                viewing_staff = self.request.user.staff_profile
                user_roles = viewing_staff.staffrole_set.select_related('role').all()
                role_names = [staff_role.role.name for staff_role in user_roles]
                
                viewing_user_is_admin = 'Admin' in role_names
                viewing_user_is_superadmin = 'SuperAdmin' in role_names
                viewing_user_is_staff = 'Staff' in role_names  # Staff role users can see assignments regardless of other roles
                viewing_user_is_manager = 'Manager' in role_names
                viewing_user_is_leader = 'Leader' in role_names
            except Exception:
                pass
        
        # Determine which assignment sections to show based on the staff member being viewed
        # Client assignments are shown for staff members who have the Staff role
        # Program assignments are shown for staff members who have Manager/Leader roles
        staff_has_staff_role = staff.is_staff_only()
        staff_has_manager_role = staff.is_program_manager()
        staff_has_leader_role = staff.is_leader()
        
        show_client_assignments = staff_has_staff_role  # Show client assignments for staff members with Staff role
        
        # Only show program assignments for staff members who have Manager or Leader roles
        # AND the viewing user has appropriate permissions
        if staff_has_manager_role or staff_has_leader_role:
            if viewing_user_is_superadmin or viewing_user_is_admin or viewing_user_is_leader or viewing_user_is_manager:
                show_program_assignments = True
            else:
                show_program_assignments = False
        else:
            show_program_assignments = False  # Don't show program assignments for Staff role users
        
        show_assignments = show_client_assignments or show_program_assignments  # Overall flag for any assignments
        
        context['show_assignments'] = show_assignments
        context['show_client_assignments'] = show_client_assignments
        context['show_program_assignments'] = show_program_assignments
        
        
        # Add context for template to check if user can manage client assignments
        # SuperAdmin, Admin, and Staff role users can manage client assignments
        context['can_manage_client_assignments'] = viewing_user_is_superadmin or viewing_user_is_admin or viewing_user_is_staff
        
        

        if show_assignments:
            # Get staff client assignments
            context['staff_client_assignments'] = StaffClientAssignment.objects.filter(
                staff=staff, 
                is_active=True
            ).select_related('client')

            # Get staff program assignments
            context['staff_program_assignments'] = StaffProgramAssignment.objects.filter(
                staff=staff, 
                is_active=True
            ).select_related('program', 'program__department')

            # Check if staff has program manager role
            has_program_manager_role = staff.is_program_manager()
            context['has_program_manager_role'] = has_program_manager_role

            # Check if staff has only Staff role
            has_staff_only_role = staff.is_staff_only()
            context['has_staff_only_role'] = has_staff_only_role

            # Check if staff has Leader role
            has_leader_role = staff.is_leader()
            context['has_leader_role'] = has_leader_role

            if has_program_manager_role:
                context['assigned_programs'] = ProgramManagerAssignment.objects.filter(
                    staff=staff,
                    is_active=True
                ).select_related('program', 'program__department')

            if has_staff_only_role:
                context['staff_assigned_programs'] = StaffProgramAssignment.objects.filter(
                    staff=staff,
                    is_active=True
                ).select_related('program', 'program__department')

            if has_leader_role:
                from core.models import DepartmentLeaderAssignment
                context['department_assignments'] = DepartmentLeaderAssignment.objects.filter(
                    staff=staff,
                    is_active=True
                ).select_related('department')
        else:
            # For Admin/SuperAdmin users, don't load assignment data
            context['staff_client_assignments'] = []
            context['staff_program_assignments'] = []
            context['has_program_manager_role'] = False
            context['has_staff_only_role'] = False
            context['has_leader_role'] = False
            context['assigned_programs'] = []
            context['staff_assigned_programs'] = []
            context['department_assignments'] = []
        
        return context

@method_decorator(require_roles('SuperAdmin', 'Admin'), name='dispatch')
class StaffCreateView(CreateView):
    model = Staff
    template_name = 'staff/staff_form.html'
    fields = ['first_name', 'last_name', 'email', 'active']
    success_url = reverse_lazy('staff:list')

    def form_valid(self, form):
        """Override to create both User and Staff records"""
        try:
            # Get form data
            first_name = form.cleaned_data['first_name']
            last_name = form.cleaned_data['last_name']
            email = form.cleaned_data['email']
            active = form.cleaned_data['active']

            # Create username from email (before @ symbol)
            username = email.split('@')[0]
            
            # Ensure username is unique
            base_username = username
            counter = 1
            while User.objects.filter(username=username).exists():
                username = f"{base_username}{counter}"
                counter += 1

            # Create User record first
            user = User.objects.create_user(
                email=email,
                username=username,
                first_name=first_name,
                last_name=last_name,
                is_staff=True,
                is_active=active
            )

            # Create Staff record linked to the User
            staff = Staff.objects.create(
                user=user,
                first_name=first_name,
                last_name=last_name,
                email=email,
                active=active
            )

            messages.success(
                self.request, 
                f'Staff member {first_name} {last_name} has been created successfully.'
            )
            return redirect(self.success_url)

        except Exception as e:
            messages.error(self.request, f'Error creating staff member: {str(e)}')
            return self.form_invalid(form)

@method_decorator(require_roles('SuperAdmin', 'Admin'), name='dispatch')
class StaffUpdateView(UpdateView):
    model = Staff
    template_name = 'staff/staff_form.html'
    fields = ['first_name', 'last_name', 'email', 'active']
    slug_field = 'external_id'
    slug_url_kwarg = 'external_id'
    success_url = reverse_lazy('staff:list')

    def form_valid(self, form):
        """Override to also update the linked User record if it exists"""
        try:
            staff = form.save(commit=False)
            
            # Update the linked User record if it exists
            if staff.user:
                staff.user.first_name = staff.first_name
                staff.user.last_name = staff.last_name
                staff.user.email = staff.email
                staff.user.is_active = staff.active
                staff.user.save()
            
            staff.save()
            
            messages.success(
                self.request, 
                f'Staff member {staff.first_name} {staff.last_name} has been updated successfully.'
            )
            return redirect(self.success_url)
            
        except Exception as e:
            messages.error(self.request, f'Error updating staff member: {str(e)}')
            return self.form_invalid(form)

@method_decorator(require_roles('SuperAdmin', 'Admin'), name='dispatch')
class StaffDeleteView(DeleteView):
    model = Staff
    template_name = 'staff/staff_confirm_delete.html'
    slug_field = 'external_id'
    slug_url_kwarg = 'external_id'
    success_url = reverse_lazy('staff:list')

    def form_valid(self, form):
        """Override to delete both Staff and linked User records"""
        try:
            # Check confirmation text
            confirmation = self.request.POST.get('confirmation_name', '').strip().upper()
            if confirmation != 'DELETE':
                messages.error(self.request, 'Please type "DELETE" to confirm deletion.')
                return self.form_invalid(form)
            
            staff = self.get_object()
            staff_name = f"{staff.first_name} {staff.last_name}"
            
            # Delete the linked User record if it exists
            if staff.user:
                user_email = staff.user.email
                user = staff.user
                # Clear the relationship first to avoid cascade issues
                staff.user = None
                staff.save()
                user.delete()
                print(f"Deleted user: {user_email}")
            
            # Delete the Staff record
            staff.delete()
            print(f"Deleted staff: {staff_name}")
            
            messages.success(
                self.request, 
                f'Staff member {staff_name} and their user account have been deleted successfully.'
            )
            return redirect(self.success_url)
            
        except Exception as e:
            print(f"Error deleting staff member: {str(e)}")
            messages.error(self.request, f'Error deleting staff member: {str(e)}')
            return redirect(self.success_url)

@login_required
@require_roles('SuperAdmin', 'Admin')
def upgrade_user_to_staff(request, external_id):
    """Upgrade a regular user to staff status"""
    if request.method == 'POST':
        try:
            user = get_object_or_404(User, external_id=external_id)
            
            # Create staff profile if it doesn't exist
            staff, created = Staff.objects.get_or_create(
                user=user,
                defaults={
                    'first_name': user.first_name,
                    'last_name': user.last_name,
                    'email': user.email,
                    'active': True
                }
            )
            
            # Update user to staff status
            user.is_staff = True
            user.save(update_fields=['is_staff'])
            
            if created:
                messages.success(request, f'User {user.first_name} {user.last_name} has been upgraded to staff.')
            else:
                messages.info(request, f'User {user.first_name} {user.last_name} is already a staff member.')
            
            return redirect('staff:detail', external_id=staff.external_id)
        except Exception as e:
            messages.error(request, f'Error upgrading user: {str(e)}')
            return redirect('staff:list')
    
    return redirect('staff:list')

    
@method_decorator(require_roles('SuperAdmin', 'Admin'), name='dispatch')
class StaffRoleManageView(DetailView):
    """View for managing staff roles"""
    model = Staff
    template_name = 'staff/staff_role_manage.html'
    context_object_name = 'staff_member'
    slug_field = 'external_id'
    slug_url_kwarg = 'external_id'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        staff = self.get_object()
        context['role_form'] = StaffRoleForm(staff=staff)
        context['current_roles'] = staff.staffrole_set.select_related('role').all()
        context['available_roles'] = Role.objects.all()
        return context

    def post(self, request, *args, **kwargs):
        staff = self.get_object()
        form = StaffRoleForm(request.POST, staff=staff)
        
        if form.is_valid():
            form.save(staff)
            messages.success(request, f'Roles updated successfully for {staff.first_name} {staff.last_name}')
            return redirect('staff:detail', external_id=staff.external_id)
        else:
            messages.error(request, 'There was an error updating roles.')
            return self.get(request, *args, **kwargs)


@login_required
@require_roles('SuperAdmin', 'Admin')
def update_staff_roles(request, external_id):
    """AJAX endpoint for updating staff roles"""
    if request.method == 'POST':
        staff = get_object_or_404(Staff, external_id=external_id)
        role_ids = request.POST.getlist('roles')
        
        try:
            # Clear existing roles
            staff.staffrole_set.all().delete()
            
            # Add new roles
            for role_id in role_ids:
                role = Role.objects.get(id=role_id)
                StaffRole.objects.create(staff=staff, role=role)
            
            return JsonResponse({'success': True, 'message': 'Roles updated successfully'})
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})
    
    return JsonResponse({'success': False, 'message': 'Invalid request method'})


@login_required
@require_roles('SuperAdmin', 'Admin')
def toggle_staff_role(request, external_id):
    """AJAX endpoint for toggling staff roles - supports multiple roles"""
    if request.method == 'POST':
        import json
        staff = get_object_or_404(Staff, external_id=external_id)
        data = json.loads(request.body)
        role_id = data.get('role_id')
        action = data.get('action')  # 'add' or 'remove'
        
        try:
            role = Role.objects.get(id=role_id)
            
            if action == 'add':
                # Check if role already exists
                if not StaffRole.objects.filter(staff=staff, role=role).exists():
                    StaffRole.objects.create(staff=staff, role=role)
                    message = f'Role "{role.name}" assigned successfully'
                else:
                    message = f'Role "{role.name}" is already assigned'
            elif action == 'remove':
                # Remove the specific role
                deleted_count = StaffRole.objects.filter(staff=staff, role=role).delete()[0]
                if deleted_count > 0:
                    message = f'Role "{role.name}" removed successfully'
                else:
                    message = f'Role "{role.name}" was not assigned'
            else:
                return JsonResponse({'success': False, 'message': 'Invalid action'})
            
            # Get current roles for response
            current_roles = list(staff.staffrole_set.all().values_list('role__name', flat=True))
            
            return JsonResponse({
                'success': True, 
                'message': message,
                'current_roles': current_roles
            })
        except Role.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'Role not found'})
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})
    
    return JsonResponse({'success': False, 'message': 'Invalid request method'})



@login_required
@require_roles('SuperAdmin', 'Admin', 'Manager', 'Leader')  # SuperAdmin, Admin, Manager, and Leader roles can manage program manager assignments
def manage_program_assignments(request, external_id):
    """View for managing program assignments for program managers - Manager and Leader roles only"""
    staff = get_object_or_404(Staff, external_id=external_id)
    
    # Check if staff has program manager role
    has_program_manager_role = staff.is_program_manager()
    
    if not has_program_manager_role:
        messages.error(request, 'This staff member does not have the Manager role.')
        return redirect('staff:detail', external_id=staff.external_id)
    
    if request.method == 'POST':
        form = ProgramManagerAssignmentForm(request.POST, staff=staff)
        if form.is_valid():
            # Get the current user's staff profile
            try:
                assigned_by = request.user.staff_profile
            except:
                assigned_by = None
            
            form.save(staff, assigned_by)
            messages.success(request, f'Program assignments updated successfully for {staff.first_name} {staff.last_name}')
            return redirect('staff:detail', external_id=staff.external_id)
    else:
        form = ProgramManagerAssignmentForm(staff=staff)
    
    # Get current program assignments
    current_program_assignments = ProgramManagerAssignment.objects.filter(
        staff=staff, 
        is_active=True
    ).select_related('program', 'program__department')
    
    # Get all available programs grouped by department
    from collections import defaultdict
    programs_by_department = defaultdict(list)
    for program in Program.objects.filter(status='active').select_related('department'):
        programs_by_department[program.department].append(program)
    
    context = {
        'staff_member': staff,
        'form': form,
        'current_program_assignments': current_program_assignments,
        'programs_by_department': dict(programs_by_department),
    }
    
    return render(request, 'staff/staff_program_assignments.html', context)




@login_required
@require_roles('SuperAdmin', 'Admin', 'Manager', 'Leader')  # SuperAdmin, Admin, Manager, and Leader roles can manage program assignments
def manage_program_assignments_staff(request, external_id):
    """View for managing program assignments for staff members - Staff, Manager, and Leader roles"""
    staff = get_object_or_404(Staff, external_id=external_id)
    
    # Check if staff member has Manager role - redirect to existing manager assignment system
    if staff.is_program_manager():
        messages.info(request, 'Manager role users use the existing program assignment system.')
        return redirect('staff:detail', external_id=staff.external_id)
    
    if request.method == 'POST':
        form = StaffProgramAssignmentForm(request.POST, staff=staff)
        if form.is_valid():
            try:
                # Get the current user's staff profile
                assigned_by = request.user.staff_profile
                form.save(staff, assigned_by)
                messages.success(request, f'Program assignments updated successfully for {staff.first_name} {staff.last_name}')
                return redirect('staff:detail', external_id=staff.external_id)
            except Exception as e:
                messages.error(request, f'Error updating program assignments: {str(e)}')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = StaffProgramAssignmentForm(staff=staff)
    
    # Get current program assignments
    current_program_assignments = StaffProgramAssignment.objects.filter(
        staff=staff, 
        is_active=True
    ).select_related('program', 'program__department')
    
    # Get all available programs grouped by department
    from collections import defaultdict
    programs_by_department = defaultdict(list)
    for program in Program.objects.filter(status='active').select_related('department'):
        programs_by_department[program.department].append(program)
    
    context = {
        'staff_member': staff,
        'form': form,
        'current_program_assignments': current_program_assignments,
        'programs_by_department': dict(programs_by_department),
    }
    
    return render(request, 'staff/staff_program_assignments_staff.html', context)


@login_required
@require_roles('SuperAdmin', 'Admin')
def manage_department_assignments(request, external_id):
    """Manage department assignments for Leader role users"""
    staff = get_object_or_404(Staff, external_id=external_id)
    
    # Check if staff has Leader role
    if not staff.is_leader():
        messages.error(request, 'This staff member does not have Leader role.')
        return redirect('staff:detail', external_id=external_id)
    
    if request.method == 'POST':
        department_ids = request.POST.getlist('departments')
        
        # Remove existing assignments
        DepartmentLeaderAssignment.objects.filter(staff=staff).update(is_active=False)
        
        # Add new assignments
        for department_id in department_ids:
            department = get_object_or_404(Department, id=department_id)
            assignment, created = DepartmentLeaderAssignment.objects.get_or_create(
                staff=staff,
                department=department,
                defaults={
                    'assigned_by': request.user.staff_profile,
                    'is_active': True
                }
            )
            if not created:
                assignment.is_active = True
                assignment.assigned_by = request.user.staff_profile
                assignment.save()
        
        messages.success(request, f'Department assignments updated for {staff.first_name} {staff.last_name}.')
        return redirect('staff:detail', external_id=external_id)
    
    # Get current department assignments
    current_department_assignments = DepartmentLeaderAssignment.objects.filter(
        staff=staff,
        is_active=True
    ).select_related('department')
    
    # Get all available departments
    available_departments = Department.objects.all().order_by('name')
    
    context = {
        'staff_member': staff,
        'current_department_assignments': current_department_assignments,
        'available_departments': available_departments,
    }
    
    return render(request, 'staff/manage_department_assignments.html', context)


@login_required
@require_roles('Staff')  # Only Staff role users can manage client assignments
def manage_client_assignments(request, external_id):
    """Manage client assignments for Staff role users"""
    staff = get_object_or_404(Staff, external_id=external_id)
    
    # Check if staff has Staff role
    if not staff.is_staff_only():
        messages.error(request, 'This staff member does not have Staff role.')
        return redirect('staff:detail', external_id=external_id)
    
    if request.method == 'POST':
        form = StaffClientAssignmentForm(request.POST, staff=staff)
        if form.is_valid():
            try:
                # Get the current user's staff profile
                assigned_by = request.user.staff_profile
                form.save(staff, assigned_by)
                messages.success(request, f'Client assignments updated successfully for {staff.first_name} {staff.last_name}')
                return redirect('staff:detail', external_id=staff.external_id)
            except Exception as e:
                messages.error(request, f'Error updating client assignments: {str(e)}')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = StaffClientAssignmentForm(staff=staff)
    
    # Get current client assignments
    current_client_assignments = StaffClientAssignment.objects.filter(
        staff=staff, 
        is_active=True
    ).select_related('client')
    
    # Get all available clients (showing all clients for now to debug)
    available_clients = Client.objects.all().order_by('first_name', 'last_name')
    
    context = {
        'staff_member': staff,
        'form': form,
        'current_client_assignments': current_client_assignments,
        'available_clients': available_clients,
    }
    
    return render(request, 'staff/manage_client_assignments.html', context)