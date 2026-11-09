from rest_framework.generics import (
    ListCreateAPIView,
    RetrieveUpdateDestroyAPIView,
    RetrieveAPIView,
)

from offers_app.api.permissions import IsBusinessOrReadOnly
from offers_app.api.serializers import OfferSerializer
from offers_app.models import Offer


class OfferListCreateView(ListCreateAPIView):
    """Allow public reads and business-only offer creation."""

    queryset = Offer.objects.all()
    serializer_class = OfferSerializer
    permission_classes = [IsBusinessOrReadOnly]


class OfferDetailView(RetrieveUpdateDestroyAPIView):
    http_method_names = ['get', 'patch', 'delete', 'options']


class OfferPackageDetailView(RetrieveAPIView):
    pass
