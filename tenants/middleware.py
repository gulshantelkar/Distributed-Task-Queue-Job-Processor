"""
Middleware for tenant authentication and isolation.
"""

import logging
from django.utils.deprecation import MiddlewareMixin
from django.http import JsonResponse
from .models import Tenant

logger = logging.getLogger(__name__)


class TenantMiddleware(MiddlewareMixin):
    
    # Paths that don't require authentication
    EXEMPT_PATHS = [
        '/admin/',
        '/api/health/',
        '/api/docs/',
        '/api/tenants/',  # Tenant management endpoints (for getting API keys)
        '/static/',
        '/media/',
    ]
    
    def process_request(self, request):
        """Process incoming request to extract and validate authentication."""
        
        # Skip authentication for exempt paths
        if any(request.path.startswith(path) for path in self.EXEMPT_PATHS):
            return None
        
        # Skip for WebSocket connections (handled separately)
        if request.path.startswith('/ws/'):
            return None
        
        # Check session authentication first (for logged-in users via dashboard)
        if hasattr(request, 'user') and request.user.is_authenticated:
            # User is logged in via Django session
            try:
                # Get tenant for this user
                tenant = Tenant.objects.get(user=request.user, is_active=True)
                request.tenant = tenant
                logger.debug(f"Session authenticated: {tenant.name} ({tenant.id})")
                return None
            except Tenant.DoesNotExist:
                # User exists but no tenant - might be admin
                if request.user.is_staff:
                    return None
                # For API endpoints, require tenant
                if request.path.startswith('/api/'):
                    return JsonResponse({
                        'error': 'No tenant found for this user'
                    }, status=403)
                return None
        
        # For API endpoints, also check for API key (for external API access)
        if request.path.startswith('/api/'):
            api_key = self._extract_api_key(request)
            
            if api_key:
                # Validate API key and get tenant
                try:
                    tenant = Tenant.objects.get(api_key=api_key, is_active=True)
                    request.tenant = tenant
                    logger.debug(f"API key authenticated: {tenant.name} ({tenant.id})")
                    return None
                except Tenant.DoesNotExist:
                    logger.warning(f"Invalid API key: {api_key[:10]}...")
                    return JsonResponse({
                        'error': 'Invalid API key',
                        'detail': 'The provided API key is invalid or inactive'
                    }, status=401)
            else:
                # No session and no API key for API endpoint
                logger.warning(f"Missing authentication for {request.path}")
                return JsonResponse({
                    'error': 'Authentication required',
                    'detail': 'Please log in or provide an API key'
                }, status=401)
        
        return None
    
    def _extract_api_key(self, request):
        """
        Extract API key from request headers or query parameters.
        
        Returns:
            str: API key if found, None otherwise
        """
        # Check Authorization header (Bearer token)
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            return auth_header[7:].strip()
        
        # Check X-API-Key header
        api_key_header = request.headers.get('X-API-Key', '')
        if api_key_header:
            return api_key_header.strip()
        
        # Check query parameter (less secure, but convenient for testing)
        api_key_param = request.GET.get('api_key', '')
        if api_key_param:
            return api_key_param.strip()
        
        return None

