from django.urls import path
from . import views

app_name = 'programs'

urlpatterns = [
    path('', views.ProgramListView.as_view(), name='list'),
    path('export/', views.ProgramCSVExportView.as_view(), name='export'),
    path('upload/', views.ProgramCSVUploadView.as_view(), name='upload'),
    path('<uuid:external_id>/', views.ProgramDetailView.as_view(), name='detail'),
    path('create/', views.ProgramCreateView.as_view(), name='create'),
    path('<uuid:external_id>/edit/', views.ProgramUpdateView.as_view(), name='edit'),
    path('<uuid:external_id>/delete/', views.ProgramDeleteView.as_view(), name='delete'),
    path('<uuid:external_id>/enroll/', views.ProgramBulkEnrollView.as_view(), name='bulk_enroll'),
    path('<uuid:external_id>/assign-managers/', views.ProgramBulkAssignManagersView.as_view(), name='bulk_assign_managers'),
    path('bulk-delete/', views.ProgramBulkDeleteView.as_view(), name='bulk_delete'),
    path('bulk-restore/', views.ProgramBulkRestoreView.as_view(), name='bulk_restore'),
    path('bulk-change-department/', views.ProgramBulkChangeDepartmentView.as_view(), name='bulk_change_department'),
]
