"""
Serializers for Job API.
"""

from rest_framework import serializers
from .models import Job, DeadLetterQueue, JobHistory


class JobCreateSerializer(serializers.Serializer):
    """Serializer for creating a new job."""
    job_type = serializers.CharField(
        max_length=100,
        help_text="Type of job to process"
    )
    payload = serializers.JSONField(
        help_text="Job data/parameters"
    )
    idempotency_key = serializers.CharField(
        max_length=255,
        required=False,
        allow_null=True,
        help_text="Optional key to prevent duplicate jobs"
    )
    priority = serializers.IntegerField(
        default=0,
        required=False,
        help_text="Job priority (higher = processed first)"
    )
    max_retries = serializers.IntegerField(
        default=3,
        required=False,
        help_text="Maximum number of retries"
    )
    metadata = serializers.JSONField(
        default=dict,
        required=False,
        help_text="Additional metadata"
    )
    
    def validate_job_type(self, value):
        """Validate job_type."""
        if not value or not value.strip():
            raise serializers.ValidationError("job_type cannot be empty")
        return value.strip()
    
    def validate_payload(self, value):
        """Validate payload is a valid dict."""
        if not isinstance(value, dict):
            raise serializers.ValidationError("payload must be a JSON object")
        return value
    
    def validate_priority(self, value):
        """Validate priority is reasonable."""
        if value < -100 or value > 100:
            raise serializers.ValidationError("priority must be between -100 and 100")
        return value


class JobSerializer(serializers.ModelSerializer):
    """Serializer for Job model."""
    tenant_name = serializers.CharField(source='tenant.name', read_only=True)
    duration_seconds = serializers.SerializerMethodField()
    
    class Meta:
        model = Job
        fields = [
            'id', 'tenant', 'tenant_name', 'job_type', 'payload', 'result',
            'status', 'priority', 'retry_count', 'max_retries',
            'worker_id', 'created_at', 'started_at', 'completed_at',
            'error_message', 'metadata', 'duration_seconds'
        ]
        read_only_fields = fields
    
    def get_duration_seconds(self, obj):
        """Calculate job duration in seconds."""
        if obj.started_at and obj.completed_at:
            return (obj.completed_at - obj.started_at).total_seconds()
        return None


class JobDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer for Job model (includes traces)."""
    tenant_name = serializers.CharField(source='tenant.name', read_only=True)
    duration_seconds = serializers.SerializerMethodField()
    
    class Meta:
        model = Job
        fields = [
            'id', 'tenant', 'tenant_name', 'job_type', 'payload', 'result',
            'status', 'version', 'priority', 'retry_count', 'max_retries',
            'worker_id', 'lease_until', 'last_heartbeat',
            'created_at', 'started_at', 'completed_at',
            'error_message', 'error_trace', 'metadata',
            'idempotency_key', 'duration_seconds'
        ]
        read_only_fields = fields
    
    def get_duration_seconds(self, obj):
        """Calculate job duration in seconds."""
        if obj.started_at and obj.completed_at:
            return (obj.completed_at - obj.started_at).total_seconds()
        return None


class DLQSerializer(serializers.ModelSerializer):
    """Serializer for Dead Letter Queue."""
    tenant_name = serializers.CharField(source='tenant.name', read_only=True)
    
    class Meta:
        model = DeadLetterQueue
        fields = [
            'id', 'original_job_id', 'tenant', 'tenant_name',
            'job_type', 'payload', 'retry_count',
            'final_error_message', 'final_error_trace',
            'created_at', 'retried', 'retried_at', 'new_job_id'
        ]
        read_only_fields = fields


class JobHistorySerializer(serializers.ModelSerializer):
    """Serializer for Job History."""
    class Meta:
        model = JobHistory
        fields = [
            'id', 'job_id', 'event_type', 'status',
            'worker_id', 'error_message', 'timestamp', 'metadata'
        ]
        read_only_fields = fields


class JobStatsSerializer(serializers.Serializer):
    """Serializer for job statistics."""
    total = serializers.IntegerField()
    pending = serializers.IntegerField()
    running = serializers.IntegerField()
    completed = serializers.IntegerField()
    failed = serializers.IntegerField()
    dead_letter = serializers.IntegerField()
    success_rate = serializers.FloatField(required=False)
    avg_duration_seconds = serializers.FloatField(required=False)


class MetricsSerializer(serializers.Serializer):
    """Serializer for system metrics."""
    jobs = JobStatsSerializer()
    tenants = serializers.DictField()
    workers = serializers.DictField()
    system = serializers.DictField()

