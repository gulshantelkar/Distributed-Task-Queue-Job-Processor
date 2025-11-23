"""
URL configuration for taskqueue project.
"""

from django.contrib import admin
from django.urls import path, include
from django.views.generic import TemplateView

urlpatterns = [
    # Admin interface
    path('admin/', admin.site.urls),
    
    # API endpoints
    path('api/', include('jobs.urls', namespace='jobs')),
    path('api/tenants/', include('tenants.urls', namespace='tenants')),
    
    # Landing page (Register/Login)
    path('', TemplateView.as_view(template_name='dashboard/landing.html'), name='landing'),
    
    # Dashboard (Protected)
    path('dashboard/', TemplateView.as_view(template_name='dashboard/index.html'), name='dashboard'),
]
