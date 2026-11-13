from rest_framework.permissions import BasePermission


class IsCustomer(BasePermission):
    """Allow review creation for authenticated customers."""

    def has_permission(self, request, view):
        profile = getattr(request.user, "profile", None)
        return (
            request.user.is_authenticated
            and getattr(profile, "type", None) == "customer"
        )


class IsReviewOwner(BasePermission):
    """Restrict review updates to their authenticated reviewer."""

    def has_object_permission(self, request, view, obj):
        return obj.reviewer_id == request.user.pk
