from django.db.models import Min
from rest_framework.filters import SearchFilter
from rest_framework.generics import (
    ListCreateAPIView,
    RetrieveUpdateDestroyAPIView,
    RetrieveAPIView,
)

from offers_app.api.filters import OfferListFilter
from offers_app.api.pagination import OfferPagination
from offers_app.api.permissions import IsBusinessOrReadOnly
from offers_app.api.serializers import OfferListSerializer, OfferSerializer
from offers_app.models import Offer


class OfferListCreateView(ListCreateAPIView):
    """Allow public reads and business-only offer creation."""

    queryset = Offer.objects.all()
    serializer_class = OfferSerializer
    permission_classes = [IsBusinessOrReadOnly]
    pagination_class = OfferPagination
    filter_backends = [OfferListFilter, SearchFilter]
    search_fields = ["title", "description"]

    def get_serializer_class(self):
        if self.request.method in ("GET", "HEAD"):
            return OfferListSerializer
        return self.serializer_class

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.request.method not in ("GET", "HEAD"):
            return queryset
        queryset = queryset.select_related("user").prefetch_related("details")
        return queryset.annotate(
            min_price=Min("details__price"),
            min_delivery_time=Min("details__delivery_time_in_days"),
        )


class OfferDetailView(RetrieveUpdateDestroyAPIView):
    http_method_names = ['get', 'patch', 'delete', 'options']


class OfferPackageDetailView(RetrieveAPIView):
    pass
