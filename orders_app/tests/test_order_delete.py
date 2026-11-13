"""Card 30 staff-only deletion through the routed API with real tokens."""

from django.urls import resolve, reverse
from rest_framework.test import APITestCase

from offers_app.tests import test_offer_delete as deletion
from offers_app.tests.helpers import OfferTestHelpers
from orders_app.api.views import OrderDetailView
from orders_app.models import Order
from reviews_app.models import Review


class OrderDeleteTests(OfferTestHelpers, APITestCase):
    """Verify method-specific authorization and precise database changes."""

    assert_error = deletion.OfferDeleteTests.assert_error

    def setUp(self):
        super().setUp()
        self.owner = self.make_user("owner", "business")
        self.customer = self.make_user("customer", "customer")
        self.staff = self.make_user("staff", staff=True)
        self.offer = self.make_offer(self.owner)
        self.detail = self.offer.details.get(offer_type="basic")
        self.order = self.make_order(self.detail, "in_progress")
        self.make_order(self.detail)
        self.make_order(None, "cancelled")
        Review.objects.create(business_user=self.owner, reviewer=self.customer,
                              rating=5, description="Unrelated review")
        self.url = reverse("order-detail", args=[self.order.pk])
        self.authenticate(self.staff)

    def snapshot(self):
        return [list(Review.objects.order_by("pk").values())] + (
            super().snapshot())

    def assert_deleted(self):
        before = self.snapshot()
        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, 204)
        self.assertIsNone(response.data)
        self.assertIs(type(response.content), bytes)
        self.assertEqual(response.content, b"")
        self.assertFalse(Order.objects.filter(pk=self.order.pk).exists())
        before[-1] = [row for row in before[-1]
                      if row["id"] != self.order.pk]
        self.assertEqual(self.snapshot(), before)

    def assert_forbidden(self):
        self.assert_error(403, "permission_denied")

    def test_url_routes_to_existing_order_detail_view(self):
        self.assertEqual(self.url, f"/api/orders/{self.order.pk}/")
        self.assertIs(resolve(self.url).func.view_class, OrderDetailView)

    def test_unrelated_staff_can_delete_with_any_or_no_profile(self):
        for role in ("customer", "business", None):
            with self.subTest(role=role):
                user = self.make_user(f"staff-{role}", role, staff=True)
                self.assertNotIn(user.pk, (self.order.customer_user_id,
                                          self.order.business_user_id))
                self.authenticate(user)
                self.assert_deleted()
                self.order = self.make_order(self.detail)
                self.url = reverse("order-detail", args=[self.order.pk])

    def test_assigned_customer_and_business_staff_can_delete(self):
        for user in (self.customer, self.owner):
            with self.subTest(user=user.username):
                user.is_staff = True
                user.save(update_fields=["is_staff"])
                self.authenticate(user)
                self.assert_deleted()
                self.order = self.make_order(self.detail)
                self.url = reverse("order-detail", args=[self.order.pk])

    def test_staff_can_delete_each_order_status(self):
        for status in Order.OrderStatus.values:
            with self.subTest(status=status):
                Order.objects.filter(pk=self.order.pk).update(status=status)
                self.assert_deleted()
                self.order = self.make_order(self.detail)
                self.url = reverse("order-detail", args=[self.order.pk])

    def test_staff_can_delete_order_after_source_offer_is_deleted(self):
        self.offer.delete()
        self.order.refresh_from_db()
        self.assertIsNone(self.order.offer_detail_id)
        self.assert_deleted()

    def test_anonymous_request_returns_401_without_changes(self):
        self.client.credentials()
        self.assert_error(401, "not_authenticated")

    def test_invalid_and_missing_token_values_return_401(self):
        for header in ("Token invalid", "Token", "Token "):
            with self.subTest(header=header):
                self.client.credentials(HTTP_AUTHORIZATION=header)
                self.assert_error(401, "authentication_failed")

    def test_unrelated_non_staff_roles_return_403_without_changes(self):
        for role in ("customer", "business", None):
            with self.subTest(role=role):
                user = self.make_user(f"non-staff-{role}", role)
                self.authenticate(user)
                self.assert_forbidden()

    def test_assigned_non_staff_customer_and_business_owner_are_denied(self):
        for user in (self.customer, self.owner):
            with self.subTest(user=user.username):
                self.assertFalse(user.is_staff)
                self.authenticate(user)
                self.assert_forbidden()

    def test_superuser_without_staff_is_denied(self):
        self.staff.is_staff = False
        self.staff.is_superuser = True
        self.staff.save(update_fields=["is_staff", "is_superuser"])
        self.assert_forbidden()

    def test_staff_nonexistent_order_returns_404_without_changes(self):
        missing = Order.objects.order_by("pk").last().pk + 1
        self.assertFalse(Order.objects.filter(pk=missing).exists())
        url = reverse("order-detail", args=[missing])
        self.assert_error(404, "not_found", url)

    def test_repeated_delete_returns_404_without_further_changes(self):
        self.assert_deleted()
        self.assert_error(404, "not_found")

    def test_non_staff_missing_order_is_rejected_before_lookup(self):
        self.authenticate(self.owner)
        missing = Order.objects.order_by("pk").last().pk + 1
        self.url = reverse("order-detail", args=[missing])
        self.assert_forbidden()
