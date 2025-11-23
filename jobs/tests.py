"""
Tests for job management functionality.
"""

import time
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from datetime import timedelta

from tenants.models import Tenant
from jobs.models import Job, JobStatus, DeadLetterQueue
from jobs.services import JobService
from jobs.exceptions import QuotaExceededException, RateLimitExceededException


class JobCreationTestCase(TestCase):
    """Test job creation and idempotency."""
    
    def setUp(self):
        """Create test tenant."""
        self.tenant = Tenant.objects.create(
            name="Test Tenant",
            api_key="test_key_123",
            max_concurrent_jobs=5,
            max_jobs_per_minute=100,
            max_jobs_per_hour=1000
        )
    
    def test_create_job_success(self):
        """Test successful job creation."""
        job, created = JobService.create_job(
            tenant=self.tenant,
            job_type="test_job",
            payload={"duration": 5},
            priority=0
        )
        
        self.assertTrue(created)
        self.assertEqual(job.status, JobStatus.PENDING)
        self.assertEqual(job.tenant, self.tenant)
        self.assertEqual(job.job_type, "test_job")
        self.assertEqual(job.payload, {"duration": 5})
        self.assertEqual(job.priority, 0)
    
    def test_idempotency_key_prevents_duplicates(self):
        """Test idempotency key prevents duplicate job submissions."""
        idempotency_key = "unique_key_123"
        
        # Create first job
        job1, created1 = JobService.create_job(
            tenant=self.tenant,
            job_type="test_job",
            payload={"duration": 5},
            idempotency_key=idempotency_key
        )
        
        self.assertTrue(created1)
        
        # Try to create duplicate
        job2, created2 = JobService.create_job(
            tenant=self.tenant,
            job_type="test_job",
            payload={"duration": 5},
            idempotency_key=idempotency_key
        )
        
        self.assertFalse(created2)
        self.assertEqual(job1.id, job2.id)
        
        # Only one job should exist
        self.assertEqual(Job.objects.count(), 1)
    
    def test_concurrent_quota_limit(self):
        """Test concurrent job quota enforcement."""
        # Set low quota
        self.tenant.max_concurrent_jobs = 2
        self.tenant.save()
        
        # Create 2 running jobs (at quota)
        job1 = Job.objects.create(
            tenant=self.tenant,
            job_type="test_job",
            payload={},
            status=JobStatus.RUNNING
        )
        job2 = Job.objects.create(
            tenant=self.tenant,
            job_type="test_job",
            payload={},
            status=JobStatus.RUNNING
        )
        
        # Third job should fail quota check
        with self.assertRaises(QuotaExceededException):
            JobService.create_job(
                tenant=self.tenant,
                job_type="test_job",
                payload={}
            )
    
    def test_rate_limit_per_minute(self):
        """Test per-minute rate limiting."""
        # Set very low rate limit
        self.tenant.max_jobs_per_minute = 2
        self.tenant.save()
        
        # Create 2 jobs (at limit)
        JobService.create_job(self.tenant, "test_job", {})
        JobService.create_job(self.tenant, "test_job", {})
        
        # Third job should fail rate limit
        with self.assertRaises(RateLimitExceededException):
            JobService.create_job(self.tenant, "test_job", {})


class JobProcessingTestCase(TransactionTestCase):
    """Test job processing, leasing, and retry logic."""
    
    def setUp(self):
        """Create test tenant and jobs."""
        self.tenant = Tenant.objects.create(
            name="Test Tenant",
            api_key="test_key_456",
            max_concurrent_jobs=10,
            max_jobs_per_minute=100,
            max_jobs_per_hour=1000
        )
    
    def test_lease_next_job_fifo_with_priority(self):
        """Test job leasing respects priority and FIFO order."""
        # Create jobs with different priorities
        job_low = Job.objects.create(
            tenant=self.tenant,
            job_type="test_job",
            payload={},
            priority=-10,
            status=JobStatus.PENDING
        )
        
        job_medium = Job.objects.create(
            tenant=self.tenant,
            job_type="test_job",
            payload={},
            priority=5,
            status=JobStatus.PENDING
        )
        
        job_high = Job.objects.create(
            tenant=self.tenant,
            job_type="test_job",
            payload={},
            priority=10,
            status=JobStatus.PENDING
        )
        
        # Lease next job - should get highest priority
        leased_job = Job.lease_next_job("worker-1", lease_duration=60)
        self.assertEqual(leased_job.id, job_high.id)
        self.assertEqual(leased_job.status, JobStatus.RUNNING)
        self.assertEqual(leased_job.worker_id, "worker-1")
        
        # Lease again - should get medium priority
        leased_job2 = Job.lease_next_job("worker-2", lease_duration=60)
        self.assertEqual(leased_job2.id, job_medium.id)
        
        # Lease again - should get low priority
        leased_job3 = Job.lease_next_job("worker-3", lease_duration=60)
        self.assertEqual(leased_job3.id, job_low.id)
    
    def test_lease_skip_locked(self):
        """Test that multiple workers don't lease the same job."""
        job = Job.objects.create(
            tenant=self.tenant,
            job_type="test_job",
            payload={},
            status=JobStatus.PENDING
        )
        
        # First worker leases job
        leased1 = Job.lease_next_job("worker-1", lease_duration=60)
        self.assertIsNotNone(leased1)
        self.assertEqual(leased1.id, job.id)
        
        # Second worker tries to lease - should get nothing
        leased2 = Job.lease_next_job("worker-2", lease_duration=60)
        self.assertIsNone(leased2)
    
    def test_job_ack_success(self):
        """Test successful job acknowledgment."""
        job = Job.objects.create(
            tenant=self.tenant,
            job_type="test_job",
            payload={},
            status=JobStatus.RUNNING
        )
        
        result = {"success": True, "message": "Done"}
        success = job.ack(result=result)
        
        self.assertTrue(success)
        
        # Refresh from DB
        job.refresh_from_db()
        self.assertEqual(job.status, JobStatus.COMPLETED)
        self.assertEqual(job.result, result)
        self.assertIsNotNone(job.completed_at)
    
    def test_job_retry_logic(self):
        """Test job retry logic with nack."""
        job = Job.objects.create(
            tenant=self.tenant,
            job_type="test_job",
            payload={},
            status=JobStatus.RUNNING,
            max_retries=3,
            retry_count=0
        )
        
        # First failure - should retry
        moved_to_dlq = job.nack(
            error_message="Test error",
            error_trace="Test trace"
        )
        
        self.assertFalse(moved_to_dlq)
        job.refresh_from_db()
        self.assertEqual(job.status, JobStatus.PENDING)
        self.assertEqual(job.retry_count, 1)
        
        # Second failure - should retry
        job.status = JobStatus.RUNNING
        job.save()
        moved_to_dlq = job.nack(
            error_message="Test error 2",
            error_trace="Test trace 2"
        )
        
        self.assertFalse(moved_to_dlq)
        job.refresh_from_db()
        self.assertEqual(job.retry_count, 2)
        
        # Third failure - should move to DLQ (retry_count=3 >= max_retries=3)
        job.status = JobStatus.RUNNING
        job.save()
        moved_to_dlq = job.nack(
            error_message="Test error 3",
            error_trace="Test trace 3"
        )
        
        self.assertTrue(moved_to_dlq)
        job.refresh_from_db()
        self.assertEqual(job.status, JobStatus.DEAD_LETTER)
        self.assertEqual(job.retry_count, 3)
        
        # Check DLQ
        dlq_items = DeadLetterQueue.objects.filter(original_job_id=job.id)
        self.assertEqual(dlq_items.count(), 1)
        dlq_item = dlq_items.first()
        self.assertEqual(dlq_item.retry_count, 3)
        self.assertIn("Test error 3", dlq_item.final_error_message)
    
    def test_expired_lease_can_be_reclaimed(self):
        """Test that jobs with expired leases can be picked up again."""
        # Create job with expired lease
        job = Job.objects.create(
            tenant=self.tenant,
            job_type="test_job",
            payload={},
            status=JobStatus.RUNNING,
            worker_id="worker-1",
            lease_until=timezone.now() - timedelta(seconds=10)  # Expired
        )
        
        # Another worker should be able to lease it
        leased_job = Job.lease_next_job("worker-2", lease_duration=60)
        
        self.assertIsNotNone(leased_job)
        self.assertEqual(leased_job.id, job.id)
        self.assertEqual(leased_job.worker_id, "worker-2")
    
    def test_optimistic_locking_prevents_double_ack(self):
        """Test that optimistic locking prevents race conditions."""
        job = Job.objects.create(
            tenant=self.tenant,
            job_type="test_job",
            payload={},
            status=JobStatus.RUNNING,
            version=1
        )
        
        # Get two references to same job (simulating two workers)
        job_worker1 = Job.objects.get(id=job.id)
        job_worker2 = Job.objects.get(id=job.id)
        
        # Both have same version at this point
        self.assertEqual(job_worker1.version, job_worker2.version)
        
        # First worker acks
        success1 = job_worker1.ack(result={"worker": "worker-1"})
        self.assertTrue(success1)
        
        # Second worker tries to ack with stale version
        success2 = job_worker2.ack(result={"worker": "worker-2"})
        self.assertFalse(success2)
        
        # Check final state
        job.refresh_from_db()
        self.assertEqual(job.status, JobStatus.COMPLETED)
        self.assertEqual(job.result["worker"], "worker-1")


class JobStatsTestCase(TestCase):
    """Test job statistics and metrics."""
    
    def setUp(self):
        """Create test tenant."""
        self.tenant = Tenant.objects.create(
            name="Test Tenant",
            api_key="test_key_789",
            max_concurrent_jobs=10,
            max_jobs_per_minute=100,
            max_jobs_per_hour=1000
        )
    
    def test_job_stats_aggregation(self):
        """Test job statistics aggregation."""
        # Create jobs in different states
        Job.objects.create(
            tenant=self.tenant,
            job_type="test_job",
            payload={},
            status=JobStatus.PENDING
        )
        Job.objects.create(
            tenant=self.tenant,
            job_type="test_job",
            payload={},
            status=JobStatus.PENDING
        )
        Job.objects.create(
            tenant=self.tenant,
            job_type="test_job",
            payload={},
            status=JobStatus.RUNNING
        )
        Job.objects.create(
            tenant=self.tenant,
            job_type="test_job",
            payload={},
            status=JobStatus.COMPLETED
        )
        Job.objects.create(
            tenant=self.tenant,
            job_type="test_job",
            payload={},
            status=JobStatus.COMPLETED
        )
        Job.objects.create(
            tenant=self.tenant,
            job_type="test_job",
            payload={},
            status=JobStatus.COMPLETED
        )
        Job.objects.create(
            tenant=self.tenant,
            job_type="test_job",
            payload={},
            status=JobStatus.DEAD_LETTER
        )
        
        # Get stats
        stats = JobService.get_job_stats(tenant=self.tenant)
        
        self.assertEqual(stats['pending'], 2)
        self.assertEqual(stats['running'], 1)
        self.assertEqual(stats['completed'], 3)
        self.assertEqual(stats['dead_letter'], 1)
        self.assertEqual(stats['total'], 7)
        
        # Success rate = 3/7 = 42.86%
        self.assertAlmostEqual(stats['success_rate'], 42.857, places=2)
