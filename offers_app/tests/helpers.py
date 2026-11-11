"""Shared fixture and authentication helpers for offer API tests."""

from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token

from auth_app.models import Profile
from offers_app.models import Offer, OfferDetail


class OfferTestHelpers:
    """Provide users, three-package offers and real token authentication."""

    def make_user(self, name, role=None, staff=False):
        user = User.objects.create_user(username=name, is_staff=staff)
        if role:
            Profile.objects.create(user=user, type=role)
        return user

    def authenticate(self, user):
        token, _ = Token.objects.get_or_create(user=user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

    def make_offer(self, owner, price=Decimal("100.25"), days=3):
        offer = Offer.objects.create(
            user=owner, title="Design package", description="Logo and print",
        )
        for index, kind in enumerate(("basic", "standard", "premium")):
            OfferDetail.objects.create(
                offer=offer, offer_type=kind, title=kind, revisions=2,
                price=price + index * 10,
                delivery_time_in_days=days + 2 - index,
                features=["Logo", "Source files"],
            )
        return offer
