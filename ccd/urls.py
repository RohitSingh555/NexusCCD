from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import TemplateView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', TemplateView.as_view(template_name='home.html'), name='home'),
    path('test/', TemplateView.as_view(template_name='test.html'), name='test'),
    path('core/', include('core.urls')),
    path('clients/', include('clients.urls')),
    path('programs/', include('programs.urls')),
    path('staff/', include('staff.urls')),
    path('reports/', include('reports.urls')),
    path('accounts/', include('django.contrib.auth.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)