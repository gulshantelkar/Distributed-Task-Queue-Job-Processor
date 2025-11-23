"""
Admin interface for Job models.
"""

from django.contrib import admin
from django.utils.html import format_html
from .models import Job, DeadLetterQueue, JobHistory, JobStatus


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'job_type', 'status_badge', 'tenant', 
        'priority', 'retry_count', 'worker_id', 'created_at'
    ]
    list_filter = ['status', 'job_type', 'created_at', 'priority']
    search_fields = ['id', 'job_type', 'tenant__name', 'worker_id']
    readonly_fields = [
        'id', 'created_at', 'started_at', 'completed_at',
        'version', 'last_heartbeat'
    ]
    
    fieldsets = (
        ('Job Information', {
            'fields': ('id', 'tenant', 'job_type', 'status', 'priority')
        }),
        ('Data', {
            'fields': ('payload', 'result'),
            'classes': ('collapse',)
        }),
        ('Execution', {
            'fields': (
                'worker_id', 'lease_until', 'last_heartbeat',
                'retry_count', 'max_retries'
            )
        }),
        ('Error Information', {
            'fields': ('error_message', 'error_trace'),
            'classes': ('collapse',)
        }),
        ('Idempotency', {
            'fields': ('idempotency_key', 'version')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'started_at', 'completed_at')
        }),
        ('Metadata', {
            'fields': ('metadata',),
            'classes': ('collapse',)
        }),
    )
    
    actions = ['reset_to_pending', 'move_to_dlq']
    
    def status_badge(self, obj):
        """Display status with color coding."""
        colors = {
            JobStatus.PENDING: 'gray',
            JobStatus.RUNNING: 'blue',
            JobStatus.COMPLETED: 'green',
            JobStatus.FAILED: 'red',
            JobStatus.DEAD_LETTER: 'darkred',
        }
        color = colors.get(obj.status, 'gray')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_badge.short_description = 'Status'
    
    def reset_to_pending(self, request, queryset):
        """Reset selected jobs to pending status."""
        updated = queryset.update(
            status=JobStatus.PENDING,
            lease_until=None,
            worker_id=None,
            error_message=None,
            error_trace=None
        )
        self.message_user(request, f'{updated} jobs reset to pending.')
    reset_to_pending.short_description = 'Reset to pending'
    
    def move_to_dlq(self, request, queryset):
        """Move selected jobs to dead letter queue."""
        for job in queryset:
            if job.status != JobStatus.DEAD_LETTER:
                DeadLetterQueue.create_from_job(job)
                job.status = JobStatus.DEAD_LETTER
                job.save()
        self.message_user(request, f'{queryset.count()} jobs moved to DLQ.')
    move_to_dlq.short_description = 'Move to DLQ'


@admin.register(DeadLetterQueue)
class DeadLetterQueueAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'original_job_id', 'job_type', 
        'tenant', 'retry_count', 'retried', 'created_at'
    ]
    list_filter = ['retried', 'created_at', 'job_type']
    search_fields = ['id', 'original_job_id', 'tenant__name', 'job_type']
    readonly_fields = [
        'id', 'original_job_id', 'tenant', 'job_type', 
        'payload', 'retry_count', 'final_error_message',
        'final_error_trace', 'created_at'
    ]
    
    fieldsets = (
        ('DLQ Information', {
            'fields': ('id', 'original_job_id', 'tenant', 'job_type')
        }),
        ('Job Data', {
            'fields': ('payload',),
            'classes': ('collapse',)
        }),
        ('Error Information', {
            'fields': ('retry_count', 'final_error_message', 'final_error_trace')
        }),
        ('Retry Status', {
            'fields': ('retried', 'retried_at', 'new_job_id')
        }),
        ('Timestamps', {
            'fields': ('created_at',)
        }),
    )
    
    actions = ['retry_jobs']
    
    def retry_jobs(self, request, queryset):
        """Retry jobs from DLQ."""
        from .services import JobService
        
        retried_count = 0
        for dlq_item in queryset.filter(retried=False):
            try:
                new_job = JobService.create_job(
                    tenant=dlq_item.tenant,
                    job_type=dlq_item.job_type,
                    payload=dlq_item.payload
                )
                dlq_item.retried = True
                dlq_item.retried_at = timezone.now()
                dlq_item.new_job_id = new_job.id
                dlq_item.save()
                retried_count += 1
            except Exception as e:
                self.message_user(request, f'Error retrying {dlq_item.id}: {e}', level='error')
        
        self.message_user(request, f'{retried_count} jobs retried from DLQ.')
    retry_jobs.short_description = 'Retry jobs'


@admin.register(JobHistory)
class JobHistoryAdmin(admin.ModelAdmin):
    list_display = ['id', 'job_id', 'event_type', 'status', 'worker_id', 'timestamp']
    list_filter = ['event_type', 'status', 'timestamp']
    search_fields = ['job_id', 'worker_id']
    readonly_fields = ['id', 'job_id', 'event_type', 'status', 'worker_id', 'timestamp', 'metadata']
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False
