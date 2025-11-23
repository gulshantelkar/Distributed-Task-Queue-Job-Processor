"""
WebSocket URL routing for jobs app.
"""

from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/jobs/(?P<tenant_id>[^/]+)/$', consumers.JobUpdateConsumer.as_asgi()),
]

