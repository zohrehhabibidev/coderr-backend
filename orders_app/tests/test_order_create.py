"""Card 27 contract tests through the routed POST API with real tokens."""

from copy import deepcopy
from decimal import Decimal

from django.urls import resolve, reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.test import APITestCase

from offers_app.tests import test_offer_delete as deletion
from offers_app.tests.helpers import OfferTestHelpers
from orders_app.api.views import OrderListCreateView
from orders_app.models import Order


class OrderCreateTests(OfferTestHelpers, APITestCase):
    """Check creation, rejected writes and durable package snapshots."""

    snapshot = deletion.OfferDeleteTests.snapshot
    make_order = deletion.OfferDeleteTests.make_order
    package_fields = (
        "title", "revisions", "delivery_time_in_days", "price", "features",
        "offer_type",
    )

    def setUp(self):
        super().setUp()
        self.owner = self.make_user("owner", "business")
        self.customer = self.make_user("customer", "customer")
        self.offer = self.make_offer(self.owner)
        self.details = {d.offer_type: d for d in self.offer.details.all()}
        self.detail = self.details["basic"]
        self.url = reverse("order-list")
        self.authenticate(self.customer)
        self.existing = self.make_order(self.detail)

    def package_snapshot(self, detail):
        return {name: deepcopy(getattr(detail, name))
                for name in self.package_fields}

    def assert_created(self, detail):
        before = self.snapshot()
        expected = self.package_snapshot(detail)
        started = timezone.now()
        response = self.client.post(self.url, {"offer_detail_id": detail.pk},
                                    format="json")
        self.assertEqual(response.status_code, 201)
        order = Order.objects.get(pk=response.json()["id"])
        self.assert_creation_state(before, order, detail, expected)
        self.assert_creation_response(response, order, expected, started,
                                      detail.offer.user_id)
        return order

    def assert_creation_state(self, before, order, detail, expected):
        after = self.snapshot()
        self.assertEqual(after[:-1], before[:-1])
        self.assertEqual(len(after[-1]), len(before[-1]) + 1)
        self.assertEqual([r for r in after[-1] if r["id"] != order.pk],
                         before[-1])
        self.assertEqual(order.customer_user_id, self.customer.pk)
        self.assertEqual(order.business_user_id, detail.offer.user_id)
        self.assertEqual(order.offer_detail_id, detail.pk)
        self.assertEqual(self.package_snapshot(order), expected)
        self.assertIs(type(order.price), Decimal)
        self.assertEqual(order.status, "in_progress")

    def assert_creation_response(self, response, order, expected, started,
                                 business_id):
        self.assertEqual(response["Content-Type"], "application/json")
        data = response.json()
        self.assertIsInstance(data, dict)
        expected = {**expected, "price": float(expected["price"]),
                    "id": order.pk, "customer_user": self.customer.pk,
                    "business_user": business_id, "status": "in_progress"}
        for name in ("created_at", "updated_at"):
            self.assert_timestamp(data[name], getattr(order, name), started)
            expected[name] = data[name]
        self.assertEqual(data, expected)
        self.assert_response_types(data)

    def assert_timestamp(self, value, persisted, started):
        self.assertIs(type(value), str)
        parsed = parse_datetime(value)
        self.assertIsNotNone(parsed)
        self.assertTrue(timezone.is_aware(parsed))
        self.assertEqual(parsed, persisted)
        self.assertLessEqual(started, parsed)
        self.assertLessEqual(parsed, timezone.now())

    def assert_response_types(self, data):
        for name in ("id", "customer_user", "business_user", "revisions",
                     "delivery_time_in_days"):
            self.assertIs(type(data[name]), int)
        for name in ("title", "offer_type", "status"):
            self.assertIs(type(data[name]), str)
        self.assertIn(type(data["price"]), (int, float))
        self.assertIs(type(data["features"]), list)
        for feature in data["features"]:
            self.assertIs(type(feature), str)

    def assert_error(self, payload, status, expected, codes, **kwargs):
        before = self.snapshot()
        response = self.client.post(self.url, payload, **kwargs)
        self.assertEqual(response.status_code, status)
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertIsInstance(response.json(), dict)
        self.assertEqual(response.json(), expected)
        for field, code in codes.items():
            errors = response.data[field]
            for error in errors if isinstance(errors, list) else [errors]:
                self.assertIsInstance(error, str)
                self.assertNotEqual(error, "")
                self.assertEqual(error.code, code)
        self.assertEqual(self.snapshot(), before)

    def assert_invalid_id(self, payload, message, code):
        self.assert_error(payload, 400, {"offer_detail_id": [message]},
                          {"offer_detail_id": code}, format="json")

    def assert_detail_error(self, status, message, code, payload=None):
        payload = payload or {"offer_detail_id": self.detail.pk}
        self.assert_error(
            payload, status, {"detail": message}, {"detail": code},
            format="json",
        )

    def test_routed_url_targets_order_creation(self):
        self.assertEqual(self.url, "/api/orders/")
        self.assertIs(resolve(self.url).func.view_class, OrderListCreateView)

    def test_customer_creates_each_package_with_exact_response(self):
        for kind, detail in self.details.items():
            with self.subTest(offer_type=kind):
                self.assert_created(detail)

    def test_empty_features_and_zero_revisions_are_preserved(self):
        self.detail.features = []
        self.detail.revisions = 0
        self.detail.save()
        order = self.assert_created(self.detail)
        self.assertEqual(order.features, [])
        self.assertEqual(order.revisions, 0)

    def test_business_user_matches_selected_package_owner_across_sellers(self):
        other = self.make_user("other-seller", "business")
        other_offer = self.make_offer(other)
        other_detail = other_offer.details.get(offer_type="basic")
        self.assertNotEqual(self.owner.pk, other.pk)
        for detail in (other_detail, self.detail, other_detail):
            with self.subTest(detail=detail.pk):
                order = self.assert_created(detail)
                self.assertEqual(order.business_user_id, detail.offer.user_id)

    def test_decimal_prices_are_numeric_and_persist_without_rounding(self):
        for price in ("0.01", "150.10", "99999999.99"):
            with self.subTest(price=price):
                self.detail.price = Decimal(price)
                self.detail.save(update_fields=["price"])
                order = self.assert_created(self.detail)
                self.assertEqual(order.price, Decimal(price))

    def test_separate_customers_can_order_the_same_package(self):
        first = self.assert_created(self.detail)
        self.customer = self.make_user("second-customer", "customer")
        self.authenticate(self.customer)
        second = self.assert_created(self.detail)
        self.assertNotEqual(first.pk, second.pk)
        self.assertNotEqual(first.customer_user_id, second.customer_user_id)
        self.assertEqual(first.offer_detail_id, second.offer_detail_id)

    def test_snapshot_survives_changes_to_every_package_field(self):
        order = self.assert_created(self.detail)
        before = Order.objects.values().get(pk=order.pk)
        changes = dict(title="Updated", revisions=99, price=Decimal("9.99"),
                       delivery_time_in_days=99, features=["Replacement"],
                       offer_type="premium")
        self.details["premium"].delete()
        for name, value in changes.items():
            setattr(self.detail, name, value)
        self.detail.save()
        self.assertEqual(Order.objects.values().get(pk=order.pk), before)
        self.assertEqual(self.assert_created(self.detail).title, "Updated")

    def test_offer_deletion_detaches_and_preserves_created_order(self):
        order = self.assert_created(self.detail)
        before = Order.objects.values().get(pk=order.pk)
        self.offer.delete()
        order.refresh_from_db()
        self.assertIsNone(order.offer_detail_id)
        before["offer_detail_id"] = None
        self.assertEqual(Order.objects.values().get(pk=order.pk), before)

    def test_order_features_are_independent_between_purchases_and_source(self):
        first = self.assert_created(self.detail)
        second = self.assert_created(self.detail)
        original = deepcopy(self.detail.features)
        first.features.append("Only first purchase")
        first.save(update_fields=["features"])
        second.refresh_from_db()
        self.detail.refresh_from_db()
        self.assertEqual(second.features, original)
        self.assertEqual(self.detail.features, original)
        self.assertNotEqual(first.features, second.features)

    def test_missing_and_null_offer_detail_id(self):
        self.assert_invalid_id({}, "This field is required.", "required")
        self.assert_invalid_id({"offer_detail_id": None},
                               "This field may not be null.", "null")

    def test_malformed_and_wrong_type_offer_detail_ids(self):
        for value in ("", "abc", "1.5", 1.5, True, False, [], {}, [1]):
            with self.subTest(value=value):
                self.assert_invalid_id({"offer_detail_id": value},
                                       "A valid integer is required.",
                                       "invalid")

    def test_zero_and_negative_offer_detail_ids(self):
        for value in (0, -1, -999):
            with self.subTest(value=value):
                self.assert_invalid_id(
                    {"offer_detail_id": value},
                    "Ensure this value is greater than or equal to 1.",
                    "min_value",
                )

    def test_non_object_request_bodies(self):
        for value, label in (([], "list"), ("bad", "str"), (7, "int")):
            with self.subTest(value=value):
                self.assert_error(
                    value, 400, {"non_field_errors": [
                        "Invalid data. Expected a dictionary, "
                        f"but got {label}."
                    ]}, {"non_field_errors": "invalid"}, format="json",
                )

    def test_malformed_json_returns_parse_error_without_changes(self):
        before = self.snapshot()
        response = self.client.post(
            self.url, '{"offer_detail_id":', content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertEqual(set(response.json()), {"detail"})
        self.assertIs(type(response.json()["detail"]), str)
        self.assertTrue(response.json()["detail"].startswith(
            "JSON parse error"))
        self.assertEqual(response.data["detail"].code, "parse_error")
        self.assertEqual(self.snapshot(), before)

    def forbidden_inputs(self):
        return dict(
            id=999, user=self.owner.pk, customer_user=self.owner.pk,
            business_user=self.customer.pk, price=1, status="completed",
            title="Forged", revisions=9, delivery_time_in_days=9,
            features=["Forged"], offer_type="premium", offer_detail=1,
            created_at="2024-01-01T00:00:00Z", updated_at=None,
            unknown="extra",
        )

    def test_client_controlled_and_unknown_fields_are_rejected(self):
        for name, value in self.forbidden_inputs().items():
            with self.subTest(field=name):
                self.assert_error(
                    {"offer_detail_id": self.detail.pk, name: value}, 400,
                    {name: "This field cannot be supplied."},
                    {name: "invalid"}, format="json",
                )

    def test_multiple_extra_fields_report_every_rejected_field(self):
        self.assert_error(
            {"offer_detail_id": self.detail.pk, "price": 1, "status": "done"},
            400, {name: "This field cannot be supplied."
                  for name in ("price", "status")},
            {name: "invalid" for name in ("price", "status")}, format="json",
        )

    def test_anonymous_request_returns_401(self):
        self.client.credentials()
        self.assert_detail_error(
            401, "Authentication credentials were not provided.",
            "not_authenticated",
        )

    def test_invalid_and_missing_token_credentials_return_401(self):
        for header, message in (
            ("Token invalid", "Invalid token."),
            ("Token", "Invalid token header. No credentials provided."),
        ):
            with self.subTest(header=header):
                self.client.credentials(HTTP_AUTHORIZATION=header)
                self.assert_detail_error(401, message, "authentication_failed")

    def test_non_customer_roles_return_403(self):
        for role, staff in (("business", False), ("business", True),
                            (None, False), (None, True)):
            with self.subTest(role=role, staff=staff):
                user = self.make_user(f"denied-{role}-{staff}", role, staff)
                self.authenticate(user)
                self.assert_detail_error(
                    403, "You do not have permission to perform this action.",
                    "permission_denied",
                )

    def test_nonexistent_positive_offer_detail_id_returns_404(self):
        missing = max(detail.pk for detail in self.details.values()) + 1
        self.assertFalse(self.offer.details.filter(pk=missing).exists())
        self.assert_detail_error(
            404, "No OfferDetail matches the given query.", "not_found",
            {"offer_detail_id": missing},
        )
