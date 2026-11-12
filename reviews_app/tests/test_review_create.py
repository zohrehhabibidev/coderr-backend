"""Card 33 review creation contract tests using real token authentication."""

from unittest.mock import patch

from django.db import IntegrityError, transaction
from django.urls import resolve, reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from reviews_app.api.serializers import ReviewCreateSerializer
from reviews_app.api.views import ReviewListCreateView
from reviews_app.models import Review
from reviews_app.tests.helpers import ReviewTestHelpers


class ReviewCreateTests(ReviewTestHelpers, APITestCase):
    """Verify review responses, role permissions and rejected-write safety."""

    def setUp(self):
        super().setUp()
        self.owner = self.make_user("seller", "business")
        self.customer = self.make_user("buyer", "customer")
        self.other = self.make_user("other-buyer", "customer")
        self.url = reverse("review-list")
        self.payload = dict(business_user=self.owner.pk, rating=4,
                            description="Alles war toll!")
        Review.objects.create(business_user=self.owner, reviewer=self.other,
                              rating=3, description="Existing review")
        self.authenticate(self.customer)

    def assert_created(self, payload=None):
        payload = self.payload if payload is None else payload
        before = self.snapshot()
        started = timezone.now()
        response = self.client.post(self.url, payload, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertIs(type(response.json()), dict)
        review = Review.objects.get(pk=response.json()["id"])
        self.assert_creation_response(response.json(), review, payload,
                                      started)
        self.assert_creation_state(before, review, payload)
        return review

    def assert_creation_state(self, before, review, payload):
        after = self.snapshot()
        self.assertEqual(after[:-1], before[:-1])
        self.assertEqual(len(after[-1]), len(before[-1]) + 1)
        self.assertEqual([r for r in after[-1] if r["id"] != review.pk],
                         before[-1])
        self.assertEqual(review.reviewer_id, self.customer.pk)
        self.assertEqual(review.business_user_id, payload["business_user"])
        self.assertEqual(review.rating, payload["rating"])
        self.assertEqual(review.description, payload["description"])

    def assert_creation_response(self, data, review, payload, started):
        expected = {key: payload[key] for key in
                    ("business_user", "rating", "description")}
        expected.update(id=review.pk, reviewer=self.customer.pk)
        for name in ("created_at", "updated_at"):
            self.assert_timestamp(data[name], getattr(review, name), started)
            expected[name] = data[name]
        self.assertEqual(data, expected)
        for name in ("id", "business_user", "reviewer", "rating"):
            self.assertIs(type(data[name]), int)
        self.assertIs(type(data["description"]), str)
        self.assertLessEqual(review.created_at, review.updated_at)

    def assert_error(self, payload, status, codes, **kwargs):
        before = self.snapshot()
        response = self.client.post(self.url, payload, **kwargs)
        self.assertEqual(response.status_code, status)
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertIs(type(response.json()), dict)
        self.assertEqual(set(response.json()), set(codes))
        for field, code in codes.items():
            self.assert_error_content(response.data[field], code)
        self.assertEqual(self.snapshot(), before)
        if status == 401:
            self.assertEqual(response["WWW-Authenticate"], "Token")
        return response

    def assert_field_error(self, field, value, code):
        payload = {**self.payload, field: value}
        self.assert_error(payload, 400, {field: code}, format="json")

    def test_route_targets_review_creation(self):
        self.assertEqual(self.url, "/api/reviews/")
        self.assertIs(resolve(self.url).func.view_class, ReviewListCreateView)

    def test_customer_creates_review_without_any_previous_order(self):
        self.assertEqual(self.snapshot()[-2], [])
        self.assert_created()

    def test_staff_with_customer_profile_can_create(self):
        self.customer.is_staff = True
        self.customer.save(update_fields=["is_staff"])
        self.assert_created()

    def test_non_customer_profiles_and_staff_have_no_bypass(self):
        for role, staff in (("business", False), (None, False),
                            ("business", True), (None, True)):
            with self.subTest(role=role, staff=staff):
                user = self.make_user(f"denied-{role}-{staff}", role, staff)
                self.authenticate(user)
                self.assert_error(self.payload, 403,
                                  {"detail": "permission_denied"},
                                  format="json")

    def test_anonymous_request_returns_401(self):
        self.client.credentials()
        self.assert_error(self.payload, 401, {"detail": "not_authenticated"},
                          format="json")

    def test_invalid_and_malformed_tokens_return_401(self):
        for header in ("Token invalid", "Token", "Token ", "Token a b"):
            with self.subTest(header=header):
                self.client.credentials(HTTP_AUTHORIZATION=header)
                self.assert_error(self.payload, 401,
                                  {"detail": "authentication_failed"},
                                  format="json")

    def test_reviewer_and_read_only_metadata_are_server_controlled(self):
        forged = dict(reviewer=self.other.pk, id=999999,
                      created_at="2000-01-01T00:00:00Z", updated_at=None)
        review = self.assert_created({**self.payload, **forged})
        self.assertNotEqual(review.pk, forged["id"])
        self.assertEqual(review.reviewer_id, self.customer.pk)

    def test_malformed_reviewer_cannot_override_authenticated_customer(self):
        self.assert_created({**self.payload, "reviewer": {"id": "bad"}})

    def test_each_required_field_is_missing(self):
        for field in self.payload:
            with self.subTest(field=field):
                payload = {k: v for k, v in self.payload.items() if k != field}
                self.assert_error(payload, 400, {field: "required"},
                                  format="json")

    def test_empty_object_reports_all_required_fields(self):
        self.assert_error({}, 400, {k: "required" for k in self.payload},
                          format="json")

    def test_null_fields_are_rejected(self):
        for field in self.payload:
            with self.subTest(field=field):
                self.assert_field_error(field, None, "null")

    def test_invalid_business_identifiers(self):
        for value in ("abc", True, False, [], {}, [self.owner.pk]):
            with self.subTest(value=value):
                self.assert_field_error("business_user", value,
                                        "incorrect_type")

    def test_fractional_business_identifier_string_is_rejected(self):
        self.assert_field_error("business_user", f"{self.owner.pk}.5",
                                "incorrect_type")

    def test_empty_business_identifier(self):
        self.assert_field_error("business_user", "", "null")

    def test_nonexistent_business_identifiers(self):
        missing = max(self.owner.pk, self.customer.pk, self.other.pk) + 100
        for value in (missing, 0, -1):
            with self.subTest(value=value):
                self.assert_field_error("business_user", value,
                                        "does_not_exist")

    def test_existing_non_business_targets(self):
        bare = self.make_user("bare")
        staff = self.make_user("staff", staff=True)
        for target in (self.customer, self.other, bare, staff):
            with self.subTest(target=target.pk):
                self.assert_field_error("business_user", target.pk, "invalid")

    def test_invalid_rating_values(self):
        for value in ("", "bad", "1.5", 1.5, True, False, [], {}, [4]):
            with self.subTest(value=value):
                self.assert_field_error("rating", value, "invalid")

    def test_integer_ratings_from_one_to_five_are_accepted(self):
        for rating in (1, 2, 3, 4, 5):
            with self.subTest(rating=rating):
                owner = self.make_user(f"rating-seller-{rating}", "business")
                self.assert_created({**self.payload,
                                     "business_user": owner.pk,
                                     "rating": rating})

    def test_out_of_range_ratings_return_exact_errors_without_writes(self):
        for rating in (0, 6, -1, 100):
            with self.subTest(rating=rating):
                minimum = rating < 1
                code = "min_value" if minimum else "max_value"
                response = self.assert_error(
                    {**self.payload, "rating": rating}, 400,
                    {"rating": code}, format="json")
                self.assertIs(type(response.json()["rating"]), list)
                self.assertEqual(len(response.json()["rating"]), 1)
                self.assertIs(type(response.json()["rating"][0]), str)

    def test_empty_and_whitespace_descriptions(self):
        for value in ("", "   ", "\n\t"):
            with self.subTest(value=value):
                self.assert_field_error("description", value, "blank")

    def test_malformed_description_values(self):
        for value in (True, False, [], {}, ["text"]):
            with self.subTest(value=value):
                self.assert_field_error("description", value, "invalid")

    def test_non_object_request_bodies(self):
        for payload in ([], [self.payload], "bad", 7):
            with self.subTest(payload=payload):
                self.assert_error(payload, 400,
                                  {"non_field_errors": "invalid"},
                                  format="json")

    def test_malformed_json(self):
        self.assert_error('{"rating":', 400, {"detail": "parse_error"},
                          content_type="application/json")

    def test_duplicate_review_returns_400_and_preserves_original(self):
        self.assert_created()
        payload = {**self.payload, "rating": 2, "description": "Replacement"}
        self.assert_error(payload, 400, {"business_user": "invalid"},
                          format="json")

    def test_forged_reviewer_cannot_evade_duplicate_check(self):
        self.assert_created()
        payload = {**self.payload, "reviewer": self.other.pk}
        self.assert_error(payload, 400, {"business_user": "invalid"},
                          format="json")

    def test_database_enforces_unique_customer_business_pair(self):
        review = self.assert_created()
        before = self.snapshot()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Review.objects.create(business_user_id=review.business_user_id,
                                      reviewer_id=review.reviewer_id,
                                      rating=1, description="Duplicate")
        self.assertEqual(self.snapshot(), before)

    def test_database_duplicate_fallback_returns_400_without_writes(self):
        self.assert_created()
        before = self.snapshot()
        with patch.object(ReviewCreateSerializer, "validate_unique_pair"):
            response = self.client.post(self.url, self.payload, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertIs(type(response.json()), list)
        self.assert_error_content(response.data, "invalid")
        self.assertEqual(self.snapshot(), before)

    def test_same_customer_can_review_different_businesses(self):
        first = self.assert_created()
        other = self.make_user("second-seller", "business")
        second = self.assert_created(
            {**self.payload, "business_user": other.pk})
        self.assertNotEqual(first.business_user_id, second.business_user_id)
        self.assertEqual(first.reviewer_id, second.reviewer_id)

    def test_different_customers_can_review_same_business(self):
        first = self.assert_created()
        self.customer = self.make_user("second-customer", "customer")
        self.authenticate(self.customer)
        second = self.assert_created()
        self.assertNotEqual(first.reviewer_id, second.reviewer_id)
        self.assertEqual(first.business_user_id, second.business_user_id)

    def test_unicode_and_multiline_description_persists(self):
        self.assert_created({**self.payload,
                             "description": "Toll! \u2605\nVielen Dank!"})
