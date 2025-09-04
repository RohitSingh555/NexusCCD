from django.urls import path
from . import views

app_name = 'staff'

urlpatterns = [
    path('', views.StaffListView.as_view(), name='list'),
    path('<uuid:external_id>/', views.StaffDetailView.as_view(), name='detail'),
    path('create/', views.StaffCreateView.as_view(), name='create'),
    path('<uuid:external_id>/edit/', views.StaffUpdateView.as_view(), name='edit'),
    path('<uuid:external_id>/delete/', views.StaffDeleteView.as_view(), name='delete'),
]
