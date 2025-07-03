from rest_framework import permissions


class IsPharmacyOwner(permissions.BasePermission):
    """
    Custom permission to only allow pharmacy owners to access certain views.
    """
    def has_permission(self, request, view):
        return request.user.is_authenticated and getattr(request.user, 'is_pharmacy_owner', False)

    def has_object_permission(self, request, view, obj):
        if hasattr(obj, 'pharmacy'):
            return obj.pharmacy.owner == request.user
        elif hasattr(obj, 'owner'):
            return obj.owner == request.user
        return False


class IsPatient(permissions.BasePermission):
    """
    Custom permission to only allow authenticated patients to access certain views.
    """
    def has_permission(self, request, view):
        return request.user.is_authenticated and getattr(request.user, 'is_patient', False)


class IsOwnerOrReadOnly(permissions.BasePermission):
    """
    Custom permission to only allow owners of an object to edit it.
    """

    def has_object_permission(self, request, view, obj):
        # Read permissions for any authenticated user
        if request.method in permissions.SAFE_METHODS:
            return request.user.is_authenticated

        # Write permissions only to the owner
        return obj.user == request.user


class IsAdminOrReadOnly(permissions.BasePermission):
    """
    Custom permission to only allow admin users to edit, others can read.
    """

    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user.is_authenticated and request.user.is_staff


class IsVerifiedPharmacy(permissions.BasePermission):
    """
    Custom permission for verified pharmacies only.
    """

    def has_permission(self, request, view):
        return (
                request.user.is_authenticated and
                getattr(request.user, 'is_pharmacy_owner', False) and
                hasattr(request.user, 'pharmacy') and
                request.user.pharmacy.verified
        )