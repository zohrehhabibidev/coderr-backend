from rest_framework.generics import (
    ListCreateAPIView,
    RetrieveUpdateDestroyAPIView,
)
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from reviews_app.api.permissions import IsCustomer, IsReviewOwner
from reviews_app.api.serializers import (
    ReviewCreateSerializer,
    ReviewListQuerySerializer,
    ReviewUpdateSerializer,
)
from reviews_app.models import Review


class ReviewListCreateView(ListCreateAPIView):
    serializer_class = ReviewCreateSerializer
    permission_classes = [IsAuthenticated, IsCustomer]
    http_method_names = ["get", "post", "options"]
    pagination_class = None

    def get_permissions(self):
        if self.request.method == "GET":
            return [IsAuthenticated()]
        return super().get_permissions()

    def get_queryset(self):
        params = self.request.query_params.dict()
        query = ReviewListQuerySerializer(data=params)
        query.is_valid(raise_exception=True)
        values = query.validated_data
        filters = {
            field: values[field]
            for field in ("business_user_id", "reviewer_id")
            if field in values
        }
        queryset = Review.objects.filter(**filters)
        if "ordering" in values:
            return queryset.order_by(values["ordering"])
        return queryset


class ReviewDetailView(RetrieveUpdateDestroyAPIView):
    """Allow authenticated reviewers to update or delete their reviews."""

    queryset = Review.objects.all()
    serializer_class = ReviewUpdateSerializer
    permission_classes = [IsAuthenticated, IsReviewOwner]
    http_method_names = ["patch", "delete", "options"]


class BaseInfoView(APIView):
    pass
