from django.urls import path
from . import views

app_name = 'reports'

urlpatterns = [
    path('', views.ReportListView.as_view(), name='list'),
    path('organizational-summary/', views.OrganizationalSummaryView.as_view(), name='organizational_summary'),
    path('vacancy-tracker/', views.VacancyTrackerView.as_view(), name='vacancy_tracker'),
    path('export/<str:report_type>/', views.ReportExportView.as_view(), name='export'),
]
