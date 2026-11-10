from django.db.models import Min
from rest_framework.filters import SearchFilter
from rest_framework.generics import (
    ListCreateAPIView,
    RetrieveAPIView,
    RetrieveUpdateAPIView,
)
from rest_framework.permissions import IsAuthenticated

from offers_app.api.filters import OfferListFilter
from offers_app.api.pagination import OfferPagination
from offers_app.api.permissions import (
    IsBusinessOrReadOnly,
    IsOfferOwnerOrReadOnly,
)
from offers_app.api.serializers import (
    OfferDetailSerializer,
    OfferListSerializer,
    OfferRetrieveSerializer,
    OfferSerializer,
    OfferUpdateSerializer,
)
from offers_app.models import Offer, OfferDetail


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


class OfferDetailView(RetrieveUpdateAPIView):
    """Allow authenticated retrieval and owner-only partial updates."""

    queryset = Offer.objects.prefetch_related("details").annotate(
        min_price=Min("details__price"),
        min_delivery_time=Min("details__delivery_time_in_days"),
    )
    serializer_class = OfferRetrieveSerializer
    permission_classes = [IsAuthenticated, IsOfferOwnerOrReadOnly]
    http_method_names = ["get", "patch", "options"]

    def get_serializer_class(self):
        if self.request.method == "PATCH":
            return OfferUpdateSerializer
        return self.serializer_class


class OfferPackageDetailView(RetrieveAPIView):
    queryset = OfferDetail.objects.all()
    serializer_class = OfferDetailSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "options"]
