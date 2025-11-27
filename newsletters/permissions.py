"""
Permissions for newsletters system.

Implements role-based access control:
- Admins/SuperAdmins can create, update, delete
- All authenticated users can read
"""

from rest_framework import permissions


class IsAdminOrReadOnly(permissions.BasePermission):
    """
    Permission that allows:
    - Read access (GET, HEAD, OPTIONS) for all authenticated users
    - Write access (POST, PUT, PATCH, DELETE) for admins and super_admins only
    """
    
    def has_permission(self, request, view):
        # Check if user is authenticated
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Allow read-only methods for all authenticated users
        if request.method in permissions.SAFE_METHODS:
            return True
        
        # Write methods require admin or super_admin role
        user_role = getattr(request.user, 'role', None)
        return user_role in ['admin', 'super_admin']
    
    def has_object_permission(self, request, view, obj):
        # Check if user is authenticated
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Allow read-only methods for all authenticated users
        if request.method in permissions.SAFE_METHODS:
            return True
        
        # Write methods require admin or super_admin role
        user_role = getattr(request.user, 'role', None)
        return user_role in ['admin', 'super_admin']
