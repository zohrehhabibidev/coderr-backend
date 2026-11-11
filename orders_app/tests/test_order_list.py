"""Card 28 list contract through the routed API with real tokens."""

from django.urls import resolve, reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from offers_app.tests.helpers import OfferTestHelpers
from orders_app.api.views import OrderListCreateView
from orders_app.models import Order
from orders_app.tests import test_order_create as creation


class OrderListTests(OfferTestHelpers, APITestCase):
    """Verify private order history, snapshots and read-only GET requests."""

    make_order = creation.OrderCreateTests.make_order
    snapshot = creation.OrderCreateTests.snapshot
    package_snapshot = creation.OrderCreateTests.package_snapshot
    package_fields = creation.OrderCreateTests.package_fields
    assert_response_types = creation.OrderCreateTests.assert_response_types
    assert_timestamp = creation.OrderCreateTests.assert_timestamp

    def setUp(self):
        super().setUp()
        self.started = timezone.now()
        self.customer = self.make_user("buyer", "customer")
        self.owner = self.make_user("seller", "business")
        self.other = self.make_user("other-buyer", "customer")
        self.staff = self.make_user("staff", staff=True)
        self.offer = self.make_offer(self.owner)
        self.details = list(self.offer.details.order_by("pk"))
        self.orders = [self.make_order(detail, state) for detail, state in
                       zip(self.details, ("in_progress", "completed",
                                          "cancelled"))]
        self.url = reverse("order-list")

    def assert_list(self, user, orders, params=None):
        self.authenticate(user)
        before = self.snapshot()
        response = self.client.get(self.url, params or {})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")
        data = response.json()
        self.assert_rows(data, orders)
        self.assertEqual(self.snapshot(), before)
        return data

    def assert_rows(self, data, orders):
        self.assertIs(type(data), list)
        self.assertEqual(len(data), len(orders))
        self.assertEqual({row["id"] for row in data},
                         {order.pk for order in orders})
        expected = {order.pk: order for order in orders}
        for row in data:
            self.assert_order(row, expected[row["id"]])

    def assert_order(self, data, order):
        expected = self.package_snapshot(order)
        expected.update(id=order.pk, customer_user=order.customer_user_id,
                        business_user=order.business_user_id,
                        price=float(order.price), status=order.status)
        for name in ("created_at", "updated_at"):
            self.assert_timestamp(data[name], getattr(order, name),
                                  self.started)
            expected[name] = data[name]
        self.assertEqual(len(data), 12)
        self.assertEqual(data, expected)
        self.assert_response_types(data)

    def assert_unauthorized(self, message, code):
        before = self.snapshot()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertEqual(response.json(), {"detail": message})
        self.assertIs(type(response.json()["detail"]), str)
        self.assertEqual(response.data["detail"].code, code)
        self.assertEqual(self.snapshot(), before)

    def test_url_uses_existing_order_list_create_view(self):
        self.assertEqual(self.url, "/api/orders/")
        self.assertIs(resolve(self.url).func.view_class, OrderListCreateView)

    def test_customer_sees_only_own_multiple_orders(self):
        Order.objects.filter(pk=self.orders[1].pk).update(
            customer_user=self.other)
        self.assert_list(self.customer, [self.orders[0], self.orders[2]])

    def test_business_sees_only_orders_assigned_to_them(self):
        Order.objects.filter(pk=self.orders[1].pk).update(
            business_user=self.staff)
        self.assert_list(self.owner, [self.orders[0], self.orders[2]])

    def test_staff_sees_only_linked_orders_without_global_access(self):
        first, second = self.orders[:2]
        first.customer_user = self.staff
        first.save(update_fields=["customer_user"])
        second.business_user = self.staff
        second.save(update_fields=["business_user"])
        self.assert_list(self.staff, [first, second])

    def test_customer_can_match_business_side_of_ownership(self):
        order = self.orders[0]
        order.customer_user = self.other
        order.business_user = self.customer
        order.save(update_fields=["customer_user", "business_user"])
        self.assert_list(self.customer, self.orders)

    def test_business_can_match_customer_side_of_ownership(self):
        order = self.orders[0]
        order.customer_user = self.owner
        order.business_user = self.staff
        order.save(update_fields=["customer_user", "business_user"])
        self.assert_list(self.owner, self.orders)

    def test_order_matching_both_sides_is_returned_once(self):
        order = self.orders[0]
        order.business_user = self.customer
        order.save(update_fields=["business_user"])
        self.assert_list(self.customer, self.orders)

    def test_customer_without_linked_orders_receives_empty_array(self):
        self.assertEqual(self.assert_list(self.other, []), [])

    def test_business_without_linked_orders_receives_empty_array(self):
        user = self.make_user("unrelated-seller", "business")
        self.assertEqual(self.assert_list(user, []), [])

    def test_staff_without_linked_orders_receives_empty_array(self):
        self.assertEqual(self.assert_list(self.staff, []), [])

    def test_empty_database_returns_empty_array(self):
        Order.objects.all().delete()
        self.assertEqual(self.assert_list(self.customer, []), [])

    def test_page_parameters_do_not_paginate_or_wrap_results(self):
        for params in ({"page": 1, "page_size": 1}, {"page": 999}):
            with self.subTest(params=params):
                self.assert_list(self.customer, self.orders, params)

    def test_client_cannot_select_another_users_orders(self):
        self.assert_list(self.other, [], {"customer_user": self.customer.pk,
                                         "business_user": self.owner.pk})

    def test_anonymous_get_returns_401_without_database_changes(self):
        self.client.credentials()
        self.assert_unauthorized(
            "Authentication credentials were not provided.",
            "not_authenticated",
        )

    def test_invalid_token_returns_401_without_database_changes(self):
        self.client.credentials(HTTP_AUTHORIZATION="Token invalid")
        self.assert_unauthorized("Invalid token.", "authentication_failed")

    def test_missing_token_value_returns_401_without_database_changes(self):
        self.client.credentials(HTTP_AUTHORIZATION="Token")
        self.assert_unauthorized(
            "Invalid token header. No credentials provided.",
            "authentication_failed",
        )

    def test_get_uses_snapshots_after_source_package_changes(self):
        self.offer.details.update(title="Replacement", revisions=99,
                                  delivery_time_in_days=99, price="9.99",
                                  features=["Replacement"])
        self.details[2].delete()
        self.details[0].offer_type = "premium"
        self.details[0].save(update_fields=["offer_type"])
        self.assert_list(self.customer, self.orders)

    def test_get_preserves_snapshots_after_source_offer_deletion(self):
        self.offer.delete()
        self.assertFalse(Order.objects.exclude(offer_detail=None).exists())
        self.assert_list(self.customer, self.orders)

    def test_empty_features_zero_revisions_and_decimal_price(self):
        order = self.orders[0]
        order.features = []
        order.revisions = 0
        order.price = "0.01"
        order.save(update_fields=["features", "revisions", "price"])
        order.refresh_from_db()
        self.assert_list(self.customer, self.orders)
