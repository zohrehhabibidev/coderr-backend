from collections.abc import Mapping
from copy import deepcopy

from django.shortcuts import get_object_or_404
from rest_framework import serializers

from offers_app.models import OfferDetail
from orders_app.models import Order


class OrderCreateSerializer(serializers.ModelSerializer):
    offer_detail_id = serializers.IntegerField(write_only=True, min_value=1)

    class Meta:
        model = Order
        fields = [
            "id", "customer_user", "business_user", "title", "revisions",
            "delivery_time_in_days", "price", "features", "offer_type",
            "status", "created_at", "updated_at", "offer_detail_id",
        ]
        read_only_fields = fields[:-1]
        extra_kwargs = {"price": {"coerce_to_string": False}}

    def to_internal_value(self, data):
        if isinstance(data, Mapping):
            invalid = set(data) - {"offer_detail_id"}
            if invalid:
                raise serializers.ValidationError({
                    name: "This field cannot be supplied." for name in invalid
                })
        return super().to_internal_value(data)

    def validate_offer_detail_id(self, value):
        return get_object_or_404(
            OfferDetail.objects.select_related("offer__user"), pk=value,
        )

    def create(self, validated_data):
        detail = validated_data["offer_detail_id"]
        return Order.objects.create(
            customer_user=self.context["request"].user,
            business_user=detail.offer.user,
            offer_detail=detail,
            title=detail.title,
            revisions=detail.revisions,
            delivery_time_in_days=detail.delivery_time_in_days,
            price=detail.price,
            features=deepcopy(detail.features),
            offer_type=detail.offer_type,
            status=Order.OrderStatus.IN_PROGRESS,
        )


class OrderUpdateSerializer(serializers.ModelSerializer):
    """Update only status and return the complete order snapshot."""

    status = serializers.ChoiceField(choices=Order.OrderStatus.choices)

    class Meta:
        model = Order
        fields = [
            "id", "customer_user", "business_user", "title", "revisions",
            "delivery_time_in_days", "price", "features", "offer_type",
            "status", "created_at", "updated_at",
        ]
        read_only_fields = [field for field in fields if field != "status"]
        extra_kwargs = {"price": {"coerce_to_string": False}}

    def to_internal_value(self, data):
        if isinstance(data, Mapping):
            if "status" not in data:
                raise serializers.ValidationError({
                    "status": "This field is required."
                })
            invalid = set(data) - {"status"}
            if invalid:
                raise serializers.ValidationError({
                    name: "This field cannot be updated." for name in invalid
                })
        return super().to_internal_value(data)

    def update(self, instance, validated_data):
        instance.status = validated_data.get("status", instance.status)
        instance.save(update_fields=["status", "updated_at"])
        return instance
