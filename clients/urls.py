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
]
