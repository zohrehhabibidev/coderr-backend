from rest_framework.permissions import SAFE_METHODS, BasePermission


class IsBusinessOrReadOnly(BasePermission):
    """Allow public reads and authenticated business writes."""

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        profile = getattr(request.user, "profile", None)
        return (
            request.user.is_authenticated
            and getattr(profile, "type", None) == "business"
        )


class IsOfferOwnerOrReadOnly(BasePermission):
    """Restrict offer changes to the authenticated owner."""

    def has_object_permission(self, request, view, obj):
        return request.method in SAFE_METHODS or obj.user_id == request.user.pk
