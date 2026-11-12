from rest_framework.permissions import BasePermission


class IsCustomer(BasePermission):
    """Allow review creation only for authenticated customer profiles."""

    def has_permission(self, request, view):
        profile = getattr(request.user, "profile", None)
        return (
            request.user.is_authenticated
            and getattr(profile, "type", None) == "customer"
        )
