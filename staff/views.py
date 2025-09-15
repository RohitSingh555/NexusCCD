from django.shortcuts import render
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy
from core.models import Staff

class StaffListView(ListView):
    model = Staff
    template_name = 'staff/staff_list.html'
    context_object_name = 'staff'
    paginate_by = 10

class StaffDetailView(DetailView):
    model = Staff
    template_name = 'staff/staff_detail.html'
    context_object_name = 'staff_member'
    slug_field = 'external_id'
    slug_url_kwarg = 'external_id'

class StaffCreateView(CreateView):
    model = Staff
    template_name = 'staff/staff_form.html'
    fields = ['first_name', 'last_name', 'email', 'active']
    success_url = reverse_lazy('staff:list')

class StaffUpdateView(UpdateView):
    model = Staff
    template_name = 'staff/staff_form.html'
    fields = ['first_name', 'last_name', 'email', 'active']
    slug_field = 'external_id'
    slug_url_kwarg = 'external_id'
    success_url = reverse_lazy('staff:list')

class StaffDeleteView(DeleteView):
    model = Staff
    template_name = 'staff/staff_confirm_delete.html'
    slug_field = 'external_id'
    slug_url_kwarg = 'external_id'
    success_url = reverse_lazy('staff:list')