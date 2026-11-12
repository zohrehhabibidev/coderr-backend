"""Card 35 partial review updates with real token authentication."""

from copy import deepcopy

from django.urls import resolve, reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from reviews_app.api.views import ReviewDetailView
from reviews_app.models import Review
from reviews_app.tests.helpers import ReviewTestHelpers


class ReviewPatchTests(ReviewTestHelpers, APITestCase):
    """Verify ownership, validation, exact responses and write isolation."""

    def setUp(self):
        super().setUp()
        self.owner = self.make_user("seller", "business")
        self.customer = self.make_user("buyer", "customer")
        self.other = self.make_user("other-buyer", "customer")
        self.review = self.make_review(self.owner, self.customer, 3, 1)
        self.make_review(self.owner, self.other, 2, 2)
        self.offer = self.make_offer(self.owner)
        self.make_order(self.offer.details.get(offer_type="basic"))
        self.url = reverse("review-detail", args=[self.review.pk])
        self.authenticate(self.customer)

    def assert_updated(self, payload):
        before = self.snapshot()
        started = timezone.now()
        response = self.client.patch(self.url, payload, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertIs(type(response.json()), dict)
        self.review.refresh_from_db()
        self.assert_record(response.json(), self.review)
        self.assert_update_state(before, payload, started)

    def assert_update_state(self, before, payload, started):
        expected = deepcopy(before)
        row = next(r for r in expected[-1] if r["id"] == self.review.pk)
        if payload:
            self.assertGreater(self.review.updated_at, row["updated_at"])
            self.assertLessEqual(started, self.review.updated_at)
            self.assertLessEqual(self.review.updated_at, timezone.now())
            row.update(payload, updated_at=self.review.updated_at)
        self.assertEqual(self.snapshot(), expected)

    def assert_rejected(self, payload, status, codes, **kwargs):
        before = self.snapshot()
        response = self.client.patch(self.url, payload, **kwargs)
        self.assertEqual(response.status_code, status)
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertIs(type(response.json()), dict)
        self.assertEqual(set(response.json()), set(codes))
        for field, code in codes.items():
            self.assert_error_content(response.data[field], code)
        self.assertEqual(self.snapshot(), before)
        if status == 401:
            self.assertEqual(response["WWW-Authenticate"], "Token")

    def assert_invalid(self, payload, codes):
        self.assert_rejected(payload, 400, codes, format="json")

    def assert_denied(self, status, code):
        self.assert_rejected({"rating": 5}, status, {"detail": code},
                             format="json")

    def test_url_routes_to_review_detail(self):
        self.assertEqual(self.url, f"/api/reviews/{self.review.pk}/")
        match = resolve(self.url)
        self.assertIs(match.func.view_class, ReviewDetailView)
        self.assertEqual(match.kwargs, {"pk": self.review.pk})

    def test_owner_updates_rating_only(self):
        self.assert_updated({"rating": 5})

    def test_owner_updates_description_only(self):
        self.assert_updated({"description": "Vielen Dank!\n\u2605 Excellent"})

    def test_owner_updates_both_fields(self):
        self.assert_updated({"rating": 1, "description": "Changed review"})

    def test_empty_patch_preserves_every_row_and_updated_at(self):
        self.assert_updated({})

    def test_each_integer_rating_from_one_to_five(self):
        for rating in range(1, 6):
            with self.subTest(rating=rating):
                self.assert_updated({"rating": rating})

    def test_staff_owner_can_update(self):
        self.customer.is_staff = True
        self.customer.save(update_fields=["is_staff"])
        self.assert_updated({"rating": 4})

    def test_invalid_rating_types_and_blank_values(self):
        for value in ("", " ", "bad", "1.5", 1.5, True, False,
                      [], {}, [4]):
            with self.subTest(value=value):
                self.assert_invalid({"rating": value}, {"rating": "invalid"})

    def test_null_rating(self):
        self.assert_invalid({"rating": None}, {"rating": "null"})

    def test_ratings_below_minimum(self):
        for value in (0, -1, -100):
            with self.subTest(value=value):
                self.assert_invalid({"rating": value},
                                    {"rating": "min_value"})

    def test_ratings_above_maximum(self):
        for value in (6, 100):
            with self.subTest(value=value):
                self.assert_invalid({"rating": value},
                                    {"rating": "max_value"})

    def test_null_description(self):
        self.assert_invalid({"description": None}, {"description": "null"})

    def test_blank_descriptions(self):
        for value in ("", "   ", "\n\t"):
            with self.subTest(value=value):
                self.assert_invalid({"description": value},
                                    {"description": "blank"})

    def test_invalid_description_types(self):
        for value in (True, False, [], {}, ["text"]):
            with self.subTest(value=value):
                self.assert_invalid({"description": value},
                                    {"description": "invalid"})

    def test_invalid_rating_does_not_save_valid_description(self):
        self.assert_invalid({"rating": 6, "description": "Must not persist"},
                            {"rating": "max_value"})

    def test_invalid_description_does_not_save_valid_rating(self):
        self.assert_invalid({"rating": 5, "description": None},
                            {"description": "null"})

    def test_both_invalid_fields_report_errors(self):
        self.assert_invalid({"rating": 0, "description": ""},
                            {"rating": "min_value", "description": "blank"})

    def forbidden_fields(self):
        return dict(id=999999, reviewer=self.other.pk,
                    business_user=self.other.pk,
                    created_at="2000-01-01T00:00:00Z", updated_at=None,
                    unknown="extra", reviewer_id=self.other.pk,
                    business_user_id=self.other.pk)

    def test_read_only_and_unknown_fields_alone_and_with_valid_update(self):
        for name, value in self.forbidden_fields().items():
            for valid in ({}, {"rating": 5, "description": "Forged"}):
                with self.subTest(field=name, valid=valid):
                    self.assert_invalid({**valid, name: value},
                                        {name: "invalid"})

    def test_multiple_forged_fields_are_all_rejected(self):
        fields = self.forbidden_fields()
        self.assert_invalid({"rating": 5, **fields},
                            {name: "invalid" for name in fields})

    def test_malformed_read_only_fields_are_rejected(self):
        for name in ("id", "reviewer", "business_user", "created_at",
                     "updated_at"):
            with self.subTest(field=name):
                self.assert_invalid({name: {"bad": []}}, {name: "invalid"})

    def test_non_object_json_bodies(self):
        for value in ([], [{"rating": 5}], "bad", 7, True):
            with self.subTest(value=value):
                self.assert_invalid(value, {"non_field_errors": "invalid"})

    def test_malformed_json_leaves_all_data_unchanged(self):
        self.assert_rejected('{"rating":', 400, {"detail": "parse_error"},
                             content_type="application/json")

    def test_anonymous_user_returns_401(self):
        self.client.credentials()
        self.assert_denied(401, "not_authenticated")

    def test_invalid_and_malformed_tokens_return_401(self):
        for header in ("Token invalid", "Token", "Token ", "Token a b"):
            with self.subTest(header=header):
                self.client.credentials(HTTP_AUTHORIZATION=header)
                self.assert_denied(401, "authentication_failed")

    def test_reviewed_business_cannot_update_review(self):
        self.authenticate(self.owner)
        self.assert_denied(403, "permission_denied")

    def test_unrelated_customer_cannot_update_review(self):
        self.authenticate(self.other)
        self.assert_denied(403, "permission_denied")

    def test_unrelated_roles_and_staff_have_no_ownership_bypass(self):
        for role in ("customer", "business", None):
            for staff in (False, True):
                with self.subTest(role=role, staff=staff):
                    user = self.make_user(f"other-{role}-{staff}", role,
                                          staff)
                    self.authenticate(user)
                    self.assert_denied(403, "permission_denied")

    def test_nonexistent_review_returns_404(self):
        missing = Review.objects.order_by("pk").last().pk + 1
        self.assertFalse(Review.objects.filter(pk=missing).exists())
        self.url = reverse("review-detail", args=[missing])
        self.assert_denied(404, "not_found")

    def test_options_advertises_patch_delete_and_options(self):
        before = self.snapshot()
        response = self.client.options(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertIs(type(response.json()), dict)
        self.assertEqual(set(response["Allow"].split(", ")),
                         {"PATCH", "DELETE", "OPTIONS"})
        self.assertEqual(self.snapshot(), before)

    def test_unsupported_methods_return_405_without_changes(self):
        for method in ("get", "post", "put", "head"):
            with self.subTest(method=method):
                self.assert_method_not_allowed(method)

    def assert_method_not_allowed(self, method):
        before = self.snapshot()
        response = getattr(self.client, method)(self.url)
        self.assertEqual(response.status_code, 405)
        self.assertEqual(set(response["Allow"].split(", ")),
                         {"PATCH", "DELETE", "OPTIONS"})
        if method != "head":
            self.assertEqual(response["Content-Type"], "application/json")
            self.assertIs(type(response.json()), dict)
            self.assertEqual(set(response.json()), {"detail"})
            self.assert_error_content(response.data["detail"],
                                      "method_not_allowed")
        self.assertEqual(self.snapshot(), before)
