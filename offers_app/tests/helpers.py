"""Shared fixture and authentication helpers for offer and order tests."""

from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token

from auth_app.models import Profile
from offers_app.models import Offer, OfferDetail
from orders_app.models import Order


class OfferTestHelpers:
    """Provide users, offers, orders, snapshots and token authentication."""

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

    def make_order(self, detail, state="completed"):
        return Order.objects.create(
            customer_user=self.customer,
            business_user=detail.offer.user if detail else self.owner,
            offer_detail=detail, title="Original purchased title",
            offer_type=detail.offer_type if detail else "basic",
            price=Decimal("49.75"), revisions=7,
            delivery_time_in_days=12, features=["Original", "Stored feature"],
            status=state,
        )

    def snapshot(self):
        return [list(model.objects.order_by("pk").values())
                for model in (Offer, OfferDetail, User, Profile, Token, Order)]
