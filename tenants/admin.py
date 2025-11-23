"""
Admin interface for Tenant models.
"""

from django.contrib import admin
from .models import Tenant, RateLimitTracker


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'id', 'is_active', 
        'max_concurrent_jobs', 'max_jobs_per_minute',
        'created_at'
    ]
    list_filter = ['is_active', 'created_at']
    search_fields = ['name', 'api_key', 'email']
    readonly_fields = ['id', 'api_key', 'created_at', 'updated_at']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'email', 'is_active')
        }),
        ('Authentication', {
            'fields': ('api_key',)
        }),
        ('Quotas', {
            'fields': (
                'max_concurrent_jobs',
                'max_jobs_per_minute',
                'max_jobs_per_hour'
            )
        }),
        ('Metadata', {
            'fields': ('metadata',),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('id', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(RateLimitTracker)
class RateLimitTrackerAdmin(admin.ModelAdmin):
    list_display = ['tenant', 'window_type', 'window_start', 'request_count']
    list_filter = ['window_type', 'window_start']
    search_fields = ['tenant__name']
    readonly_fields = ['tenant', 'window_start', 'window_type', 'request_count']
