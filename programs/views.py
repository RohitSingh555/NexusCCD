from django.shortcuts import render
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy
from django.contrib.auth.mixins import LoginRequiredMixin
from core.models import Program, Department
from core.views import jwt_required
from django.utils.decorators import method_decorator

@method_decorator(jwt_required, name='dispatch')
class ProgramListView(ListView):
    model = Program
    template_name = 'programs/program_list.html'
    context_object_name = 'programs'
    paginate_by = 20

    def get_queryset(self):
        return Program.objects.select_related('department').order_by('-created_at')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        programs = context['programs']
        
        # Create program data with capacity information
        programs_with_capacity = []
        for program in programs:
            current_enrollments = program.get_current_enrollments_count()
            capacity_percentage = program.get_capacity_percentage()
            available_capacity = program.get_available_capacity()
            is_at_capacity = program.is_at_capacity()
            
            programs_with_capacity.append({
                'program': program,
                'current_enrollments': current_enrollments,
                'capacity_percentage': capacity_percentage,
                'available_capacity': available_capacity,
                'is_at_capacity': is_at_capacity,
            })
        
        context['programs_with_capacity'] = programs_with_capacity
        return context

@method_decorator(jwt_required, name='dispatch')
class ProgramDetailView(DetailView):
    model = Program
    template_name = 'programs/program_detail.html'
    context_object_name = 'program'
    slug_field = 'external_id'
    slug_url_kwarg = 'external_id'

@method_decorator(jwt_required, name='dispatch')
class ProgramCreateView(CreateView):
    model = Program
    template_name = 'programs/program_form.html'
    fields = ['name', 'department', 'location', 'capacity_current', 'capacity_effective_date']
    success_url = reverse_lazy('programs:list')
    
    def get_initial(self):
        """Set default values for the form"""
        initial = super().get_initial()
        # Get or create NA department
        na_department, created = Department.objects.get_or_create(
            name='NA',
            defaults={'owner': 'System'}
        )
        initial['department'] = na_department
        return initial

@method_decorator(jwt_required, name='dispatch')
class ProgramUpdateView(UpdateView):
    model = Program
    template_name = 'programs/program_form.html'
    fields = ['name', 'department', 'location', 'capacity_current', 'capacity_effective_date']
    slug_field = 'external_id'
    slug_url_kwarg = 'external_id'
    success_url = reverse_lazy('programs:list')

@method_decorator(jwt_required, name='dispatch')
class ProgramDeleteView(DeleteView):
    model = Program
    template_name = 'programs/program_confirm_delete.html'
    slug_field = 'external_id'
    slug_url_kwarg = 'external_id'
    success_url = reverse_lazy('programs:list')