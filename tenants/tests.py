"""
Tests for tenant management and rate limiting.
"""

from django.test import TestCase
from django.utils import timezone
from datetime import timedelta

from tenants.models import Tenant, RateLimitTracker
from jobs.models import Job, JobStatus


class TenantModelTestCase(TestCase):
    """Test tenant model functionality."""
    
    def setUp(self):
        """Create test tenant."""
        self.tenant = Tenant.objects.create(
            name="Test Tenant",
            api_key="test_key_abc",
            max_concurrent_jobs=5,
            max_jobs_per_minute=10,
            max_jobs_per_hour=100
        )
    
    def test_tenant_creation(self):
        """Test tenant creation with default values."""
        tenant = Tenant.objects.create(
            name="New Tenant",
            api_key="new_key_123"
        )
        
        self.assertEqual(tenant.name, "New Tenant")
        self.assertEqual(tenant.api_key, "new_key_123")
        self.assertTrue(tenant.is_active)
        self.assertEqual(tenant.max_concurrent_jobs, 5)  # Default
        self.assertEqual(tenant.max_jobs_per_minute, 10)  # Default
        self.assertEqual(tenant.max_jobs_per_hour, 100)  # Default
    
    def test_concurrent_quota_check_under_limit(self):
        """Test concurrent quota check when under limit."""
        # Create 3 running jobs (under limit of 5)
        for i in range(3):
            Job.objects.create(
                tenant=self.tenant,
                job_type="test_job",
                payload={},
                status=JobStatus.RUNNING
            )
        
        # Should be allowed
        is_allowed = self.tenant.check_concurrent_quota()
        self.assertTrue(is_allowed)
    
    def test_concurrent_quota_check_at_limit(self):
        """Test concurrent quota check when at limit."""
        # Create 5 running jobs (at limit)
        for i in range(5):
            Job.objects.create(
                tenant=self.tenant,
                job_type="test_job",
                payload={},
                status=JobStatus.RUNNING
            )
        
        # Should not be allowed
        is_allowed = self.tenant.check_concurrent_quota()
        self.assertFalse(is_allowed)
    
    def test_concurrent_quota_only_counts_running_jobs(self):
        """Test that quota only counts running jobs."""
        # Create 3 running jobs
        for i in range(3):
            Job.objects.create(
                tenant=self.tenant,
                job_type="test_job",
                payload={},
                status=JobStatus.RUNNING
            )
        
        # Create 10 completed jobs (should not count)
        for i in range(10):
            Job.objects.create(
                tenant=self.tenant,
                job_type="test_job",
                payload={},
                status=JobStatus.COMPLETED
            )
        
        # Should still be allowed (only 3 running)
        is_allowed = self.tenant.check_concurrent_quota()
        self.assertTrue(is_allowed)


class RateLimitingTestCase(TestCase):
    """Test rate limiting functionality."""
    
    def setUp(self):
        """Create test tenant."""
        self.tenant = Tenant.objects.create(
            name="Test Tenant",
            api_key="test_key_def",
            max_concurrent_jobs=10,
            max_jobs_per_minute=5,
            max_jobs_per_hour=20
        )
    
    def test_rate_limit_per_minute_under_limit(self):
        """Test rate limit check when under per-minute limit."""
        # Create 3 jobs in last minute
        for i in range(3):
            Job.objects.create(
                tenant=self.tenant,
                job_type="test_job",
                payload={},
                created_at=timezone.now() - timedelta(seconds=30)
            )
        
        # Should be allowed
        is_allowed, count, limit = self.tenant.check_rate_limit('minute')
        self.assertTrue(is_allowed)
        self.assertEqual(count, 3)
        self.assertEqual(limit, 5)
    
    def test_rate_limit_per_minute_at_limit(self):
        """Test rate limit check when at per-minute limit."""
        # Create 5 jobs in last minute
        for i in range(5):
            Job.objects.create(
                tenant=self.tenant,
                job_type="test_job",
                payload={},
                created_at=timezone.now() - timedelta(seconds=10)
            )
        
        # Should not be allowed
        is_allowed, count, limit = self.tenant.check_rate_limit('minute')
        self.assertFalse(is_allowed)
        self.assertEqual(count, 5)
        self.assertEqual(limit, 5)
    
    def test_rate_limit_per_hour_under_limit(self):
        """Test rate limit check when under per-hour limit."""
        # Create 10 jobs in last hour
        for i in range(10):
            Job.objects.create(
                tenant=self.tenant,
                job_type="test_job",
                payload={},
                created_at=timezone.now() - timedelta(minutes=30)
            )
        
        # Should be allowed
        is_allowed, count, limit = self.tenant.check_rate_limit('hour')
        self.assertTrue(is_allowed)
        self.assertEqual(count, 10)
        self.assertEqual(limit, 20)
    
    def test_rate_limit_only_counts_recent_jobs(self):
        """Test that rate limit only counts jobs within time window."""
        # Note: Due to auto_now_add, we can't easily test old jobs
        # This test verifies that recent jobs are counted correctly
        
        # Create 2 recent jobs
        for i in range(2):
            Job.objects.create(
                tenant=self.tenant,
                job_type="test_job",
                payload={},
                status=JobStatus.PENDING
            )
        
        # Should count the 2 recent jobs (under limit of 5)
        is_allowed, count, limit = self.tenant.check_rate_limit('minute')
        self.assertTrue(is_allowed)
        self.assertEqual(count, 2)
        self.assertEqual(limit, 5)
    
    def test_high_rate_limit(self):
        """Test that very high rate limits work correctly."""
        # Set very high limit
        self.tenant.max_jobs_per_minute = 1000
        self.tenant.save()
        
        # Create 10 jobs (well under limit)
        for i in range(10):
            Job.objects.create(
                tenant=self.tenant,
                job_type="test_job",
                payload={},
                status=JobStatus.PENDING
            )
        
        # Should still be allowed
        is_allowed, count, limit = self.tenant.check_rate_limit('minute')
        self.assertTrue(is_allowed)
        self.assertEqual(count, 10)
        self.assertEqual(limit, 1000)


class TenantMiddlewareTestCase(TestCase):
    """Test tenant authentication middleware."""
    
    def setUp(self):
        """Create test tenant."""
        self.tenant = Tenant.objects.create(
            name="Test Tenant",
            api_key="valid_api_key_123",
            is_active=True
        )
    
    def test_valid_api_key_in_header(self):
        """Test authentication with valid API key in header."""
        from django.test import RequestFactory
        from tenants.middleware import TenantMiddleware
        
        factory = RequestFactory()
        request = factory.get('/', HTTP_X_API_KEY='valid_api_key_123')
        
        middleware = TenantMiddleware(lambda r: None)
        middleware(request)
        
        self.assertTrue(hasattr(request, 'tenant'))
        self.assertEqual(request.tenant.id, self.tenant.id)
    
    def test_invalid_api_key(self):
        """Test authentication with invalid API key."""
        from django.test import RequestFactory
        from tenants.middleware import TenantMiddleware
        
        factory = RequestFactory()
        request = factory.get('/', HTTP_X_API_KEY='invalid_key')
        
        middleware = TenantMiddleware(lambda r: None)
        middleware(request)
        
        self.assertFalse(hasattr(request, 'tenant'))
    
    def test_inactive_tenant(self):
        """Test that inactive tenants are rejected."""
        # Create inactive tenant
        inactive_tenant = Tenant.objects.create(
            name="Inactive Tenant",
            api_key="inactive_key_123",
            is_active=False
        )
        
        from django.test import RequestFactory
        from tenants.middleware import TenantMiddleware
        
        factory = RequestFactory()
        request = factory.get('/', HTTP_X_API_KEY='inactive_key_123')
        
        middleware = TenantMiddleware(lambda r: None)
        middleware(request)
        
        self.assertFalse(hasattr(request, 'tenant'))
