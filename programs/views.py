from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView, View
from django.urls import reverse_lazy, reverse
from django.shortcuts import redirect
from django.utils import timezone
from django.db import models
from django.http import HttpResponse
from core.models import Program, Department, ClientProgramEnrollment, ProgramManagerAssignment, Staff
from core.views import jwt_required, ProgramManagerAccessMixin, AnalystAccessMixin
from core.message_utils import success_message, error_message, warning_message, info_message, create_success, update_success, delete_success, validation_error, permission_error, not_found_error
from django.utils.decorators import method_decorator
import csv

@method_decorator(jwt_required, name='dispatch')
class ProgramListView(AnalystAccessMixin, ProgramManagerAccessMixin, ListView):
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
        
        # For staff-only users, filter to only their assigned programs
        if self.request.user.is_authenticated:
            try:
                staff = self.request.user.staff_profile
                user_roles = staff.staffrole_set.select_related('role').all()
                role_names = [staff_role.role.name for staff_role in user_roles]
                
                if 'Staff' in role_names and not any(role in ['SuperAdmin', 'Admin', 'Manager'] for role in role_names):
                    # Staff-only users see ONLY programs where their assigned clients are enrolled
                    from staff.models import StaffClientAssignment
                    
                    # Get programs where their assigned clients are enrolled
                    assigned_client_ids = StaffClientAssignment.objects.filter(
                        staff=staff,
                        is_active=True
                    ).values_list('client_id', flat=True)
                    
                    if assigned_client_ids:
                        queryset = queryset.filter(
                            clientprogramenrollment__client_id__in=assigned_client_ids
                        ).distinct()
                    else:
                        # If no client assignments, show no programs
                        queryset = queryset.none()
            except Exception:
                pass
        
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
        queryset = self.get_queryset()
        from django.db.models.query import QuerySet
        if isinstance(queryset, QuerySet):
            # It's a QuerySet
            total_filtered_count = queryset.count()
        else:
            # It's a list (from capacity filtering)
            total_filtered_count = len(queryset)
        
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
class ProgramDetailView(AnalystAccessMixin, ProgramManagerAccessMixin, DetailView):
    model = Program
    template_name = 'programs/program_detail.html'
    context_object_name = 'program'
    slug_field = 'external_id'
    slug_url_kwarg = 'external_id'
    
    def get(self, request, *args, **kwargs):
        """Override get method to handle permission checks before rendering"""
        try:
            # First, try to get the object
            self.object = self.get_object()
        except Exception:
            # If object doesn't exist, handle based on request type
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                from django.http import JsonResponse
                return JsonResponse({
                    'error': True,
                    'message': "You don't have access to this program. Only programs assigned to you are accessible.",
                    'type': 'permission_error'
                }, status=403)
            else:
                from django.shortcuts import redirect
                from django.urls import reverse
                return redirect(f"{reverse('core:permission_error')}?type=program_not_assigned&resource=program")
        
        # Check if user has access to this program
        if not request.user.is_superuser:
            try:
                staff = request.user.staff_profile
                if staff.is_program_manager():
                    assigned_programs = staff.get_assigned_programs()
                    if self.object not in assigned_programs:
                        # Handle based on request type
                        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                            from django.http import JsonResponse
                            return JsonResponse({
                                'error': True,
                                'message': f"You don't have access to {self.object.name}. Only programs assigned to you are accessible.",
                                'type': 'permission_error'
                            }, status=403)
                        else:
                            from django.shortcuts import redirect
                            from django.urls import reverse
                            return redirect(f"{reverse('core:permission_error')}?type=program_not_assigned&resource=program&name={self.object.name}")
                
                elif staff.is_leader():
                    # Leaders can only access programs from their assigned departments
                    from core.models import Department
                    assigned_departments = Department.objects.filter(
                        leader_assignments__staff=staff,
                        leader_assignments__is_active=True
                    ).distinct()
                    assigned_programs = Program.objects.filter(
                        department__in=assigned_departments
                    ).distinct()
                    
                    if self.object not in assigned_programs:
                        # Handle based on request type
                        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                            from django.http import JsonResponse
                            return JsonResponse({
                                'error': True,
                                'message': f"You don't have access to {self.object.name}. Only programs in your assigned departments are accessible.",
                                'type': 'permission_error'
                            }, status=403)
                        else:
                            from django.shortcuts import redirect
                            from django.urls import reverse
                            return redirect(f"{reverse('core:permission_error')}?type=program_not_assigned&resource=program&name={self.object.name}")
            except Exception:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    from django.http import JsonResponse
                    return JsonResponse({
                        'error': True,
                        'message': "You don't have permission to access this program.",
                        'type': 'permission_error'
                    }, status=403)
                else:
                    from django.shortcuts import redirect
                    from django.urls import reverse
                    return redirect(f"{reverse('core:permission_error')}?type=access_denied&resource=program")
        
        # If we get here, user has access, proceed with normal rendering
        context = self.get_context_data(object=self.object)
        
        # Check if this is an AJAX request for client list
        if request.GET.get('ajax') == '1':
            from django.template.loader import render_to_string
            client_list_html = render_to_string('programs/client_list_ajax.html', context)
            from django.http import HttpResponse
            return HttpResponse(client_list_html)
        
        return self.render_to_response(context)
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        program = context.get('program') or self.object
        
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
        from django.core.paginator import Paginator
        
        enrolled_client_ids = current_enrollments.values_list('client_id', flat=True)
        available_clients_queryset = Client.objects.exclude(id__in=enrolled_client_ids).order_by('first_name', 'last_name')
        
        # Add pagination for available clients
        clients_per_page = self.request.GET.get('clients_per_page', '10')
        try:
            clients_per_page = int(clients_per_page)
            if clients_per_page not in [5, 10, 50, 100]:
                clients_per_page = 10
        except (ValueError, TypeError):
            clients_per_page = 10
            
        clients_paginator = Paginator(available_clients_queryset, clients_per_page)
        clients_page_number = self.request.GET.get('clients_page', 1)
        try:
            available_clients_page = clients_paginator.get_page(clients_page_number)
        except:
            available_clients_page = clients_paginator.get_page(1)
        
        available_clients = available_clients_page
        
        # Get available staff members who can be assigned as program managers
        from core.models import Staff
        
        assigned_manager_ids = program_managers.values_list('staff_id', flat=True)
        # Only show staff members who have the Manager role
        available_staff_queryset = Staff.objects.filter(
            staffrole__role__name='Manager'
        ).exclude(id__in=assigned_manager_ids).order_by('first_name', 'last_name').distinct()
        
        # Get all available staff (no pagination)
        available_staff = available_staff_queryset
        
        # Ensure all querysets are properly initialized (defensive programming)
        if current_enrollments is None:
            current_enrollments = ClientProgramEnrollment.objects.none()
        if program_staff is None:
            program_staff = ProgramStaff.objects.none()
        if program_managers is None:
            program_managers = ProgramManagerAssignment.objects.none()
        if available_clients is None:
            available_clients = Client.objects.none()
        if available_staff is None:
            available_staff = Staff.objects.none()
        
        # Get capacity information with defensive programming
        try:
            current_enrollments_count = program.get_current_enrollments_count()
        except Exception:
            current_enrollments_count = 0
            
        try:
            capacity_percentage = program.get_capacity_percentage()
        except Exception:
            capacity_percentage = 0.0
            
        try:
            available_capacity = program.get_available_capacity()
        except Exception:
            available_capacity = 0
            
        try:
            is_at_capacity = program.is_at_capacity()
        except Exception:
            is_at_capacity = False
        
        # Get enrollment history (last 30 days)
        from datetime import timedelta
        thirty_days_ago = timezone.now().date() - timedelta(days=30)
        try:
            recent_enrollments = ClientProgramEnrollment.objects.filter(
                program=program,
                start_date__gte=thirty_days_ago
            ).select_related('client').order_by('-start_date')[:10]
        except Exception:
            recent_enrollments = ClientProgramEnrollment.objects.none()
        
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
            'clients_paginator': clients_paginator,
            'clients_page_obj': available_clients_page,
            'clients_per_page': clients_per_page,
        })
        
        return context

@method_decorator(jwt_required, name='dispatch')
class ProgramBulkEnrollView(ProgramManagerAccessMixin, View):
    """Handle bulk enrollment of clients in a program"""
    
    def dispatch(self, request, *args, **kwargs):
        """Check if user has permission to enroll clients"""
        if request.user.is_authenticated:
            try:
                staff = request.user.staff_profile
                user_roles = staff.staffrole_set.select_related('role').all()
                role_names = [staff_role.role.name for staff_role in user_roles]
                
                # Staff role users cannot enroll clients
                if 'Staff' in role_names and not any(role in ['SuperAdmin', 'Admin', 'Manager'] for role in role_names):
                    from django.contrib import messages
                    messages.error(request, 'You do not have permission to enroll clients. Contact your administrator.')
                    return redirect('programs:list')
            except Exception:
                pass
        
        return super().dispatch(request, *args, **kwargs)
    
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
        
        return redirect(reverse('programs:detail', args=[external_id]) + '?enrolled=true')

@method_decorator(jwt_required, name='dispatch')
class ProgramBulkAssignManagersView(ProgramManagerAccessMixin, View):
    """Handle bulk assignment of program managers to a program"""
    
    def dispatch(self, request, *args, **kwargs):
        """Check if user has permission to assign managers"""
        if request.user.is_authenticated:
            try:
                staff = request.user.staff_profile
                user_roles = staff.staffrole_set.select_related('role').all()
                role_names = [staff_role.role.name for staff_role in user_roles]
                
                # Only SuperAdmin users can assign managers
                if not any(role in ['SuperAdmin', 'Admin'] for role in role_names):
                    from django.contrib import messages
                    messages.error(request, 'You do not have permission to assign managers. Contact your administrator.')
                    return redirect('programs:list')
            except Exception:
                pass
        
        return super().dispatch(request, *args, **kwargs)
    
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
    fields = ['name', 'department', 'location', 'capacity_current', 'capacity_effective_date', 'status']
    success_url = reverse_lazy('programs:list')
    
    def dispatch(self, request, *args, **kwargs):
        """Check if user has permission to create programs"""
        if request.user.is_authenticated:
            try:
                staff = request.user.staff_profile
                user_roles = staff.staffrole_set.select_related('role').all()
                role_names = [staff_role.role.name for staff_role in user_roles]
                
                # Staff role users cannot create programs
                if 'Staff' in role_names and not any(role in ['SuperAdmin', 'Admin', 'Manager'] for role in role_names):
                    from django.contrib import messages
                    messages.error(request, 'You do not have permission to create programs. Contact your administrator.')
                    return redirect('programs:list')
            except Exception:
                pass
        
        return super().dispatch(request, *args, **kwargs)
    
    def get_initial(self):
        """Set default values for the form"""
        initial = super().get_initial()
        # Get or create NA department
        na_department, _ = Department.objects.get_or_create(
            name='NA',
            defaults={'owner': 'System'}
        )
        initial['department'] = na_department
        initial['status'] = 'active'  # Set default status to active
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
    fields = ['name', 'department', 'location', 'capacity_current', 'capacity_effective_date', 'status']
    slug_field = 'external_id'
    slug_url_kwarg = 'external_id'
    success_url = reverse_lazy('programs:list')
    
    def dispatch(self, request, *args, **kwargs):
        """Check if user has permission to edit programs"""
        if request.user.is_authenticated:
            try:
                staff = request.user.staff_profile
                user_roles = staff.staffrole_set.select_related('role').all()
                role_names = [staff_role.role.name for staff_role in user_roles]
                
                # Staff role users cannot edit programs
                if 'Staff' in role_names and not any(role in ['SuperAdmin', 'Admin', 'Manager'] for role in role_names):
                    from django.contrib import messages
                    messages.error(request, 'You do not have permission to edit programs. Contact your administrator.')
                    return redirect('programs:list')
            except Exception:
                pass
        
        return super().dispatch(request, *args, **kwargs)
    
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
    
    def dispatch(self, request, *args, **kwargs):
        """Check if user has permission to delete programs"""
        if request.user.is_authenticated:
            try:
                staff = request.user.staff_profile
                user_roles = staff.staffrole_set.select_related('role').all()
                role_names = [staff_role.role.name for staff_role in user_roles]
                
                # Staff role users cannot delete programs
                if 'Staff' in role_names and not any(role in ['SuperAdmin', 'Admin', 'Manager'] for role in role_names):
                    from django.contrib import messages
                    messages.error(request, 'You do not have permission to delete programs. Contact your administrator.')
                    return redirect('programs:list')
            except Exception:
                pass
        
        return super().dispatch(request, *args, **kwargs)
    
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
        
        # For staff-only users, apply the same filtering as ProgramListView
        if self.request.user.is_authenticated:
            try:
                staff = self.request.user.staff_profile
                user_roles = staff.staffrole_set.select_related('role').all()
                role_names = [staff_role.role.name for staff_role in user_roles]
                
                if 'Staff' in role_names and not any(role in ['SuperAdmin', 'Admin', 'Manager'] for role in role_names):
                    # Staff-only users see ONLY programs where their assigned clients are enrolled
                    from staff.models import StaffClientAssignment
                    
                    # Get programs where their assigned clients are enrolled
                    assigned_client_ids = StaffClientAssignment.objects.filter(
                        staff=staff,
                        is_active=True
                    ).values_list('client_id', flat=True)
                    
                    if assigned_client_ids:
                        queryset = queryset.filter(
                            clientprogramenrollment__client_id__in=assigned_client_ids
                        ).distinct()
                    else:
                        # If no client assignments, show no programs
                        queryset = queryset.none()
            except Exception:
                pass
        
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

@method_decorator(jwt_required, name='dispatch')
class ProgramBulkChangeDepartmentView(ProgramManagerAccessMixin, View):
    """Handle bulk department change for programs"""
    
    def dispatch(self, request, *args, **kwargs):
        # Check if user has permission to change departments
        if request.user.is_authenticated:
            try:
                staff = request.user.staff_profile
                user_roles = staff.staffrole_set.select_related('role').all()
                role_names = [staff_role.role.name for staff_role in user_roles]
                
                # Only SuperAdmin, Admin, and Manager can change departments
                if not any(role in ['SuperAdmin', 'Admin', 'Manager'] for role in role_names):
                    return JsonResponse({
                        'success': False,
                        'error': 'You do not have permission to change program departments.'
                    }, status=403)
            except Exception:
                return JsonResponse({
                    'success': False,
                    'error': 'Unable to verify user permissions.'
                }, status=403)
        
        return super().dispatch(request, *args, **kwargs)
    
    def post(self, request):
        from core.models import Program, Department
        from django.contrib import messages
        from django.db import transaction
        from django.shortcuts import redirect
        import json
        
        try:
            # Get data from form POST
            program_ids_json = request.POST.get('program_ids', '[]')
            new_department_id = request.POST.get('new_department_id', '')
            
            # Parse program IDs from JSON string
            try:
                program_ids = json.loads(program_ids_json)
            except json.JSONDecodeError:
                program_ids = []
            
            if not program_ids:
                messages.error(request, 'No programs selected for department change.')
                return redirect('programs:list')
            
            if not new_department_id:
                messages.error(request, 'No department selected.')
                return redirect('programs:list')
            
            # Get the new department
            try:
                new_department = Department.objects.get(id=new_department_id)
            except Department.DoesNotExist:
                messages.error(request, 'Selected department does not exist.')
                return redirect('programs:list')
            
            # Get programs to update
            programs_to_update = Program.objects.filter(external_id__in=program_ids)
            
            if not programs_to_update.exists():
                messages.error(request, 'No valid programs found to update.')
                return redirect('programs:list')
            
            updated_count = 0
            errors = []
            
            with transaction.atomic():
                for program in programs_to_update:
                    try:
                        old_department = program.department
                        program.department = new_department
                        program.save()
                        updated_count += 1
                    except Exception as e:
                        errors.append(f"Failed to update {program.name}: {str(e)}")
            
            if updated_count > 0:
                messages.success(request, f'Successfully updated department for {updated_count} program(s) to {new_department.name}.')
                
                # Show warnings for any errors that occurred
                if errors:
                    for error in errors:
                        messages.warning(request, error)
            else:
                messages.error(request, 'No programs were updated.')
                if errors:
                    for error in errors:
                        messages.warning(request, error)
            
            return redirect('programs:list')
                
        except Exception as e:
            messages.error(request, f'An error occurred: {str(e)}')
            return redirect('programs:list')


@method_decorator(jwt_required, name='dispatch')
class ProgramBulkDeleteView(ProgramManagerAccessMixin, View):
    """Handle bulk deletion of programs"""
    
    def dispatch(self, request, *args, **kwargs):
        """Check if user has permission to delete programs"""
        if request.user.is_authenticated:
            try:
                staff = request.user.staff_profile
                user_roles = staff.staffrole_set.select_related('role').all()
                role_names = [staff_role.role.name for staff_role in user_roles]
                
                # Only SuperAdmin and Admin users can bulk delete programs
                if not any(role in ['SuperAdmin', 'Admin'] for role in role_names):
                    from django.http import JsonResponse
                    return JsonResponse({
                        'success': False,
                        'error': 'You do not have permission to delete programs. Contact your administrator.'
                    }, status=403)
            except Exception:
                from django.http import JsonResponse
                return JsonResponse({
                    'success': False,
                    'error': 'You do not have permission to delete programs.'
                }, status=403)
        
        return super().dispatch(request, *args, **kwargs)
    
    def post(self, request):
        from core.models import Program, ClientProgramEnrollment, ProgramManagerAssignment
        from django.http import JsonResponse
        from django.db import transaction
        import json
        
        try:
            # Parse JSON data from request body
            data = json.loads(request.body)
            program_ids = data.get('program_ids', [])
            
            if not program_ids:
                return JsonResponse({
                    'success': False,
                    'error': 'No programs selected for deletion.'
                })
            
            # Get programs to delete
            programs_to_delete = Program.objects.filter(external_id__in=program_ids)
            
            if not programs_to_delete.exists():
                return JsonResponse({
                    'success': False,
                    'error': 'No valid programs found to delete.'
                })
            
            deleted_count = 0
            errors = []
            
            with transaction.atomic():
                for program in programs_to_delete:
                    try:
                        # Create audit log entry before deletion
                        try:
                            from core.models import create_audit_log
                            create_audit_log(
                                entity_name='Program',
                                entity_id=program.external_id,
                                action='delete',
                                changed_by=request.user,
                                diff_data={
                                    'name': program.name,
                                    'department': str(program.department),
                                    'location': program.location or '',
                                    'capacity_current': program.capacity_current,
                                    'capacity_effective_date': str(program.capacity_effective_date) if program.capacity_effective_date else None,
                                    'deleted_by': f"{request.user.first_name} {request.user.last_name}".strip() or request.user.username,
                                    'source': 'bulk_delete'
                                }
                            )
                        except Exception as e:
                            print(f"Error creating audit log for program deletion: {e}")
                        
                        # Delete related data first
                        ClientProgramEnrollment.objects.filter(program=program).delete()
                        ProgramManagerAssignment.objects.filter(program=program).delete()
                        
                        # Delete the program
                        program.delete()
                        deleted_count += 1
                        
                    except Exception as e:
                        errors.append(f"Error deleting {program.name}: {str(e)}")
            
            if deleted_count > 0:
                return JsonResponse({
                    'success': True,
                    'deleted_count': deleted_count,
                    'message': f'Successfully deleted {deleted_count} program(s).'
                })
            else:
                return JsonResponse({
                    'success': False,
                    'error': 'Failed to delete any programs.',
                    'errors': errors
                })
                
        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'error': 'Invalid JSON data.'
            })
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': f'An error occurred: {str(e)}'
            })