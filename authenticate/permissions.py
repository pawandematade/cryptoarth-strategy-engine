from rest_framework.permissions import BasePermission, SAFE_METHODS

from django.core.cache import cache


# Optional: Multiple role permission
class IsStaff(BasePermission):
    
    def has_permission(self, request, view):
        
        return (
            request.user
            and request.user.is_authenticated
            and (request.user.is_staff or request.user.is_vendor)
        )
 