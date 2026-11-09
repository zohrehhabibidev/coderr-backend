from django.db import transaction
from rest_framework import serializers

from offers_app.models import Offer, OfferDetail


class OfferDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = OfferDetail
        extra_kwargs = {"price": {"coerce_to_string": False}}
        fields = [
            "id",
            "title",
            "revisions",
            "delivery_time_in_days",
            "price",
            "features",
            "offer_type",
        ]


class OfferSerializer(serializers.ModelSerializer):
    details = OfferDetailSerializer(many=True)

    class Meta:
        model = Offer
        fields = [
            "id",
            "title",
            "image",
            "description",
            "details",
        ]

    def validate_details(self, value):
        if len(value) != 3:
            raise serializers.ValidationError(
                "An offer must contain exactly three details."
            )
        offer_types = {detail["offer_type"] for detail in value}
        if offer_types != {"basic", "standard", "premium"}:
            raise serializers.ValidationError(
                "Details must include basic, standard and premium."
            )
        return value

    @transaction.atomic
    def create(self, validated_data):
        details_data = validated_data.pop("details")
        offer = Offer.objects.create(
            user=self.context["request"].user,
            **validated_data,
        )
        for detail_data in details_data:
            OfferDetail.objects.create(
                offer=offer,
                **detail_data,
            )
        return offer
