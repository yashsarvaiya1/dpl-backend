# bmatches/permissions.py

from rest_framework.permissions import BasePermission, SAFE_METHODS


class IsAdminOrReadOnly(BasePermission):
    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return bool(request.user and request.user.is_authenticated)
        return bool(
            request.user and
            request.user.is_authenticated and
            request.user.is_staff
        )


class IsBMatchCreatorOrSuperAdmin(BasePermission):
    """
    Write access: only bmatch creator or superadmin.
    Read access: any authenticated user.
    """
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        if request.user.is_superuser:
            return True
        return obj.created_by == request.user


class IsAdminOrSuperAdmin(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            request.user.is_staff
        )
