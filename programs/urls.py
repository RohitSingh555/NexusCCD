from django.urls import path
from . import views

app_name = 'programs'

urlpatterns = [
    path('', views.ProgramListView.as_view(), name='list'),
    path('<uuid:external_id>/', views.ProgramDetailView.as_view(), name='detail'),
    path('create/', views.ProgramCreateView.as_view(), name='create'),
    path('<uuid:external_id>/edit/', views.ProgramUpdateView.as_view(), name='edit'),
    path('<uuid:external_id>/delete/', views.ProgramDeleteView.as_view(), name='delete'),
]
