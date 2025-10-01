from django import forms
from core.models import Staff, Role, StaffRole
from programs.models import ProgramService, Program



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