from django import forms
from core.models import Role, StaffRole, Client
from programs.models import Program
from .models import StaffProgramAssignment, StaffClientAssignment



class StaffRoleForm(forms.Form):
    """Form for managing staff roles"""
    roles = forms.ModelMultipleChoiceField(
        queryset=Role.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="Assign Roles"
    )
    
    def __init__(self, *args, **kwargs):
        staff = kwargs.pop('staff', None)
        super().__init__(*args, **kwargs)
        
        if staff:
            # Pre-select current roles
            current_roles = staff.staffrole_set.values_list('role_id', flat=True)
            self.fields['roles'].initial = list(current_roles)
    
    def save(self, staff):
        """Save role assignments for the staff member"""
        selected_roles = self.cleaned_data['roles']
        
        # Remove existing roles
        staff.staffrole_set.all().delete()
        
        # Add new roles
        for role in selected_roles:
            StaffRole.objects.create(staff=staff, role=role)

        if staff.user:
            staff.user.is_staff = True
            staff.user.save(update_fields=['is_staff'])

class ProgramManagerAssignmentForm(forms.Form):
    """Form for assigning programs to program managers"""
    programs = forms.ModelMultipleChoiceField(
        queryset=Program.objects.filter(status='active'),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="Assign Programs"
    )
    
    def __init__(self, *args, **kwargs):
        staff = kwargs.pop('staff', None)
        super().__init__(*args, **kwargs)
        
        if staff:
            # Pre-select currently assigned programs
            from core.models import ProgramManagerAssignment
            current_programs = ProgramManagerAssignment.objects.filter(
                staff=staff, 
                is_active=True
            ).values_list('program_id', flat=True)
            self.fields['programs'].initial = list(current_programs)
    
    def save(self, staff, assigned_by):
        """Save program assignments for the program manager"""
        from core.models import ProgramManagerAssignment
        
        selected_programs = self.cleaned_data['programs']
        
        # Deactivate all current assignments
        ProgramManagerAssignment.objects.filter(staff=staff, is_active=True).update(is_active=False)
        
        # Create new assignments or reactivate existing ones
        for program in selected_programs:
            assignment, created = ProgramManagerAssignment.objects.update_or_create(
                staff=staff,
                program=program,
                defaults={
                    'is_active': True,
                    'assigned_by': assigned_by
                }
            )




class StaffProgramAssignmentForm(forms.Form):
    """Form for assigning programs to staff members"""
    programs = forms.ModelMultipleChoiceField(
        queryset=Program.objects.filter(status='active'),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="Assign Programs"
    )
    
    def __init__(self, *args, **kwargs):
        staff = kwargs.pop('staff', None)
        super().__init__(*args, **kwargs)
        
        if staff:
            # Pre-select currently assigned programs
            current_programs = StaffProgramAssignment.objects.filter(
                staff=staff, 
                is_active=True
            ).values_list('program_id', flat=True)
            self.fields['programs'].initial = list(current_programs)
    
    def save(self, staff, assigned_by):
        """Save program assignments for the staff member"""
        selected_programs = self.cleaned_data['programs']
        
        # Deactivate all current program assignments
        StaffProgramAssignment.objects.filter(staff=staff, is_active=True).update(is_active=False)
        
        # Create new assignments or reactivate existing ones
        for program in selected_programs:
            assignment, created = StaffProgramAssignment.objects.update_or_create(
                staff=staff,
                program=program,
                defaults={
                    'is_active': True,
                    'assigned_by': assigned_by
                }
            )


class StaffClientAssignmentForm(forms.Form):
    """Form for assigning clients to staff members"""
    clients = forms.ModelMultipleChoiceField(
        queryset=Client.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label="Assign Clients"
    )
    
    def __init__(self, *args, **kwargs):
        staff = kwargs.pop('staff', None)
        super().__init__(*args, **kwargs)
        
        if staff:
            # Pre-select currently assigned clients
            current_clients = StaffClientAssignment.objects.filter(
                staff=staff, 
                is_active=True
            ).values_list('client_id', flat=True)
            self.fields['clients'].initial = list(current_clients)
    
    def save(self, staff, assigned_by):
        """Save client assignments for the staff member"""
        selected_clients = self.cleaned_data['clients']
        
        # Deactivate all current client assignments
        StaffClientAssignment.objects.filter(staff=staff, is_active=True).update(is_active=False)
        
        # Create new assignments or reactivate existing ones
        for client in selected_clients:
            assignment, created = StaffClientAssignment.objects.update_or_create(
                staff=staff,
                client=client,
                defaults={
                    'is_active': True,
                    'assigned_by': assigned_by
                }
            )