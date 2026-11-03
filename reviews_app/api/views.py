from rest_framework.generics import (
    ListCreateAPIView,
    RetrieveUpdateDestroyAPIView,
)
from rest_framework.views import APIView


class ReviewListCreateView(ListCreateAPIView):
    pass


class ReviewDetailView(RetrieveUpdateDestroyAPIView):
    http_method_names = ['patch', 'delete', 'options']


class BaseInfoView(APIView):
    pass
