"""
Tenant models for multi-tenancy and rate limiting.
"""

import uuid
import secrets
from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User
from datetime import timedelta


class Tenant(models.Model):
    """
    Multi-tenant support with quota management and rate limiting.
    Each tenant is linked to a Django user for session-based authentication.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        User, 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True,
        related_name='tenant',
        help_text="Linked Django user for authentication"
    )
    name = models.CharField(max_length=255, help_text="Tenant/organization name")
    api_key = models.CharField(
        max_length=64, 
        unique=True, 
        db_index=True,
        help_text="API key for external API access (optional)"
    )
    
    # Quotas
    max_concurrent_jobs = models.IntegerField(
        default=5,
        help_text="Maximum number of jobs that can run simultaneously"
    )
    max_jobs_per_minute = models.IntegerField(
        default=10,
        help_text="Rate limit: max jobs per minute"
    )
    max_jobs_per_hour = models.IntegerField(
        default=100,
        help_text="Rate limit: max jobs per hour"
    )
    
    # Status
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Additional info
    email = models.EmailField(blank=True, null=True)
    metadata = models.JSONField(default=dict, blank=True)
    
    class Meta:
        db_table = 'tenants'
        ordering = ['-created_at']
        verbose_name = 'Tenant'
        verbose_name_plural = 'Tenants'
    
    def __str__(self):
        return f"{self.name} ({self.id})"
    
    @classmethod
    def generate_api_key(cls):
        """Generate a secure random API key."""
        return f"tk_{secrets.token_urlsafe(40)}"
    
    def save(self, *args, **kwargs):
        """Auto-generate API key if not provided."""
        if not self.api_key:
            self.api_key = self.generate_api_key()
        super().save(*args, **kwargs)
    
    def check_concurrent_quota(self):
        """
        Check if tenant is within concurrent job limit.
        Returns True if within limit, False if exceeded.
        """
        from jobs.models import Job, JobStatus
        
        active_count = Job.objects.filter(
            tenant=self,
            status=JobStatus.RUNNING
        ).count()
        
        return active_count < self.max_concurrent_jobs
    
    def check_rate_limit(self, window='minute'):
        """
        Check rate limit for given time window.
        
        Args:
            window: Either 'minute' or 'hour'
        
        Returns:
            tuple: (is_allowed: bool, current_count: int, limit: int)
        """
        from jobs.models import Job
        
        if window == 'minute':
            since = timezone.now() - timedelta(minutes=1)
            limit = self.max_jobs_per_minute
        elif window == 'hour':
            since = timezone.now() - timedelta(hours=1)
            limit = self.max_jobs_per_hour
        else:
            raise ValueError(f"Invalid window: {window}")
        
        count = Job.objects.filter(
            tenant=self,
            created_at__gte=since
        ).count()
        
        is_allowed = count < limit
        return is_allowed, count, limit
    
    def get_stats(self):
        """Get statistics for this tenant."""
        from jobs.models import Job, JobStatus
        from django.db.models import Count, Q
        
        stats = Job.objects.filter(tenant=self).aggregate(
            total=Count('id'),
            pending=Count('id', filter=Q(status=JobStatus.PENDING)),
            running=Count('id', filter=Q(status=JobStatus.RUNNING)),
            completed=Count('id', filter=Q(status=JobStatus.COMPLETED)),
            failed=Count('id', filter=Q(status=JobStatus.FAILED)),
            dead_letter=Count('id', filter=Q(status=JobStatus.DEAD_LETTER)),
        )
        
        return stats


class RateLimitTracker(models.Model):
    """
    Track rate limit counters for more accurate rate limiting.
    Alternative to counting jobs in the database.
    """
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    window_start = models.DateTimeField(db_index=True)
    window_type = models.CharField(
        max_length=10, 
        choices=[('minute', 'Minute'), ('hour', 'Hour')]
    )
    request_count = models.IntegerField(default=0)
    
    class Meta:
        db_table = 'rate_limit_tracker'
        unique_together = [['tenant', 'window_start', 'window_type']]
        indexes = [
            models.Index(fields=['tenant', 'window_start', 'window_type']),
        ]
    
    def __str__(self):
        return f"{self.tenant.name} - {self.window_type} - {self.request_count}"
