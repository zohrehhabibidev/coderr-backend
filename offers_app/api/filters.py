from rest_framework.filters import BaseFilterBackend

from offers_app.api.serializers import OfferListQuerySerializer


class OfferListFilter(BaseFilterBackend):
    """Apply validated filters to the minimum package annotations."""

    lookups = {
        "creator_id": "user_id",
        "min_price": "min_price__gte",
        "max_delivery_time": "min_delivery_time__lte",
    }

    def filter_queryset(self, request, queryset, view):
        query = OfferListQuerySerializer(data=request.query_params.dict())
        query.is_valid(raise_exception=True)
        values = query.validated_data
        filters = {
            lookup: values[param] for param, lookup in self.lookups.items()
            if param in values
        }
        return queryset.filter(**filters).order_by(values["ordering"], "pk")
