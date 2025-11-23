"""
API views for job management.
"""

import logging
from rest_framework import viewsets, status, views
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from django_filters.rest_framework import DjangoFilterBackend
from django.shortcuts import get_object_or_404
from django.utils import timezone

from .models import Job, DeadLetterQueue, JobHistory
from .serializers import (
    JobCreateSerializer,
    JobSerializer,
    JobDetailSerializer,
    DLQSerializer,
    JobHistorySerializer,
    JobStatsSerializer,
    MetricsSerializer
)
from .services import JobService
from .exceptions import (
    QuotaExceededException,
    RateLimitExceededException,
    JobNotFoundException
)
from .permissions import HasTenantAccess

logger = logging.getLogger(__name__)


class JobViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for job management.
    
    Provides:
    - list: List all jobs for the tenant
    - retrieve: Get specific job details
    - create: Submit a new job
    - stats: Get job statistics
    """
    permission_classes = [HasTenantAccess]
    serializer_class = JobSerializer
    filterset_fields = ['status', 'job_type', 'priority']
    ordering_fields = ['created_at', 'priority', 'started_at']
    ordering = ['-created_at']
    
    def get_queryset(self):
        """Filter jobs by authenticated tenant."""
        if not hasattr(self.request, 'tenant'):
            return Job.objects.none()
        
        return Job.objects.filter(
            tenant=self.request.tenant
        ).select_related('tenant')
    
    def get_serializer_class(self):
        """Use detailed serializer for retrieve action."""
        if self.action == 'retrieve':
            return JobDetailSerializer
        return JobSerializer
    
    def create(self, request):
        """
        Submit a new job.
        
        Request body:
        {
            "job_type": "send_email",
            "payload": {"to": "user@example.com", "subject": "Hello"},
            "idempotency_key": "optional-unique-key",
            "priority": 0,
            "max_retries": 3
        }
        """
        serializer = JobCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        try:
            job, created = JobService.create_job(
                tenant=request.tenant,
                **serializer.validated_data
            )
            
            response_serializer = JobSerializer(job)
            status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
            
            return Response(
                {
                    'job': response_serializer.data,
                    'created': created,
                    'message': 'Job created successfully' if created else 'Duplicate job (idempotency)'
                },
                status=status_code
            )
        
        except QuotaExceededException as e:
            return Response(
                {
                    'error': 'Quota exceeded',
                    'detail': str(e),
                    'type': 'quota'
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS
            )
        
        except RateLimitExceededException as e:
            return Response(
                {
                    'error': 'Rate limit exceeded',
                    'detail': str(e),
                    'type': 'rate_limit'
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS
            )
    
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """
        Get job statistics for the tenant.
        
        Query parameters:
        - since_hours: Number of hours to look back (default: 24)
        """
        since_hours = int(request.query_params.get('since_hours', 24))
        stats = JobService.get_job_stats(
            tenant=request.tenant,
            since_hours=since_hours
        )
        
        serializer = JobStatsSerializer(stats)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def history(self, request, pk=None):
        """
        Get history for a specific job.
        """
        job = self.get_object()
        history = JobHistory.objects.filter(job_id=job.id)
        serializer = JobHistorySerializer(history, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """
        Cancel a pending job.
        Only works for PENDING jobs.
        """
        job = self.get_object()
        
        if job.status != 'pending':
            return Response(
                {'error': 'Can only cancel pending jobs'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        job.status = 'failed'
        job.error_message = 'Cancelled by user'
        job.save()
        
        return Response(
            JobSerializer(job).data,
            status=status.HTTP_200_OK
        )


class DLQViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for Dead Letter Queue management.
    """
    permission_classes = [HasTenantAccess]
    serializer_class = DLQSerializer
    filterset_fields = ['job_type', 'retried']
    ordering_fields = ['created_at']
    ordering = ['-created_at']
    
    def get_queryset(self):
        """Filter DLQ by authenticated tenant."""
        if not hasattr(self.request, 'tenant'):
            return DeadLetterQueue.objects.none()
        
        return DeadLetterQueue.objects.filter(
            tenant=self.request.tenant
        ).select_related('tenant')
    
    @action(detail=True, methods=['post'])
    def retry(self, request, pk=None):
        """
        Retry a job from the Dead Letter Queue.
        """
        dlq_item = self.get_object()
        
        if dlq_item.retried:
            return Response(
                {'error': 'This job has already been retried'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            new_job = JobService.retry_dlq_job(dlq_item)
            return Response(
                {
                    'message': 'Job retried successfully',
                    'new_job_id': str(new_job.id),
                    'job': JobSerializer(new_job).data
                },
                status=status.HTTP_200_OK
            )
        except Exception as e:
            logger.error(f"Error retrying DLQ job: {e}", exc_info=True)
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class MetricsView(views.APIView):
    """
    System-wide metrics endpoint.
    """
    permission_classes = [AllowAny]  # Can be restricted in production
    
    def get(self, request):
        """
        Get comprehensive system metrics.
        
        Returns metrics for:
        - Jobs (total, by status, success rate, avg duration)
        - Tenants (total, active)
        - Workers (active, running jobs)
        - System health (stale jobs, DLQ count)
        """
        metrics = JobService.get_system_metrics()
        serializer = MetricsSerializer(metrics)
        return Response(serializer.data)


class HealthView(views.APIView):
    """
    Health check endpoint for monitoring.
    """
    permission_classes = [AllowAny]
    
    def get(self, request):
        """
        Health check.
        
        Returns:
        - status: "healthy" or "unhealthy"
        - database: Database connection status
        - redis: Redis connection status (for channels)
        """
        from django.db import connection
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync
        
        health = {
            'status': 'healthy',
            'timestamp': timezone.now().isoformat(),
            'checks': {}
        }
        
        # Check database
        try:
            with connection.cursor() as cursor:
                cursor.execute('SELECT 1')
            health['checks']['database'] = 'ok'
        except Exception as e:
            health['checks']['database'] = f'error: {str(e)}'
            health['status'] = 'unhealthy'
        
        # Check Redis/Channels
        try:
            channel_layer = get_channel_layer()
            if channel_layer:
                # Try to send a test message
                async_to_sync(channel_layer.send)('test_channel', {
                    'type': 'test.message',
                    'data': 'health_check'
                })
                health['checks']['redis'] = 'ok'
            else:
                health['checks']['redis'] = 'not configured'
        except Exception as e:
            health['checks']['redis'] = f'error: {str(e)}'
            # Don't mark as unhealthy for Redis issues
        
        # Check job queue depth
        try:
            pending_count = Job.objects.filter(status='pending').count()
            health['checks']['queue_depth'] = pending_count
            
            if pending_count > 10000:
                health['checks']['queue_alert'] = 'Queue depth high'
        except Exception as e:
            health['checks']['queue_depth'] = f'error: {str(e)}'
        
        status_code = status.HTTP_200_OK if health['status'] == 'healthy' else status.HTTP_503_SERVICE_UNAVAILABLE
        
        return Response(health, status=status_code)
