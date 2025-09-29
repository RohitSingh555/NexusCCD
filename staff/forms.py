from django import forms
from core.models import Staff, Role, StaffRole


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