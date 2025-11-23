"""
Django management command to run a worker.

Usage:
    python manage.py run_worker
    python manage.py run_worker --worker-id my-worker-1
    python manage.py run_worker --lease-duration 120
"""

from django.core.management.base import BaseCommand
from workers.worker import Worker


class Command(BaseCommand):
    help = 'Run a task queue worker'
    
    def add_arguments(self, parser):
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
    
    def handle(self, *args, **options):
        worker_id = options['worker_id']
        lease_duration = options['lease_duration']
        poll_interval = options['poll_interval']
        
        self.stdout.write(
            self.style.SUCCESS(f'Starting worker{f" {worker_id}" if worker_id else ""}...')
        )
        
        worker = Worker(
            worker_id=worker_id,
            lease_duration=lease_duration,
            poll_interval=poll_interval
        )
        
        try:
            worker.start()
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING('\nWorker stopped by user'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Worker error: {e}'))
            raise

