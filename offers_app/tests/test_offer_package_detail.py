from decimal import Decimal

from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from auth_app.models import Profile
from offers_app.models import Offer, OfferDetail


class OfferPackageDetailTests(APITestCase):
    """Exercise Card 24 with persisted packages and tokens."""

    def setUp(self):
        super().setUp()
        self.owner = self.make_user("owner", "business")
        self.offer = Offer.objects.create(
            user=self.owner, title="Design", description="Design packages",
        )
        self.details = [self.make_detail(kind, index) for index, kind in
                        enumerate(("basic", "standard", "premium"))]
        self.authenticate(self.owner)

    def make_user(self, name, role=None, staff=False):
        user = User.objects.create_user(username=name, is_staff=staff)
        if role:
            Profile.objects.create(user=user, type=role)
        return user

    def authenticate(self, user):
        token, _ = Token.objects.get_or_create(user=user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

    def make_detail(self, kind, index):
        return OfferDetail.objects.create(
            offer=self.offer, offer_type=kind, title=f"{kind} design",
            revisions=index, delivery_time_in_days=index + 1,
            price=Decimal("100.25") + index * 100,
            features=[] if index == 0 else ["Logo", "Source files"],
        )

    def detail_url(self, pk):
        return reverse("offer-package-detail", args=[pk])

    def expected_detail(self, detail):
        return {
            "id": detail.pk, "title": detail.title,
            "revisions": detail.revisions,
            "delivery_time_in_days": detail.delivery_time_in_days,
            "price": float(detail.price), "features": detail.features,
            "offer_type": detail.offer_type,
        }

    def assert_types(self, data):
        for field in ("id", "revisions", "delivery_time_in_days"):
            self.assertIs(type(data[field]), int)
        for field in ("title", "offer_type"):
            self.assertIsInstance(data[field], str)
        self.assertIn(type(data["price"]), (int, float))
        self.assertIsInstance(data["features"], list)
        for feature in data["features"]:
            self.assertIsInstance(feature, str)

    def assert_retrieved(self, detail):
        response = self.client.get(self.detail_url(detail.pk))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, dict)
        expected = self.expected_detail(detail)
        self.assertEqual(set(data), set(expected))
        self.assertEqual(data, expected)
        self.assert_types(data)
        self.assertEqual(Decimal(str(data["price"])), detail.price)
        return data

    def snapshot(self):
        return [list(model.objects.order_by("pk").values())
                for model in (Offer, OfferDetail, User, Profile, Token)]

    def assert_error(self, status, code, pk=None):
        before = self.snapshot()
        pk = self.details[0].pk if pk is None else pk
        response = self.client.get(self.detail_url(pk))
        self.assertEqual(response.status_code, status)
        data = response.json()
        self.assertIsInstance(data, dict)
        self.assertEqual(set(data), {"detail"})
        self.assertIsInstance(data["detail"], str)
        self.assertTrue(data["detail"])
        self.assertEqual(response.data["detail"].code, code)
        self.assertEqual(self.snapshot(), before)

    def test_all_package_types_have_exact_schema_types_and_values(self):
        for detail in self.details:
            with self.subTest(offer_type=detail.offer_type):
                self.assert_retrieved(detail)

    def test_zero_revisions_and_empty_features_are_preserved(self):
        data = self.assert_retrieved(self.details[0])
        self.assertEqual(data["revisions"], 0)
        self.assertEqual(data["features"], [])

    def test_unicode_and_ordered_nonempty_features_are_preserved(self):
        detail = self.details[1]
        detail.title = "طراحی لوگو"
        detail.features = ["چاپ", "Source files", "چاپ"]
        detail.save()
        data = self.assert_retrieved(detail)
        self.assertEqual(data["features"], ["چاپ", "Source files", "چاپ"])

    def test_decimal_prices_preserve_zero_cents_and_maximum_precision(self):
        detail = self.details[0]
        for price in ("0.00", "0.01", "100.00", "99999999.99"):
            with self.subTest(price=price):
                detail.price = Decimal(price)
                detail.save()
                self.assert_retrieved(detail)

    def test_customer_can_retrieve_every_package(self):
        self.authenticate(self.make_user("customer", "customer"))
        for detail in self.details:
            with self.subTest(pk=detail.pk):
                self.assert_retrieved(detail)

    def test_business_owner_can_retrieve_every_package(self):
        for detail in self.details:
            with self.subTest(pk=detail.pk):
                self.assert_retrieved(detail)

    def test_nonowner_business_can_retrieve_every_package(self):
        self.authenticate(self.make_user("other", "business"))
        for detail in self.details:
            with self.subTest(pk=detail.pk):
                self.assert_retrieved(detail)

    def test_staff_without_profile_can_retrieve_every_package(self):
        self.authenticate(self.make_user("staff", staff=True))
        for detail in self.details:
            with self.subTest(pk=detail.pk):
                self.assert_retrieved(detail)

    def test_requested_detail_id_is_independent_of_parent_offer_id(self):
        other = Offer.objects.create(
            user=self.make_user("other", "business"),
            title="Other offer", description="Other owner's package",
        )
        detail = OfferDetail.objects.create(
            offer=other, offer_type="basic", title="Distinct package",
            revisions=7, delivery_time_in_days=30, price=Decimal("7.75"),
            features=["Other package"],
        )
        self.assertNotEqual(detail.pk, other.pk)
        for target in (detail, self.details[1], self.details[0]):
            self.assert_retrieved(target)

    def test_repeated_gets_do_not_modify_database(self):
        before = self.snapshot()
        for detail in self.details:
            self.assert_retrieved(detail)
            self.assert_retrieved(detail)
        self.assertEqual(self.snapshot(), before)

    def test_anonymous_request_returns_401(self):
        self.client.credentials()
        self.assert_error(401, "not_authenticated")

    def test_token_without_key_returns_401(self):
        self.client.credentials(HTTP_AUTHORIZATION="Token")
        self.assert_error(401, "authentication_failed")

    def test_invalid_token_returns_401(self):
        self.client.credentials(HTTP_AUTHORIZATION="Token invalid")
        self.assert_error(401, "authentication_failed")

    def test_nonexistent_detail_returns_404(self):
        missing_id = max(detail.pk for detail in self.details) + 1000
        self.assertFalse(OfferDetail.objects.filter(pk=missing_id).exists())
        self.assert_error(404, "not_found", missing_id)

    def test_deleted_detail_returns_404_while_parent_still_exists(self):
        detail = self.details[0]
        pk = detail.pk
        detail.delete()
        self.assertTrue(Offer.objects.filter(pk=self.offer.pk).exists())
        self.assert_error(404, "not_found", pk)
