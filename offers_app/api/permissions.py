from rest_framework.permissions import SAFE_METHODS, BasePermission


class IsBusinessOrReadOnly(BasePermission):
    """Allow reads publicly and writes only for authenticated businesses."""

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        profile = getattr(request.user, "profile", None)
        return (
            request.user.is_authenticated
            and getattr(profile, "type", None) == "business"
        )
