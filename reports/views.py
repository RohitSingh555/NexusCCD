from django.shortcuts import render
from django.views.generic import ListView, TemplateView
from django.http import HttpResponse
from django.utils import timezone
from django.db import models
from datetime import datetime, date
import csv
from core.models import Client, Program, ClientProgramEnrollment, PendingChange

class ReportListView(ListView):
    template_name = 'reports/report_list.html'
    context_object_name = 'reports'
    
    def get_queryset(self):
        return [
            {'name': 'Organizational Summary', 'description': 'Client demographics and program statistics', 'url': 'organizational-summary'},
            {'name': 'Vacancy Tracker', 'description': 'Program capacity and enrollment tracking', 'url': 'vacancy-tracker'},
        ]
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['total_clients'] = Client.objects.count()
        context['active_programs'] = Program.objects.count()
        context['enrollment_rate'] = 75.5  # Placeholder - calculate actual rate
        context['pending_approvals'] = PendingChange.objects.filter(status='pending').count()
        context['recent_reports'] = []  # Placeholder for recent reports
        return context

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
        
        # Get date filter from query parameters
        as_of_date = self.request.GET.get('as_of_date')
        if as_of_date:
            try:
                as_of_date = datetime.strptime(as_of_date, '%Y-%m-%d').date()
            except ValueError:
                as_of_date = timezone.now().date()
        else:
            as_of_date = timezone.now().date()
        
        # Get department filter
        department_id = self.request.GET.get('department')
        
        programs = Program.objects.all()
        if department_id:
            programs = programs.filter(department_id=department_id)
        
        program_data = []
        for program in programs:
            # Get active enrollments as of the specified date
            active_enrollments = ClientProgramEnrollment.objects.filter(
                program=program,
                start_date__lte=as_of_date
            ).filter(
                models.Q(end_date__isnull=True) | models.Q(end_date__gt=as_of_date)
            ).count()
            
            # Use capacity_current for now (can be enhanced to use capacity_effective_date)
            capacity = program.capacity_current
            occupied = active_enrollments
            vacant = capacity - occupied
            
            program_data.append({
                'program': program,
                'capacity': capacity,
                'occupied': occupied,
                'vacant': vacant,
                'utilization': round((occupied / capacity * 100) if capacity > 0 else 0, 1)
            })
        
        context['program_data'] = program_data
        context['as_of_date'] = as_of_date
        context['departments'] = Program.objects.values_list('department_id', 'department__name').distinct()
        context['selected_department'] = department_id
        return context

class ReportExportView(TemplateView):
    def get(self, request, report_type):
        if report_type == 'organizational-summary':
            return self.export_organizational_summary(request)
        elif report_type == 'vacancy-tracker':
            return self.export_vacancy_tracker(request)
        return HttpResponse("Report not found", status=404)
    
    def export_vacancy_tracker(self, request):
        # Get the same data as the view
        as_of_date = request.GET.get('as_of_date')
        if as_of_date:
            try:
                as_of_date = datetime.strptime(as_of_date, '%Y-%m-%d').date()
            except ValueError:
                as_of_date = timezone.now().date()
        else:
            as_of_date = timezone.now().date()
        
        department_id = request.GET.get('department')
        
        programs = Program.objects.all()
        if department_id:
            programs = programs.filter(department_id=department_id)
        
        # Create CSV response
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="vacancy_tracker_{as_of_date.strftime("%Y%m%d")}.csv"'
        
        writer = csv.writer(response)
        
        # Write header
        writer.writerow([
            'Program Name',
            'Department',
            'Location',
            'Capacity',
            'Occupied',
            'Available',
            'Utilization %',
            'As Of Date'
        ])
        
        # Write data rows
        for program in programs:
            active_enrollments = ClientProgramEnrollment.objects.filter(
                program=program,
                start_date__lte=as_of_date
            ).filter(
                models.Q(end_date__isnull=True) | models.Q(end_date__gt=as_of_date)
            ).count()
            
            capacity = program.capacity_current
            occupied = active_enrollments
            vacant = capacity - occupied
            utilization = round((occupied / capacity * 100) if capacity > 0 else 0, 1)
            
            writer.writerow([
                program.name,
                program.department.name if program.department else '',
                program.location,
                capacity,
                occupied,
                vacant,
                f"{utilization}%",
                as_of_date.strftime('%Y-%m-%d')
            ])
        
        return response
    
    def export_organizational_summary(self, request):
        # Placeholder for organizational summary export
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="organizational_summary.csv"'
        writer = csv.writer(response)
        writer.writerow(['Report', 'Value'])
        writer.writerow(['Total Clients', Client.objects.count()])
        writer.writerow(['Total Programs', Program.objects.count()])
        writer.writerow(['Active Enrollments', ClientProgramEnrollment.objects.filter(end_date__isnull=True).count()])
        return response


# Additional Report Views
class ClientDemographicsView(TemplateView):
    template_name = 'reports/client_demographics.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        clients = Client.objects.all()
        
        # Age distribution
        age_groups = {
            '0-17': 0,
            '18-25': 0,
            '26-35': 0,
            '36-45': 0,
            '46-55': 0,
            '56-65': 0,
            '65+': 0
        }
        
        for client in clients:
            age = client.dob
            if age:
                from datetime import date
                today = date.today()
                age_years = today.year - age.year - ((today.month, today.day) < (age.month, age.day))
                
                if age_years <= 17:
                    age_groups['0-17'] += 1
                elif age_years <= 25:
                    age_groups['18-25'] += 1
                elif age_years <= 35:
                    age_groups['26-35'] += 1
                elif age_years <= 45:
                    age_groups['36-45'] += 1
                elif age_years <= 55:
                    age_groups['46-55'] += 1
                elif age_years <= 65:
                    age_groups['56-65'] += 1
                else:
                    age_groups['65+'] += 1
        
        # Gender distribution
        gender_counts = {}
        for client in clients:
            gender = client.gender or 'Unknown'
            gender_counts[gender] = gender_counts.get(gender, 0) + 1
        
        # Sort gender counts by count (descending) for better display
        gender_counts = dict(sorted(gender_counts.items(), key=lambda x: x[1], reverse=True))
        
        context.update({
            'total_clients': clients.count(),
            'age_groups': age_groups,
            'gender_counts': gender_counts,
        })
        return context


class ClientEnrollmentHistoryView(TemplateView):
    template_name = 'reports/client_enrollment_history.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        enrollments = ClientProgramEnrollment.objects.select_related('client', 'program').order_by('-start_date')
        
        context.update({
            'enrollments': enrollments,
            'total_enrollments': enrollments.count(),
        })
        return context


class ClientOutcomesView(TemplateView):
    template_name = 'reports/client_outcomes.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        enrollments = ClientProgramEnrollment.objects.all()
        
        completed = enrollments.filter(end_date__isnull=False).count()
        active = enrollments.filter(end_date__isnull=True).count()
        total = enrollments.count()
        
        success_rate = (completed / total * 100) if total > 0 else 0
        
        context.update({
            'total_enrollments': total,
            'completed_enrollments': completed,
            'active_enrollments': active,
            'success_rate': round(success_rate, 1),
        })
        return context


class ProgramCapacityView(TemplateView):
    template_name = 'reports/program_capacity.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        programs = Program.objects.all()
        
        program_data = []
        for program in programs:
            active_enrollments = ClientProgramEnrollment.objects.filter(
                program=program, 
                end_date__isnull=True
            ).count()
            
            utilization = (active_enrollments / program.capacity_current * 100) if program.capacity_current > 0 else 0
            
            program_data.append({
                'program': program,
                'capacity': program.capacity_current,
                'occupied': active_enrollments,
                'vacant': program.capacity_current - active_enrollments,
                'utilization': round(utilization, 1)
            })
        
        context.update({
            'program_data': program_data,
            'total_programs': programs.count(),
        })
        return context


class ProgramPerformanceView(TemplateView):
    template_name = 'reports/program_performance.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        programs = Program.objects.all()
        
        program_metrics = []
        for program in programs:
            total_enrollments = ClientProgramEnrollment.objects.filter(program=program).count()
            completed_enrollments = ClientProgramEnrollment.objects.filter(
                program=program, 
                end_date__isnull=False
            ).count()
            
            completion_rate = (completed_enrollments / total_enrollments * 100) if total_enrollments > 0 else 0
            
            program_metrics.append({
                'program': program,
                'total_enrollments': total_enrollments,
                'completed_enrollments': completed_enrollments,
                'completion_rate': round(completion_rate, 1)
            })
        
        context.update({
            'program_metrics': program_metrics,
        })
        return context


class DepartmentSummaryView(TemplateView):
    template_name = 'reports/department_summary.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from core.models import Department
        
        departments = Department.objects.all()
        department_data = []
        
        for dept in departments:
            programs = dept.program_set.all()
            total_capacity = sum(p.capacity_current for p in programs)
            
            total_enrollments = 0
            for program in programs:
                total_enrollments += ClientProgramEnrollment.objects.filter(program=program).count()
            
            department_data.append({
                'department': dept,
                'programs_count': programs.count(),
                'total_capacity': total_capacity,
                'total_enrollments': total_enrollments,
                'utilization': round((total_enrollments / total_capacity * 100), 1) if total_capacity > 0 else 0
            })
        
        context.update({
            'department_data': department_data,
            'total_departments': departments.count(),
        })
        return context