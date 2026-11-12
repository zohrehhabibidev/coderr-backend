from django.db import IntegrityError, transaction
from rest_framework import serializers

from reviews_app.models import Review


class ReviewCreateSerializer(serializers.ModelSerializer):
    """Create a review with the authenticated customer as reviewer."""

    class Meta:
        model = Review
        fields = [
            "id", "business_user", "reviewer", "rating", "description",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "reviewer", "created_at", "updated_at"]
        validators = []
        extra_kwargs = {"rating": {"min_value": 1, "max_value": 5}}

    def validate_business_user(self, value):
        profile = getattr(value, "profile", None)
        if getattr(profile, "type", None) != "business":
            raise serializers.ValidationError(
                "The target user must have a business profile."
            )
        self.validate_unique_pair(value)
        return value

    def validate_unique_pair(self, business_user):
        if Review.objects.filter(
            reviewer=self.context["request"].user,
            business_user=business_user,
        ).exists():
            raise serializers.ValidationError(
                "You have already reviewed this business user."
            )

    def create(self, validated_data):
        validated_data["reviewer"] = self.context["request"].user
        try:
            with transaction.atomic():
                return super().create(validated_data)
        except IntegrityError as error:
            duplicate = (
                "UNIQUE constraint failed: reviews_app_review.reviewer_id, "
                "reviews_app_review.business_user_id"
            )
            if str(error) != duplicate:
                raise
            message = "You have already reviewed this business user."
            raise serializers.ValidationError(message) from error
