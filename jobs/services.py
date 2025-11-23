"""
Business logic for job management.
"""

import logging
from django.db import transaction
from django.utils import timezone
from django.db.models import Count, Q, Avg, F
from datetime import timedelta

from .models import Job, JobStatus, DeadLetterQueue, JobHistory
from .exceptions import (
    QuotaExceededException,
    RateLimitExceededException,
    DuplicateJobException
)

logger = logging.getLogger(__name__)


class JobService:
    """
    Service class for job management operations.
    Handles creation, status updates, and business logic.
    """
    
    @staticmethod
    @transaction.atomic
    def create_job(tenant, job_type, payload, idempotency_key=None, **kwargs):
        """
        Create a new job with idempotency support and rate limiting.
        
        Args:
            tenant: Tenant instance
            job_type: Type of job
            payload: Job data
            idempotency_key: Optional idempotency key
            **kwargs: Additional job parameters (priority, max_retries, etc.)
        
        Returns:
            tuple: (job: Job, created: bool)
            created is True if new job, False if existing job returned
        
        Raises:
            QuotaExceededException: If concurrent job limit exceeded
            RateLimitExceededException: If rate limit exceeded
        """
        # Check idempotency first (before rate limiting)
        if idempotency_key:
            existing_job = Job.objects.filter(
                idempotency_key=idempotency_key
            ).first()
            
            if existing_job:
                logger.info(
                    f"Duplicate job submission detected: {idempotency_key}",
                    extra={
                        'idempotency_key': idempotency_key,
                        'job_id': str(existing_job.id),
                        'tenant_id': str(tenant.id)
                    }
                )
                return existing_job, False
        
        # Check concurrent quota
        if not tenant.check_concurrent_quota():
            raise QuotaExceededException(
                f"Concurrent job limit ({tenant.max_concurrent_jobs}) reached"
            )
        
        # Check rate limits
        is_allowed_minute, count_minute, limit_minute = tenant.check_rate_limit('minute')
        if not is_allowed_minute:
            raise RateLimitExceededException(
                f"Rate limit exceeded: {count_minute}/{limit_minute} jobs per minute"
            )
        
        is_allowed_hour, count_hour, limit_hour = tenant.check_rate_limit('hour')
        if not is_allowed_hour:
            raise RateLimitExceededException(
                f"Rate limit exceeded: {count_hour}/{limit_hour} jobs per hour"
            )
        
        # Create job
        job = Job.objects.create(
            tenant=tenant,
            job_type=job_type,
            payload=payload,
            status=JobStatus.PENDING,
            idempotency_key=idempotency_key,
            **kwargs
        )
        
        logger.info(
            f"Job created: {job.id} (type: {job_type})",
            extra={
                'job_id': str(job.id),
                'job_type': job_type,
                'tenant_id': str(tenant.id),
                'priority': job.priority
            }
        )
        
        # Create history record
        JobHistory.create_from_job(job, 'created')
        
        # Notify workers via WebSocket (optional - for immediate pickup)
        job._notify_status_change()
        
        return job, True
    
    @staticmethod
    def get_job_stats(tenant=None, since_hours=24):
        """
        Get job statistics.
        
        Args:
            tenant: Optional tenant to filter by
            since_hours: Number of hours to look back
        
        Returns:
            dict: Job statistics
        """
        queryset = Job.objects.all()
        
        if tenant:
            queryset = queryset.filter(tenant=tenant)
        
        # Filter by time window
        since = timezone.now() - timedelta(hours=since_hours)
        queryset = queryset.filter(created_at__gte=since)
        
        # Aggregate stats
        stats = queryset.aggregate(
            total=Count('id'),
            pending=Count('id', filter=Q(status=JobStatus.PENDING)),
            running=Count('id', filter=Q(status=JobStatus.RUNNING)),
            completed=Count('id', filter=Q(status=JobStatus.COMPLETED)),
            failed=Count('id', filter=Q(status=JobStatus.FAILED)),
            dead_letter=Count('id', filter=Q(status=JobStatus.DEAD_LETTER)),
        )
        
        # Calculate success rate
        if stats['total'] > 0:
            stats['success_rate'] = (
                stats['completed'] / stats['total'] * 100
            )
        else:
            stats['success_rate'] = 0.0
        
        # Calculate average duration for completed jobs
        avg_duration = queryset.filter(
            status=JobStatus.COMPLETED,
            started_at__isnull=False,
            completed_at__isnull=False
        ).annotate(
            duration=F('completed_at') - F('started_at')
        ).aggregate(
            avg=Avg('duration')
        )
        
        if avg_duration['avg']:
            stats['avg_duration_seconds'] = avg_duration['avg'].total_seconds()
        else:
            stats['avg_duration_seconds'] = 0.0
        
        return stats
    
    @staticmethod
    def get_system_metrics():
        """
        Get comprehensive system metrics for monitoring.
        
        Returns:
            dict: System metrics
        """
        from tenants.models import Tenant
        from django.db.models import F
        
        # Job stats
        job_stats = JobService.get_job_stats()
        
        # Tenant stats
        tenant_stats = {
            'total': Tenant.objects.filter(is_active=True).count(),
            'active_with_jobs': Tenant.objects.filter(
                is_active=True,
                jobs__status__in=[JobStatus.RUNNING, JobStatus.PENDING]
            ).distinct().count()
        }
        
        # Worker stats (from active jobs)
        active_workers = Job.objects.filter(
            status=JobStatus.RUNNING,
            worker_id__isnull=False
        ).values('worker_id').distinct().count()
        
        worker_stats = {
            'active_workers': active_workers,
            'total_running_jobs': Job.objects.filter(
                status=JobStatus.RUNNING
            ).count()
        }
        
        # System health
        now = timezone.now()
        stale_threshold = now - timedelta(minutes=5)
        
        stale_jobs = Job.objects.filter(
            status=JobStatus.RUNNING,
            last_heartbeat__lt=stale_threshold
        ).count()
        
        system_stats = {
            'stale_jobs': stale_jobs,
            'dlq_count': DeadLetterQueue.objects.filter(retried=False).count(),
            'timestamp': now.isoformat()
        }
        
        return {
            'jobs': job_stats,
            'tenants': tenant_stats,
            'workers': worker_stats,
            'system': system_stats
        }
    
    @staticmethod
    def retry_dlq_job(dlq_item):
        """
        Retry a job from the Dead Letter Queue.
        
        Args:
            dlq_item: DeadLetterQueue instance
        
        Returns:
            Job: New job instance
        """
        if dlq_item.retried:
            raise ValueError("This DLQ item has already been retried")
        
        # Create new job with same parameters
        new_job = Job.objects.create(
            tenant=dlq_item.tenant,
            job_type=dlq_item.job_type,
            payload=dlq_item.payload,
            status=JobStatus.PENDING,
            retry_count=0,  # Reset retry count
            metadata={
                'dlq_retry': True,
                'original_job_id': str(dlq_item.original_job_id),
                'dlq_id': str(dlq_item.id)
            }
        )
        
        # Mark DLQ item as retried
        dlq_item.retried = True
        dlq_item.retried_at = timezone.now()
        dlq_item.new_job_id = new_job.id
        dlq_item.save()
        
        logger.info(
            f"DLQ job retried: {dlq_item.id} -> {new_job.id}",
            extra={
                'dlq_id': str(dlq_item.id),
                'new_job_id': str(new_job.id),
                'original_job_id': str(dlq_item.original_job_id)
            }
        )
        
        return new_job
    
    @staticmethod
    def cleanup_old_jobs(days=30):
        """
        Clean up old completed jobs and history.
        Should be run periodically (e.g., daily cron job).
        
        Args:
            days: Number of days to keep
        
        Returns:
            dict: Cleanup statistics
        """
        cutoff_date = timezone.now() - timedelta(days=days)
        
        # Delete old completed jobs
        deleted_jobs = Job.objects.filter(
            status=JobStatus.COMPLETED,
            completed_at__lt=cutoff_date
        ).delete()
        
        # Delete old history
        deleted_history = JobHistory.objects.filter(
            timestamp__lt=cutoff_date
        ).delete()
        
        logger.info(
            f"Cleanup completed: {deleted_jobs[0]} jobs, {deleted_history[0]} history records",
            extra={'days': days}
        )
        
        return {
            'jobs_deleted': deleted_jobs[0],
            'history_deleted': deleted_history[0],
            'cutoff_date': cutoff_date.isoformat()
        }

