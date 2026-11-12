from collections.abc import Mapping

from django.contrib.auth import get_user_model
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

    def validate_features(self, value):
        if not isinstance(value, list) or any(
            not isinstance(feature, str) for feature in value
        ):
            raise serializers.ValidationError("Expected a list of strings.")
        return value


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


class StrictUpdateFieldsMixin:
    """Reject fields outside the explicitly writable PATCH contract."""

    def to_internal_value(self, data):
        if isinstance(data, Mapping):
            writable = {
                name for name, field in self.fields.items() if not field.read_only
            }
            invalid = set(data) - writable
            if invalid:
                raise serializers.ValidationError({
                    name: "This field cannot be updated." for name in invalid
                })
        return super().to_internal_value(data)


class OfferDetailUpdateSerializer(
    StrictUpdateFieldsMixin, OfferDetailSerializer
):
    def validate(self, attrs):
        if "offer_type" not in attrs:
            raise serializers.ValidationError({
                "offer_type": "This field is required."
            })
        return attrs


class OfferUpdateSerializer(StrictUpdateFieldsMixin, OfferSerializer):
    details = OfferDetailUpdateSerializer(many=True)

    def validate_details(self, value):
        offer_types = [detail["offer_type"] for detail in value]
        existing = {detail.offer_type for detail in self.instance.details.all()}
        if len(offer_types) != len(set(offer_types)):
            raise serializers.ValidationError("Duplicate offer_type values.")
        if set(offer_types) - existing:
            raise serializers.ValidationError("Unknown offer_type values.")
        return value

    @transaction.atomic
    def update(self, instance, validated_data):
        details_data = validated_data.pop("details", [])
        self.update_details(instance, details_data)
        return super().update(instance, validated_data)

    def update_details(self, instance, details_data):
        existing = {detail.offer_type: detail for detail in instance.details.all()}
        serializer = self.fields["details"].child
        for detail_data in details_data:
            detail = existing[detail_data.pop("offer_type")]
            serializer.update(detail, detail_data)


class OfferDetailLinkSerializer(serializers.ModelSerializer):
    """Match the relative detail links in the list contract (A5)."""

    url = serializers.SerializerMethodField()

    class Meta:
        model = OfferDetail
        fields = ["id", "url"]

    def get_url(self, obj):
        return f"/offerdetails/{obj.pk}/"


class OfferUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = get_user_model()
        fields = ["first_name", "last_name", "username"]


class OfferListSerializer(serializers.ModelSerializer):
    """Serialize list annotations without changing the create contract."""

    details = OfferDetailLinkSerializer(many=True, read_only=True)
    min_price = serializers.DecimalField(
        max_digits=10, decimal_places=2,
        coerce_to_string=False, read_only=True,
    )
    min_delivery_time = serializers.IntegerField(read_only=True)
    user_details = OfferUserSerializer(source="user", read_only=True)

    class Meta:
        model = Offer
        fields = [
            "id", "user", "title", "image", "description", "created_at",
            "updated_at", "details", "min_price", "min_delivery_time",
            "user_details",
        ]


class OfferRetrieveDetailLinkSerializer(OfferDetailLinkSerializer):
    """Use request-based absolute package URLs for offer retrieval (A5)."""

    url = serializers.HyperlinkedIdentityField(
        view_name="offer-package-detail",
    )


class OfferRetrieveSerializer(serializers.ModelSerializer):
    """Represent one offer with package links and annotated minimum values."""

    details = OfferRetrieveDetailLinkSerializer(many=True, read_only=True)
    min_price = serializers.DecimalField(
        max_digits=10, decimal_places=2,
        coerce_to_string=False, read_only=True,
    )
    min_delivery_time = serializers.IntegerField(read_only=True)

    class Meta:
        model = Offer
        fields = [
            "id", "user", "title", "image", "description", "created_at",
            "updated_at", "details", "min_price", "min_delivery_time",
        ]


class OfferListQuerySerializer(serializers.Serializer):
    """Validate known parameters; extra query keys remain ignored."""

    creator_id = serializers.IntegerField(required=False)
    min_price = serializers.FloatField(required=False)
    max_delivery_time = serializers.IntegerField(required=False)
    ordering = serializers.ChoiceField(
        choices=["updated_at", "-updated_at", "min_price", "-min_price"],
        default="-updated_at",
    )
    page_size = serializers.IntegerField(required=False, min_value=1)
