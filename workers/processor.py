"""
Job processor that executes different job types.

This module contains the business logic for processing jobs.
Add your custom job handlers here.
"""

import time
import logging
import random

logger = logging.getLogger(__name__)


class JobProcessor:
    """
    Processes different job types.
    
    To add a new job type:
    1. Create a method: def process_<job_type>(self, job)
    2. The dispatcher will automatically route to it
    3. Return the result data (will be stored in job.result)
    """
    
    def process(self, job):
        """
        Main processing entry point.
        Dispatches to specific handler based on job_type.
        
        Args:
            job: Job instance to process
        
        Returns:
            dict: Result data
        
        Raises:
            Exception: If job processing fails
        """
        job_type = job.job_type
        handler_name = f'process_{job_type}'
        
        # Get handler method
        handler = getattr(self, handler_name, None)
        
        if handler and callable(handler):
            logger.info(f"Executing {job_type} handler for job {job.id}")
            return handler(job)
        else:
            # No specific handler, use default
            logger.warning(f"No handler for job type '{job_type}', using default")
            return self.process_default(job)
    
    
    def process_send_email(self, job):
        """
        Example: Send email job.
        
        Payload format:
        {
            "to": "user@example.com",
            "subject": "Hello",
            "body": "Email content",
            "duration": 2,  # optional: seconds to simulate
            "should_fail": false  # optional: test failure
        }
        """
        payload = job.payload
        to = payload.get('to', 'test@example.com')
        subject = payload.get('subject', 'Test Subject')
        body = payload.get('body', 'Test Body')
        duration = payload.get('duration', 2)
        should_fail = payload.get('should_fail', False)
        
        logger.info(f"Sending email to {to}: {subject}")
        
        # Simulate email sending
        time.sleep(duration)
        
        # Check for test failure
        if should_fail:
            raise Exception(f"Email job failed intentionally")
        
        return {
            'success': True,
            'email_sent_to': to,
            'timestamp': time.time()
        }
    
    def process_process_data(self, job):
        """
        Example: Process data job.
        
        Payload format:
        {
            "data": [...],
            "operation": "transform",
            "duration": 3,  # optional: seconds to simulate
            "should_fail": false  # optional: test failure
        }
        """
        payload = job.payload
        data = payload.get('data', [])
        operation = payload.get('operation', 'process')
        duration = payload.get('duration', 3)
        should_fail = payload.get('should_fail', False)
        
        logger.info(f"Processing data with operation: {operation}")
        
        # Simulate data processing
        time.sleep(duration)
        
        # Check for test failure
        if should_fail:
            raise Exception(f"Data processing job failed intentionally")
        
        result_data = {
            'processed_items': len(data),
            'operation': operation,
            'timestamp': time.time()
        }
        
        return result_data
    
    def process_generate_report(self, job):
        """
        Example: Generate report job.
        
        Payload format:
        {
            "report_type": "monthly",
            "start_date": "2024-01-01",
            "end_date": "2024-01-31",
            "duration": 5,  # optional: seconds to simulate
            "should_fail": false  # optional: test failure
        }
        """
        payload = job.payload
        report_type = payload.get('report_type', 'monthly')
        start_date = payload.get('start_date', '2024-01-01')
        end_date = payload.get('end_date', '2024-01-31')
        duration = payload.get('duration', 5)
        should_fail = payload.get('should_fail', False)
        
        logger.info(f"Generating {report_type} report from {start_date} to {end_date}")
        
        # Simulate report generation
        time.sleep(duration)
        
        # Check for test failure
        if should_fail:
            raise Exception(f"Report generation job failed intentionally")
        
        return {
            'success': True,
            'report_type': report_type,
            'report_url': f'/reports/{job.id}.pdf',
            'generated_at': time.time()
        }
    
    def process_call_webhook(self, job):
        """
        Example: Call external webhook.
        
        Payload format:
        {
            "url": "https://example.com/webhook",
            "method": "POST",
            "data": {...},
            "duration": 1,  # optional: seconds to simulate
            "should_fail": false  # optional: test failure
        }
        """
        payload = job.payload
        url = payload.get('url', 'https://example.com/webhook')
        method = payload.get('method', 'POST')
        data = payload.get('data', {})
        duration = payload.get('duration', 1)
        should_fail = payload.get('should_fail', False)
        
        logger.info(f"Calling webhook: {method} {url}")
        
        # Simulate webhook call
        time.sleep(duration)
        
        # Check for test failure
        if should_fail:
            raise Exception(f"Webhook call job failed intentionally")
        
        return {
            'success': True,
            'url': url,
            'method': method,
            'timestamp': time.time()
        }
    
    def process_test_job(self, job):
        """
        Test job for development and testing.
        
        Payload format:
        {
            "duration": 5,  # seconds to sleep
            "should_fail": false,  # whether to simulate failure
            "failure_rate": 0.1  # probability of random failure (0.0-1.0)
        }
        """
        payload = job.payload
        duration = payload.get('duration', 3)
        should_fail = payload.get('should_fail', False)
        failure_rate = payload.get('failure_rate', 0.0)
        
        logger.info(f"Test job: sleeping for {duration}s")
        
        # Simulate work
        time.sleep(duration)
        
        # Simulate random failures
        if should_fail or random.random() < failure_rate:
            raise Exception(f"Test job failed intentionally (failure_rate={failure_rate})")
        
        return {
            'success': True,
            'duration': duration,
            'message': f'Test job completed after {duration}s'
        }
    
    def process_default(self, job):
        """
        Default handler for unknown job types.
        Simply logs the job and marks it as complete.
        
        Args:
            job: Job instance
        
        Returns:
            dict: Basic result
        """
        payload = job.payload
        duration = payload.get('duration', 1)
        should_fail = payload.get('should_fail', False)
        
        logger.info(f"Processing job {job.id} with default handler")
        logger.debug(f"Job payload: {job.payload}")
        
        # Simulate some work
        time.sleep(duration)
        
        # Check for test failure
        if should_fail:
            raise Exception(f"Default job handler failed intentionally")
        
        return {
            'success': True,
            'job_type': job.job_type,
            'message': 'Processed with default handler',
            'timestamp': time.time()
        }
