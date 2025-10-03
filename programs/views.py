from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy
from django.utils import timezone
from django.db import models
from core.models import Program, Department
from core.views import jwt_required, ProgramManagerAccessMixin
from django.utils.decorators import method_decorator

@method_decorator(jwt_required, name='dispatch')
class ProgramListView(ProgramManagerAccessMixin, ListView):
    model = Program
    template_name = 'programs/program_list.html'
    context_object_name = 'programs'
    paginate_by = 20

    def get_queryset(self):
        # First apply the ProgramManagerAccessMixin filtering
        queryset = super().get_queryset()
        
        # Apply additional filters
        department_filter = self.request.GET.get('department', '')
        status_filter = self.request.GET.get('status', '')
        capacity_filter = self.request.GET.get('capacity', '')
        search_query = self.request.GET.get('search', '').strip()
        
        if department_filter:
            queryset = queryset.filter(department__name=department_filter)
        
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        if capacity_filter:
            if capacity_filter == 'at_capacity':
                # Filter programs that are at or over capacity
                queryset = [p for p in queryset if p.is_at_capacity()]
            elif capacity_filter == 'available':
                # Filter programs with available capacity
                queryset = [p for p in queryset if not p.is_at_capacity() and p.get_available_capacity() > 0]
            elif capacity_filter == 'no_limit':
                # Filter programs with no capacity limit
                queryset = queryset.filter(capacity_current__lte=0)
        
        if search_query:
            from django.db.models import Q
            queryset = queryset.filter(
                Q(name__icontains=search_query) |
                Q(department__name__icontains=search_query) |
                Q(location__icontains=search_query) |
                Q(description__icontains=search_query)
            ).distinct()
        
        return queryset
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        programs = context['programs']
        
        # Create program data with capacity information
        programs_with_capacity = []
        for program in programs:
            # Use total enrollments (including future) for display
            total_enrollments = program.get_total_enrollments_count()
            current_enrollments = program.get_current_enrollments_count()
            capacity_percentage = program.get_capacity_percentage()
            available_capacity = program.get_available_capacity()
            is_at_capacity = program.is_at_capacity()
            
            programs_with_capacity.append({
                'program': program,
                'current_enrollments': total_enrollments,  # Show total enrollments including future
                'capacity_percentage': capacity_percentage,
                'available_capacity': available_capacity,
                'is_at_capacity': is_at_capacity,
            })
        
        # Add filter options to context
        context['programs_with_capacity'] = programs_with_capacity
        context['departments'] = Department.objects.all().order_by('name')
        context['status_choices'] = Program.STATUS_CHOICES
        context['capacity_choices'] = [
            ('', 'All Programs'),
            ('at_capacity', 'At Capacity'),
            ('available', 'Has Available Spots'),
            ('no_limit', 'No Capacity Limit'),
        ]
        
        # Add current filter values
        context['current_department'] = self.request.GET.get('department', '')
        context['current_status'] = self.request.GET.get('status', '')
        context['current_capacity'] = self.request.GET.get('capacity', '')
        context['search_query'] = self.request.GET.get('search', '')
        
        return context

@method_decorator(jwt_required, name='dispatch')
class ProgramDetailView(ProgramManagerAccessMixin, DetailView):
    model = Program
    template_name = 'programs/program_detail.html'
    context_object_name = 'program'
    slug_field = 'external_id'
    slug_url_kwarg = 'external_id'
    
    def get_object(self, queryset=None):
        """Override to ensure program managers can only access their assigned programs"""
        obj = super().get_object(queryset)
        
        # The ProgramManagerAccessMixin should have already filtered the queryset
        # But let's double-check access here for extra security
        if not self.request.user.is_superuser:
            try:
                staff = self.request.user.staff_profile
                if staff.is_program_manager():
                    assigned_programs = staff.get_assigned_programs()
                    if obj not in assigned_programs:
                        from django.http import Http404
                        raise Http404("Program not found or access denied")
            except Exception:
                from django.http import Http404
                raise Http404("Program not found or access denied")
        
        return obj
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        program = context['program']
        
        # Get current enrollments
        from core.models import ClientProgramEnrollment
        current_enrollments = ClientProgramEnrollment.objects.filter(
            program=program,
            start_date__lte=timezone.now().date()
        ).filter(
            models.Q(end_date__isnull=True) | models.Q(end_date__gt=timezone.now().date())
        ).select_related('client')
        
        # Get program staff
        from core.models import ProgramStaff
        program_staff = ProgramStaff.objects.filter(program=program).select_related('staff')
        
        # Get capacity information
        current_enrollments_count = program.get_current_enrollments_count()
        capacity_percentage = program.get_capacity_percentage()
        available_capacity = program.get_available_capacity()
        is_at_capacity = program.is_at_capacity()
        
        # Get enrollment history (last 30 days)
        from datetime import timedelta
        thirty_days_ago = timezone.now().date() - timedelta(days=30)
        recent_enrollments = ClientProgramEnrollment.objects.filter(
            program=program,
            start_date__gte=thirty_days_ago
        ).select_related('client').order_by('-start_date')[:10]
        
        context.update({
            'current_enrollments': current_enrollments,
            'current_enrollments_count': current_enrollments_count,
            'capacity_percentage': capacity_percentage,
            'available_capacity': available_capacity,
            'is_at_capacity': is_at_capacity,
            'program_staff': program_staff,
            'recent_enrollments': recent_enrollments,
        })
        
        return context

@method_decorator(jwt_required, name='dispatch')
class ProgramCreateView(ProgramManagerAccessMixin, CreateView):
    model = Program
    template_name = 'programs/program_form.html'
    fields = ['name', 'department', 'location', 'capacity_current', 'capacity_effective_date']
    success_url = reverse_lazy('programs:list')
    
    def get_initial(self):
        """Set default values for the form"""
        initial = super().get_initial()
        # Get or create NA department
        na_department, _ = Department.objects.get_or_create(
            name='NA',
            defaults={'owner': 'System'}
        )
        initial['department'] = na_department
        return initial

@method_decorator(jwt_required, name='dispatch')
class ProgramUpdateView(ProgramManagerAccessMixin, UpdateView):
    model = Program
    template_name = 'programs/program_form.html'
    fields = ['name', 'department', 'location', 'capacity_current', 'capacity_effective_date']
    slug_field = 'external_id'
    slug_url_kwarg = 'external_id'
    success_url = reverse_lazy('programs:list')
    
    def get_object(self, queryset=None):
        """Override to ensure program managers can only edit their assigned programs"""
        obj = super().get_object(queryset)
        
        # The ProgramManagerAccessMixin should have already filtered the queryset
        # But let's double-check access here for extra security
        if not self.request.user.is_superuser:
            try:
                staff = self.request.user.staff_profile
                if staff.is_program_manager():
                    assigned_programs = staff.get_assigned_programs()
                    if obj not in assigned_programs:
                        from django.http import Http404
                        raise Http404("Program not found or access denied")
            except Exception:
                from django.http import Http404
                raise Http404("Program not found or access denied")
        
        return obj

@method_decorator(jwt_required, name='dispatch')
class ProgramDeleteView(ProgramManagerAccessMixin, DeleteView):
    model = Program
    template_name = 'programs/program_confirm_delete.html'
    slug_field = 'external_id'
    slug_url_kwarg = 'external_id'
    success_url = reverse_lazy('programs:list')
    
    def get_object(self, queryset=None):
        """Override to ensure program managers can only delete their assigned programs"""
        obj = super().get_object(queryset)
        
        # The ProgramManagerAccessMixin should have already filtered the queryset
        # But let's double-check access here for extra security
        if not self.request.user.is_superuser:
            try:
                staff = self.request.user.staff_profile
                if staff.is_program_manager():
                    assigned_programs = staff.get_assigned_programs()
                    if obj not in assigned_programs:
                        from django.http import Http404
                        raise Http404("Program not found or access denied")
            except Exception:
                from django.http import Http404
                raise Http404("Program not found or access denied")
        
        return obj