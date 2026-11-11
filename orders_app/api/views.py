from django.db.models import Q
from rest_framework.generics import (
    ListCreateAPIView,
    RetrieveUpdateDestroyAPIView,
)
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from orders_app.api.permissions import (
    IsBusiness,
    IsCustomer,
    IsOrderBusinessOwner,
)
from orders_app.api.serializers import (
    OrderCreateSerializer,
    OrderUpdateSerializer,
)
from orders_app.models import Order


class OrderListCreateView(ListCreateAPIView):
    serializer_class = OrderCreateSerializer
    permission_classes = [IsAuthenticated, IsCustomer]
    http_method_names = ["get", "post", "options"]
    pagination_class = None

    def get_permissions(self):
        if self.request.method == "GET":
            return [IsAuthenticated()]
        return super().get_permissions()

    def get_queryset(self):
        user = self.request.user
        return Order.objects.filter(
            Q(customer_user=user) | Q(business_user=user)
        )


class OrderDetailView(RetrieveUpdateDestroyAPIView):
    """Allow assigned businesses to update status; defer DELETE to Card 30."""

    queryset = Order.objects.all()
    serializer_class = OrderUpdateSerializer
    permission_classes = [IsAuthenticated, IsBusiness, IsOrderBusinessOwner]
    http_method_names = ["patch", "options"]


class OrderCountView(APIView):
    pass


class CompletedOrderCountView(APIView):
    pass
