"""Card 32 completed order counts through the routed API with real tokens."""

from django.contrib.auth.models import User
from django.urls import resolve, reverse
from rest_framework.test import APITestCase

from offers_app.tests.helpers import OfferTestHelpers
from orders_app.api.views import CompletedOrderCountView
from orders_app.models import Order


class CompletedOrderCountTests(OfferTestHelpers, APITestCase):
    """Check completed counts, authentication and read-only behavior."""

    def setUp(self):
        super().setUp()
        self.customer = self.make_user("buyer", "customer")
        self.owner = self.make_user("seller", "business")
        self.other = self.make_user("other-seller", "business")
        self.staff = self.make_user("staff", staff=True)
        self.offer = self.make_offer(self.owner)
        self.detail = self.offer.details.get(offer_type="basic")
        self.orders = [self.make_order(self.detail, state) for state in
                       ("completed", "completed", "in_progress",
                        "cancelled")]
        self.url = reverse("completed-order-count", args=[self.owner.pk])
        self.authenticate(self.customer)

    def assert_count(self, expected, business=None):
        business_id = business.pk if business else self.owner.pk
        url = reverse("completed-order-count", args=[business_id])
        before = self.snapshot()
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")
        data = response.json()
        self.assertIs(type(data), dict)
        self.assertEqual(data, {"completed_order_count": expected})
        self.assertIs(type(data["completed_order_count"]), int)
        self.assertEqual(self.snapshot(), before)

    def assert_error(self, expected_status, code):
        before = self.snapshot()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, expected_status)
        self.assertEqual(response["Content-Type"], "application/json")
        data = response.json()
        self.assertIs(type(data), dict)
        self.assertEqual(set(data), {"detail"})
        self.assertIs(type(data["detail"]), str)
        self.assertEqual(response.data["detail"].code, code)
        self.assertEqual(self.snapshot(), before)

    def test_existing_route_uses_order_count_view(self):
        expected = f"/api/completed-order-count/{self.owner.pk}/"
        self.assertEqual(self.url, expected)
        match = resolve(self.url)
        self.assertIs(match.func.view_class, CompletedOrderCountView)
        self.assertEqual(match.kwargs, {"business_user_id": self.owner.pk})

    def test_customer_can_read_count_for_unrelated_business(self):
        customer = self.make_user("unrelated-customer", "customer")
        self.authenticate(customer)
        self.assert_count(2)

    def test_business_can_read_own_count(self):
        self.authenticate(self.owner)
        self.assert_count(2)

    def test_business_can_read_other_business_count(self):
        self.authenticate(self.other)
        self.assert_count(2)

    def test_staff_without_profile_can_read_business_count(self):
        self.authenticate(self.staff)
        self.assert_count(2)

    def test_multiple_completed_orders_are_counted(self):
        self.make_order(self.detail, "completed")
        self.assert_count(3)

    def test_in_progress_and_cancelled_orders_are_excluded(self):
        for state in ("in_progress", "cancelled"):
            with self.subTest(status=state):
                self.make_order(self.detail, state)
                self.assert_count(2)

    def test_business_with_no_orders_returns_zero(self):
        self.assert_count(0, self.other)

    def test_empty_order_table_returns_zero(self):
        Order.objects.all().delete()
        self.assert_count(0)

    def test_only_in_progress_and_cancelled_orders_returns_zero(self):
        Order.objects.filter(status="completed").delete()
        self.assert_count(0)

    def test_multiple_businesses_have_independent_counts(self):
        detail = self.make_offer(self.other).details.get(offer_type="basic")
        self.make_order(detail, "in_progress")
        self.make_order(detail, "completed")
        self.assert_count(2, self.owner)
        self.assert_count(1, self.other)

    def test_business_on_customer_side_does_not_add_to_count(self):
        Order.objects.filter(pk=self.orders[0].pk).update(
            business_user=self.other, customer_user=self.owner)
        self.assert_count(1, self.owner)
        self.assert_count(1, self.other)

    def test_count_tracks_persisted_order_status_changes(self):
        order = self.orders[0]
        self.assert_count(2)
        for state, expected in (("in_progress", 1), ("completed", 2),
                                ("cancelled", 1), ("completed", 2)):
            with self.subTest(status=state):
                order.status = state
                order.save(update_fields=["status"])
                order.refresh_from_db()
                self.assertEqual(order.status, state)
                self.assert_count(expected)

    def test_anonymous_request_returns_401(self):
        self.client.credentials()
        self.assert_error(401, "not_authenticated")

    def test_invalid_token_returns_401(self):
        self.client.credentials(HTTP_AUTHORIZATION="Token invalid")
        self.assert_error(401, "authentication_failed")

    def test_nonexistent_user_returns_404(self):
        missing = User.objects.order_by("pk").last().pk + 1
        self.assertFalse(User.objects.filter(pk=missing).exists())
        self.url = reverse("completed-order-count", args=[missing])
        self.assert_error(404, "not_found")

    def test_customer_id_returns_404(self):
        self.url = reverse("completed-order-count", args=[self.customer.pk])
        self.assert_error(404, "not_found")

    def test_staff_without_business_profile_id_returns_404(self):
        self.url = reverse("completed-order-count", args=[self.staff.pk])
        self.assert_error(404, "not_found")

    def test_non_business_with_assigned_orders_still_returns_404(self):
        Order.objects.filter(pk=self.orders[0].pk).update(
            business_user=self.customer)
        self.url = reverse("completed-order-count", args=[self.customer.pk])
        self.assert_error(404, "not_found")

    def test_anonymous_nonexistent_user_still_returns_401(self):
        missing = User.objects.order_by("pk").last().pk + 1
        self.url = reverse("completed-order-count", args=[missing])
        self.client.credentials()
        self.assert_error(401, "not_authenticated")

    def test_invalid_token_precedes_missing_business_lookup(self):
        self.url = reverse("completed-order-count", args=[0])
        self.assertFalse(User.objects.filter(pk=0).exists())
        self.client.credentials(HTTP_AUTHORIZATION="Token invalid")
        self.assert_error(401, "authentication_failed")

    def test_authentication_precedes_non_business_lookup(self):
        for user in (self.customer, self.staff):
            with self.subTest(target=user.username):
                self.url = reverse("completed-order-count", args=[user.pk])
                self.client.credentials()
                self.assert_error(401, "not_authenticated")
                self.client.credentials(HTTP_AUTHORIZATION="Token invalid")
                self.assert_error(401, "authentication_failed")

    def test_completed_snapshot_counts_after_source_offer_deleted(self):
        self.offer.delete()
        self.assertFalse(Order.objects.filter(
            offer_detail__isnull=False).exists())
        self.assert_count(2)

    def test_unrelated_customer_can_read_zero_count(self):
        self.authenticate(self.make_user("unrelated", "customer"))
        self.assert_count(0, self.other)
