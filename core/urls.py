from django.urls import path
from . import api_views, views
from .permission_error_view import PermissionErrorView, permission_error_ajax

app_name = 'core'

urlpatterns = [
    # API endpoints
    path('api/auth/register/', api_views.register, name='register'),
    path('api/auth/login/', api_views.login, name='login'),
    path('api/auth/refresh/', api_views.refresh_token, name='refresh_token'),
    path('api/auth/logout/', api_views.logout, name='logout'),
    path('api/auth/profile/', api_views.user_profile, name='user_profile'),
    path('api/debug/', api_views.debug_info, name='debug_info'),

    # Profile views
    path('profile/', views.profile, name='profile'),
    path('profile/edit/', views.edit_profile, name='edit_profile'),
    path('profile/password/', views.change_password, name='change_password'),
    
    # Main views
    path('departments/', views.departments, name='departments'),
    path('enrollments/', views.EnrollmentListView.as_view(), name='enrollments'),
    path('enrollments/export/', views.EnrollmentCSVExportView.as_view(), name='enrollments_export'),
    path('restrictions/', views.RestrictionListView.as_view(), name='restrictions'),
    path('restrictions/export/', views.RestrictionCSVExportView.as_view(), name='restrictions_export'),
    path('audit-log/', views.AuditLogListView.as_view(), name='audit_log'),
    path('audit-log/restore/<int:log_id>/', views.AuditLogRestoreView.as_view(), name='audit_log_restore'),
    path('audit-log/clear-old/', views.clear_old_audit_logs, name='audit_log_clear_old'),
    path('test-messages/', views.test_messages, name='test_messages'),
    path('test-messages/success/', views.test_success, name='test_success'),
    path('test-messages/error/', views.test_error, name='test_error'),
    path('test-messages/warning/', views.test_warning, name='test_warning'),
    path('test-messages/info/', views.test_info, name='test_info'),
    path('test-messages/create-success/', views.test_create_success, name='test_create_success'),
    path('test-messages/update-success/', views.test_update_success, name='test_update_success'),
    path('test-messages/delete-success/', views.test_delete_success, name='test_delete_success'),
    path('test-messages/validation-error/', views.test_validation_error, name='test_validation_error'),
    path('test-messages/permission-error/', views.test_permission_error, name='test_permission_error'),
    path('test-messages/not-found-error/', views.test_not_found_error, name='test_not_found_error'),
    path('test-messages/bulk-success/', views.test_bulk_operation_success, name='test_bulk_operation_success'),
    path('test-messages/bulk-error/', views.test_bulk_operation_error, name='test_bulk_operation_error'),
    
    # API endpoints for capacity checking
    path('check-program-capacity/', views.check_program_capacity, name='check_program_capacity'),
    
    # API endpoints for client and program search
    path('search-clients/', views.search_clients, name='search_clients'),
    path('search-programs/', views.search_programs, name='search_programs'),
    path('search-staff/', views.search_staff, name='search_staff'),
    path('notifications/', views.notifications_list, name='notifications_list'),
    path('notifications/<uuid:notification_id>/read/', views.notification_mark_read, name='notification_mark_read'),
    path('notifications/<uuid:notification_id>/unread/', views.notification_mark_unread, name='notification_mark_unread'),
    path('notifications/read-all/', views.notification_mark_all_read, name='notification_mark_all_read'),
    
    # Department CRUD views
    path('departments/create/', views.DepartmentCreateView.as_view(), name='departments_create'),
    path('departments/<uuid:external_id>/', views.DepartmentDetailView.as_view(), name='departments_detail'),
    path('departments/<uuid:external_id>/edit/', views.DepartmentUpdateView.as_view(), name='departments_edit'),
    path('departments/<uuid:external_id>/delete/', views.DepartmentDeleteView.as_view(), name='departments_delete'),
    path('departments/bulk-delete/', views.bulk_delete_departments, name='departments_bulk_delete'),
    path('departments/bulk-restore/', views.bulk_restore_departments, name='departments_bulk_restore'),
    
    # Enrollment CRUD views
    path('enrollments/create/', views.EnrollmentCreateView.as_view(), name='enrollments_create'),
    path('enrollments/<uuid:external_id>/', views.EnrollmentDetailView.as_view(), name='enrollments_detail'),
    path('enrollments/<uuid:external_id>/edit/', views.EnrollmentUpdateView.as_view(), name='enrollments_edit'),
    path('enrollments/<uuid:external_id>/delete/', views.EnrollmentDeleteView.as_view(), name='enrollments_delete'),
    
    # Service Restriction CRUD views
    path('restrictions/create/', views.RestrictionCreateView.as_view(), name='restrictions_create'),
    path('restrictions/<uuid:external_id>/', views.RestrictionDetailView.as_view(), name='restrictions_detail'),
    path('restrictions/<uuid:external_id>/edit/', views.RestrictionUpdateView.as_view(), name='restrictions_edit'),
    path('restrictions/<uuid:external_id>/delete/', views.RestrictionDeleteView.as_view(), name='restrictions_delete'),
    path('restrictions/<uuid:external_id>/approve/', views.approve_restriction, name='restrictions_approve'),
    path('restrictions/bulk-delete/', views.bulk_delete_restrictions, name='restrictions_bulk_delete'),
    path('restrictions/bulk-restore/', views.bulk_restore_restrictions, name='restrictions_bulk_restore'),
    
    # Enrollment bulk operations
    path('enrollments/bulk-delete/', views.bulk_delete_enrollments, name='enrollments_bulk_delete'),
    path('enrollments/bulk-restore/', views.bulk_restore_enrollments, name='enrollments_bulk_restore'),
    
    # Permission error handling
    path('permission-error/', PermissionErrorView.as_view(), name='permission_error'),
    path('api/permission-error/', permission_error_ajax, name='permission_error_ajax'),

    # Help page
    path('help/', views.help_page, name='help'),
]

# In your main urls.py, add:
from django.conf import settings
from django.conf.urls.static import static

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
