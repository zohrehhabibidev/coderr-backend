from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.db import transaction
from rest_framework import serializers
from rest_framework.authtoken.models import Token

from auth_app.models import Profile


class RegistrationSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(
        required=True, allow_blank=False, max_length=254
    )
    repeated_password = serializers.CharField(write_only=True)
    type = serializers.ChoiceField(
        choices=["customer", "business"],
        write_only=True,
    )
    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = [
            "username",
            "email",
            "password",
            "repeated_password",
            "type",
        ]

    def validate(self, attrs):
        if attrs["password"] != attrs["repeated_password"]:
            raise serializers.ValidationError(
                {"repeated_password": "Passwords do not match."}
            )
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        user_type = validated_data.pop("type")
        validated_data.pop("repeated_password")
        user = User.objects.create_user(**validated_data)
        Profile.objects.create(user=user, type=user_type)
        Token.objects.create(user=user)
        return user


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        user = authenticate(
            username=attrs["username"],
            password=attrs["password"],
        )
        if user is None:
            raise serializers.ValidationError("Invalid username or password.")
        attrs["user"] = user
        return attrs


class ProfileSerializer(serializers.ModelSerializer):
    """Profile details with partial updates to the related account."""

    username = serializers.CharField(source="user.username", read_only=True)
    first_name = serializers.CharField(
        source="user.first_name", required=False,
        allow_blank=True, max_length=150
    )
    last_name = serializers.CharField(
        source="user.last_name", required=False,
        allow_blank=True, max_length=150
    )
    email = serializers.EmailField(
        source="user.email", required=False, allow_blank=True, max_length=254
    )
    created_at = serializers.DateTimeField(
        source="user.date_joined", read_only=True
    )

    class Meta:
        model = Profile
        fields = [
            "user", "username", "first_name", "last_name", "file",
            "location", "tel", "description", "working_hours", "type",
            "email", "created_at",
        ]
        read_only_fields = ["user", "username", "type", "created_at"]

    @transaction.atomic
    def update(self, instance, validated_data):
        # Email remains writable pending the A2 teacher/contract clarification.
        user_data = validated_data.pop("user", {})
        for field, value in user_data.items():
            setattr(instance.user, field, value)
        if user_data:
            instance.user.save(update_fields=list(user_data))
        return super().update(instance, validated_data)


class BusinessProfileSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    first_name = serializers.CharField(source="user.first_name", read_only=True)
    last_name = serializers.CharField(source="user.last_name", read_only=True)

    class Meta:
        model = Profile
        fields = [
            "user", "username", "first_name", "last_name", "file",
            "location", "tel", "description", "working_hours", "type",
        ]
