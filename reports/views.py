from django.shortcuts import render
from django.views.generic import ListView, TemplateView
from django.http import HttpResponse
from core.models import Client, Program, ClientProgramEnrollment

class ReportListView(ListView):
    template_name = 'reports/report_list.html'
    context_object_name = 'reports'
    
    def get_queryset(self):
        return [
            {'name': 'Organizational Summary', 'description': 'Client demographics and program statistics', 'url': 'organizational-summary'},
            {'name': 'Vacancy Tracker', 'description': 'Program capacity and enrollment tracking', 'url': 'vacancy-tracker'},
        ]

class OrganizationalSummaryView(TemplateView):
    template_name = 'reports/organizational_summary.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['total_clients'] = Client.objects.count()
        context['total_programs'] = Program.objects.count()
        context['active_enrollments'] = ClientProgramEnrollment.objects.filter(end_date__isnull=True).count()
        return context

class VacancyTrackerView(TemplateView):
    template_name = 'reports/vacancy_tracker.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        programs = Program.objects.all()
        program_data = []
        for program in programs:
            active_enrollments = ClientProgramEnrollment.objects.filter(
                program=program, 
                end_date__isnull=True
            ).count()
            program_data.append({
                'program': program,
                'capacity': program.capacity_current,
                'occupied': active_enrollments,
                'vacant': program.capacity_current - active_enrollments
            })
        context['program_data'] = program_data
        return context

class ReportExportView(TemplateView):
    def get(self, request, report_type):
        if report_type == 'organizational-summary':
            return HttpResponse("CSV export for organizational summary", content_type='text/csv')
        elif report_type == 'vacancy-tracker':
            return HttpResponse("CSV export for vacancy tracker", content_type='text/csv')
        return HttpResponse("Report not found", status=404)