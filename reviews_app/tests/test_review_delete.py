"""Card 36 owner-only review deletion with real token authentication."""

from django.urls import reverse
from rest_framework.test import APITestCase

from reviews_app.models import Review
from reviews_app.tests.helpers import ReviewTestHelpers


class ReviewDeleteTests(ReviewTestHelpers, APITestCase):
    """Verify deletion responses, ownership and database isolation."""

    def setUp(self):
        super().setUp()
        self.owner = self.make_user("seller", "business")
        self.customer = self.make_user("buyer", "customer")
        self.other = self.make_user("other-buyer", "customer")
        self.review = self.make_review(self.owner, self.customer, 3, 1)
        self.make_review(self.owner, self.other, 2, 2)
        business = self.make_user("other-seller", "business")
        self.make_review(business, self.customer, 5, 3)
        offer = self.make_offer(self.owner)
        self.make_order(offer.details.get(offer_type="basic"))
        self.url = reverse("review-detail", args=[self.review.pk])
        self.authenticate(self.customer)

    def assert_deleted(self):
        before = self.snapshot()
        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, 204)
        self.assertIsNone(response.data)
        self.assertIs(type(response.content), bytes)
        self.assertEqual(response.content, b"")
        self.assertFalse(Review.objects.filter(pk=self.review.pk).exists())
        before[-1] = [row for row in before[-1]
                      if row["id"] != self.review.pk]
        self.assertEqual(self.snapshot(), before)

    def assert_rejected(self, status, code):
        before = self.snapshot()
        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, status)
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertIs(type(response.json()), dict)
        self.assertEqual(set(response.json()), {"detail"})
        self.assert_error_content(response.data["detail"], code)
        self.assertEqual(self.snapshot(), before)
        if status == 401:
            self.assertEqual(response["WWW-Authenticate"], "Token")

    def test_owner_deletes_only_target_review_with_empty_body(self):
        self.assert_deleted()

    def test_staff_owner_can_delete(self):
        self.customer.is_staff = True
        self.customer.save(update_fields=["is_staff"])
        self.assert_deleted()

    def test_anonymous_user_returns_401(self):
        self.client.credentials()
        self.assert_rejected(401, "not_authenticated")

    def test_invalid_and_malformed_tokens_return_401(self):
        for header in ("Token invalid", "Token", "Token ", "Token a b"):
            with self.subTest(header=header):
                self.client.credentials(HTTP_AUTHORIZATION=header)
                self.assert_rejected(401, "authentication_failed")

    def test_reviewed_business_cannot_delete_review(self):
        self.authenticate(self.owner)
        self.assert_rejected(403, "permission_denied")

    def test_other_reviewer_cannot_delete_review(self):
        self.authenticate(self.other)
        self.assert_rejected(403, "permission_denied")

    def test_unrelated_roles_and_staff_have_no_ownership_bypass(self):
        for role in ("customer", "business", None):
            for staff in (False, True):
                with self.subTest(role=role, staff=staff):
                    user = self.make_user(f"other-{role}-{staff}", role,
                                          staff)
                    self.authenticate(user)
                    self.assert_rejected(403, "permission_denied")

    def test_nonexistent_review_returns_404(self):
        missing = Review.objects.order_by("pk").last().pk + 1
        self.assertFalse(Review.objects.filter(pk=missing).exists())
        self.url = reverse("review-detail", args=[missing])
        self.assert_rejected(404, "not_found")

    def test_repeated_delete_returns_404_without_further_changes(self):
        self.assert_deleted()
        self.assert_rejected(404, "not_found")
