"""
Views for tenant management.
"""

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib.auth import authenticate, login as django_login, logout as django_logout
from django.contrib.auth.models import User
from django.db import transaction
import json

from .models import Tenant


@csrf_exempt
@require_http_methods(["POST"])
def register(request):
    """
    Register a new user with username and password.
    
    POST /api/auth/register/
    Body: {
        "username": "john_doe",
        "password": "secure_password",
        "email": "john@company.com",
        "name": "John Doe"
    }
    
    Returns: {
        "success": true,
        "message": "Registration successful",
        "user": {
            "username": "john_doe",
            "email": "john@company.com"
        }
    }
    """
    try:
        data = json.loads(request.body)
        username = data.get('username')
        password = data.get('password')
        email = data.get('email', '')
        name = data.get('name', '')
        
        # Validation
        if not username or not password:
            return JsonResponse({
                'error': 'Username and password are required'
            }, status=400)
        
        if len(password) < 6:
            return JsonResponse({
                'error': 'Password must be at least 6 characters long'
            }, status=400)
        
        # Check if username exists
        if User.objects.filter(username=username).exists():
            return JsonResponse({
                'error': 'Username already exists'
            }, status=400)
        
        # Check if email exists
        if email and User.objects.filter(email=email).exists():
            return JsonResponse({
                'error': 'Email already registered'
            }, status=400)
        
        # Create user and tenant atomically
        with transaction.atomic():
            # Create Django user
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                first_name=name
            )
            
            # Create tenant for this user
            tenant = Tenant.objects.create(
                name=name or username,
                email=email,
                user=user  # Link tenant to user
            )
            
            # Auto-login after registration
            django_login(request, user)
        
        return JsonResponse({
            'success': True,
            'message': 'Registration successful! You are now logged in.',
            'user': {
                'username': user.username,
                'email': user.email,
                'name': name or username
            }
        }, status=201)
        
    except json.JSONDecodeError:
        return JsonResponse({
            'error': 'Invalid JSON'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def login(request):
    """
    Login with username and password.
    
    POST /api/auth/login/
    Body: {
        "username": "john_doe",
        "password": "secure_password"
    }
    
    Returns: {
        "success": true,
        "message": "Login successful",
        "user": {
            "username": "john_doe",
            "email": "john@company.com"
        }
    }
    """
    try:
        data = json.loads(request.body)
        username = data.get('username')
        password = data.get('password')
        
        if not username or not password:
            return JsonResponse({
                'error': 'Username and password are required'
            }, status=400)
        
        # Authenticate user
        user = authenticate(username=username, password=password)
        
        if user is not None:
            if user.is_active:
                django_login(request, user)
                
                # Get tenant info
                try:
                    tenant = Tenant.objects.get(user=user)
                    tenant_name = tenant.name
                except Tenant.DoesNotExist:
                    tenant_name = user.username
                
                return JsonResponse({
                    'success': True,
                    'message': 'Login successful!',
                    'user': {
                        'username': user.username,
                        'email': user.email,
                        'name': tenant_name
                    }
                })
            else:
                return JsonResponse({
                    'error': 'Account is disabled'
                }, status=403)
        else:
            return JsonResponse({
                'error': 'Invalid username or password'
            }, status=401)
            
    except json.JSONDecodeError:
        return JsonResponse({
            'error': 'Invalid JSON'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def logout(request):
    """
    Logout current user.
    
    POST /api/auth/logout/
    
    Returns: {
        "success": true,
        "message": "Logged out successfully"
    }
    """
    django_logout(request)
    return JsonResponse({
        'success': True,
        'message': 'Logged out successfully'
    })


@require_http_methods(["GET"])
def current_user(request):
    """
    Get current logged in user info.
    
    GET /api/auth/me/
    
    Returns user info if authenticated, error otherwise.
    """
    if request.user.is_authenticated:
        try:
            tenant = Tenant.objects.get(user=request.user)
            tenant_name = tenant.name
        except Tenant.DoesNotExist:
            tenant_name = request.user.username
        
        return JsonResponse({
            'authenticated': True,
            'user': {
                'username': request.user.username,
                'email': request.user.email,
                'name': tenant_name
            }
        })
    else:
        return JsonResponse({
            'authenticated': False,
            'error': 'Not authenticated'
        }, status=401)


@csrf_exempt
@require_http_methods(["POST"])
def create_tenant(request):
    try:
        data = json.loads(request.body)
        name = data.get('name')
        email = data.get('email', '')
        
        if not name:
            return JsonResponse({
                'error': 'Name is required'
            }, status=400)
        
        if not email:
            return JsonResponse({
                'error': 'Email is required'
            }, status=400)
        
        # Check if email already exists
        if Tenant.objects.filter(email=email).exists():
            return JsonResponse({
                'error': 'A tenant with this email already exists'
            }, status=400)
        
        # Create tenant
        tenant = Tenant.objects.create(
            name=name,
            email=email
        )
        
        return JsonResponse({
            'tenant_id': str(tenant.id),
            'name': tenant.name,
            'email': tenant.email,
            'api_key': tenant.api_key,
            'max_concurrent_jobs': tenant.max_concurrent_jobs,
            'max_jobs_per_minute': tenant.max_jobs_per_minute,
            'max_jobs_per_hour': tenant.max_jobs_per_hour,
            'created_at': tenant.created_at.isoformat(),
            'message': '⚠️ IMPORTANT: Save this API key securely. It will not be shown again!'
        }, status=201)
        
    except json.JSONDecodeError:
        return JsonResponse({
            'error': 'Invalid JSON'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'error': str(e)
        }, status=500)


@require_http_methods(["GET"])
def list_tenants(request):
    """
    List all tenants (ADMIN ONLY - for management purposes).
    
    GET /api/tenants/list/
    
    NOTE: This endpoint is for admin use only. API keys are hidden for security.
    """
    # Check if user is admin/staff
    if not (hasattr(request, 'user') and request.user.is_authenticated and request.user.is_staff):
        return JsonResponse({
            'error': 'Admin access required'
        }, status=403)
    
    tenants = Tenant.objects.all().order_by('-created_at')[:20]
    
    return JsonResponse({
        'count': tenants.count(),
        'tenants': [
            {
                'tenant_id': str(t.id),
                'name': t.name,
                'email': t.email,
                'api_key': f"{t.api_key[:10]}...{t.api_key[-10:]}",  # Masked for security
                'is_active': t.is_active,
                'max_concurrent_jobs': t.max_concurrent_jobs,
                'max_jobs_per_minute': t.max_jobs_per_minute,
                'max_jobs_per_hour': t.max_jobs_per_hour,
                'created_at': t.created_at.isoformat()
            }
            for t in tenants
        ]
    })

