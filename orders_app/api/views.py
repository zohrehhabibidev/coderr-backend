from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework.generics import (
    ListCreateAPIView,
    RetrieveUpdateDestroyAPIView,
)
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from auth_app.models import Profile
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
    """Allow business owners to update status and staff to delete orders."""

    queryset = Order.objects.all()
    serializer_class = OrderUpdateSerializer
    permission_classes = [IsAuthenticated, IsBusiness, IsOrderBusinessOwner]
    http_method_names = ["patch", "delete", "options"]

    def get_permissions(self):
        if self.request.method == "DELETE":
            return [IsAuthenticated(), IsAdminUser()]
        return super().get_permissions()


class OrderCountView(APIView):
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "options"]

    def get(self, request, business_user_id):
        get_object_or_404(
            Profile,
            user_id=business_user_id,
            type=Profile.UserType.BUSINESS,
        )
        order_count = Order.objects.filter(
            business_user_id=business_user_id,
            status=Order.OrderStatus.IN_PROGRESS,
        ).count()
        return Response({"order_count": order_count})


class CompletedOrderCountView(APIView):
    pass
