"""
Job models with atomic lease mechanism and race condition fixes.
"""

import uuid
import logging
from django.db import models, transaction
from django.db.models import F
from django.utils import timezone
from datetime import timedelta

logger = logging.getLogger(__name__)


class JobStatus(models.TextChoices):
    """Job status choices."""
    PENDING = 'pending', 'Pending'
    RUNNING = 'running', 'Running'
    COMPLETED = 'completed', 'Completed'
    FAILED = 'failed', 'Failed'
    DEAD_LETTER = 'dead_letter', 'Dead Letter'


class Job(models.Model):
    """
    Core job model with optimized indexing for queue operations.
    Includes atomic lease mechanism and race condition protection.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        'tenants.Tenant', 
        on_delete=models.CASCADE, 
        db_index=True,
        related_name='jobs'
    )
    
    # Job details
    job_type = models.CharField(
        max_length=100, 
        db_index=True,
        help_text="Type of job to process (e.g., 'send_email', 'process_data')"
    )
    payload = models.JSONField(
        help_text="Job data/parameters as JSON"
    )
    result = models.JSONField(
        null=True, 
        blank=True,
        help_text="Job result data after completion"
    )
    
    # Status tracking
    status = models.CharField(
        max_length=20,
        choices=JobStatus.choices,
        default=JobStatus.PENDING,
        db_index=True  # Critical for queue queries
    )
    
    # Version field for optimistic locking
    version = models.IntegerField(
        default=0,
        help_text="Version number for optimistic locking"
    )
    
    # Retry logic
    retry_count = models.IntegerField(default=0)
    max_retries = models.IntegerField(default=3)
    
    # Lease mechanism (prevents duplicate processing)
    lease_until = models.DateTimeField(
        null=True, 
        blank=True, 
        db_index=True,
        help_text="Lease expiry time - job can be re-assigned after this"
    )
    worker_id = models.CharField(
        max_length=100, 
        null=True, 
        blank=True,
        help_text="ID of worker currently processing this job"
    )
    
    # Timing
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    # Idempotency
    idempotency_key = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        unique=True,
        db_index=True,
        help_text="Unique key to prevent duplicate job submissions"
    )
    
    # Error handling
    error_message = models.TextField(null=True, blank=True)
    error_trace = models.TextField(null=True, blank=True)
    
    # Metadata
    priority = models.IntegerField(
        default=0, 
        db_index=True,
        help_text="Higher priority jobs processed first"
    )
    metadata = models.JSONField(
        default=dict, 
        blank=True,
        help_text="Additional metadata"
    )
    
    # Heartbeat tracking (for long-running jobs)
    last_heartbeat = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last heartbeat from worker"
    )
    
    class Meta:
        db_table = 'jobs'
        indexes = [
            # Composite index for efficient queue polling
            models.Index(fields=['status', 'priority', 'created_at'], name='job_queue_idx'),
            # For lease expiry checks
            models.Index(fields=['status', 'lease_until'], name='job_lease_idx'),
            # For tenant queries
            models.Index(fields=['tenant', 'status', 'created_at'], name='job_tenant_idx'),
            # For job type queries
            models.Index(fields=['job_type', 'status'], name='job_type_status_idx'),
        ]
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Job {self.id} ({self.job_type}) - {self.status}"
    
    @classmethod
    def lease_next_job(cls, worker_id, lease_duration=60):
        """
        Atomically lease the next available job.
        Uses SELECT FOR UPDATE SKIP LOCKED for concurrency safety.
        
        This prevents race conditions by:
        1. Locking the selected row
        2. SKIP LOCKED ensures other workers skip locked rows
        3. Atomic update ensures only one worker gets the job
        
        Args:
            worker_id: Unique identifier for the worker
            lease_duration: Lease duration in seconds (default 60)
        
        Returns:
            Job instance if available, None otherwise
        """
        from django.db import connection
        
        with transaction.atomic():
            # Use raw SQL for PostgreSQL-specific SKIP LOCKED
            with connection.cursor() as cursor:
                cursor.execute("""
                    UPDATE jobs
                    SET 
                        status = %s,
                        started_at = COALESCE(started_at, NOW()),
                        lease_until = NOW() + INTERVAL '%s seconds',
                        worker_id = %s,
                        last_heartbeat = NOW(),
                        version = version + 1
                    WHERE id = (
                        SELECT id FROM jobs
                        WHERE (
                            status = %s 
                            OR (status = %s AND lease_until < NOW())
                        )
                        ORDER BY priority DESC, created_at ASC
                        FOR UPDATE SKIP LOCKED
                        LIMIT 1
                    )
                    RETURNING id;
                """, [
                    JobStatus.RUNNING,
                    lease_duration,
                    worker_id,
                    JobStatus.PENDING,
                    JobStatus.RUNNING
                ])
                
                result = cursor.fetchone()
                if result:
                    job = cls.objects.get(id=result[0])
                    logger.info(
                        f"Job leased: {job.id} by worker {worker_id}",
                        extra={
                            'job_id': str(job.id),
                            'worker_id': worker_id,
                            'job_type': job.job_type,
                            'tenant_id': str(job.tenant_id)
                        }
                    )
                    return job
        
        return None
    
    def ack(self, result=None):
        """
        Mark job as completed successfully.
        Uses optimistic locking to prevent race conditions.
        
        Args:
            result: Optional result data to store
        
        Returns:
            bool: True if ack successful, False if job was already processed
        """
        # Atomic update with version check (optimistic locking)
        updated = Job.objects.filter(
            id=self.id,
            version=self.version  # Ensures we're updating the right version
        ).update(
            status=JobStatus.COMPLETED,
            completed_at=timezone.now(),
            result=result,
            version=F('version') + 1
        )
        
        if not updated:
            logger.warning(
                f"Job {self.id} already processed or modified",
                extra={'job_id': str(self.id), 'version': self.version}
            )
            return False
        
        # Refresh from DB
        self.refresh_from_db()
        
        logger.info(
            f"Job completed: {self.id}",
            extra={
                'job_id': str(self.id),
                'job_type': self.job_type,
                'tenant_id': str(self.tenant_id),
                'duration_seconds': (
                    (self.completed_at - self.started_at).total_seconds()
                    if self.started_at else None
                )
            }
        )
        
        # Create history record
        JobHistory.create_from_job(self, 'completed')
        
        # Notify via WebSocket
        self._notify_status_change()
        
        return True
    
    def nack(self, error_message=None, error_trace=None):
        """
        Mark job as failed and handle retry/DLQ logic.
        
        Args:
            error_message: Error message string
            error_trace: Full error traceback
        
        Returns:
            bool: True if moved to DLQ, False if retrying
        """
        self.retry_count += 1
        self.error_message = error_message
        self.error_trace = error_trace
        
        if self.retry_count >= self.max_retries:
            # Move to Dead Letter Queue
            self.status = JobStatus.DEAD_LETTER
            DeadLetterQueue.create_from_job(self)
            logger.error(
                f"Job {self.id} moved to DLQ after {self.retry_count} retries",
                extra={
                    'job_id': str(self.id),
                    'job_type': self.job_type,
                    'retry_count': self.retry_count,
                    'error': error_message
                }
            )
            moved_to_dlq = True
        else:
            # Reset for retry
            self.status = JobStatus.PENDING
            self.lease_until = None
            self.worker_id = None
            logger.warning(
                f"Job {self.id} failed, retry {self.retry_count}/{self.max_retries}",
                extra={
                    'job_id': str(self.id),
                    'retry_count': self.retry_count,
                    'error': error_message
                }
            )
            moved_to_dlq = False
        
        self.save()
        
        # Create history record
        JobHistory.create_from_job(self, 'failed')
        
        # Notify via WebSocket
        self._notify_status_change()
        
        return moved_to_dlq
    
    def extend_lease(self, seconds=30):
        """
        Extend lease for long-running jobs.
        Workers should call this periodically (heartbeat).
        
        Args:
            seconds: Number of seconds to extend the lease
        """
        self.lease_until = timezone.now() + timedelta(seconds=seconds)
        self.last_heartbeat = timezone.now()
        self.save(update_fields=['lease_until', 'last_heartbeat'])
        
        logger.debug(
            f"Lease extended for job {self.id} by {seconds}s",
            extra={'job_id': str(self.id), 'worker_id': self.worker_id}
        )
    
    def release_lease(self):
        """
        Release the lease on this job (for graceful shutdown).
        """
        self.status = JobStatus.PENDING
        self.lease_until = None
        self.worker_id = None
        self.save(update_fields=['status', 'lease_until', 'worker_id'])
        
        logger.info(
            f"Lease released for job {self.id}",
            extra={'job_id': str(self.id)}
        )
    
    def _notify_status_change(self):
        """Send WebSocket notification for job status change."""
        try:
            from channels.layers import get_channel_layer
            from asgiref.sync import async_to_sync
            
            channel_layer = get_channel_layer()
            if channel_layer:
                async_to_sync(channel_layer.group_send)(
                    f"tenant_{self.tenant_id}",
                    {
                        "type": "job_update",
                        "job_id": str(self.id),
                        "status": self.status,
                        "job_type": self.job_type,
                    }
                )
        except Exception as e:
            logger.error(f"Failed to send WebSocket notification: {e}")


class DeadLetterQueue(models.Model):
    """
    Failed jobs that exceeded max retries.
    Can be manually retried or investigated.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    original_job_id = models.UUIDField(db_index=True)
    tenant = models.ForeignKey('tenants.Tenant', on_delete=models.CASCADE)
    
    job_type = models.CharField(max_length=100)
    payload = models.JSONField()
    
    retry_count = models.IntegerField()
    final_error_message = models.TextField()
    final_error_trace = models.TextField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    
    # For manual retry
    retried = models.BooleanField(default=False)
    retried_at = models.DateTimeField(null=True, blank=True)
    new_job_id = models.UUIDField(null=True, blank=True)
    
    class Meta:
        db_table = 'dead_letter_queue'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"DLQ {self.id} (Job: {self.original_job_id})"
    
    @classmethod
    def create_from_job(cls, job):
        """Create a DLQ entry from a failed job."""
        return cls.objects.create(
            original_job_id=job.id,
            tenant=job.tenant,
            job_type=job.job_type,
            payload=job.payload,
            retry_count=job.retry_count,
            final_error_message=job.error_message or '',
            final_error_trace=job.error_trace
        )


class JobHistory(models.Model):
    """
    Audit trail for all job state changes.
    Useful for debugging and monitoring.
    """
    id = models.BigAutoField(primary_key=True)
    job_id = models.UUIDField(db_index=True)
    
    event_type = models.CharField(
        max_length=50,
        help_text="Event type: created, started, completed, failed, etc."
    )
    status = models.CharField(max_length=20)
    
    worker_id = models.CharField(max_length=100, null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)
    
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    metadata = models.JSONField(default=dict)
    
    class Meta:
        db_table = 'job_history'
        indexes = [
            models.Index(fields=['job_id', 'timestamp'], name='job_history_idx'),
        ]
        ordering = ['-timestamp']
    
    def __str__(self):
        return f"{self.event_type} - Job {self.job_id}"
    
    @classmethod
    def create_from_job(cls, job, event_type):
        """Create a history entry from a job."""
        return cls.objects.create(
            job_id=job.id,
            event_type=event_type,
            status=job.status,
            worker_id=job.worker_id,
            error_message=job.error_message,
            metadata={
                'retry_count': job.retry_count,
                'job_type': job.job_type,
                'tenant_id': str(job.tenant_id)
            }
        )
