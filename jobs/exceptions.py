"""
Custom exceptions for job management.
"""

from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status
import logging

logger = logging.getLogger(__name__)


class JobException(Exception):
    """Base exception for job-related errors."""
    pass


class QuotaExceededException(JobException):
    """Raised when tenant quota is exceeded."""
    pass


class RateLimitExceededException(JobException):
    """Raised when rate limit is exceeded."""
    pass


class DuplicateJobException(JobException):
    """Raised when duplicate job is detected via idempotency key."""
    pass


class JobNotFoundException(JobException):
    """Raised when job is not found."""
    pass


class ConcurrencyException(JobException):
    """Raised when optimistic locking fails."""
    pass


def custom_exception_handler(exc, context):
    """
    Custom exception handler for REST framework.
    Provides structured error responses and logging.
    """
    # Call REST framework's default exception handler first
    response = exception_handler(exc, context)
    
    # Handle our custom exceptions
    if isinstance(exc, RateLimitExceededException):
        logger.warning(f"Rate limit exceeded: {exc}")
        return Response({
            'error': 'Rate limit exceeded',
            'detail': str(exc),
            'type': 'rate_limit'
        }, status=status.HTTP_429_TOO_MANY_REQUESTS)
    
    elif isinstance(exc, QuotaExceededException):
        logger.warning(f"Quota exceeded: {exc}")
        return Response({
            'error': 'Quota exceeded',
            'detail': str(exc),
            'type': 'quota'
        }, status=status.HTTP_429_TOO_MANY_REQUESTS)
    
    elif isinstance(exc, JobNotFoundException):
        return Response({
            'error': 'Job not found',
            'detail': str(exc),
            'type': 'not_found'
        }, status=status.HTTP_404_NOT_FOUND)
    
    elif isinstance(exc, ConcurrencyException):
        logger.error(f"Concurrency error: {exc}")
        return Response({
            'error': 'Concurrency error',
            'detail': str(exc),
            'type': 'concurrency'
        }, status=status.HTTP_409_CONFLICT)
    
    # Log unhandled exceptions
    if response is None:
        logger.error(f"Unhandled exception: {exc}", exc_info=True)
    
    return response

