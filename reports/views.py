from django.shortcuts import render
from django.views.generic import ListView, TemplateView
from django.http import HttpResponse
from django.utils import timezone
from django.db import models
from datetime import datetime, date
import csv
from core.models import Client, Program, ClientProgramEnrollment, Staff, Department

def get_date_range_filter(request):
    """Helper function to get date range filter parameters from request"""
    start_date = request.GET.get('start_date', '').strip()
    end_date = request.GET.get('end_date', '').strip()
    
    # Parse dates if provided
    parsed_start_date = None
    parsed_end_date = None
    
    if start_date:
        try:
            parsed_start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        except ValueError:
            parsed_start_date = None
    
    if end_date:
        try:
            parsed_end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        except ValueError:
            parsed_end_date = None
    
    return start_date, end_date, parsed_start_date, parsed_end_date

def get_program_manager_filtering(request):
    """Helper function to get program manager, leader, analyst, and staff-only filtering data"""
    is_program_manager = False
    is_leader = False
    is_analyst = False
    is_staff_only = False
    assigned_programs = None
    assigned_clients = None
    
    if request.user.is_authenticated:
        try:
            staff_profile = request.user.staff_profile
            user_roles = staff_profile.staffrole_set.select_related('role').all()
            role_names = [staff_role.role.name for staff_role in user_roles]
            
            if staff_profile.is_program_manager():
                is_program_manager = True
                assigned_programs = staff_profile.get_assigned_programs()
            elif staff_profile.is_leader():
                is_leader = True
                # Get assigned programs for leader users via departments using direct queries
                assigned_departments = Department.objects.filter(
                    leader_assignments__staff=staff_profile,
                    leader_assignments__is_active=True
                ).distinct()
                assigned_programs = Program.objects.filter(
                    department__in=assigned_departments
                ).distinct()
                # Get clients enrolled in assigned programs
                assigned_clients = Client.objects.filter(
                    clientprogramenrollment__program__in=assigned_programs
                ).distinct()
            elif 'Analyst' in role_names:
                is_analyst = True
                # Analysts see all data - no filtering needed
                assigned_programs = None
                assigned_clients = None
            elif staff_profile.is_staff_only():
                is_staff_only = True
                # Get directly assigned clients for staff users
                from staff.models import StaffClientAssignment
                assigned_clients = Client.objects.filter(
                    staff_assignments__staff=staff_profile,
                    staff_assignments__is_active=True
                ).distinct()
                # Get programs where assigned clients are enrolled
                assigned_programs = Program.objects.filter(
                    clientprogramenrollment__client__in=assigned_clients
                ).distinct()
        except Exception:
            pass
    
    return is_program_manager, is_leader, is_analyst, is_staff_only, assigned_programs, assigned_clients

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
        
        # Get date range filter parameters
        start_date, end_date, parsed_start_date, parsed_end_date = get_date_range_filter(self.request)
        context['start_date'] = start_date
        context['end_date'] = end_date
        
        # Get program manager and staff-only filtering
        is_program_manager, is_leader, is_analyst, is_staff_only, assigned_programs, assigned_clients = get_program_manager_filtering(self.request)
        
        # Filter data based on user role
        if is_analyst:
            # Analysts see all data across all clients and programs
            # Apply date filtering if provided
            client_queryset = Client.objects.all()
            if parsed_start_date:
                client_queryset = client_queryset.filter(created_at__date__gte=parsed_start_date)
            if parsed_end_date:
                client_queryset = client_queryset.filter(created_at__date__lte=parsed_end_date)
            
            context['total_clients'] = client_queryset.count()
            
            # Count programs that have enrollments within the date range
            program_queryset = Program.objects.filter(
                clientprogramenrollment__isnull=False
            ).distinct()
            
            if parsed_start_date:
                program_queryset = program_queryset.filter(
                    clientprogramenrollment__start_date__gte=parsed_start_date
                )
            if parsed_end_date:
                program_queryset = program_queryset.filter(
                    clientprogramenrollment__start_date__lte=parsed_end_date
                )
            
            context['active_programs'] = program_queryset.count()
            
            # Calculate enrollment rate for all programs
            total_capacity = 0
            active_enrollments = 0
            today = timezone.now().date()
            
            for program in Program.objects.all():
                total_capacity += program.capacity_current
                
                # Count active enrollments for this program with date filtering
                enrollment_queryset = ClientProgramEnrollment.objects.filter(
                    program=program,
                    start_date__lte=today
                ).filter(
                    models.Q(end_date__isnull=True) | models.Q(end_date__gt=today)
                )
                
                # Apply date filtering to enrollments
                if parsed_start_date:
                    enrollment_queryset = enrollment_queryset.filter(start_date__gte=parsed_start_date)
                if parsed_end_date:
                    enrollment_queryset = enrollment_queryset.filter(start_date__lte=parsed_end_date)
                
                program_active_enrollments = enrollment_queryset.count()
                active_enrollments += program_active_enrollments
        elif (is_program_manager or is_leader) and assigned_programs:
            # Program managers see only data for their assigned programs
            client_queryset = Client.objects.filter(
                clientprogramenrollment__program__in=assigned_programs
            ).distinct()
            
            # Apply date filtering if provided
            if parsed_start_date:
                client_queryset = client_queryset.filter(created_at__date__gte=parsed_start_date)
            if parsed_end_date:
                client_queryset = client_queryset.filter(created_at__date__lte=parsed_end_date)
            
            context['total_clients'] = client_queryset.count()
            
            # Count assigned programs that have enrollments within the date range
            program_queryset = assigned_programs.filter(
                clientprogramenrollment__isnull=False
            ).distinct()
            
            if parsed_start_date:
                program_queryset = program_queryset.filter(
                    clientprogramenrollment__start_date__gte=parsed_start_date
                )
            if parsed_end_date:
                program_queryset = program_queryset.filter(
                    clientprogramenrollment__start_date__lte=parsed_end_date
                )
            
            context['active_programs'] = program_queryset.count()
            
            # Calculate enrollment rate for assigned programs only
            total_capacity = 0
            active_enrollments = 0
            today = timezone.now().date()
            
            for program in assigned_programs:
                total_capacity += program.capacity_current
                
                # Count active enrollments for this program
                program_active_enrollments = ClientProgramEnrollment.objects.filter(
                    program=program,
                    start_date__lte=today
                ).filter(
                    models.Q(end_date__isnull=True) | models.Q(end_date__gt=today)
                ).count()
                
                active_enrollments += program_active_enrollments
        elif is_staff_only and assigned_clients:
            # Staff-only users see only data for their assigned clients and programs
            client_queryset = assigned_clients
            
            # Apply date filtering if provided
            if parsed_start_date:
                client_queryset = client_queryset.filter(created_at__date__gte=parsed_start_date)
            if parsed_end_date:
                client_queryset = client_queryset.filter(created_at__date__lte=parsed_end_date)
            
            context['total_clients'] = client_queryset.count()
            
            # Count assigned programs that have enrollments within the date range
            if assigned_programs:
                program_queryset = assigned_programs.filter(
                    clientprogramenrollment__isnull=False
                ).distinct()
                
                if parsed_start_date:
                    program_queryset = program_queryset.filter(
                        clientprogramenrollment__start_date__gte=parsed_start_date
                    )
                if parsed_end_date:
                    program_queryset = program_queryset.filter(
                        clientprogramenrollment__start_date__lte=parsed_end_date
                    )
                
                context['active_programs'] = program_queryset.count()
            else:
                context['active_programs'] = 0
            
            # Calculate enrollment rate for assigned programs only
            total_capacity = 0
            active_enrollments = 0
            today = timezone.now().date()
            
            for program in assigned_programs:
                total_capacity += program.capacity_current
                
                # Count active enrollments for this program with date filtering
                enrollment_queryset = ClientProgramEnrollment.objects.filter(
                    program=program,
                    start_date__lte=today
                ).filter(
                    models.Q(end_date__isnull=True) | models.Q(end_date__gt=today)
                )
                
                # Apply date filtering to enrollments
                if parsed_start_date:
                    enrollment_queryset = enrollment_queryset.filter(start_date__gte=parsed_start_date)
                if parsed_end_date:
                    enrollment_queryset = enrollment_queryset.filter(start_date__lte=parsed_end_date)
                
                program_active_enrollments = enrollment_queryset.count()
                active_enrollments += program_active_enrollments
        else:
            # SuperAdmin and Staff see all data
            # Apply date filtering if provided
            client_queryset = Client.objects.all()
            if parsed_start_date:
                client_queryset = client_queryset.filter(created_at__date__gte=parsed_start_date)
            if parsed_end_date:
                client_queryset = client_queryset.filter(created_at__date__lte=parsed_end_date)
            
            context['total_clients'] = client_queryset.count()
            
            # Count programs that have enrollments within the date range
            program_queryset = Program.objects.filter(
                clientprogramenrollment__isnull=False
            ).distinct()
            
            if parsed_start_date:
                program_queryset = program_queryset.filter(
                    clientprogramenrollment__start_date__gte=parsed_start_date
                )
            if parsed_end_date:
                program_queryset = program_queryset.filter(
                    clientprogramenrollment__start_date__lte=parsed_end_date
                )
            
            context['active_programs'] = program_queryset.count()
            
            # Calculate actual enrollment rate
            # Enrollment rate = (Total active enrollments / Total program capacity) * 100
            total_capacity = 0
            active_enrollments = 0
            today = timezone.now().date()
            
            for program in Program.objects.all():
                total_capacity += program.capacity_current
                
                # Count active enrollments for this program with date filtering
                enrollment_queryset = ClientProgramEnrollment.objects.filter(
                    program=program,
                    start_date__lte=today
                ).filter(
                    models.Q(end_date__isnull=True) | models.Q(end_date__gt=today)
                )
                
                # Apply date filtering to enrollments
                if parsed_start_date:
                    enrollment_queryset = enrollment_queryset.filter(start_date__gte=parsed_start_date)
                if parsed_end_date:
                    enrollment_queryset = enrollment_queryset.filter(start_date__lte=parsed_end_date)
                
                program_active_enrollments = enrollment_queryset.count()
                active_enrollments += program_active_enrollments
        
        # Calculate enrollment rate
        enrollment_rate = (active_enrollments / total_capacity * 100) if total_capacity > 0 else 0
        context['enrollment_rate'] = round(enrollment_rate, 1)
        
        context['recent_reports'] = []  # Placeholder for recent reports
        context['is_program_manager'] = is_program_manager
        return context

class OrganizationalSummaryView(TemplateView):
    template_name = 'reports/organizational_summary.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get date range filter parameters
        start_date, end_date, parsed_start_date, parsed_end_date = get_date_range_filter(self.request)
        context['start_date'] = start_date
        context['end_date'] = end_date
        
        # Get program manager and staff-only filtering
        is_program_manager, is_leader, is_analyst, is_staff_only, assigned_programs, assigned_clients = get_program_manager_filtering(self.request)
        
        # Filter data based on user role
        if is_analyst:
            # Analysts see all data across all clients and programs
            # Apply date filtering if provided
            client_queryset = Client.objects.all()
            if parsed_start_date:
                client_queryset = client_queryset.filter(created_at__date__gte=parsed_start_date)
            if parsed_end_date:
                client_queryset = client_queryset.filter(created_at__date__lte=parsed_end_date)
            
            context['total_clients'] = client_queryset.count()
            
            # Count programs that have enrollments within the date range
            program_queryset = Program.objects.filter(
                clientprogramenrollment__isnull=False
            ).distinct()
            
            if parsed_start_date:
                program_queryset = program_queryset.filter(
                    clientprogramenrollment__start_date__gte=parsed_start_date
                )
            if parsed_end_date:
                program_queryset = program_queryset.filter(
                    clientprogramenrollment__start_date__lte=parsed_end_date
                )
            
            context['total_programs'] = program_queryset.count()
            
            # Calculate active enrollments using date-based logic for all programs
            enrollments = ClientProgramEnrollment.objects.all()
            
            # Apply date filtering to enrollments
            if parsed_start_date:
                enrollments = enrollments.filter(start_date__gte=parsed_start_date)
            if parsed_end_date:
                enrollments = enrollments.filter(start_date__lte=parsed_end_date)
        elif (is_program_manager or is_leader) and assigned_programs:
            # Program managers see only data for their assigned programs
            client_queryset = Client.objects.filter(
                clientprogramenrollment__program__in=assigned_programs
            ).distinct()
            
            # Apply date filtering if provided
            if parsed_start_date:
                client_queryset = client_queryset.filter(created_at__date__gte=parsed_start_date)
            if parsed_end_date:
                client_queryset = client_queryset.filter(created_at__date__lte=parsed_end_date)
            
            context['total_clients'] = client_queryset.count()
            
            # Count assigned programs that have enrollments within the date range
            program_queryset = assigned_programs.filter(
                clientprogramenrollment__isnull=False
            ).distinct()
            
            if parsed_start_date:
                program_queryset = program_queryset.filter(
                    clientprogramenrollment__start_date__gte=parsed_start_date
                )
            if parsed_end_date:
                program_queryset = program_queryset.filter(
                    clientprogramenrollment__start_date__lte=parsed_end_date
                )
            
            context['total_programs'] = program_queryset.count()
            
            # Calculate active enrollments using date-based logic for assigned programs
            enrollments = ClientProgramEnrollment.objects.filter(program__in=assigned_programs)
            
            # Apply date filtering to enrollments
            if parsed_start_date:
                enrollments = enrollments.filter(start_date__gte=parsed_start_date)
            if parsed_end_date:
                enrollments = enrollments.filter(start_date__lte=parsed_end_date)
        elif is_staff_only and assigned_clients:
            # Staff-only users see only data for their assigned clients and programs
            client_queryset = assigned_clients
            
            # Apply date filtering if provided
            if parsed_start_date:
                client_queryset = client_queryset.filter(created_at__date__gte=parsed_start_date)
            if parsed_end_date:
                client_queryset = client_queryset.filter(created_at__date__lte=parsed_end_date)
            
            context['total_clients'] = client_queryset.count()
            
            # Count assigned programs that have enrollments within the date range
            if assigned_programs:
                program_queryset = assigned_programs.filter(
                    clientprogramenrollment__isnull=False
                ).distinct()
                
                if parsed_start_date:
                    program_queryset = program_queryset.filter(
                        clientprogramenrollment__start_date__gte=parsed_start_date
                    )
                if parsed_end_date:
                    program_queryset = program_queryset.filter(
                        clientprogramenrollment__start_date__lte=parsed_end_date
                    )
                
                context['total_programs'] = program_queryset.count()
            else:
                context['total_programs'] = 0
            
            # Calculate active enrollments using date-based logic for assigned programs
            enrollments = ClientProgramEnrollment.objects.filter(program__in=assigned_programs) if assigned_programs else ClientProgramEnrollment.objects.none()
            
            # Apply date filtering to enrollments
            if parsed_start_date:
                enrollments = enrollments.filter(start_date__gte=parsed_start_date)
            if parsed_end_date:
                enrollments = enrollments.filter(start_date__lte=parsed_end_date)
        else:
            # SuperAdmin and Staff see all data
            # Apply date filtering if provided
            client_queryset = Client.objects.all()
            if parsed_start_date:
                client_queryset = client_queryset.filter(created_at__date__gte=parsed_start_date)
            if parsed_end_date:
                client_queryset = client_queryset.filter(created_at__date__lte=parsed_end_date)
            
            context['total_clients'] = client_queryset.count()
            
            # Count programs that have enrollments within the date range
            program_queryset = Program.objects.filter(
                clientprogramenrollment__isnull=False
            ).distinct()
            
            if parsed_start_date:
                program_queryset = program_queryset.filter(
                    clientprogramenrollment__start_date__gte=parsed_start_date
                )
            if parsed_end_date:
                program_queryset = program_queryset.filter(
                    clientprogramenrollment__start_date__lte=parsed_end_date
                )
            
            context['total_programs'] = program_queryset.count()
            
            # Calculate active enrollments using date-based logic
            enrollments = ClientProgramEnrollment.objects.all()
            
            # Apply date filtering to enrollments
            if parsed_start_date:
                enrollments = enrollments.filter(start_date__gte=parsed_start_date)
            if parsed_end_date:
                enrollments = enrollments.filter(start_date__lte=parsed_end_date)
        
        today = timezone.now().date()
        active_count = 0
        for enrollment in enrollments:
            if today < enrollment.start_date:
                # Pending - not active yet
                continue
            elif enrollment.end_date:
                if today > enrollment.end_date:
                    # Completed - not active
                    continue
                else:
                    # Active - between start and end date
                    active_count += 1
            else:
                # Active - no end date set
                active_count += 1
        
        context['active_enrollments'] = active_count
        context['is_program_manager'] = is_program_manager
        
        # Add date range parameters to context
        context['start_date'] = start_date
        context['end_date'] = end_date
        
        return context

class VacancyTrackerView(TemplateView):
    template_name = 'reports/vacancy_tracker.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get program manager and staff-only filtering
        is_program_manager, is_leader, is_analyst, is_staff_only, assigned_programs, assigned_clients = get_program_manager_filtering(self.request)
        
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
        
        # Filter programs based on user role
        if is_analyst:
            # Analysts see all programs
            programs = Program.objects.all()
        elif (is_program_manager or is_leader) and assigned_programs:
            programs = assigned_programs
        elif is_staff_only:
            programs = assigned_programs if assigned_programs else Program.objects.none()
        else:
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
        context['is_program_manager'] = is_program_manager
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
        
        # Get program manager and staff-only filtering
        is_program_manager, is_leader, is_analyst, is_staff_only, assigned_programs, assigned_clients = get_program_manager_filtering(request)
        
        # Filter programs based on user role
        if is_analyst:
            # Analysts see all programs
            programs = Program.objects.all()
        elif (is_program_manager or is_leader) and assigned_programs:
            programs = assigned_programs
        elif is_staff_only:
            programs = assigned_programs if assigned_programs else Program.objects.none()
        else:
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
        
        # Get date range filter parameters
        start_date, end_date, parsed_start_date, parsed_end_date = get_date_range_filter(self.request)
        
        # Get program manager and staff-only filtering
        is_program_manager, is_leader, is_analyst, is_staff_only, assigned_programs, assigned_clients = get_program_manager_filtering(self.request)
        
        # Filter clients based on user role
        if (is_program_manager or is_leader) and assigned_programs:
            clients = Client.objects.filter(
                clientprogramenrollment__program__in=assigned_programs
            ).distinct()
        elif is_staff_only and assigned_clients:
            clients = assigned_clients
        else:
            clients = Client.objects.all()
        
        # Apply date range filtering if specified
        if parsed_start_date or parsed_end_date:
            if parsed_start_date and parsed_end_date:
                # Filter clients created within the date range
                clients = clients.filter(created_at__date__range=[parsed_start_date, parsed_end_date])
            elif parsed_start_date:
                clients = clients.filter(created_at__date__gte=parsed_start_date)
            elif parsed_end_date:
                clients = clients.filter(created_at__date__lte=parsed_end_date)
        
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
            'is_program_manager': is_program_manager,
            'start_date': start_date,
            'end_date': end_date,
        })
        return context


class ClientEnrollmentHistoryView(ListView):
    model = ClientProgramEnrollment
    template_name = 'reports/client_enrollment_history.html'
    context_object_name = 'enrollments'
    paginate_by = 10  # Default: Show 10 enrollments per page
    
    def get_paginate_by(self, queryset):
        """Get number of items to paginate by from request parameter"""
        per_page = self.request.GET.get('per_page', self.paginate_by)
        try:
            return int(per_page)
        except (ValueError, TypeError):
            return self.paginate_by
    
    def get_queryset(self):
        """Get enrollments ordered by most recent start date first"""
        # Get date range filter parameters
        start_date, end_date, parsed_start_date, parsed_end_date = get_date_range_filter(self.request)
        
        # Get program manager and staff-only filtering
        is_program_manager, is_leader, is_analyst, is_staff_only, assigned_programs, assigned_clients = get_program_manager_filtering(self.request)
        
        # Filter enrollments based on user role
        if (is_program_manager or is_leader) and assigned_programs:
            if assigned_programs:
                queryset = ClientProgramEnrollment.objects.filter(
                    program__in=assigned_programs
                ).select_related('client', 'program', 'program__department')
            else:
                return ClientProgramEnrollment.objects.none()
        elif is_staff_only:
            if assigned_programs:
                queryset = ClientProgramEnrollment.objects.filter(
                    program__in=assigned_programs
                ).select_related('client', 'program', 'program__department')
            else:
                return ClientProgramEnrollment.objects.none()
        else:
            queryset = ClientProgramEnrollment.objects.select_related('client', 'program', 'program__department')
        
        # Apply date filtering
        if parsed_start_date:
            queryset = queryset.filter(start_date__gte=parsed_start_date)
        if parsed_end_date:
            queryset = queryset.filter(start_date__lte=parsed_end_date)
        
        return queryset.order_by('-start_date')
    
    def get_context_data(self, **kwargs):
        """Add statistics to context"""
        context = super().get_context_data(**kwargs)
        
        # Get date range filter parameters
        start_date, end_date, parsed_start_date, parsed_end_date = get_date_range_filter(self.request)
        context['start_date'] = start_date
        context['end_date'] = end_date
        
        # Get program manager and staff-only filtering
        is_program_manager, is_leader, is_analyst, is_staff_only, assigned_programs, assigned_clients = get_program_manager_filtering(self.request)
        
        # Get all enrollments for statistics (not just current page)
        if (is_program_manager or is_leader) and assigned_programs:
            all_enrollments = ClientProgramEnrollment.objects.filter(program__in=assigned_programs)
        elif is_staff_only:
            all_enrollments = ClientProgramEnrollment.objects.filter(program__in=assigned_programs)
        else:
            all_enrollments = ClientProgramEnrollment.objects.all()
        
        # Apply date filtering to statistics
        if parsed_start_date:
            all_enrollments = all_enrollments.filter(start_date__gte=parsed_start_date)
        if parsed_end_date:
            all_enrollments = all_enrollments.filter(start_date__lte=parsed_end_date)
        today = timezone.now().date()
        
        # Calculate active, completed, and pending enrollments based on date logic
        active_count = 0
        completed_count = 0
        pending_count = 0
        
        for enrollment in all_enrollments:
            if today < enrollment.start_date:
                pending_count += 1
            elif enrollment.end_date:
                if today > enrollment.end_date:
                    completed_count += 1
                else:
                    active_count += 1
            else:
                active_count += 1
        
        context['total_enrollments'] = all_enrollments.count()
        context['active_enrollments'] = active_count
        context['completed_enrollments'] = completed_count
        context['pending_enrollments'] = pending_count
        
        # Add per_page to context for the template
        context['per_page'] = str(self.get_paginate_by(self.get_queryset()))
        context['is_program_manager'] = is_program_manager
        
        # Add date range parameters to context
        start_date, end_date, parsed_start_date, parsed_end_date = get_date_range_filter(self.request)
        context['start_date'] = start_date
        context['end_date'] = end_date
        
        return context


class ClientEnrollmentHistoryExportView(ListView):
    """Export client enrollment history to CSV"""
    model = ClientProgramEnrollment
    template_name = 'reports/client_enrollment_history.html'
    
    def get_queryset(self):
        """Get enrollments ordered by most recent start date first"""
        # Get program manager and staff-only filtering
        is_program_manager, is_leader, is_analyst, is_staff_only, assigned_programs, assigned_clients = get_program_manager_filtering(self.request)
        
        # Filter enrollments based on user role
        if (is_program_manager or is_leader) and assigned_programs:
            if assigned_programs:
                return ClientProgramEnrollment.objects.filter(
                    program__in=assigned_programs
                ).select_related('client', 'program', 'program__department').order_by('-start_date')
            else:
                return ClientProgramEnrollment.objects.none()
        elif is_staff_only:
            if assigned_programs:
                return ClientProgramEnrollment.objects.filter(
                    program__in=assigned_programs
                ).select_related('client', 'program', 'program__department').order_by('-start_date')
            else:
                return ClientProgramEnrollment.objects.none()
        else:
            return ClientProgramEnrollment.objects.select_related('client', 'program', 'program__department').order_by('-start_date')
    
    def get(self, request, *args, **kwargs):
        # Create CSV response
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = "attachment; filename=\"client_enrollment_history_export.csv\""
        
        # Create CSV writer
        writer = csv.writer(response)
        
        # Write header row
        writer.writerow([
            "Client Name",
            "Program Name",
            "Department",
            "Start Date",
            "End Date",
            "Status",
            "Duration (Days)"
        ])
        
        # Get enrollment data
        enrollments = self.get_queryset()
        
        # Write data rows
        for enrollment in enrollments:
            # Calculate duration in days and determine status based on current date
            today = timezone.now().date()
            if today < enrollment.start_date:
                duration = 0  # Not started yet
                status = "Pending"
            elif enrollment.end_date:
                duration = (enrollment.end_date - enrollment.start_date).days
                if today > enrollment.end_date:
                    status = "Completed"
                else:
                    status = "Active"
            else:
                duration = (today - enrollment.start_date).days
                status = "Active"
            
            writer.writerow([
                f"{enrollment.client.first_name} {enrollment.client.last_name}",
                enrollment.program.name,
                enrollment.program.department.name if enrollment.program.department else '',
                enrollment.start_date.strftime('%Y-%m-%d'),
                enrollment.end_date.strftime('%Y-%m-%d') if enrollment.end_date else '',
                status,
                duration
            ])
        
        return response


class ClientOutcomesView(TemplateView):
    template_name = 'reports/client_outcomes.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get date range filter parameters
        start_date, end_date, parsed_start_date, parsed_end_date = get_date_range_filter(self.request)
        
        # Get program manager and staff-only filtering
        is_program_manager, is_leader, is_analyst, is_staff_only, assigned_programs, assigned_clients = get_program_manager_filtering(self.request)
        
        # Filter enrollments based on user role
        if (is_program_manager or is_leader) and assigned_programs:
            enrollments = ClientProgramEnrollment.objects.filter(program__in=assigned_programs)
        elif is_staff_only:
            enrollments = ClientProgramEnrollment.objects.filter(program__in=assigned_programs)
        else:
            enrollments = ClientProgramEnrollment.objects.all()
        
        # Apply date range filtering if specified
        if parsed_start_date or parsed_end_date:
            if parsed_start_date and parsed_end_date:
                # Filter enrollments by start date within the range
                enrollments = enrollments.filter(start_date__date__range=[parsed_start_date, parsed_end_date])
            elif parsed_start_date:
                enrollments = enrollments.filter(start_date__date__gte=parsed_start_date)
            elif parsed_end_date:
                enrollments = enrollments.filter(start_date__date__lte=parsed_end_date)
        
        # Calculate statistics using date-based logic
        today = timezone.now().date()
        
        total = enrollments.count()
        active_count = 0
        completed_count = 0
        pending_count = 0
        
        for enrollment in enrollments:
            if today < enrollment.start_date:
                pending_count += 1
            elif enrollment.end_date:
                if today > enrollment.end_date:
                    completed_count += 1
                else:
                    active_count += 1
            else:
                active_count += 1
        
        success_rate = (completed_count / total * 100) if total > 0 else 0
        
        context.update({
            'total_enrollments': total,
            'completed_enrollments': completed_count,
            'active_enrollments': active_count,
            'pending_enrollments': pending_count,
            'success_rate': round(success_rate, 1),
            'is_program_manager': is_program_manager,
            'start_date': start_date,
            'end_date': end_date,
        })
        return context


class ProgramCapacityView(ListView):
    template_name = 'reports/program_capacity.html'
    context_object_name = 'program_data'
    paginate_by = 10
    
    def get_paginate_by(self, queryset):
        """Get the number of items to paginate by from request parameters"""
        per_page = self.request.GET.get('per_page', '10')
        try:
            per_page = int(per_page)
            # Limit to reasonable values
            if per_page < 5:
                per_page = 5
            elif per_page > 100:
                per_page = 100
        except (ValueError, TypeError):
            per_page = 10
        return per_page
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get date range filter parameters
        start_date, end_date, parsed_start_date, parsed_end_date = get_date_range_filter(self.request)
        # Add the current per_page value to context for the pagination component
        context['per_page'] = str(self.get_paginate_by(self.get_queryset()))
        
        # Get program manager and staff-only filtering
        is_program_manager, is_leader, is_analyst, is_staff_only, assigned_programs, assigned_clients = get_program_manager_filtering(self.request)
        context['is_program_manager'] = is_program_manager
        
        # Add date range parameters to context
        context['start_date'] = start_date
        context['end_date'] = end_date
        
        return context
    
    def get_queryset(self):
        # Get program manager and staff-only filtering
        is_program_manager, is_leader, is_analyst, is_staff_only, assigned_programs, assigned_clients = get_program_manager_filtering(self.request)
        
        # Filter programs based on user role
        if is_analyst:
            # Analysts see all programs
            programs = Program.objects.all()
        elif (is_program_manager or is_leader) and assigned_programs:
            programs = assigned_programs
        elif is_staff_only:
            programs = assigned_programs if assigned_programs else Program.objects.none()
        else:
            programs = Program.objects.all()
        
        program_data = []
        today = timezone.now().date()
        
        for program in programs:
            # Get active enrollments using proper date-based logic
            active_enrollments = ClientProgramEnrollment.objects.filter(
                program=program,
                start_date__lte=today
            ).filter(
                models.Q(end_date__isnull=True) | models.Q(end_date__gt=today)
            ).count()
            
            utilization = (active_enrollments / program.capacity_current * 100) if program.capacity_current > 0 else 0
            
            program_data.append({
                'program': program,
                'capacity': program.capacity_current,
                'occupied': active_enrollments,
                'vacant': program.capacity_current - active_enrollments,
                'utilization': round(utilization, 1)
            })
        
        return program_data


class ProgramCapacityExportView(ListView):
    """Export program capacity data to CSV"""
    model = Program
    template_name = 'reports/program_capacity.html'
    
    def get_queryset(self):
        # Get program manager and staff-only filtering
        is_program_manager, is_leader, is_analyst, is_staff_only, assigned_programs, assigned_clients = get_program_manager_filtering(self.request)
        
        # Filter programs based on user role
        if is_analyst:
            # Analysts see all programs
            programs = Program.objects.all()
        elif (is_program_manager or is_leader) and assigned_programs:
            programs = assigned_programs
        elif is_staff_only:
            programs = assigned_programs if assigned_programs else Program.objects.none()
        else:
            programs = Program.objects.all()
        
        program_data = []
        today = timezone.now().date()
        
        for program in programs:
            # Get active enrollments using proper date-based logic
            active_enrollments = ClientProgramEnrollment.objects.filter(
                program=program,
                start_date__lte=today
            ).filter(
                models.Q(end_date__isnull=True) | models.Q(end_date__gt=today)
            ).count()
            
            utilization = (active_enrollments / program.capacity_current * 100) if program.capacity_current > 0 else 0
            
            program_data.append({
                'program': program,
                'capacity': program.capacity_current,
                'occupied': active_enrollments,
                'vacant': program.capacity_current - active_enrollments,
                'utilization': round(utilization, 1)
            })
        
        return program_data
    
    def get(self, request, *args, **kwargs):
        # Create CSV response
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = "attachment; filename=\"program_capacity_export.csv\""
        
        # Create CSV writer
        writer = csv.writer(response)
        
        # Write header row
        writer.writerow([
            "Program Name",
            "Department",
            "Location",
            "Capacity",
            "Occupied",
            "Vacant",
            "Utilization %",
            "Status"
        ])
        
        # Get program data
        program_data = self.get_queryset()
        
        # Write data rows
        for data in program_data:
            # Determine status based on utilization
            if data['utilization'] >= 90:
                status = "Over Capacity"
            elif data['utilization'] >= 80:
                status = "Near Capacity"
            elif data['utilization'] >= 60:
                status = "Good Utilization"
            else:
                status = "Available Capacity"
            
            writer.writerow([
                data['program'].name,
                data['program'].department.name if data['program'].department else '',
                data['program'].location,
                data['capacity'],
                data['occupied'],
                data['vacant'],
                f"{data['utilization']}%",
                status
            ])
        
        return response


class ProgramPerformanceView(ListView):
    template_name = 'reports/program_performance.html'
    context_object_name = 'program_metrics'
    paginate_by = 10
    
    def get_paginate_by(self, queryset):
        """Get the number of items to paginate by from request parameters"""
        per_page = self.request.GET.get('per_page', '10')
        try:
            per_page = int(per_page)
            # Limit to reasonable values
            if per_page < 5:
                per_page = 5
            elif per_page > 100:
                per_page = 100
        except (ValueError, TypeError):
            per_page = 10
        return per_page
    
    def get_queryset(self):
        # Get program manager and staff-only filtering
        is_program_manager, is_leader, is_analyst, is_staff_only, assigned_programs, assigned_clients = get_program_manager_filtering(self.request)
        
        # Filter programs based on user role
        if is_analyst:
            # Analysts see all programs
            programs = Program.objects.all()
        elif (is_program_manager or is_leader) and assigned_programs:
            programs = assigned_programs
        elif is_staff_only:
            programs = assigned_programs if assigned_programs else Program.objects.none()
        else:
            programs = Program.objects.all()
        
        program_metrics = []
        today = timezone.now().date()
        
        for program in programs:
            # Get all enrollments for this program
            all_enrollments = ClientProgramEnrollment.objects.filter(program=program)
            
            # Calculate active and completed enrollments using date-based logic
            active_count = 0
            completed_count = 0
            
            for enrollment in all_enrollments:
                if today < enrollment.start_date:
                    # Pending - not counted in active or completed
                    continue
                elif enrollment.end_date:
                    if today > enrollment.end_date:
                        completed_count += 1
                    else:
                        active_count += 1
                else:
                    active_count += 1
            
            total_enrollments = all_enrollments.count()
            completion_rate = (completed_count / total_enrollments * 100) if total_enrollments > 0 else 0
            
            program_metrics.append({
                'program': program,
                'total_enrollments': total_enrollments,
                'active_enrollments': active_count,
                'completed_enrollments': completed_count,
                'completion_rate': round(completion_rate, 1)
            })
        
        return program_metrics
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get date range filter parameters
        start_date, end_date, parsed_start_date, parsed_end_date = get_date_range_filter(self.request)
        
        # Add the current per_page value to context for the pagination component
        context['per_page'] = str(self.get_paginate_by(self.get_queryset()))
        
        # Add date range parameters to context
        context['start_date'] = start_date
        context['end_date'] = end_date
        
        return context


class ProgramPerformanceExportView(ListView):
    """Export program performance data to CSV"""
    model = Program
    template_name = 'reports/program_performance.html'
    
    def get_queryset(self):
        # Get program manager and staff-only filtering
        is_program_manager, is_leader, is_analyst, is_staff_only, assigned_programs, assigned_clients = get_program_manager_filtering(self.request)
        
        # Filter programs based on user role
        if is_analyst:
            # Analysts see all programs
            programs = Program.objects.all()
        elif (is_program_manager or is_leader) and assigned_programs:
            programs = assigned_programs
        elif is_staff_only:
            programs = assigned_programs if assigned_programs else Program.objects.none()
        else:
            programs = Program.objects.all()
        
        program_metrics = []
        today = timezone.now().date()
        
        for program in programs:
            # Get all enrollments for this program
            all_enrollments = ClientProgramEnrollment.objects.filter(program=program)
            
            # Calculate active and completed enrollments using date-based logic
            active_count = 0
            completed_count = 0
            
            for enrollment in all_enrollments:
                if today < enrollment.start_date:
                    # Pending - not counted in active or completed
                    continue
                elif enrollment.end_date:
                    if today > enrollment.end_date:
                        completed_count += 1
                    else:
                        active_count += 1
                else:
                    active_count += 1
            
            total_enrollments = all_enrollments.count()
            completion_rate = (completed_count / total_enrollments * 100) if total_enrollments > 0 else 0
            
            program_metrics.append({
                'program': program,
                'total_enrollments': total_enrollments,
                'active_enrollments': active_count,
                'completed_enrollments': completed_count,
                'completion_rate': round(completion_rate, 1)
            })
        
        return program_metrics
    
    def get(self, request, *args, **kwargs):
        # Create CSV response
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = "attachment; filename=\"program_performance_export.csv\""
        
        # Create CSV writer
        writer = csv.writer(response)
        
        # Write header row
        writer.writerow([
            "Program Name",
            "Department",
            "Location",
            "Total Enrollments",
            "Active Enrollments",
            "Completed Enrollments",
            "Completion Rate %",
            "Performance Status"
        ])
        
        # Get program data
        program_metrics = self.get_queryset()
        
        # Write data rows
        for metric in program_metrics:
            # Determine performance status
            if metric['completion_rate'] >= 80:
                performance_status = "Excellent"
            elif metric['completion_rate'] >= 60:
                performance_status = "Good"
            elif metric['completion_rate'] >= 40:
                performance_status = "Fair"
            else:
                performance_status = "Needs Improvement"
            
            writer.writerow([
                metric['program'].name,
                metric['program'].department.name if metric['program'].department else '',
                metric['program'].location,
                metric['total_enrollments'],
                metric['active_enrollments'],
                metric['completed_enrollments'],
                f"{metric['completion_rate']}%",
                performance_status
            ])
        
        return response


class DepartmentSummaryView(TemplateView):
    template_name = 'reports/department_summary.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from core.models import Department
        
        # Get program manager and staff-only filtering
        is_program_manager, is_leader, is_analyst, is_staff_only, assigned_programs, assigned_clients = get_program_manager_filtering(self.request)
        
        # Filter departments based on user role
        if (is_program_manager or is_leader) and assigned_programs:
            # Get departments that have assigned programs
            department_ids = assigned_programs.values_list('department_id', flat=True).distinct()
            departments = Department.objects.filter(id__in=department_ids)
        elif is_staff_only:
            # Get departments that have assigned programs
            department_ids = assigned_programs.values_list('department_id', flat=True).distinct()
            departments = Department.objects.filter(id__in=department_ids)
        else:
            departments = Department.objects.all()
        department_data = []
        
        for dept in departments:
            programs = dept.program_set.all()
            
            # Filter programs based on user role
            if (is_program_manager or is_leader) and assigned_programs:
                programs = programs.filter(id__in=assigned_programs.values_list('id', flat=True))
            elif is_staff_only:
                programs = programs.filter(id__in=assigned_programs.values_list('id', flat=True))
            
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


# Export Views for the three specific reports
class ClientDemographicsExportView(TemplateView):
    """Export client demographics report to CSV"""
    
    def get(self, request, *args, **kwargs):
        # Get date range filter parameters
        start_date, end_date, parsed_start_date, parsed_end_date = get_date_range_filter(request)
        
        # Get the same data as the main view
        is_program_manager, is_leader, is_analyst, is_staff_only, assigned_programs, assigned_clients = get_program_manager_filtering(request)
        
        # Filter clients based on user role
        if (is_program_manager or is_leader) and assigned_programs:
            clients = Client.objects.filter(
                clientprogramenrollment__program__in=assigned_programs
            ).distinct()
        elif is_staff_only and assigned_clients:
            clients = assigned_clients
        else:
            clients = Client.objects.all()
        
        # Apply date range filtering if specified
        if parsed_start_date or parsed_end_date:
            if parsed_start_date and parsed_end_date:
                # Filter clients created within the date range
                clients = clients.filter(created_at__date__range=[parsed_start_date, parsed_end_date])
            elif parsed_start_date:
                clients = clients.filter(created_at__date__gte=parsed_start_date)
            elif parsed_end_date:
                clients = clients.filter(created_at__date__lte=parsed_end_date)
        
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
        
        # Create CSV response
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="client_demographics_report.csv"'
        
        writer = csv.writer(response)
        
        # Write header
        writer.writerow(['Client Demographics Report'])
        writer.writerow(['Generated on', timezone.now().strftime('%Y-%m-%d %H:%M:%S')])
        writer.writerow(['Total Clients', clients.count()])
        writer.writerow([])
        
        # Age Distribution Section
        writer.writerow(['AGE DISTRIBUTION'])
        writer.writerow(['Age Group', 'Count', 'Percentage'])
        total_clients = clients.count()
        for age_group, count in age_groups.items():
            percentage = (count / total_clients * 100) if total_clients > 0 else 0
            writer.writerow([age_group, count, f"{percentage:.1f}%"])
        
        writer.writerow([])
        
        # Gender Distribution Section
        writer.writerow(['GENDER DISTRIBUTION'])
        writer.writerow(['Gender', 'Count', 'Percentage'])
        for gender, count in gender_counts.items():
            percentage = (count / total_clients * 100) if total_clients > 0 else 0
            writer.writerow([gender, count, f"{percentage:.1f}%"])
        
        writer.writerow([])
        
        # Detailed Client Information
        writer.writerow(['DETAILED CLIENT INFORMATION'])
        writer.writerow(['Client ID', 'First Name', 'Last Name', 'Preferred Name', 'Date of Birth', 'Age', 'Gender', 'Programs'])
        
        for client in clients:
            # Calculate age
            age = "N/A"
            if client.dob:
                from datetime import date
                today = date.today()
                age = today.year - client.dob.year - ((today.month, today.day) < (client.dob.month, client.dob.day))
            
            # Get programs for this client
            client_programs = ClientProgramEnrollment.objects.filter(client=client).values_list('program__name', flat=True)
            programs_str = ', '.join(client_programs) if client_programs else 'None'
            
            writer.writerow([
                client.client_id or '',
                client.first_name or '',
                client.last_name or '',
                client.preferred_name or '',
                client.dob.strftime('%Y-%m-%d') if client.dob else '',
                age,
                client.gender or 'Unknown',
                programs_str
            ])
        
        return response


class ClientOutcomesExportView(TemplateView):
    """Export client outcomes report to CSV"""
    
    def get(self, request, *args, **kwargs):
        # Get the same data as the main view
        is_program_manager, is_leader, is_analyst, is_staff_only, assigned_programs, assigned_clients = get_program_manager_filtering(request)
        
        # Filter enrollments based on user role
        if (is_program_manager or is_leader) and assigned_programs:
            enrollments = ClientProgramEnrollment.objects.filter(program__in=assigned_programs)
        elif is_staff_only:
            enrollments = ClientProgramEnrollment.objects.filter(program__in=assigned_programs)
        else:
            enrollments = ClientProgramEnrollment.objects.all()
        
        # Calculate statistics using date-based logic
        today = timezone.now().date()
        
        total = enrollments.count()
        active_count = 0
        completed_count = 0
        pending_count = 0
        
        for enrollment in enrollments:
            if today < enrollment.start_date:
                pending_count += 1
            elif enrollment.end_date:
                if today > enrollment.end_date:
                    completed_count += 1
                else:
                    active_count += 1
            else:
                active_count += 1
        
        success_rate = (completed_count / total * 100) if total > 0 else 0
        
        # Create CSV response
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="client_outcomes_report.csv"'
        
        writer = csv.writer(response)
        
        # Write header
        writer.writerow(['Client Outcomes Report'])
        writer.writerow(['Generated on', timezone.now().strftime('%Y-%m-%d %H:%M:%S')])
        writer.writerow([])
        
        # Summary Statistics
        writer.writerow(['SUMMARY STATISTICS'])
        writer.writerow(['Metric', 'Value'])
        writer.writerow(['Total Enrollments', total])
        writer.writerow(['Completed Enrollments', completed_count])
        writer.writerow(['Active Enrollments', active_count])
        writer.writerow(['Pending Enrollments', pending_count])
        writer.writerow(['Success Rate', f"{success_rate:.1f}%"])
        
        writer.writerow([])
        
        # Performance Insights
        writer.writerow(['PERFORMANCE INSIGHTS'])
        if success_rate >= 80:
            insight = f"Excellent completion rate! Your programs are highly effective with {success_rate:.1f}% success rate."
        elif success_rate >= 60:
            insight = f"Good completion rate of {success_rate:.1f}%. Consider reviewing program structure for improvement opportunities."
        else:
            insight = f"Completion rate of {success_rate:.1f}% indicates room for improvement. Consider program evaluation and client feedback."
        
        writer.writerow(['Completion Analysis', insight])
        writer.writerow(['Active Engagement', f"Currently {active_count} clients are actively engaged in programs, representing {(active_count/total*100):.1f}% of total enrollments."])
        
        writer.writerow([])
        
        # Detailed Enrollment Information
        writer.writerow(['DETAILED ENROLLMENT INFORMATION'])
        writer.writerow(['Client Name', 'Program Name', 'Department', 'Start Date', 'End Date', 'Status', 'Duration (Days)', 'Created By'])
        
        for enrollment in enrollments:
            # Calculate duration and status
            if today < enrollment.start_date:
                duration = 0
                status = "Pending"
            elif enrollment.end_date:
                duration = (enrollment.end_date - enrollment.start_date).days
                if today > enrollment.end_date:
                    status = "Completed"
                else:
                    status = "Active"
            else:
                duration = (today - enrollment.start_date).days
                status = "Active"
            
            writer.writerow([
                f"{enrollment.client.first_name} {enrollment.client.last_name}",
                enrollment.program.name,
                enrollment.program.department.name if enrollment.program.department else '',
                enrollment.start_date.strftime('%Y-%m-%d'),
                enrollment.end_date.strftime('%Y-%m-%d') if enrollment.end_date else 'Ongoing',
                status,
                duration,
                enrollment.created_by or ''
            ])
        
        return response


class OrganizationalSummaryExportView(TemplateView):
    """Export organizational summary report to CSV"""
    
    def get(self, request, *args, **kwargs):
        # Get the same data as the main view
        is_program_manager, is_leader, is_analyst, is_staff_only, assigned_programs, assigned_clients = get_program_manager_filtering(request)
        
        # Filter data based on user role
        if is_analyst:
            # Analysts see all data across all clients and programs
            total_clients = Client.objects.count()
            total_programs = Program.objects.count()
            
            # Calculate active enrollments using date-based logic for all programs
            enrollments = ClientProgramEnrollment.objects.all()
        elif (is_program_manager or is_leader) and assigned_programs:
            total_clients = Client.objects.filter(
                clientprogramenrollment__program__in=assigned_programs
            ).distinct().count()
            total_programs = assigned_programs.count()
            enrollments = ClientProgramEnrollment.objects.filter(program__in=assigned_programs)
        elif is_staff_only and assigned_clients:
            total_clients = assigned_clients.count()
            total_programs = assigned_programs.count() if assigned_programs else 0
            enrollments = ClientProgramEnrollment.objects.filter(program__in=assigned_programs) if assigned_programs else ClientProgramEnrollment.objects.none()
        else:
            total_clients = Client.objects.count()
            total_programs = Program.objects.count()
            enrollments = ClientProgramEnrollment.objects.all()
        
        # Calculate active enrollments using date-based logic
        today = timezone.now().date()
        active_count = 0
        for enrollment in enrollments:
            if today < enrollment.start_date:
                continue
            elif enrollment.end_date:
                if today > enrollment.end_date:
                    continue
                else:
                    active_count += 1
            else:
                active_count += 1
        
        # Create CSV response
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="organizational_summary_report.csv"'
        
        writer = csv.writer(response)
        
        # Write header
        writer.writerow(['Organizational Summary Report'])
        writer.writerow(['Generated on', timezone.now().strftime('%Y-%m-%d %H:%M:%S')])
        writer.writerow([])
        
        # Summary Statistics
        writer.writerow(['ORGANIZATIONAL OVERVIEW'])
        writer.writerow(['Metric', 'Value'])
        writer.writerow(['Total Clients', total_clients])
        writer.writerow(['Total Programs', total_programs])
        writer.writerow(['Active Enrollments', active_count])
        writer.writerow(['Enrollment Rate', f"{(active_count/total_clients*100):.1f}%" if total_clients > 0 else "0%"])
        writer.writerow(['Average per Program', f"{(active_count/total_programs):.1f}" if total_programs > 0 else "0"])
        
        writer.writerow([])
        
        # Client Demographics
        writer.writerow(['CLIENT DEMOGRAPHICS'])
        if (is_program_manager or is_leader) and assigned_programs:
            clients = Client.objects.filter(
                clientprogramenrollment__program__in=assigned_programs
            ).distinct()
        else:
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
        
        writer.writerow(['Age Group', 'Count', 'Percentage'])
        for age_group, count in age_groups.items():
            percentage = (count / total_clients * 100) if total_clients > 0 else 0
            writer.writerow([age_group, count, f"{percentage:.1f}%"])
        
        writer.writerow([])
        
        # Gender distribution
        gender_counts = {}
        for client in clients:
            gender = client.gender or 'Unknown'
            gender_counts[gender] = gender_counts.get(gender, 0) + 1
        
        writer.writerow(['Gender', 'Count', 'Percentage'])
        for gender, count in gender_counts.items():
            percentage = (count / total_clients * 100) if total_clients > 0 else 0
            writer.writerow([gender, count, f"{percentage:.1f}%"])
        
        writer.writerow([])
        
        # Program Statistics
        writer.writerow(['PROGRAM STATISTICS'])
        if (is_program_manager or is_leader) and assigned_programs:
            programs = assigned_programs
        else:
            programs = Program.objects.all()
        
        writer.writerow(['Program Name', 'Department', 'Location', 'Capacity', 'Active Enrollments', 'Utilization %'])
        
        for program in programs:
            program_enrollments = ClientProgramEnrollment.objects.filter(program=program)
            program_active = 0
            
            for enrollment in program_enrollments:
                if today < enrollment.start_date:
                    continue
                elif enrollment.end_date:
                    if today > enrollment.end_date:
                        continue
                    else:
                        program_active += 1
                else:
                    program_active += 1
            
            utilization = (program_active / program.capacity_current * 100) if program.capacity_current > 0 else 0
            
            writer.writerow([
                program.name,
                program.department.name if program.department else '',
                program.location or '',
                program.capacity_current,
                program_active,
                f"{utilization:.1f}%"
            ])
        
        return response