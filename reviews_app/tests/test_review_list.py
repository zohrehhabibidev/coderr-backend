"""Card 34 GET contract and current query-validation behavior tests."""

from django.urls import resolve, reverse
from rest_framework.test import APITestCase

from reviews_app.api.views import ReviewListCreateView
from reviews_app.models import Review
from reviews_app.tests.helpers import ReviewTestHelpers


class ReviewListTests(ReviewTestHelpers, APITestCase):
    """Check authenticated listing, exact records and read-only safety."""

    def setUp(self):
        super().setUp()
        self.owner = self.make_user("seller", "business")
        self.business = self.make_user("other-seller", "business")
        self.customer = self.make_user("buyer", "customer")
        self.other = self.make_user("other-buyer", "customer")
        self.url = reverse("review-list")
        self.reviews = [self.make_review(self.owner, self.customer, 4, 3),
                        self.make_review(self.business, self.other, 1, 1),
                        self.make_review(self.owner, self.other, 5, 4),
                        self.make_review(self.business, self.customer, 2, 2)]
        self.make_offer(self.owner)
        self.authenticate(self.customer)

    def assert_list(self, reviews, query="", ordered=False):
        before = self.snapshot()
        response = self.client.get(self.url + query)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")
        data = response.json()
        self.assertIs(type(data), list)
        self.assertCountEqual([r["id"] for r in data], [r.pk for r in reviews])
        for row in data:
            self.assert_record(row, Review.objects.get(pk=row["id"]))
        if ordered:
            self.assertEqual([row["id"] for row in data],
                             [review.pk for review in reviews])
        self.assertEqual(self.snapshot(), before)

    def assert_error(self, query, status, codes):
        before = self.snapshot()
        response = self.client.get(self.url + query)
        self.assertEqual(response.status_code, status)
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertIs(type(response.json()), dict)
        self.assertEqual(set(response.json()), set(codes))
        for field, code in codes.items():
            self.assert_error_content(response.data[field], code)
        if status == 401:
            self.assertEqual(response["WWW-Authenticate"], "Token")
        self.assertEqual(self.snapshot(), before)

    def test_url_resolution_and_get_availability(self):
        self.assertEqual(self.url, "/api/reviews/")
        self.assertIs(resolve(self.url).func.view_class, ReviewListCreateView)
        self.assert_list(self.reviews)

    def test_unfiltered_list_includes_other_customers_and_businesses(self):
        self.assertEqual(self.snapshot()[-2], [])
        self.assert_list(self.reviews)

    def test_empty_database_returns_exact_empty_array(self):
        Review.objects.all().delete()
        self.assert_list([])

    def test_customer_can_read_all_reviews(self):
        self.assert_list(self.reviews)

    def test_business_can_read_all_reviews(self):
        self.authenticate(self.owner)
        self.assert_list(self.reviews)

    def test_staff_without_profile_can_read_all_reviews(self):
        staff = self.make_user("staff", staff=True)
        self.authenticate(staff)
        self.assert_list(self.reviews)

    def test_authenticated_user_without_profile_can_read_all_reviews(self):
        self.authenticate(self.make_user("bare"))
        self.assert_list(self.reviews)

    def test_anonymous_request_returns_authentication_error(self):
        self.client.credentials()
        self.assert_error("", 401, {"detail": "not_authenticated"})

    def test_invalid_and_malformed_token_headers_return_401(self):
        for header in ("Token invalid", "Token", "Token ", "Token a b"):
            with self.subTest(header=header):
                self.client.credentials(HTTP_AUTHORIZATION=header)
                self.assert_error("", 401, {"detail": "authentication_failed"})

    def test_business_filter_selects_only_requested_business(self):
        self.assert_list([self.reviews[0], self.reviews[2]],
                         f"?business_user_id={self.owner.pk}")

    def test_reviewer_filter_selects_only_requested_customer(self):
        self.assert_list([self.reviews[0], self.reviews[3]],
                         f"?reviewer_id={self.customer.pk}")

    def test_combined_filters_return_only_intersection(self):
        self.assert_list([self.reviews[0]],
                         f"?business_user_id={self.owner.pk}"
                         f"&reviewer_id={self.customer.pk}")

    def test_nonexistent_filter_ids_return_empty_arrays(self):
        missing = max(self.owner.pk, self.business.pk,
                      self.customer.pk, self.other.pk) + 100
        for query in (f"?business_user_id={missing}",
                      f"?reviewer_id={missing}",
                      f"?business_user_id={missing}&reviewer_id={missing}"):
            with self.subTest(query=query):
                self.assert_list([], query)

    def test_rating_order_uses_deliberately_unsorted_ratings(self):
        expected = [self.reviews[i] for i in (1, 3, 0, 2)]
        self.assert_list(expected, "?ordering=rating", ordered=True)

    def test_updated_at_order_uses_distinct_persisted_timestamps(self):
        expected = [self.reviews[i] for i in (1, 3, 0, 2)]
        self.assert_list(expected, "?ordering=updated_at", ordered=True)

    def test_each_filter_combines_with_each_supported_ordering(self):
        cases = (("business_user_id", self.business.pk, (1, 3)),
                 ("reviewer_id", self.customer.pk, (3, 0)))
        for field, value, indices in cases:
            for ordering in ("rating", "updated_at"):
                with self.subTest(field=field, ordering=ordering):
                    self.assert_list([self.reviews[i] for i in indices],
                                     f"?{field}={value}&ordering={ordering}",
                                     ordered=True)

    def test_both_filters_combine_with_ordering(self):
        for ordering in ("rating", "updated_at"):
            with self.subTest(ordering=ordering):
                self.assert_list([self.reviews[0]],
                                 f"?business_user_id={self.owner.pk}"
                                 f"&reviewer_id={self.customer.pk}"
                                 f"&ordering={ordering}", ordered=True)

    def test_omitted_ordering_has_no_required_default_order(self):
        self.assert_list([self.reviews[0], self.reviews[3]],
                         f"?reviewer_id={self.customer.pk}")

    def test_current_serializer_rejects_invalid_integer_filters(self):
        """HTTP 400 reflects current validation beyond documented statuses."""
        for field in ("business_user_id", "reviewer_id"):
            for value in ("", "abc", "1.5", "true", "[]", "{}", "null"):
                with self.subTest(field=field, value=value):
                    self.assert_error(f"?{field}={value}", 400,
                                      {field: "invalid"})

    def test_current_serializer_rejects_invalid_ordering(self):
        for value in ("", "-rating", "-updated_at", "id", "rating,updated_at"):
            with self.subTest(value=value):
                self.assert_error(f"?ordering={value}", 400,
                                  {"ordering": "invalid_choice"})

    def test_malformed_query_values_return_validation_errors(self):
        for query in ("?business_user_id", "?business_user_id=%00",
                      "?business_user_id=1&business_user_id=bad"):
            with self.subTest(query=query):
                self.assert_error(query, 400, {"business_user_id": "invalid"})
        self.assert_error("?reviewer_id=bad&ordering=bad", 400,
                          {"reviewer_id": "invalid",
                           "ordering": "invalid_choice"})

    def test_current_unknown_query_keys_and_pagination_are_ignored(self):
        """Characterize unspecified keys without adding a contract rule."""
        for query in ("?page=1&page_size=1", "?business_user_id[]=bad",
                      "?unknown=%ZZ"):
            with self.subTest(query=query):
                self.assert_list(self.reviews, query)
