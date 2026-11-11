from rest_framework.generics import (
    ListCreateAPIView,
    RetrieveUpdateDestroyAPIView,
)
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from orders_app.api.permissions import IsCustomer
from orders_app.api.serializers import OrderCreateSerializer


class OrderListCreateView(ListCreateAPIView):
    serializer_class = OrderCreateSerializer
    permission_classes = [IsAuthenticated, IsCustomer]
    http_method_names = ["post", "options"]


class OrderDetailView(RetrieveUpdateDestroyAPIView):
    http_method_names = ['patch', 'delete', 'options']


class OrderCountView(APIView):
    pass


class CompletedOrderCountView(APIView):
    pass
