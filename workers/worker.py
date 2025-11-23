"""
Worker implementation with lease mechanism and heartbeat.

This worker:
1. Polls for jobs atomically using SELECT FOR UPDATE SKIP LOCKED
2. Maintains heartbeat to extend lease for long-running jobs
3. Handles graceful shutdown
4. Implements proper ack/nack logic with race condition protection
"""

import os
import sys
import signal
import time
import uuid
import logging
import threading
from datetime import timedelta

# Add parent directory to path for Django imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Setup Django
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'taskqueue.settings')
django.setup()

from django.conf import settings
from django.utils import timezone
from jobs.models import Job, JobStatus
from workers.processor import JobProcessor

logger = logging.getLogger(__name__)


class Worker:
    """
    Main worker class that polls and processes jobs.
    
    Features:
    - Atomic job leasing with PostgreSQL SKIP LOCKED
    - Heartbeat mechanism for long-running jobs
    - Graceful shutdown handling
    - Race condition protection with optimistic locking
    """
    
    def __init__(
        self,
        worker_id=None,
        lease_duration=None,
        poll_interval=None,
        heartbeat_interval=15
    ):
        """
        Initialize worker.
        
        Args:
            worker_id: Unique identifier for this worker
            lease_duration: How long to lease jobs (seconds)
            poll_interval: How often to poll for jobs (seconds)
            heartbeat_interval: How often to send heartbeat (seconds)
        """
        self.worker_id = worker_id or f"worker-{uuid.uuid4().hex[:8]}"
        self.lease_duration = lease_duration or getattr(settings, 'WORKER_LEASE_DURATION', 60)
        self.poll_interval = poll_interval or getattr(settings, 'WORKER_POLL_INTERVAL', 2)
        self.heartbeat_interval = heartbeat_interval
        
        self.running = False
        self.current_job = None
        self.heartbeat_thread = None
        self.heartbeat_stop_event = threading.Event()
        
        # Register signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self._handle_shutdown)
        signal.signal(signal.SIGINT, self._handle_shutdown)
        
        logger.info(
            f"Worker initialized: {self.worker_id}",
            extra={
                'worker_id': self.worker_id,
                'lease_duration': self.lease_duration,
                'poll_interval': self.poll_interval
            }
        )
    
    def start(self):
        """
        Start the worker main loop.
        
        This loop:
        1. Polls for available jobs
        2. Leases and processes jobs
        3. Handles errors and retries
        4. Continues until shutdown signal received
        """
        self.running = True
        logger.info(f"Worker {self.worker_id} starting...")
        
        while self.running:
            try:
                # Try to lease next job
                job = Job.lease_next_job(
                    worker_id=self.worker_id,
                    lease_duration=self.lease_duration
                )
                
                if job:
                    self.current_job = job
                    self._process_job(job)
                    self.current_job = None
                else:
                    # No jobs available, sleep before polling again
                    time.sleep(self.poll_interval)
            
            except KeyboardInterrupt:
                logger.info("Keyboard interrupt received, shutting down...")
                break
            
            except Exception as e:
                logger.error(
                    f"Worker error: {e}",
                    exc_info=True,
                    extra={'worker_id': self.worker_id}
                )
                time.sleep(self.poll_interval)
        
        logger.info(f"Worker {self.worker_id} stopped")
    
    def _process_job(self, job):
        """
        Process a single job with heartbeat mechanism.
        
        This method:
        1. Starts heartbeat thread
        2. Processes the job
        3. Handles success/failure
        4. Stops heartbeat
        5. Acknowledges or negatively acknowledges job
        
        Args:
            job: Job instance to process
        """
        logger.info(
            f"Processing job {job.id}",
            extra={
                'job_id': str(job.id),
                'job_type': job.job_type,
                'worker_id': self.worker_id,
                'tenant_id': str(job.tenant_id),
                'retry_count': job.retry_count
            }
        )
        
        # Start heartbeat thread for this job
        self._start_heartbeat(job)
        
        try:
            # Verify job is still in RUNNING state (race condition check)
            job.refresh_from_db()
            if job.status != JobStatus.RUNNING:
                logger.warning(
                    f"Job {job.id} no longer in RUNNING state, skipping",
                    extra={'job_id': str(job.id), 'status': job.status}
                )
                return
            
            # Process the job
            processor = JobProcessor()
            result = processor.process(job)
            
            # Acknowledge success
            ack_success = job.ack(result=result)
            
            if ack_success:
                logger.info(
                    f"Job {job.id} completed successfully",
                    extra={
                        'job_id': str(job.id),
                        'job_type': job.job_type,
                        'worker_id': self.worker_id
                    }
                )
            else:
                logger.warning(
                    f"Job {job.id} already processed by another worker",
                    extra={'job_id': str(job.id)}
                )
        
        except Exception as e:
            logger.error(
                f"Job {job.id} failed: {e}",
                exc_info=True,
                extra={
                    'job_id': str(job.id),
                    'job_type': job.job_type,
                    'worker_id': self.worker_id,
                    'error': str(e)
                }
            )
            
            # Negative acknowledge (will retry or move to DLQ)
            import traceback
            moved_to_dlq = job.nack(
                error_message=str(e),
                error_trace=traceback.format_exc()
            )
            
            if moved_to_dlq:
                logger.error(
                    f"Job {job.id} moved to DLQ after {job.retry_count} retries",
                    extra={'job_id': str(job.id)}
                )
            else:
                logger.info(
                    f"Job {job.id} will be retried (attempt {job.retry_count}/{job.max_retries})",
                    extra={'job_id': str(job.id)}
                )
        
        finally:
            # Stop heartbeat thread
            self._stop_heartbeat()
    
    def _start_heartbeat(self, job):
        """
        Start heartbeat thread for a job.
        
        The heartbeat thread periodically extends the job lease
        to prevent other workers from picking it up.
        
        Args:
            job: Job instance
        """
        self.heartbeat_stop_event.clear()
        
        def heartbeat_loop():
            """Heartbeat loop that runs in a separate thread."""
            while not self.heartbeat_stop_event.is_set():
                try:
                    # Sleep first (so we don't extend immediately)
                    time.sleep(self.heartbeat_interval)
                    
                    if self.heartbeat_stop_event.is_set():
                        break
                    
                    # Extend the lease
                    job.extend_lease(seconds=self.lease_duration)
                    logger.debug(
                        f"Heartbeat: lease extended for job {job.id}",
                        extra={
                            'job_id': str(job.id),
                            'worker_id': self.worker_id
                        }
                    )
                
                except Exception as e:
                    logger.error(
                        f"Heartbeat error for job {job.id}: {e}",
                        extra={'job_id': str(job.id)}
                    )
        
        self.heartbeat_thread = threading.Thread(target=heartbeat_loop, daemon=True)
        self.heartbeat_thread.start()
        logger.debug(f"Heartbeat started for job {job.id}")
    
    def _stop_heartbeat(self):
        """Stop the heartbeat thread."""
        if self.heartbeat_thread and self.heartbeat_thread.is_alive():
            self.heartbeat_stop_event.set()
            self.heartbeat_thread.join(timeout=2)
            logger.debug("Heartbeat stopped")
    
    def _handle_shutdown(self, signum, frame):
        """
        Handle shutdown signal (SIGTERM, SIGINT).
        
        Implements graceful shutdown:
        1. Stop accepting new jobs
        2. Wait for current job to finish
        3. Release lease if job not finished
        4. Exit cleanly
        
        Args:
            signum: Signal number
            frame: Current stack frame
        """
        signal_name = 'SIGTERM' if signum == signal.SIGTERM else 'SIGINT'
        logger.info(
            f"Worker {self.worker_id} received {signal_name}, initiating graceful shutdown",
            extra={'worker_id': self.worker_id}
        )
        
        # Stop the main loop
        self.running = False
        
        # If processing a job, give it time to finish
        if self.current_job:
            logger.info(
                f"Waiting for current job {self.current_job.id} to finish...",
                extra={'job_id': str(self.current_job.id)}
            )
            
            # Extend lease to ensure we have time to finish
            try:
                self.current_job.extend_lease(seconds=120)
            except Exception as e:
                logger.error(f"Failed to extend lease during shutdown: {e}")
            
            # Note: The job will finish naturally or fail
            # The finally block in _process_job will clean up
        
        logger.info(f"Worker {self.worker_id} shutdown complete")


def main():
    """
    Main entry point for worker process.
    
    Usage:
        python workers/worker.py [worker_id]
    """
    import argparse
    
    parser = argparse.ArgumentParser(description='Task Queue Worker')
    parser.add_argument(
        '--worker-id',
        type=str,
        default=None,
        help='Unique worker ID (auto-generated if not provided)'
    )
    parser.add_argument(
        '--lease-duration',
        type=int,
        default=None,
        help='Job lease duration in seconds'
    )
    parser.add_argument(
        '--poll-interval',
        type=int,
        default=None,
        help='Polling interval in seconds'
    )
    
    args = parser.parse_args()
    
    # Create and start worker
    worker = Worker(
        worker_id=args.worker_id,
        lease_duration=args.lease_duration,
        poll_interval=args.poll_interval
    )
    
    try:
        worker.start()
    except KeyboardInterrupt:
        logger.info("Worker interrupted")
    except Exception as e:
        logger.error(f"Worker crashed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()

