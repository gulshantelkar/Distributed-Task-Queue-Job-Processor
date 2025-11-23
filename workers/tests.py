"""
Tests for worker functionality and job processing.
"""

from django.test import TestCase, TransactionTestCase
from unittest.mock import Mock, patch
import time

from tenants.models import Tenant
from jobs.models import Job, JobStatus
from workers.processor import JobProcessor


class JobProcessorTestCase(TestCase):
    """Test job processor functionality."""
    
    def setUp(self):
        """Create test tenant and jobs."""
        self.tenant = Tenant.objects.create(
            name="Test Tenant",
            api_key="test_key_processor",
            max_concurrent_jobs=10
        )
        self.processor = JobProcessor()
    
    def test_process_test_job_success(self):
        """Test successful test job processing."""
        job = Job.objects.create(
            tenant=self.tenant,
            job_type="test_job",
            payload={"duration": 0, "should_fail": False},
            status=JobStatus.RUNNING
        )
        
        result = self.processor.process(job)
        
        self.assertIsNotNone(result)
        self.assertTrue(result.get('success'))
        self.assertIn('duration', result)
    
    def test_process_test_job_failure(self):
        """Test test job intentional failure."""
        job = Job.objects.create(
            tenant=self.tenant,
            job_type="test_job",
            payload={"duration": 0, "should_fail": True},
            status=JobStatus.RUNNING
        )
        
        with self.assertRaises(Exception) as context:
            self.processor.process(job)
        
        self.assertIn("failed intentionally", str(context.exception))
    
    def test_process_send_email_job(self):
        """Test send_email job processing."""
        job = Job.objects.create(
            tenant=self.tenant,
            job_type="send_email",
            payload={
                "to": "test@example.com",
                "subject": "Test Subject",
                "body": "Test Body"
            },
            status=JobStatus.RUNNING
        )
        
        result = self.processor.process(job)
        
        self.assertIsNotNone(result)
        self.assertTrue(result.get('success'))
        self.assertEqual(result.get('email_sent_to'), "test@example.com")
    
    def test_process_process_data_job(self):
        """Test process_data job processing."""
        job = Job.objects.create(
            tenant=self.tenant,
            job_type="process_data",
            payload={
                "data": [1, 2, 3, 4, 5],
                "operation": "transform"
            },
            status=JobStatus.RUNNING
        )
        
        result = self.processor.process(job)
        
        self.assertIsNotNone(result)
        self.assertEqual(result.get('processed_items'), 5)
        self.assertEqual(result.get('operation'), "transform")
    
    def test_process_generate_report_job(self):
        """Test generate_report job processing."""
        job = Job.objects.create(
            tenant=self.tenant,
            job_type="generate_report",
            payload={
                "report_type": "monthly",
                "start_date": "2024-01-01",
                "end_date": "2024-01-31"
            },
            status=JobStatus.RUNNING
        )
        
        result = self.processor.process(job)
        
        self.assertIsNotNone(result)
        self.assertTrue(result.get('success'))
        self.assertEqual(result.get('report_type'), "monthly")
        self.assertIn('report_url', result)
    
    def test_process_call_webhook_job(self):
        """Test call_webhook job processing."""
        job = Job.objects.create(
            tenant=self.tenant,
            job_type="call_webhook",
            payload={
                "url": "https://example.com/webhook",
                "method": "POST",
                "data": {"key": "value"}
            },
            status=JobStatus.RUNNING
        )
        
        result = self.processor.process(job)
        
        self.assertIsNotNone(result)
        self.assertTrue(result.get('success'))
        self.assertEqual(result.get('url'), "https://example.com/webhook")
        self.assertEqual(result.get('method'), "POST")
    
    def test_process_unknown_job_type(self):
        """Test processing unknown job type uses default handler."""
        job = Job.objects.create(
            tenant=self.tenant,
            job_type="unknown_job_type",
            payload={"key": "value"},
            status=JobStatus.RUNNING
        )
        
        result = self.processor.process(job)
        
        self.assertIsNotNone(result)
        self.assertTrue(result.get('success'))
        self.assertEqual(result.get('job_type'), "unknown_job_type")
        self.assertIn('default handler', result.get('message'))


class WorkerLeasingTestCase(TransactionTestCase):
    """Test worker job leasing logic."""
    
    def setUp(self):
        """Create test tenant."""
        self.tenant = Tenant.objects.create(
            name="Test Tenant",
            api_key="test_key_worker",
            max_concurrent_jobs=10
        )
    
    def test_worker_leases_highest_priority_first(self):
        """Test worker leases jobs in priority order."""
        # Create jobs with different priorities
        job_low = Job.objects.create(
            tenant=self.tenant,
            job_type="test_job",
            payload={},
            priority=1,
            status=JobStatus.PENDING
        )
        
        job_high = Job.objects.create(
            tenant=self.tenant,
            job_type="test_job",
            payload={},
            priority=100,
            status=JobStatus.PENDING
        )
        
        job_medium = Job.objects.create(
            tenant=self.tenant,
            job_type="test_job",
            payload={},
            priority=50,
            status=JobStatus.PENDING
        )
        
        # Lease jobs one by one
        leased1 = Job.lease_next_job("worker-1", lease_duration=60)
        self.assertEqual(leased1.id, job_high.id)
        
        leased2 = Job.lease_next_job("worker-2", lease_duration=60)
        self.assertEqual(leased2.id, job_medium.id)
        
        leased3 = Job.lease_next_job("worker-3", lease_duration=60)
        self.assertEqual(leased3.id, job_low.id)
    
    def test_worker_respects_fifo_for_same_priority(self):
        """Test FIFO order for jobs with same priority."""
        # Create jobs with same priority but different times
        job1 = Job.objects.create(
            tenant=self.tenant,
            job_type="test_job",
            payload={},
            priority=0,
            status=JobStatus.PENDING
        )
        
        time.sleep(0.01)  # Small delay to ensure different timestamps
        
        job2 = Job.objects.create(
            tenant=self.tenant,
            job_type="test_job",
            payload={},
            priority=0,
            status=JobStatus.PENDING
        )
        
        time.sleep(0.01)
        
        job3 = Job.objects.create(
            tenant=self.tenant,
            job_type="test_job",
            payload={},
            priority=0,
            status=JobStatus.PENDING
        )
        
        # Should lease in order of creation
        leased1 = Job.lease_next_job("worker-1", lease_duration=60)
        self.assertEqual(leased1.id, job1.id)
        
        leased2 = Job.lease_next_job("worker-2", lease_duration=60)
        self.assertEqual(leased2.id, job2.id)
        
        leased3 = Job.lease_next_job("worker-3", lease_duration=60)
        self.assertEqual(leased3.id, job3.id)
    
    def test_lease_sets_correct_metadata(self):
        """Test that leasing sets correct job metadata."""
        job = Job.objects.create(
            tenant=self.tenant,
            job_type="test_job",
            payload={},
            status=JobStatus.PENDING
        )
        
        leased_job = Job.lease_next_job("worker-test-123", lease_duration=60)
        
        self.assertIsNotNone(leased_job)
        self.assertEqual(leased_job.status, JobStatus.RUNNING)
        self.assertEqual(leased_job.worker_id, "worker-test-123")
        self.assertIsNotNone(leased_job.started_at)
        self.assertIsNotNone(leased_job.lease_until)
        self.assertIsNotNone(leased_job.last_heartbeat)
    
    def test_no_jobs_available_returns_none(self):
        """Test that lease returns None when no jobs available."""
        leased_job = Job.lease_next_job("worker-1", lease_duration=60)
        self.assertIsNone(leased_job)


class WorkerHeartbeatTestCase(TestCase):
    """Test worker heartbeat and lease extension."""
    
    def setUp(self):
        """Create test tenant."""
        self.tenant = Tenant.objects.create(
            name="Test Tenant",
            api_key="test_key_heartbeat",
            max_concurrent_jobs=10
        )
    
    def test_extend_lease_updates_lease_until(self):
        """Test that extend_lease updates the lease_until time."""
        from django.utils import timezone
        
        job = Job.objects.create(
            tenant=self.tenant,
            job_type="test_job",
            payload={},
            status=JobStatus.RUNNING,
            lease_until=timezone.now()
        )
        
        old_lease = job.lease_until
        
        # Extend lease
        job.extend_lease(seconds=60)
        
        job.refresh_from_db()
        self.assertGreater(job.lease_until, old_lease)
        self.assertIsNotNone(job.last_heartbeat)
    
    def test_heartbeat_updates_last_heartbeat(self):
        """Test that heartbeat updates last_heartbeat timestamp."""
        from django.utils import timezone
        from datetime import timedelta
        
        job = Job.objects.create(
            tenant=self.tenant,
            job_type="test_job",
            payload={},
            status=JobStatus.RUNNING,
            last_heartbeat=timezone.now() - timedelta(seconds=30)
        )
        
        old_heartbeat = job.last_heartbeat
        
        # Send heartbeat
        job.extend_lease(seconds=60)
        
        job.refresh_from_db()
        self.assertGreater(job.last_heartbeat, old_heartbeat)


class WorkerIntegrationTestCase(TransactionTestCase):
    """Integration tests for worker processing flow."""
    
    def setUp(self):
        """Create test tenant."""
        self.tenant = Tenant.objects.create(
            name="Test Tenant",
            api_key="test_key_integration",
            max_concurrent_jobs=10
        )
        self.processor = JobProcessor()
    
    def test_full_worker_lifecycle_success(self):
        """Test complete worker lifecycle: lease -> process -> ack."""
        # Create pending job
        job = Job.objects.create(
            tenant=self.tenant,
            job_type="test_job",
            payload={"duration": 0, "should_fail": False},
            status=JobStatus.PENDING
        )
        
        # Worker leases job
        leased_job = Job.lease_next_job("worker-integration", lease_duration=60)
        self.assertIsNotNone(leased_job)
        self.assertEqual(leased_job.id, job.id)
        self.assertEqual(leased_job.status, JobStatus.RUNNING)
        
        # Worker processes job
        result = self.processor.process(leased_job)
        self.assertIsNotNone(result)
        
        # Worker acks job
        success = leased_job.ack(result=result)
        self.assertTrue(success)
        
        # Verify final state
        leased_job.refresh_from_db()
        self.assertEqual(leased_job.status, JobStatus.COMPLETED)
        self.assertIsNotNone(leased_job.completed_at)
        self.assertIsNotNone(leased_job.result)
    
    def test_full_worker_lifecycle_with_retry(self):
        """Test complete worker lifecycle with failure and retry."""
        # Create pending job with max_retries=3 (allows 2 retries before DLQ)
        job = Job.objects.create(
            tenant=self.tenant,
            job_type="test_job",
            payload={"duration": 0, "should_fail": True},
            status=JobStatus.PENDING,
            max_retries=3  # After 3 failures, retry_count reaches 3 and moves to DLQ
        )
        
        # First attempt
        leased_job = Job.lease_next_job("worker-retry-1", lease_duration=60)
        self.assertIsNotNone(leased_job)
        
        try:
            self.processor.process(leased_job)
            self.fail("Should have raised exception")
        except Exception as e:
            # Worker nacks job
            moved_to_dlq = leased_job.nack(
                error_message=str(e),
                error_trace="test trace"
            )
            self.assertFalse(moved_to_dlq)
        
        # Verify job is back to pending with retry count
        leased_job.refresh_from_db()
        self.assertEqual(leased_job.status, JobStatus.PENDING)
        self.assertEqual(leased_job.retry_count, 1)
        
        # Second attempt - should retry again
        leased_job2 = Job.lease_next_job("worker-retry-2", lease_duration=60)
        self.assertIsNotNone(leased_job2)
        self.assertEqual(leased_job2.id, job.id)
        
        try:
            self.processor.process(leased_job2)
            self.fail("Should have raised exception")
        except Exception:
            moved_to_dlq = leased_job2.nack(
                error_message="Failed again",
                error_trace="test trace 2"
            )
            self.assertFalse(moved_to_dlq)  # Should still retry
        
        # Verify retry count increased
        leased_job2.refresh_from_db()
        self.assertEqual(leased_job2.status, JobStatus.PENDING)
        self.assertEqual(leased_job2.retry_count, 2)
        
        # Third attempt - should move to DLQ (retry_count will become 3 >= max_retries 3)
        leased_job3 = Job.lease_next_job("worker-retry-3", lease_duration=60)
        self.assertIsNotNone(leased_job3)
        self.assertEqual(leased_job3.id, job.id)
        
        try:
            self.processor.process(leased_job3)
            self.fail("Should have raised exception")
        except Exception:
            moved_to_dlq = leased_job3.nack(
                error_message="Final failure",
                error_trace="test trace 3"
            )
            self.assertTrue(moved_to_dlq)
        
        # Verify job moved to DLQ
        leased_job3.refresh_from_db()
        self.assertEqual(leased_job3.status, JobStatus.DEAD_LETTER)
        self.assertEqual(leased_job3.retry_count, 3)
