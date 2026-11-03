from rest_framework.generics import (
    ListCreateAPIView,
    RetrieveUpdateDestroyAPIView,
)
from rest_framework.views import APIView


class OrderListCreateView(ListCreateAPIView):
    pass


class OrderDetailView(RetrieveUpdateDestroyAPIView):
    http_method_names = ['patch', 'delete', 'options']


class OrderCountView(APIView):
    pass


class CompletedOrderCountView(APIView):
    pass
