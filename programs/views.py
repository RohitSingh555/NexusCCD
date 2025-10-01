from django.shortcuts import render
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy
from core.models import Program
from core.views import ProgramManagerAccessMixin

class ProgramListView(ProgramManagerAccessMixin, ListView):
    model = Program
    template_name = 'programs/program_list.html'
    context_object_name = 'programs'
    paginate_by = 10
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Add capacity information for each program
        programs_with_capacity = []
        for program in context['programs']:
            program_data = {
                'program': program,
                'current_enrollments': program.get_current_enrollments_count(),
                'available_capacity': program.get_available_capacity(),
                'capacity_percentage': round(program.get_capacity_percentage(), 1),
                'is_at_capacity': program.is_at_capacity()
            }
            programs_with_capacity.append(program_data)
        
        context['programs_with_capacity'] = programs_with_capacity
        return context

class ProgramDetailView(ProgramManagerAccessMixin, DetailView):
    model = Program
    template_name = 'programs/program_detail.html'
    context_object_name = 'program'
    slug_field = 'external_id'
    slug_url_kwarg = 'external_id'

class ProgramCreateView(CreateView):
    model = Program
    template_name = 'programs/program_form.html'
    fields = ['name', 'department', 'location', 'capacity_current', 'capacity_effective_date']
    success_url = reverse_lazy('programs:list')

class ProgramUpdateView(ProgramManagerAccessMixin, UpdateView):
    model = Program
    template_name = 'programs/program_form.html'
    fields = ['name', 'department', 'location', 'capacity_current', 'capacity_effective_date']
    slug_field = 'external_id'
    slug_url_kwarg = 'external_id'
    success_url = reverse_lazy('programs:list')

class ProgramDeleteView(ProgramManagerAccessMixin, DeleteView):
    model = Program
    template_name = 'programs/program_confirm_delete.html'
    slug_field = 'external_id'
    slug_url_kwarg = 'external_id'
    success_url = reverse_lazy('programs:list')