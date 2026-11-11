from datetime import datetime, timedelta, timezone
from decimal import Decimal
from urllib.parse import urlparse

from django.contrib.auth.models import User
from django.urls import resolve, reverse
from django.utils.dateparse import parse_datetime
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from auth_app.models import Profile
from offers_app.models import Offer, OfferDetail
from offers_app.tests.helpers import OfferTestHelpers


class OfferRetrieveTests(OfferTestHelpers, APITestCase):
    """Verify Card 23 through HTTP with persisted offers and real tokens."""

    def setUp(self):
        super().setUp()
        self.owner = self.make_user("owner", "business")
        self.offer = self.make_offer(self.owner)
        self.url = reverse("offer-detail", args=[self.offer.pk])
        self.authenticate(self.owner)

    def get_offer(self, url=None, **kwargs):
        response = self.client.get(url or self.url, **kwargs)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, dict)
        return data

    def expected_offer(self):
        offer = self.offer
        return {
            "id": offer.pk, "user": offer.user_id, "title": offer.title,
            "image": None, "description": offer.description,
            "created_at": offer.created_at.isoformat().replace("+00:00", "Z"),
            "updated_at": offer.updated_at.isoformat().replace("+00:00", "Z"),
            "details": [{"id": detail.pk, "url": "http://testserver" +
                         reverse("offer-package-detail", args=[detail.pk])}
                        for detail in offer.details.order_by("pk")],
            "min_price": 100.25, "min_delivery_time": 3,
        }

    def test_success_has_exact_documented_schema_and_values(self):
        data = self.get_offer()
        expected = self.expected_offer()
        self.assertEqual(set(data), set(expected))
        for row in (data, expected):
            row["details"] = sorted(
                row["details"], key=lambda item: item["id"],
            )
        self.assertEqual(data, expected)

    def test_response_field_types(self):
        data = self.get_offer()
        for key in ("id", "user", "min_delivery_time"):
            self.assertIs(type(data[key]), int)
        for key in ("title", "description", "created_at", "updated_at"):
            self.assertIsInstance(data[key], str)
        self.assertIn(type(data["min_price"]), (int, float))
        self.assertIsNone(data["image"])
        self.assertIsInstance(data["details"], list)

    def test_package_links_have_exact_schema_and_persisted_ids(self):
        details = self.get_offer()["details"]
        self.assertEqual(len(details), 3)
        self.assertEqual({item["id"] for item in details},
                         set(self.offer.details.values_list("pk", flat=True)))
        for item in details:
            self.assertIsInstance(item, dict)
            self.assertEqual(set(item), {"id", "url"})
            self.assertIs(type(item["id"]), int)
            self.assertIsInstance(item["url"], str)
            self.assert_package_url(item, "http", "testserver")

    def assert_package_url(self, item, scheme, host):
        parsed = urlparse(item["url"])
        path = reverse("offer-package-detail", args=[item["id"]])
        self.assertEqual(path, f"/api/offerdetails/{item['id']}/")
        self.assertEqual((parsed.scheme, parsed.netloc, parsed.path),
                         (scheme, host, path))
        self.assertEqual((parsed.query, parsed.fragment), ("", ""))
        match = resolve(parsed.path)
        self.assertEqual(match.url_name, "offer-package-detail")
        self.assertEqual(match.kwargs, {"pk": item["id"]})

    def test_package_links_use_custom_request_host_and_scheme(self):
        with self.settings(ALLOWED_HOSTS=["offers.example.test"]):
            data = self.get_offer(
                HTTP_HOST="offers.example.test:8443", secure=True,
            )
        for item in data["details"]:
            self.assert_package_url(item, "https", "offers.example.test:8443")

    def test_distinct_timestamps_match_persisted_instants(self):
        created = datetime(2026, 1, 2, 10, 30, tzinfo=timezone.utc)
        updated = created + timedelta(days=2, microseconds=123456)
        Offer.objects.filter(pk=self.offer.pk).update(
            created_at=created, updated_at=updated,
        )
        data = self.get_offer()
        for key, value in (("created_at", created), ("updated_at", updated)):
            self.assertEqual(parse_datetime(data[key]), value)
            expected = value.isoformat().replace("+00:00", "Z")
            self.assertEqual(data[key], expected)

    def test_null_and_empty_image_are_json_null(self):
        for value in (None, ""):
            with self.subTest(image=value):
                Offer.objects.filter(pk=self.offer.pk).update(image=value)
                self.assertIsNone(self.get_offer()["image"])

    def test_decimal_minima_come_from_different_packages(self):
        data = self.get_offer()
        basic = self.offer.details.get(offer_type="basic")
        premium = self.offer.details.get(offer_type="premium")
        self.assertEqual(basic.price, Decimal("100.25"))
        self.assertEqual(premium.delivery_time_in_days, 3)
        self.assertGreater(basic.delivery_time_in_days, 3)
        self.assertGreater(premium.price, basic.price)
        self.assertIn(type(data["min_price"]), (int, float))
        self.assertEqual(Decimal(str(data["min_price"])), basic.price)
        self.assertEqual(data["min_delivery_time"], 3)

    def test_related_updates_change_subsequent_minima(self):
        before = self.get_offer()
        self.offer.details.filter(offer_type="standard").update(
            price=Decimal("25.50"), delivery_time_in_days=1,
        )
        after = self.get_offer()
        self.assertEqual((before["min_price"], before["min_delivery_time"]),
                         (100.25, 3))
        self.assertEqual((after["min_price"], after["min_delivery_time"]),
                         (25.5, 1))

    def test_requested_offer_isolated_from_other_owner_and_packages(self):
        other = self.make_user("other", "business")
        offer = self.make_offer(other, Decimal("1.75"), 1)
        first = self.get_offer()
        second = self.get_offer(reverse("offer-detail", args=[offer.pk]))
        self.assertEqual((first["id"], first["user"], first["min_price"],
                          first["min_delivery_time"]),
                         (self.offer.pk, self.owner.pk, 100.25, 3))
        self.assertEqual((second["id"], second["user"], second["min_price"],
                          second["min_delivery_time"]),
                         (offer.pk, other.pk, 1.75, 1))
        self.assertEqual({item["id"] for item in second["details"]},
                         set(offer.details.values_list("pk", flat=True)))

    def snapshot(self):
        return [list(model.objects.order_by("pk").values())
                for model in (Offer, OfferDetail, User, Profile, Token)]

    def test_successful_get_does_not_modify_records(self):
        before = self.snapshot()
        self.get_offer()
        self.assertEqual(self.snapshot(), before)

    def assert_error(self, status, code, url=None):
        before = self.snapshot()
        response = self.client.get(url or self.url)
        self.assertEqual(response.status_code, status)
        data = response.json()
        self.assertIsInstance(data, dict)
        self.assertEqual(set(data), {"detail"})
        self.assertIsInstance(data["detail"], str)
        self.assertTrue(data["detail"])
        self.assertEqual(response.data["detail"].code, code)
        self.assertEqual(self.snapshot(), before)

    def test_anonymous_request_returns_401(self):
        self.client.credentials()
        self.assert_error(401, "not_authenticated")

    def test_invalid_token_returns_401(self):
        self.client.credentials(HTTP_AUTHORIZATION="Token invalid")
        self.assert_error(401, "authentication_failed")

    def test_customer_other_business_and_staff_can_retrieve(self):
        for role, staff in (("customer", False), ("business", False),
                            ("customer", True), ("business", True)):
            with self.subTest(role=role, staff=staff):
                user = self.make_user(f"{role}-{staff}", role, staff)
                self.authenticate(user)
                self.assertNotEqual(user.pk, self.offer.user_id)
                data = self.get_offer()
                self.assertEqual(data["id"], self.offer.pk)
                self.assertEqual(data["user"], self.owner.pk)

    def test_staff_without_profile_can_retrieve(self):
        user = self.make_user("staff", staff=True)
        self.assertFalse(Profile.objects.filter(user=user).exists())
        self.authenticate(user)
        self.assertEqual(self.get_offer()["id"], self.offer.pk)

    def test_authenticated_user_without_profile_can_retrieve(self):
        user = self.make_user("no-profile")
        self.authenticate(user)
        self.assertEqual(self.get_offer()["id"], self.offer.pk)

    def test_missing_offer_returns_404_without_database_changes(self):
        missing_id = self.offer.pk + 1000
        self.assertFalse(Offer.objects.filter(pk=missing_id).exists())
        url = reverse("offer-detail", args=[missing_id])
        self.assert_error(404, "not_found", url)
