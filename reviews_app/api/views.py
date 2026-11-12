from rest_framework.generics import (
    ListCreateAPIView,
    RetrieveUpdateDestroyAPIView,
)
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from reviews_app.api.permissions import IsCustomer
from reviews_app.api.serializers import ReviewCreateSerializer


class ReviewListCreateView(ListCreateAPIView):
    serializer_class = ReviewCreateSerializer
    permission_classes = [IsAuthenticated, IsCustomer]
    http_method_names = ["post", "options"]


class ReviewDetailView(RetrieveUpdateDestroyAPIView):
    http_method_names = ['patch', 'delete', 'options']


class BaseInfoView(APIView):
    pass
