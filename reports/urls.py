from django.urls import path
from . import views

app_name = 'reports'

urlpatterns = [
    path('', views.ReportListView.as_view(), name='list'),
    path('organizational-summary/', views.OrganizationalSummaryView.as_view(), name='organizational_summary'),
    path('organizational-summary/export/', views.OrganizationalSummaryExportView.as_view(), name='organizational_summary_export'),
    path('vacancy-tracker/', views.VacancyTrackerView.as_view(), name='vacancy_tracker'),
    path('export/<str:report_type>/', views.ReportExportView.as_view(), name='export'),
    
    # Client Reports
    path('client-demographics/', views.ClientDemographicsView.as_view(), name='client_demographics'),
    path('client-demographics/export/', views.ClientDemographicsExportView.as_view(), name='client_demographics_export'),
    path('client-enrollment-history/', views.ClientEnrollmentHistoryView.as_view(), name='client_enrollment_history'),
    path('client-enrollment-history/export/', views.ClientEnrollmentHistoryExportView.as_view(), name='client_enrollment_history_export'),
    path('client-outcomes/', views.ClientOutcomesView.as_view(), name='client_outcomes'),
    path('client-outcomes/export/', views.ClientOutcomesExportView.as_view(), name='client_outcomes_export'),
    
    # Program Reports
    path('program-capacity/', views.ProgramCapacityView.as_view(), name='program_capacity'),
    path('program-capacity/export/', views.ProgramCapacityExportView.as_view(), name='program_capacity_export'),
    path('program-performance/', views.ProgramPerformanceView.as_view(), name='program_performance'),
    path('program-performance/export/', views.ProgramPerformanceExportView.as_view(), name='program_performance_export'),
    path('department-summary/', views.DepartmentSummaryView.as_view(), name='department_summary'),
]
