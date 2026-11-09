from copy import deepcopy
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.urls import resolve, reverse
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from auth_app.models import Profile
from offers_app.api.views import OfferListCreateView
from offers_app.models import Offer, OfferDetail


class OfferCreateTests(APITestCase):
    """Exercise Card 21 through the routed endpoint with real tokens."""

    def setUp(self):
        super().setUp()
        self.business = User.objects.create_user(username="business")
        self.customer = User.objects.create_user(username="customer")
        Profile.objects.create(user=self.business, type="business")
        Profile.objects.create(user=self.customer, type="customer")
        self.url = reverse("offer-list")
        self.payload = {
            "title": "Design", "image": None, "description": "Design package",
            "details": [self.detail(kind) for kind in
                        ("basic", "standard", "premium")],
        }
        self.authenticate(self.business)

    def detail(self, kind):
        prices = {"basic": 100.25, "standard": 200.50, "premium": 500.75}
        revisions = {"basic": 2, "standard": 5, "premium": 10}.get(kind, 2)
        return {
            "title": kind,
            "revisions": revisions,
            "delivery_time_in_days": revisions + 3,
            "price": prices.get(kind, 100),
            "features": [f"{kind} Logo", f"{kind} source files"],
            "offer_type": kind,
        }

    def authenticate(self, user):
        token, _ = Token.objects.get_or_create(user=user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

    def assert_rejected(self, payload, expected=400):
        before = (Offer.objects.count(), OfferDetail.objects.count())
        response = self.client.post(self.url, payload, format="json")
        self.assertEqual(response.status_code, expected)
        self.assertIsInstance(response.data, dict)
        self.assertTrue(response.data)
        self.assertEqual(
            (Offer.objects.count(), OfferDetail.objects.count()), before,
        )
        return response.data

    def assert_validation_error(self, payload, path, code):
        errors = self.assert_rejected(payload)
        for key in path:
            self.assertIsInstance(errors, (dict, list))
            errors = errors[key]
        self.assertIsInstance(errors, list)
        self.assertTrue(errors)
        for error in errors:
            self.assertIsInstance(error, str)
            self.assertTrue(error)
            self.assertEqual(error.code, code)

    def assert_detail_types(self, response):
        for detail in response.json()["details"]:
            with self.subTest(offer_type=detail["offer_type"]):
                self.assertIs(type(detail["id"]), int)
                self.assertIn(type(detail["price"]), (int, float))

    def add_detail_ids(self, expected, offer):
        details_by_type = {
            detail.offer_type: detail for detail in offer.details.all()
        }
        for detail in expected["details"]:
            detail["id"] = details_by_type[detail["offer_type"]].pk

    def assert_creation_response(self, response, offer):
        expected = deepcopy(self.payload)
        expected["id"] = offer.pk
        self.add_detail_ids(expected, offer)
        actual = response.json()
        self.assertIsInstance(actual["id"], int)
        self.assertIsInstance(actual["details"], list)
        self.assert_detail_types(response)
        self.assertEqual(len(actual["details"]), 3)
        for data in (actual, expected):
            data["details"] = {
                detail["offer_type"]: detail for detail in data["details"]
            }
        self.assertEqual(actual, expected)

    def assert_offer_persisted(self, offer):
        self.assertEqual(Offer.objects.count(), 1)
        self.assertEqual(offer.user, self.business)
        self.assertEqual(offer.title, self.payload["title"])
        self.assertEqual(offer.description, self.payload["description"])
        self.assertFalse(offer.image)

    def assert_details_persisted(self, offer):
        self.assertEqual(OfferDetail.objects.count(), 3)
        self.assertEqual(offer.details.count(), 3)
        details = {
            detail.offer_type: detail for detail in OfferDetail.objects.all()
        }
        self.assertEqual(set(details), {"basic", "standard", "premium"})
        for submitted in self.payload["details"]:
            with self.subTest(offer_type=submitted["offer_type"]):
                detail = details[submitted["offer_type"]]
                self.assertEqual(detail.offer_id, offer.pk)
                self.assert_detail_persisted(detail, submitted)

    def assert_detail_persisted(self, detail, submitted):
        for field, expected in submitted.items():
            with self.subTest(field=field):
                if field == "price":
                    expected = Decimal(str(expected))
                self.assertEqual(getattr(detail, field), expected)

    def test_business_creation_matches_documented_response(self):
        response = self.client.post(self.url, self.payload, format="json")
        self.assertEqual(response.status_code, 201)
        offer = Offer.objects.get()
        self.assert_creation_response(response, offer)
        self.assert_offer_persisted(offer)
        self.assert_details_persisted(offer)

    def test_anonymous_post_returns_401(self):
        self.client.credentials()
        self.assert_rejected(self.payload, 401)

    def test_invalid_token_returns_401(self):
        self.client.credentials(HTTP_AUTHORIZATION="Token invalid")
        self.assert_rejected(self.payload, 401)

    def test_customer_post_returns_403(self):
        self.authenticate(self.customer)
        self.assert_rejected(self.payload, 403)

    def test_staff_customer_cannot_create_offer(self):
        self.customer.is_staff = True
        self.customer.save()
        self.authenticate(self.customer)
        self.assert_rejected(self.payload, 403)

    def test_staff_business_can_create_offer(self):
        self.business.is_staff = True
        self.business.save()
        response = self.client.post(self.url, self.payload, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Offer.objects.get().user, self.business)
        self.assertEqual(OfferDetail.objects.count(), 3)

    def test_staff_without_profile_cannot_create_offer(self):
        self.business.is_staff = True
        self.business.save()
        self.business.profile.delete()
        self.assert_rejected(self.payload, 403)

    def test_user_without_profile_returns_403(self):
        self.business.profile.delete()
        self.assert_rejected(self.payload, 403)

    def test_owner_input_cannot_override_request_user(self):
        payload = {**self.payload, "user": self.customer.pk}
        response = self.client.post(self.url, payload, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Offer.objects.get().user, self.business)
        self.assertNotIn("user", response.json())

    def test_missing_required_fields(self):
        for field in ("title", "description", "details"):
            with self.subTest(field=field):
                payload = deepcopy(self.payload)
                del payload[field]
                before = (Offer.objects.count(), OfferDetail.objects.count())
                response = self.client.post(self.url, payload, format="json")
                self.assertEqual(response.status_code, 400)
                self.assertIsInstance(response.data, dict)
                self.assertIn(field, response.data)
                self.assertTrue(response.data[field])
                counts = (Offer.objects.count(), OfferDetail.objects.count())
                self.assertEqual(counts, before)

    def test_blank_or_null_title_returns_400(self):
        for value in ("", None):
            with self.subTest(value=value):
                payload = deepcopy(self.payload)
                payload["title"] = value
                response = self.client.post(self.url, payload, format="json")
                self.assertEqual(response.status_code, 400)
                self.assertIsInstance(response.data, dict)
                self.assertIn("title", response.data)
                self.assertTrue(response.data["title"])
                self.assertEqual(Offer.objects.count(), 0)
                self.assertEqual(OfferDetail.objects.count(), 0)

    def test_invalid_package_counts(self):
        for count in (0, 1, 2, 4):
            with self.subTest(count=count):
                payload = deepcopy(self.payload)
                payload["details"] = [self.detail("basic")] * count
                self.assert_validation_error(payload, ("details",), "invalid")

    def test_duplicate_unknown_and_missing_package_types(self):
        for kind in ("basic", "unknown", None):
            with self.subTest(kind=kind):
                payload = deepcopy(self.payload)
                payload["details"][2]["offer_type"] = kind
                path, code = ("details",), "invalid"
                if kind != "basic":
                    path = ("details", 2, "offer_type")
                    code = "null" if kind is None else "invalid_choice"
                self.assert_validation_error(payload, path, code)

    def test_missing_nested_field(self):
        payload = deepcopy(self.payload)
        del payload["details"][0]["offer_type"]
        self.assert_validation_error(
            payload, ("details", 0, "offer_type"), "required",
        )

    def test_missing_required_package_fields(self):
        for field in ("title", "revisions", "delivery_time_in_days", "price"):
            with self.subTest(field=field):
                payload = deepcopy(self.payload)
                del payload["details"][0][field]
                self.assert_validation_error(
                    payload, ("details", 0, field), "required",
                )

    def test_invalid_details_structure(self):
        cases = (
            (None, (), "null"),
            ("invalid", ("non_field_errors",), "not_a_list"),
            ({}, ("non_field_errors",), "not_a_list"),
            ([7], (0, "non_field_errors"), "invalid"),
        )
        for value, path, code in cases:
            with self.subTest(details=value):
                payload = {**self.payload, "details": value}
                self.assert_validation_error(
                    payload, ("details",) + path, code,
                )

    def test_invalid_nested_values(self):
        for field, value in (("price", "bad"), ("revisions", -1)):
            with self.subTest(field=field):
                payload = deepcopy(self.payload)
                payload["details"][0][field] = value
                code = "invalid" if field == "price" else "min_value"
                self.assert_validation_error(
                    payload, ("details", 0, field), code,
                )

    def test_public_get_minimum_configuration(self):
        self.client.credentials()
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_routing(self):
        self.assertEqual(self.url, "/api/offers/")
        self.assertIs(resolve(self.url).func.view_class, OfferListCreateView)

    def test_failure_on_second_package_rolls_back_everything(self):
        self.original_create = OfferDetail.objects.create
        with patch(
            "offers_app.api.serializers.OfferDetail.objects.create",
            side_effect=self.create_package_or_fail,
        ):
            with self.assertRaises(RuntimeError):
                self.client.post(self.url, self.payload, format="json")
        self.assertEqual(Offer.objects.count(), 0)
        self.assertEqual(OfferDetail.objects.count(), 0)

    def create_package_or_fail(self, **kwargs):
        if kwargs["offer_type"] == "standard":
            self.assertEqual(OfferDetail.objects.count(), 1)
            raise RuntimeError("Simulated second package failure")
        return self.original_create(**kwargs)
