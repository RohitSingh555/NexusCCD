from django.urls import path
from . import views

app_name = 'clients'

urlpatterns = [
    path('', views.ClientListView.as_view(), name='list'),
    path('<uuid:external_id>/', views.ClientDetailView.as_view(), name='detail'),
    path('create/', views.ClientCreateView.as_view(), name='create'),
    path('<uuid:external_id>/edit/', views.ClientUpdateView.as_view(), name='edit'),
    path('<uuid:external_id>/delete/', views.ClientDeleteView.as_view(), name='delete'),
    path('upload/', views.ClientUploadView.as_view(), name='upload'),
    path('upload/process/', views.upload_clients, name='upload_process'),
    path('download-sample/<str:file_type>/', views.download_sample, name='download_sample'),
    path('bulk-delete/', views.bulk_delete_clients, name='bulk_delete'),
    path('dedupe/', views.ClientDedupeView.as_view(), name='dedupe'),
    path('dedupe/action/<int:duplicate_id>/<str:action>/', views.mark_duplicate_action, name='duplicate_action'),
    path('dedupe/bulk-action/', views.bulk_duplicate_action, name='bulk_duplicate_action'),
    path('dedupe/compare/<int:duplicate_id>/', views.client_duplicate_comparison, name='duplicate-comparison'),
    path('dedupe/not-duplicate/<int:duplicate_id>/', views.client_not_duplicate_comparison, name='not-duplicate-comparison'),
    path('dedupe/merge/<int:duplicate_id>/', views.client_merge_view, name='duplicate-merge'),
    path('dedupe/merge/<int:duplicate_id>/process/', views.merge_clients, name='merge_clients'),
    path('dedupe/resolve/<int:duplicate_id>/', views.resolve_duplicate_selection, name='resolve_duplicate'),
    path('export/', views.export_clients, name='export'),
    path('<uuid:external_id>/update-profile-picture/', views.update_profile_picture, name='update_profile_picture'),
    path('<uuid:external_id>/remove-profile-picture/', views.remove_profile_picture, name='remove_profile_picture'),
]
