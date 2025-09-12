from django.shortcuts import render
from django.views.generic import ListView, TemplateView
from django.http import HttpResponse
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