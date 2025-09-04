from django.shortcuts import render
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy
from core.models import Program

class ProgramListView(ListView):
    model = Program
    template_name = 'programs/program_list.html'
    context_object_name = 'programs'
    paginate_by = 20

class ProgramDetailView(DetailView):
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

class ProgramUpdateView(UpdateView):
    model = Program
    template_name = 'programs/program_form.html'
    fields = ['name', 'department', 'location', 'capacity_current', 'capacity_effective_date']
    slug_field = 'external_id'
    slug_url_kwarg = 'external_id'
    success_url = reverse_lazy('programs:list')

class ProgramDeleteView(DeleteView):
    model = Program
    template_name = 'programs/program_confirm_delete.html'
    slug_field = 'external_id'
    slug_url_kwarg = 'external_id'
    success_url = reverse_lazy('programs:list')