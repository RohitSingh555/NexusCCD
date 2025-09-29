from django.shortcuts import render, get_object_or_404, redirect
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy
from django.contrib import messages
from django.http import JsonResponse
from django.contrib.auth import get_user_model
from core.models import Staff, Role, StaffRole, User
from .forms import StaffRoleForm
import uuid

class StaffListView(ListView):
    model = Staff
    template_name = 'staff/staff_list.html'
    context_object_name = 'staff'
    paginate_by = 10

    def get_queryset(self):
        queryset = super().get_queryset()
        # Add role information to each staff member
        for staff in queryset:
            staff.current_roles = staff.staffrole_set.select_related('role').all()
        return queryset

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
        context['available_roles'] = Role.objects.all()
        return context

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

class StaffDeleteView(DeleteView):
    model = Staff
    template_name = 'staff/staff_confirm_delete.html'
    slug_field = 'external_id'
    slug_url_kwarg = 'external_id'
    success_url = reverse_lazy('staff:list')

    def delete(self, request, *args, **kwargs):
        """Override to delete both Staff and linked User records"""
        try:
            staff = self.get_object()
            staff_name = f"{staff.first_name} {staff.last_name}"
            
            # Delete the linked User record if it exists
            if staff.user:
                staff.user.delete()
            
            # Delete the Staff record
            staff.delete()
            
            messages.success(
                request, 
                f'Staff member {staff_name} and their user account have been deleted successfully.'
            )
            return redirect(self.success_url)
            
        except Exception as e:
            messages.error(request, f'Error deleting staff member: {str(e)}')
            return redirect(self.success_url)

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