"""Card 29 status updates through the routed API with real tokens."""

from copy import deepcopy
from datetime import timedelta

from django.urls import resolve, reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from offers_app.tests.helpers import OfferTestHelpers
from orders_app.api.views import OrderDetailView
from orders_app.models import Order
from orders_app.tests import test_order_list as listing


class OrderPatchTests(OfferTestHelpers, APITestCase):
    """Check status-only writes, snapshot integrity and rejected requests."""

    make_order = listing.OrderListTests.make_order
    snapshot = listing.OrderListTests.snapshot
    package_snapshot = listing.OrderListTests.package_snapshot
    package_fields = listing.OrderListTests.package_fields
    assert_response_types = listing.OrderListTests.assert_response_types
    assert_timestamp = listing.OrderListTests.assert_timestamp
    assert_order = listing.OrderListTests.assert_order
    statuses = ("in_progress", "completed", "cancelled")

    def setUp(self):
        super().setUp()
        self.started = timezone.now() - timedelta(days=1)
        self.owner = self.make_user("owner", "business")
        self.customer = self.make_user("customer", "customer")
        self.offer = self.make_offer(self.owner)
        self.details = {d.offer_type: d for d in self.offer.details.all()}
        self.order = self.make_order(self.details["basic"], "in_progress")
        self.make_order(self.details["premium"])
        Order.objects.update(updated_at=self.started)
        self.url = reverse("order-detail", args=[self.order.pk])
        self.authenticate(self.owner)

    def assert_updated(self, status):
        before = self.snapshot()
        started = timezone.now()
        response = self.client.patch(self.url, {"status": status},
                                     format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertIs(type(response.json()), dict)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, status)
        self.assert_order(response.json(), self.order)
        self.assert_timestamp(response.json()["updated_at"],
                              self.order.updated_at, started)
        self.assert_only_status_changed(before, status)

    def assert_only_status_changed(self, before, status):
        expected = deepcopy(before)
        row = next(row for row in expected[-1]
                   if row["id"] == self.order.pk)
        self.assertGreater(self.order.updated_at, row["updated_at"])
        row.update(status=status, updated_at=self.order.updated_at)
        self.assertEqual(self.snapshot(), expected)

    def assert_rejected(self, status, payload, expected, codes, **kwargs):
        before = self.snapshot()
        response = self.client.patch(self.url, payload, **kwargs)
        self.assertEqual(response.status_code, status)
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertIs(type(response.json()), dict)
        self.assertEqual(response.json(), expected)
        self.assert_error_types(response, expected, codes)
        self.assertEqual(self.snapshot(), before)

    def assert_error_types(self, response, expected, codes):
        for field, value in expected.items():
            actual = response.json()[field]
            self.assertIs(type(actual), type(value))
            errors = response.data[field]
            for error in errors if isinstance(errors, list) else [errors]:
                self.assertIsInstance(error, str)
                self.assertEqual(error.code, codes[field])
            for message in actual if isinstance(actual, list) else [actual]:
                self.assertIs(type(message), str)

    def assert_denied(self, status):
        message, code = self.expected_denial(status)
        self.assert_rejected(status, {"status": "completed"},
                             {"detail": message}, {"detail": code},
                             format="json")

    def expected_denial(self, status):
        if status == 403:
            return ("You do not have permission to perform this action.",
                    "permission_denied")
        if status == 404:
            return "No Order matches the given query.", "not_found"
        header = self.client._credentials.get("HTTP_AUTHORIZATION", "")
        if not header:
            return ("Authentication credentials were not provided.",
                    "not_authenticated")
        message = ("Invalid token." if header == "Token invalid" else
                   "Invalid token header. No credentials provided.")
        return message, "authentication_failed"

    def assert_invalid(self, payload, field="status"):
        expected, code = self.expected_validation(payload, field)
        self.assert_rejected(400, payload, expected,
                             {name: code for name in expected}, format="json")

    def expected_validation(self, payload, field):
        if field == "non_field_errors":
            label = type(payload).__name__
            return {field: ["Invalid data. Expected a dictionary, "
                            f"but got {label}."]}, "invalid"
        if "status" not in payload:
            return {"status": "This field is required."}, "invalid"
        extra = set(payload) - {"status"}
        if extra:
            return {name: "This field cannot be updated."
                    for name in extra}, "invalid"
        message, code = self.expected_status_error(payload["status"])
        return {"status": [message]}, code

    def expected_status_error(self, value):
        if value is None:
            return "This field may not be null.", "null"
        return f'"{value}" is not a valid choice.', "invalid_choice"

    def test_url_routes_to_order_detail_view(self):
        self.assertEqual(self.url, f"/api/orders/{self.order.pk}/")
        self.assertIs(resolve(self.url).func.view_class, OrderDetailView)

    def test_assigned_business_updates_each_documented_status(self):
        for status in self.statuses:
            with self.subTest(status=status):
                self.assert_updated(status)

    def test_status_values_do_not_introduce_transition_restrictions(self):
        for source in self.statuses:
            for target in self.statuses:
                with self.subTest(source=source, target=target):
                    Order.objects.filter(pk=self.order.pk).update(
                        status=source, updated_at=self.started)
                    self.assert_updated(target)

    def test_each_package_snapshot_is_preserved(self):
        for kind, detail in self.details.items():
            with self.subTest(offer_type=kind):
                self.order = self.make_order(detail, "in_progress")
                self.url = reverse("order-detail", args=[self.order.pk])
                self.assert_updated("completed")

    def test_changed_source_package_does_not_replace_order_snapshot(self):
        self.offer.details.update(title="Replacement", price="1.01",
                                  features=["Changed"], revisions=99,
                                  delivery_time_in_days=99)
        self.assert_updated("completed")

    def test_deleted_source_offer_does_not_prevent_status_update(self):
        self.offer.delete()
        self.assert_updated("cancelled")
        self.assertIsNone(self.order.offer_detail_id)

    def test_empty_features_zero_revisions_and_decimal_price(self):
        Order.objects.filter(pk=self.order.pk).update(
            features=[], revisions=0, price="0.01")
        self.assert_updated("completed")

    def test_assigned_business_staff_can_update(self):
        self.owner.is_staff = True
        self.owner.save(update_fields=["is_staff"])
        self.assert_updated("completed")

    def test_empty_object_and_missing_status_return_400(self):
        for payload in ({}, {"title": "Forged"}):
            with self.subTest(payload=payload):
                self.assert_invalid(payload)

    def test_null_blank_and_invalid_status_return_400(self):
        for value in (None, "", "pending", "COMPLETED", " completed "):
            with self.subTest(status=value):
                self.assert_invalid({"status": value})

    def test_wrong_status_types_return_400(self):
        for value in (True, False, 0, 1, 1.5, [], {}, ["completed"]):
            with self.subTest(status=value):
                self.assert_invalid({"status": value})

    def forbidden_inputs(self):
        return dict(
            id=999, customer_user=self.owner.pk,
            business_user=self.customer.pk, title="Forged", revisions=99,
            delivery_time_in_days=99, price=1, features=["Forged"],
            offer_type="premium", created_at="2024-01-01T00:00:00Z",
            updated_at=None, offer_detail=self.details["premium"].pk,
            offer_detail_id=self.details["premium"].pk, unknown="extra",
        )

    def test_read_only_and_unknown_fields_return_400(self):
        for name, value in self.forbidden_inputs().items():
            with self.subTest(field=name):
                self.assert_invalid({"status": "completed", name: value},
                                    name)

    def test_multiple_extra_fields_return_400(self):
        self.assert_invalid({"status": "completed", "price": 1,
                             "title": "Forged"}, "price")

    def test_non_object_bodies_return_400(self):
        for value in ([], ["completed"], "completed", 7, True):
            with self.subTest(body=value):
                self.assert_invalid(value, "non_field_errors")

    def test_malformed_json_returns_400_without_changes(self):
        self.assert_rejected(
            400, '{"status":', {"detail": "JSON parse error - Expecting "
                               "value: line 1 column 11 (char 10)"},
            {"detail": "parse_error"}, content_type="application/json",
        )

    def test_anonymous_request_returns_401(self):
        self.client.credentials()
        self.assert_denied(401)

    def test_invalid_and_missing_token_values_return_401(self):
        for header in ("Token invalid", "Token", "Token "):
            with self.subTest(header=header):
                self.client.credentials(HTTP_AUTHORIZATION=header)
                self.assert_denied(401)

    def test_assigned_customer_returns_403(self):
        self.authenticate(self.customer)
        self.assert_denied(403)

    def test_unrelated_users_including_staff_return_403(self):
        for role in ("customer", "business", None):
            for staff in (False, True):
                with self.subTest(role=role, staff=staff):
                    user = self.make_user(f"other-{role}-{staff}", role,
                                          staff)
                    self.authenticate(user)
                    self.assert_denied(403)

    def test_assigned_user_without_business_role_returns_403(self):
        for role in ("customer", None):
            with self.subTest(role=role):
                user = self.make_user(f"assigned-{role}", role, staff=True)
                Order.objects.filter(pk=self.order.pk).update(
                    business_user=user)
                self.authenticate(user)
                self.assert_denied(403)

    def test_business_on_customer_side_has_no_update_permission(self):
        user = self.make_user("business-buyer", "business")
        Order.objects.filter(pk=self.order.pk).update(customer_user=user)
        self.authenticate(user)
        self.assert_denied(403)

    def test_nonexistent_order_returns_404_without_changes(self):
        missing = Order.objects.order_by("pk").last().pk + 1
        self.assertFalse(Order.objects.filter(pk=missing).exists())
        self.url = reverse("order-detail", args=[missing])
        self.assert_denied(404)

    def test_options_advertises_patch_and_delete_without_changes(self):
        before = self.snapshot()
        response = self.client.options(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response["Allow"].split(", ")),
                         {"PATCH", "DELETE", "OPTIONS"})
        self.assertEqual(self.snapshot(), before)
