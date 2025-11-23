"""
URL configuration for tenant management.
"""

from django.urls import path
from . import views

app_name = 'tenants'

urlpatterns = [
    # Authentication endpoints
    path('register/', views.register, name='register'),
    path('login/', views.login, name='login'),
    path('logout/', views.logout, name='logout'),
    path('me/', views.current_user, name='current_user'),
    
    # Legacy API key endpoints (for API access)
    path('create/', views.create_tenant, name='create_tenant'),
    path('list/', views.list_tenants, name='list_tenants'),
]

