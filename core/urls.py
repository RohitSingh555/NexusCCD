from django.urls import path
from . import api_views, views

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
    path('restrictions/', views.restrictions, name='restrictions'),
    path('approvals/', views.approvals, name='approvals'),
    path('audit-log/', views.audit_log, name='audit_log'),
    
    # API endpoints for capacity checking
    path('check-program-capacity/', views.check_program_capacity, name='check_program_capacity'),
    
    # API endpoints for client and program search
    path('search-clients/', views.search_clients, name='search_clients'),
    path('search-programs/', views.search_programs, name='search_programs'),
    
    # Department CRUD views
    path('departments/create/', views.DepartmentCreateView.as_view(), name='departments_create'),
    path('departments/<uuid:external_id>/', views.DepartmentDetailView.as_view(), name='departments_detail'),
    path('departments/<uuid:external_id>/edit/', views.DepartmentUpdateView.as_view(), name='departments_edit'),
    path('departments/<uuid:external_id>/delete/', views.DepartmentDeleteView.as_view(), name='departments_delete'),
    
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
    path('restrictions/bulk-delete/', views.bulk_delete_restrictions, name='restrictions_bulk_delete'),
    
    # Enrollment bulk operations
    path('enrollments/bulk-delete/', views.bulk_delete_enrollments, name='enrollments_bulk_delete'),
]

# In your main urls.py, add:
from django.conf import settings
from django.conf.urls.static import static

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
