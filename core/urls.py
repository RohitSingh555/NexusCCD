from django.urls import path
from . import api_views

app_name = 'core'

urlpatterns = [
    path('api/auth/register/', api_views.register, name='register'),
    path('api/auth/login/', api_views.login, name='login'),
    path('api/auth/refresh/', api_views.refresh_token, name='refresh_token'),
    path('api/auth/logout/', api_views.logout, name='logout'),
    path('api/auth/profile/', api_views.user_profile, name='user_profile'),
    path('api/debug/', api_views.debug_info, name='debug_info'),
]
