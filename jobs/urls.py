"""
URL routing for jobs API.
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import JobViewSet, DLQViewSet, MetricsView, HealthView

# Create router and register viewsets
router = DefaultRouter()
router.register(r'jobs', JobViewSet, basename='job')
router.register(r'dlq', DLQViewSet, basename='dlq')

app_name = 'jobs'

urlpatterns = [
    # Viewset routes
    path('', include(router.urls)),
    
    # Additional endpoints
    path('metrics/', MetricsView.as_view(), name='metrics'),
    path('health/', HealthView.as_view(), name='health'),
]

