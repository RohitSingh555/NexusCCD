from django.urls import path
from . import views

app_name = 'staff'

urlpatterns = [
    path('', views.StaffListView.as_view(), name='list'),
    path('<uuid:external_id>/', views.StaffDetailView.as_view(), name='detail'),
    path('create/', views.StaffCreateView.as_view(), name='create'),
    path('<uuid:external_id>/edit/', views.StaffUpdateView.as_view(), name='edit'),
    path('<uuid:external_id>/delete/', views.StaffDeleteView.as_view(), name='delete'),
    path('<uuid:external_id>/roles/', views.StaffRoleManageView.as_view(), name='manage_roles'),
    path('<uuid:external_id>/roles/update/', views.update_staff_roles, name='update_roles'),
    path('upgrade-user/<uuid:external_id>/', views.upgrade_user_to_staff, name='upgrade_user'),
    path('<uuid:external_id>/toggle-role/', views.toggle_staff_role, name='toggle_role'),
    path('<uuid:external_id>/programs/', views.manage_program_assignments, name='manage_programs'),
    path('<uuid:external_id>/program-assignments/', views.manage_program_assignments_staff, name='manage_program_assignments_staff'),
    path('<uuid:external_id>/client-assignments/', views.manage_client_assignments, name='manage_client_assignments'),
    path('<uuid:external_id>/department-assignments/', views.manage_department_assignments, name='manage_department_assignments'),
]