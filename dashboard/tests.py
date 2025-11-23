"""
Tests for dashboard and API endpoints.
"""

from django.test import TestCase, Client
from django.urls import reverse
import json

from tenants.models import Tenant
from jobs.models import Job, JobStatus, DeadLetterQueue


class JobAPITestCase(TestCase):
    """Test job API endpoints."""
    
    def setUp(self):
        """Create test tenant and client."""
        self.tenant = Tenant.objects.create(
            name="API Test Tenant",
            api_key="test_api_key_123",
            max_concurrent_jobs=10,
            max_jobs_per_minute=100,
            max_jobs_per_hour=1000
        )
        self.client = Client()
        self.api_key_header = {'HTTP_X_API_KEY': 'test_api_key_123'}
    
    def test_create_job_success(self):
        """Test successful job creation via API."""
        response = self.client.post(
            '/api/jobs/',
            data=json.dumps({
                'job_type': 'test_job',
                'payload': {'duration': 5},
                'priority': 10
            }),
            content_type='application/json',
            **self.api_key_header
        )
        
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertIn('job', data)
        self.assertEqual(data['job']['job_type'], 'test_job')
        self.assertEqual(data['job']['priority'], 10)
        self.assertEqual(data['job']['status'], JobStatus.PENDING)
    
    def test_create_job_without_api_key(self):
        """Test job creation fails without API key."""
        response = self.client.post(
            '/api/jobs/',
            data=json.dumps({
                'job_type': 'test_job',
                'payload': {'duration': 5}
            }),
            content_type='application/json'
        )
        
        self.assertIn(response.status_code, [401, 403])  # Either unauthorized status is fine
    
    def test_create_job_with_invalid_api_key(self):
        """Test job creation fails with invalid API key."""
        response = self.client.post(
            '/api/jobs/',
            data=json.dumps({
                'job_type': 'test_job',
                'payload': {'duration': 5}
            }),
            content_type='application/json',
            HTTP_X_API_KEY='invalid_key'
        )
        
        self.assertIn(response.status_code, [401, 403])  # Either unauthorized status is fine
    
    def test_create_job_with_idempotency_key(self):
        """Test job creation with idempotency key."""
        idempotency_key = 'unique_test_key_123'
        
        # First request
        response1 = self.client.post(
            '/api/jobs/',
            data=json.dumps({
                'job_type': 'test_job',
                'payload': {'duration': 5},
                'idempotency_key': idempotency_key
            }),
            content_type='application/json',
            **self.api_key_header
        )
        
        self.assertEqual(response1.status_code, 201)
        job_id1 = response1.json()['job']['id']
        
        # Second request with same key
        response2 = self.client.post(
            '/api/jobs/',
            data=json.dumps({
                'job_type': 'test_job',
                'payload': {'duration': 5},
                'idempotency_key': idempotency_key
            }),
            content_type='application/json',
            **self.api_key_header
        )
        
        self.assertEqual(response2.status_code, 200)
        job_id2 = response2.json()['job']['id']
        
        # Should return same job
        self.assertEqual(job_id1, job_id2)
    
    def test_get_job_status(self):
        """Test retrieving job status via API."""
        # Create job
        job = Job.objects.create(
            tenant=self.tenant,
            job_type='test_job',
            payload={'key': 'value'},
            status=JobStatus.PENDING
        )
        
        # Get job status
        response = self.client.get(
            f'/api/jobs/{job.id}/',
            **self.api_key_header
        )
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['id'], str(job.id))
        self.assertEqual(data['job_type'], 'test_job')
        self.assertEqual(data['status'], JobStatus.PENDING)
    
    def test_list_jobs(self):
        """Test listing jobs via API."""
        # Create multiple jobs
        for i in range(5):
            Job.objects.create(
                tenant=self.tenant,
                job_type='test_job',
                payload={'index': i},
                status=JobStatus.PENDING
            )
        
        # List jobs
        response = self.client.get(
            '/api/jobs/',
            **self.api_key_header
        )
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('results', data)
        self.assertEqual(len(data['results']), 5)
    
    def test_get_job_stats(self):
        """Test job statistics endpoint."""
        # Create jobs in different states
        Job.objects.create(tenant=self.tenant, job_type='test_job', payload={}, status=JobStatus.PENDING)
        Job.objects.create(tenant=self.tenant, job_type='test_job', payload={}, status=JobStatus.PENDING)
        Job.objects.create(tenant=self.tenant, job_type='test_job', payload={}, status=JobStatus.RUNNING)
        Job.objects.create(tenant=self.tenant, job_type='test_job', payload={}, status=JobStatus.COMPLETED)
        Job.objects.create(tenant=self.tenant, job_type='test_job', payload={}, status=JobStatus.COMPLETED)
        Job.objects.create(tenant=self.tenant, job_type='test_job', payload={}, status=JobStatus.DEAD_LETTER)
        
        # Get stats
        response = self.client.get(
            '/api/jobs/stats/',
            **self.api_key_header
        )
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['pending'], 2)
        self.assertEqual(data['running'], 1)
        self.assertEqual(data['completed'], 2)
        self.assertEqual(data['dead_letter'], 1)
        self.assertEqual(data['total'], 6)
    
    def test_list_dlq(self):
        """Test listing dead letter queue items."""
        # Create job that went to DLQ
        job = Job.objects.create(
            tenant=self.tenant,
            job_type='test_job',
            payload={},
            status=JobStatus.DEAD_LETTER
        )
        
        dlq_item = DeadLetterQueue.objects.create(
            tenant=self.tenant,
            original_job_id=job.id,
            job_type='test_job',
            payload={},
            retry_count=3,
            final_error_message='Test error'
        )
        
        # List DLQ
        response = self.client.get(
            '/api/dlq/',
            **self.api_key_header
        )
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('results', data)
        self.assertEqual(len(data['results']), 1)
        self.assertEqual(data['results'][0]['retry_count'], 3)
    
    def test_filter_jobs_by_status(self):
        """Test filtering jobs by status."""
        # Create jobs with different statuses
        Job.objects.create(tenant=self.tenant, job_type='test_job', payload={}, status=JobStatus.PENDING)
        Job.objects.create(tenant=self.tenant, job_type='test_job', payload={}, status=JobStatus.COMPLETED)
        Job.objects.create(tenant=self.tenant, job_type='test_job', payload={}, status=JobStatus.COMPLETED)
        
        # Filter for completed jobs
        response = self.client.get(
            '/api/jobs/?status=completed',
            **self.api_key_header
        )
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data['results']), 2)
        self.assertTrue(all(j['status'] == 'completed' for j in data['results']))


class DashboardViewTestCase(TestCase):
    """Test dashboard view."""
    
    def test_dashboard_loads(self):
        """Test that dashboard page loads successfully."""
        response = self.client.get('/')
        
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Task Queue Dashboard')
        self.assertContains(response, 'Submit New Job')
        self.assertContains(response, 'Recent Jobs')
        self.assertContains(response, 'Dead Letter Queue')
