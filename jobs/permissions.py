"""
Custom permissions for API key authentication.
"""

from rest_framework import permissions


class HasTenantAccess(permissions.BasePermission):
    """
    Custom permission to check for API key via tenant middleware.
    
    The TenantMiddleware sets request.tenant if a valid API key is provided.
    This permission class just verifies that the tenant was set.
    """
    
    def has_permission(self, request, view):
        """
        Check if request has a valid tenant (set by TenantMiddleware).
        """
        # Check if tenant was set by middleware
        return hasattr(request, 'tenant') and request.tenant is not None
    
    message = "Valid API key required. Provide via X-API-Key header or Authorization: Bearer header."

