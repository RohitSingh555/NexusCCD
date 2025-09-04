from django.shortcuts import render
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django.urls import reverse_lazy
from core.models import Client

class ClientListView(ListView):
    model = Client
    template_name = 'clients/client_list.html'
    context_object_name = 'clients'
    paginate_by = 20

class ClientDetailView(DetailView):
    model = Client
    template_name = 'clients/client_detail.html'
    context_object_name = 'client'
    slug_field = 'external_id'
    slug_url_kwarg = 'external_id'

class ClientCreateView(CreateView):
    model = Client
    template_name = 'clients/client_form.html'
    fields = ['first_name', 'last_name', 'preferred_name', 'alias', 'dob', 'gender', 
              'sexual_orientation', 'languages_spoken', 'race', 'immigration_status', 
              'phone_number', 'email', 'address', 'uid_external']
    success_url = reverse_lazy('clients:list')

class ClientUpdateView(UpdateView):
    model = Client
    template_name = 'clients/client_form.html'
    fields = ['first_name', 'last_name', 'preferred_name', 'alias', 'dob', 'gender', 
              'sexual_orientation', 'languages_spoken', 'race', 'immigration_status', 
              'phone_number', 'email', 'address', 'uid_external']
    slug_field = 'external_id'
    slug_url_kwarg = 'external_id'
    success_url = reverse_lazy('clients:list')

class ClientDeleteView(DeleteView):
    model = Client
    template_name = 'clients/client_confirm_delete.html'
    slug_field = 'external_id'
    slug_url_kwarg = 'external_id'
    success_url = reverse_lazy('clients:list')