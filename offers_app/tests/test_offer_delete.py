from copy import deepcopy

from django.urls import reverse
from rest_framework.test import APITestCase

from offers_app.models import Offer, OfferDetail
from offers_app.tests.helpers import OfferTestHelpers
from orders_app.models import Order


class OfferDeleteTests(OfferTestHelpers, APITestCase):
    """Verify owner-only deletion and stored order history."""

    def setUp(self):
        super().setUp()
        self.owner = self.make_user("owner", "business")
        self.customer = self.make_user("customer", "customer")
        self.other = self.make_user("other", "business")
        self.offer = self.make_offer(self.owner)
        self.url = reverse("offer-detail", args=[self.offer.pk])
        self.detail_ids = set(self.offer.details.values_list("pk", flat=True))
        self.create_order_history()
        self.authenticate(self.owner)

    def create_order_history(self):
        for detail in self.offer.details.order_by("pk"):
            for state in ("in_progress", "completed", "cancelled"):
                self.make_order(detail, state)
        for owner in (self.owner, self.other):
            unrelated = self.make_offer(owner)
            for detail in unrelated.details.all():
                self.make_order(detail)
        self.make_order(None)

    def expected_deletion(self, before):
        expected = deepcopy(before)
        expected[0] = [row for row in expected[0]
                       if row["id"] != self.offer.pk]
        expected[1] = [row for row in expected[1]
                       if row["id"] not in self.detail_ids]
        for order in expected[-1]:
            if order["offer_detail_id"] in self.detail_ids:
                order["offer_detail_id"] = None
        return expected

    def assert_deleted(self):
        before = self.snapshot()
        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, 204)
        self.assertIsNone(response.data)
        self.assertIs(type(response.content), bytes)
        self.assertEqual(response.content, b"")
        self.assertFalse(Offer.objects.filter(pk=self.offer.pk).exists())
        self.assertFalse(OfferDetail.objects.filter(
            pk__in=self.detail_ids).exists())
        self.assertEqual(self.snapshot(), self.expected_deletion(before))
        self.assert_orders_preserved(before[-1])

    def assert_orders_preserved(self, before):
        self.assertEqual(Order.objects.count(), len(before))
        for original in before:
            actual = Order.objects.values().get(pk=original["id"])
            for field, value in original.items():
                with self.subTest(order=original["id"], field=field):
                    if (field == "offer_detail_id" and
                            value in self.detail_ids):
                        self.assertIsNone(actual[field])
                    else:
                        self.assertIs(type(actual[field]), type(value))
                        self.assertEqual(actual[field], value)

    def assert_error(self, status, code, url=None):
        before = self.snapshot()
        response = self.client.delete(url or self.url)
        self.assertEqual(response.status_code, status)
        self.assertEqual(response["Content-Type"], "application/json")
        data = response.json()
        self.assertIsInstance(data, dict)
        self.assertEqual(set(data), {"detail"})
        self.assertIs(type(data["detail"]), str)
        self.assertTrue(data["detail"].strip())
        self.assertEqual(response.data["detail"].code, code)
        self.assertEqual(self.snapshot(), before)

    def assert_non_owner_denied(self, role=None, staff=False):
        user = self.make_user("non-owner", role, staff)
        self.assertNotEqual(user.pk, self.offer.user_id)
        self.authenticate(user)
        self.assert_error(403, "permission_denied")

    def test_owner_deletes_all_packages_and_preserves_order_history(self):
        self.assertEqual(set(self.offer.details.values_list(
            "offer_type", flat=True)), {"basic", "standard", "premium"})
        self.assertEqual(len(self.detail_ids), 3)
        self.assert_deleted()

    def test_anonymous_delete_returns_401_without_changes(self):
        self.client.credentials()
        self.assert_error(401, "not_authenticated")

    def test_invalid_token_returns_401_without_changes(self):
        self.client.credentials(HTTP_AUTHORIZATION="Token invalid")
        self.assert_error(401, "authentication_failed")

    def test_non_owner_customer_returns_403_without_changes(self):
        self.assert_non_owner_denied("customer")

    def test_non_owner_business_returns_403_without_changes(self):
        self.assert_non_owner_denied("business")

    def test_non_owner_customer_staff_returns_403_without_changes(self):
        self.assert_non_owner_denied("customer", staff=True)

    def test_non_owner_business_staff_returns_403_without_changes(self):
        self.assert_non_owner_denied("business", staff=True)

    def test_staff_without_profile_returns_403_without_changes(self):
        self.assert_non_owner_denied(staff=True)

    def test_user_without_profile_returns_403_without_changes(self):
        self.assert_non_owner_denied()

    def test_nonexistent_offer_returns_404_without_changes(self):
        missing = Offer.objects.order_by("pk").last().pk + 1
        self.assertFalse(Offer.objects.filter(pk=missing).exists())
        url = reverse("offer-detail", args=[missing])
        self.assert_error(404, "not_found", url)

    def test_repeated_delete_returns_404_without_further_changes(self):
        self.assert_deleted()
        self.assert_error(404, "not_found")

    def test_offer_without_orders_can_be_deleted(self):
        Order.objects.filter(offer_detail_id__in=self.detail_ids).delete()
        self.assert_deleted()

    def test_staff_owner_can_delete_offer(self):
        self.owner.is_staff = True
        self.owner.save(update_fields=["is_staff"])
        self.assert_deleted()
