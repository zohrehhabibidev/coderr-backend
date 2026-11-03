from rest_framework.generics import (
    ListCreateAPIView,
    RetrieveUpdateDestroyAPIView,
    RetrieveAPIView,
)


class OfferListCreateView(ListCreateAPIView):
    pass


class OfferDetailView(RetrieveUpdateDestroyAPIView):
    http_method_names = ['get', 'patch', 'delete', 'options']


class OfferPackageDetailView(RetrieveAPIView):
    pass
