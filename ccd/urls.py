from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import TemplateView
from django.http import HttpResponse
from django.views.decorators.cache import cache_control
from django.contrib.auth import views as auth_views
from core.views import home, dashboard
import os

@cache_control(max_age=86400)  # Cache for 1 day
def favicon_view(request):
    """Serve favicon.ico"""
    favicon_path = os.path.join(settings.STATIC_ROOT, 'favicon.ico')
    if os.path.exists(favicon_path):
        with open(favicon_path, 'rb') as f:
            return HttpResponse(f.read(), content_type='image/x-icon')
    # Fallback to static URL if not in STATIC_ROOT
    from django.shortcuts import redirect
    return redirect(settings.STATIC_URL + 'favicon.ico')

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', home, name='home'),
    path('dashboard/', dashboard, name='dashboard'),
    path('test/', TemplateView.as_view(template_name='test.html'), name='test'),
    path('core/', include('core.urls')),
    path('clients/', include('clients.urls')),
    path('programs/', include('programs.urls')),
    path('staff/', include('staff.urls')),
    path('reports/', include('reports.urls')),
    # Override login to redirect authenticated users
    path('accounts/login/', auth_views.LoginView.as_view(
        template_name='registration/login.html',
        redirect_authenticated_user=True
    ), name='login'),
    # Include other auth URLs (logout, password reset, etc.)
    path('accounts/', include('django.contrib.auth.urls')),
    # Direct favicon route for browsers that request /favicon.ico
    path('favicon.ico', favicon_view),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)