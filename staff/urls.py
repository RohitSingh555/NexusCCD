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
]