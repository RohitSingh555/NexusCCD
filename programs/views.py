from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, View
from django.urls import reverse_lazy
from django.utils import timezone
from django.db import models
from django.http import HttpResponse
from core.models import Program, Department, ClientProgramEnrollment, ProgramManagerAssignment, Staff
from core.views import jwt_required, ProgramManagerAccessMixin
from core.message_utils import success_message, error_message, warning_message, info_message, create_success, update_success, delete_success, validation_error, permission_error, not_found_error
from django.utils.decorators import method_decorator
import csv

@method_decorator(jwt_required, name='dispatch')
class ProgramListView(ProgramManagerAccessMixin, ListView):
    model = Program
    template_name = 'programs/program_list.html'
    context_object_name = 'programs'
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
                # Filter programs with available capacity (including programs with no capacity limit)
                queryset = [p for p in queryset if not p.is_at_capacity() and (p.get_available_capacity() is None or p.get_available_capacity() > 0)]
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
        
        # Get the total count of filtered programs (not just current page)
        total_filtered_count = self.get_queryset().count()
        
        # Add filter options to context
        context['programs_with_capacity'] = programs_with_capacity
        context['total_filtered_count'] = total_filtered_count
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
        context['per_page'] = self.request.GET.get('per_page', '10')
        
        # Force pagination to be enabled if there are any results
        if context.get('paginator') and context['paginator'].count > 0:
            context['is_paginated'] = True
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
        
        # Get program managers
        from core.models import ProgramManagerAssignment
        program_managers = ProgramManagerAssignment.objects.filter(
            program=program,
            is_active=True
        ).select_related('staff')
        
        # Get available clients (not currently enrolled in this program)
        from core.models import Client
        enrolled_client_ids = current_enrollments.values_list('client_id', flat=True)
        available_clients = Client.objects.exclude(id__in=enrolled_client_ids).order_by('first_name', 'last_name')
        
        # Get available staff members who can be assigned as program managers
        from core.models import Staff
        assigned_manager_ids = program_managers.values_list('staff_id', flat=True)
        available_staff = Staff.objects.exclude(id__in=assigned_manager_ids).order_by('first_name', 'last_name')
        
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
            'program_managers': program_managers,
            'available_clients': available_clients,
            'available_staff': available_staff,
            'recent_enrollments': recent_enrollments,
        })
        
        return context

@method_decorator(jwt_required, name='dispatch')
class ProgramBulkEnrollView(ProgramManagerAccessMixin, View):
    """Handle bulk enrollment of clients in a program"""
    
    def post(self, request, external_id):
        from core.models import Program, ClientProgramEnrollment
        from django.contrib import messages
        from django.shortcuts import redirect
        from django.utils import timezone
        from django.db import transaction
        
        try:
            program = Program.objects.get(external_id=external_id)
            client_ids = request.POST.getlist('client_ids')
            start_date = request.POST.get('start_date', timezone.now().date())
            
            if not client_ids:
                messages.error(request, 'Please select at least one client to enroll.')
                return redirect('programs:detail', external_id=external_id)
            
            # Convert start_date string to date object if needed
            if isinstance(start_date, str):
                from datetime import datetime
                start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            
            enrolled_count = 0
            errors = []
            
            with transaction.atomic():
                for client_id in client_ids:
                    try:
                        from core.models import Client
                        client = Client.objects.get(id=client_id)
                        
                        # Check if client can be enrolled
                        can_enroll, message = program.can_enroll_client(client, start_date)
                        
                        if can_enroll:
                            # Create enrollment
                            enrollment = ClientProgramEnrollment.objects.create(
                                client=client,
                                program=program,
                                start_date=start_date,
                                status='active',
                                created_by=request.user.get_full_name() or request.user.username,
                                updated_by=request.user.get_full_name() or request.user.username
                            )
                            
                            # Create audit log entry for enrollment creation
                            try:
                                from core.models import create_audit_log
                                create_audit_log(
                                    entity_name='Enrollment',
                                    entity_id=enrollment.external_id,
                                    action='create',
                                    changed_by=request.user,
                                    diff_data={
                                        'client': str(enrollment.client),
                                        'program': str(enrollment.program),
                                        'start_date': str(enrollment.start_date),
                                        'status': enrollment.status,
                                        'created_by': enrollment.created_by,
                                        'source': 'program_detail_page'
                                    }
                                )
                            except Exception as e:
                                print(f"Error creating audit log for enrollment: {e}")
                            
                            enrolled_count += 1
                        else:
                            errors.append(f"{client.first_name} {client.last_name}: {message}")
                            
                    except Client.DoesNotExist:
                        errors.append(f"Client with ID {client_id} not found.")
                    except Exception as e:
                        errors.append(f"Error enrolling client {client_id}: {str(e)}")
            
            # Show success/error messages
            if enrolled_count > 0:
                messages.success(request, f'Successfully enrolled {enrolled_count} client(s) in {program.name}.')
            
            if errors:
                for error in errors:
                    messages.warning(request, error)
            
        except Program.DoesNotExist:
            messages.error(request, 'Program not found.')
            return redirect('programs:list')
        except Exception as e:
            messages.error(request, f'An error occurred: {str(e)}')
        
        return redirect('programs:detail', external_id=external_id)

@method_decorator(jwt_required, name='dispatch')
class ProgramBulkAssignManagersView(ProgramManagerAccessMixin, View):
    """Handle bulk assignment of program managers to a program"""
    
    def post(self, request, external_id):
        from core.models import Program, ProgramManagerAssignment, Staff
        from django.contrib import messages
        from django.shortcuts import redirect
        from django.db import transaction
        
        try:
            program = Program.objects.get(external_id=external_id)
            staff_ids = request.POST.getlist('staff_ids')
            
            if not staff_ids:
                messages.error(request, 'Please select at least one staff member to assign as program manager.')
                return redirect('programs:detail', external_id=external_id)
            
            assigned_count = 0
            errors = []
            
            with transaction.atomic():
                for staff_id in staff_ids:
                    try:
                        staff = Staff.objects.get(id=staff_id)
                        
                        # Check if staff already assigned to this program
                        existing_assignment = ProgramManagerAssignment.objects.filter(
                            staff=staff,
                            program=program,
                            is_active=True
                        ).exists()
                        
                        if not existing_assignment:
                            # Create new assignment
                            assignment = ProgramManagerAssignment.objects.create(
                                staff=staff,
                                program=program,
                                assigned_by=request.user.staff_profile if hasattr(request.user, 'staff_profile') else None
                            )
                            assigned_count += 1
                        else:
                            errors.append(f"{staff.first_name} {staff.last_name} is already assigned as a program manager for this program.")
                            
                    except Staff.DoesNotExist:
                        errors.append(f"Staff member with ID {staff_id} not found.")
                    except Exception as e:
                        errors.append(f"Error assigning staff {staff_id}: {str(e)}")
            
            # Show success/error messages
            if assigned_count > 0:
                messages.success(request, f'Successfully assigned {assigned_count} program manager(s) to {program.name}.')
            
            if errors:
                for error in errors:
                    messages.warning(request, error)
            
        except Program.DoesNotExist:
            messages.error(request, 'Program not found.')
            return redirect('programs:list')
        except Exception as e:
            messages.error(request, f'An error occurred: {str(e)}')
        
        return redirect('programs:detail', external_id=external_id)

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
    
    def form_valid(self, form):
        """Handle program creation with audit logging"""
        program = form.save(commit=False)
        program.save()
        
        # Create audit log entry for program creation
        try:
            from core.models import create_audit_log
            create_audit_log(
                entity_name='Program',
                entity_id=program.external_id,
                action='create',
                changed_by=self.request.user,
                diff_data={
                    'name': program.name,
                    'department': str(program.department),
                    'location': program.location or '',
                    'capacity_current': program.capacity_current,
                    'capacity_effective_date': str(program.capacity_effective_date) if program.capacity_effective_date else None,
                    'created_by': self.request.user.get_full_name() or self.request.user.username
                }
            )
        except Exception as e:
            print(f"Error creating audit log for program creation: {e}")
        
        create_success(self.request, 'Program')
        return super().form_valid(form)

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
    
    def form_valid(self, form):
        """Handle program updates with audit logging"""
        # Get the original program data before saving
        original_program = self.get_object()
        
        # Set the updated_by field before saving
        program = form.save(commit=False)
        program.save()
        
        # Create audit log entry for program update
        try:
            from core.models import create_audit_log
            
            # Compare original and updated values to detect changes
            changes = {}
            
            # Check each field for changes
            if original_program.name != program.name:
                changes['name'] = f"{original_program.name} → {program.name}"
            
            if original_program.department != program.department:
                changes['department'] = f"{str(original_program.department)} → {str(program.department)}"
            
            if original_program.location != program.location:
                changes['location'] = f"{original_program.location or ''} → {program.location or ''}"
            
            if original_program.capacity_current != program.capacity_current:
                changes['capacity_current'] = f"{original_program.capacity_current} → {program.capacity_current}"
            
            if original_program.capacity_effective_date != program.capacity_effective_date:
                changes['capacity_effective_date'] = f"{original_program.capacity_effective_date} → {program.capacity_effective_date}"
            
            # Only create audit log if there were changes
            if changes:
                create_audit_log(
                    entity_name='Program',
                    entity_id=program.external_id,
                    action='update',
                    changed_by=self.request.user,
                    diff_data=changes
                )
        except Exception as e:
            print(f"Error creating audit log for program update: {e}")
        
        update_success(self.request, 'Program')
        return super().form_valid(form)

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
    
    def form_valid(self, form):
        """Handle program deletion with audit logging"""
        # Get the program object first
        program = self.get_object()
        
        # Create audit log entry before deletion
        try:
            from core.models import create_audit_log
            create_audit_log(
                entity_name='Program',
                entity_id=program.external_id,
                action='delete',
                changed_by=self.request.user,
                diff_data={
                    'name': program.name,
                    'department': str(program.department),
                    'location': program.location or '',
                    'capacity_current': program.capacity_current,
                    'capacity_effective_date': str(program.capacity_effective_date) if program.capacity_effective_date else None,
                    'deleted_by': f"{self.request.user.first_name} {self.request.user.last_name}".strip() or self.request.user.username
                }
            )
        except Exception as e:
            print(f"Error creating audit log for program deletion: {e}")
        
        # Delete the program
        program.delete()
        
        delete_success(self.request, 'Program', program.name)
        return super().form_valid(form)

@method_decorator(jwt_required, name="dispatch")
class ProgramCSVExportView(ProgramManagerAccessMixin, ListView):
    """Export programs to CSV with filtering support"""
    model = Program
    template_name = "programs/program_list.html"
    
    def get_queryset(self):
        # Use the same filtering logic as ProgramListView
        queryset = super().get_queryset()
        
        # Apply additional filters
        department_filter = self.request.GET.get("department", "")
        status_filter = self.request.GET.get("status", "")
        capacity_filter = self.request.GET.get("capacity", "")
        search_query = self.request.GET.get("search", "").strip()
        
        if department_filter:
            queryset = queryset.filter(department__name=department_filter)
        
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        if capacity_filter:
            if capacity_filter == "at_capacity":
                # Filter programs that are at or over capacity
                queryset = [p for p in queryset if p.is_at_capacity()]
            elif capacity_filter == "available":
                # Filter programs that have available capacity
                queryset = [p for p in queryset if not p.is_at_capacity()]
        
        if search_query:
            queryset = queryset.filter(
                models.Q(name__icontains=search_query) |
                models.Q(description__icontains=search_query) |
                models.Q(location__icontains=search_query) |
                models.Q(department__name__icontains=search_query)
            )
        
        return queryset.order_by("-created_at")
    
    def get(self, request, *args, **kwargs):
        # Create CSV response
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = "attachment; filename=\"programs_export.csv\""
        
        # Create CSV writer
        writer = csv.writer(response)
        
        # Write header row
        writer.writerow([
            "Program Name",
            "Department",
            "Location",
            "Status",
            "Capacity",
            "Current Enrollments",
            "Capacity Percentage",
            "Description",
            "Created At",
            "Updated At",
            "Current Enrollments (Client Names)",
            "Program Staff (Manager Names)"
        ])
        
        # Get filtered programs
        programs = self.get_queryset()
        
        # Write data rows
        for program in programs:
            # Get current enrollments
            current_enrollments = ClientProgramEnrollment.objects.filter(
                program=program,
                is_archived=False
            ).select_related("client")
            
            # Get program staff/managers
            program_managers = ProgramManagerAssignment.objects.filter(
                program=program
            ).select_related("staff")
            
            # Calculate capacity percentage
            capacity_percentage = 0
            if program.capacity_current > 0:
                current_count = current_enrollments.count()
                capacity_percentage = min(100, (current_count / program.capacity_current) * 100)
            
            # Create comma-separated lists
            client_names = ", ".join([
                f"{enrollment.client.first_name} {enrollment.client.last_name}"
                for enrollment in current_enrollments
            ])
            
            manager_names = ", ".join([
                f"{assignment.staff.first_name} {assignment.staff.last_name}"
                for assignment in program_managers
            ])
            
            writer.writerow([
                program.name,
                program.department.name,
                program.location or "",
                program.get_status_display(),
                program.capacity_current if program.capacity_current > 0 else "No limit",
                current_enrollments.count(),
                f"{capacity_percentage:.1f}%",
                program.description or "",
                program.created_at.strftime("%Y-%m-%d %H:%M:%S") if program.created_at else "",
                program.updated_at.strftime("%Y-%m-%d %H:%M:%S") if program.updated_at else "",
                client_names,
                manager_names
            ])
        
        return response
