from rest_framework.permissions import BasePermission


class IsCustomer(BasePermission):
    """Allow order creation only for authenticated customer profiles."""

    def has_permission(self, request, view):
        profile = getattr(request.user, "profile", None)
        return (
            request.user.is_authenticated
            and getattr(profile, "type", None) == "customer"
        )


class IsBusiness(BasePermission):
    """Allow order updates only for authenticated business profiles."""

    def has_permission(self, request, view):
        profile = getattr(request.user, "profile", None)
        return (
            request.user.is_authenticated
            and getattr(profile, "type", None) == "business"
        )


class IsOrderBusinessOwner(BasePermission):
    """Restrict updates to the business assigned to the order."""

    def has_object_permission(self, request, view, obj):
        return obj.business_user_id == request.user.id
