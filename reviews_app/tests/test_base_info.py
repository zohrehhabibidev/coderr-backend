"""Card 37 statistics and persisted aggregation tests."""

from django.contrib.auth.models import User
from django.urls import resolve, reverse
from rest_framework.test import APITestCase

from auth_app.models import Profile
from offers_app.models import Offer
from reviews_app.api.views import BaseInfoView
from reviews_app.models import Review
from reviews_app.tests.helpers import ReviewTestHelpers


class BaseInfoTests(ReviewTestHelpers, APITestCase):
    """Verify statistics and read-only API access."""

    def setUp(self):
        super().setUp()
        self.owner = self.make_user("seller", "business")
        self.business = self.make_user("other-seller", "business")
        self.customer = self.make_user("buyer", "customer")
        self.other = self.make_user("other-buyer", "customer")
        self.reviews = [self.make_review(self.owner, self.customer, 5, 1),
                        self.make_review(self.owner, self.other, 4, 2),
                        self.make_review(self.business, self.customer, 1, 3)]
        self.offer = self.make_offer(self.owner)
        self.make_offer(self.business)
        self.url = reverse("base-info")

    def assert_statistics(
            self, reviews=3, average=3.3, businesses=2, offers=2):
        before = self.snapshot()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")
        data = response.json()
        self.assertIs(type(data), dict)
        self.assertEqual(data, dict(review_count=reviews,
                                   average_rating=average,
                                   business_profile_count=businesses,
                                   offer_count=offers))
        self.assert_statistic_types(data)
        self.assertEqual(self.snapshot(), before)

    def assert_statistic_types(self, data):
        for field in ("review_count", "business_profile_count", "offer_count"):
            self.assertIs(type(data[field]), int)
        self.assertIn(type(data["average_rating"]), (int, float))

    def test_url_resolves_to_base_info_view(self):
        self.assertEqual(self.url, "/api/base-info/")
        self.assertIs(resolve(self.url).func.view_class, BaseInfoView)
        self.assertEqual(resolve(self.url).kwargs, {})
        self.assert_statistics()

    def test_anonymous_request_succeeds_without_token(self):
        self.client.credentials()
        self.assertFalse(self.client._credentials)
        self.assert_statistics()

    def test_authenticated_customer_can_read_statistics(self):
        self.authenticate(self.customer)
        self.assert_statistics()

    def test_authenticated_business_can_read_statistics(self):
        self.authenticate(self.owner)
        self.assert_statistics()

    def test_authenticated_staff_without_profile_can_read_statistics(self):
        self.authenticate(self.make_user("staff", staff=True))
        self.assert_statistics()

    def test_authenticated_user_without_profile_can_read_statistics(self):
        self.authenticate(self.make_user("bare"))
        self.assert_statistics()

    def test_all_businesses_and_reviewers_contribute_to_global_average(self):
        self.make_review(self.business, self.other, 5, 4)
        self.assert_statistics(reviews=4, average=3.8)

    def test_average_rounds_down_and_up_to_one_decimal(self):
        self.assert_statistics(average=3.3)
        Review.objects.filter(pk=self.reviews[2].pk).update(rating=2)
        self.assert_statistics(average=3.7)

    def test_no_reviews_returns_zero_count_and_numeric_zero_average(self):
        Review.objects.all().delete()
        self.assert_statistics(reviews=0, average=0)

    def test_only_business_profiles_contribute_to_business_count(self):
        self.make_user("additional-customer", "customer")
        self.make_user("bare")
        self.make_user("staff", staff=True)
        self.assert_statistics()

    def test_all_offers_count_regardless_of_owner(self):
        for owner in (self.owner, self.business, self.owner):
            self.make_offer(owner)
        self.assert_statistics(offers=5)

    def test_empty_database_returns_exact_zero_statistics(self):
        User.objects.all().delete()
        self.assert_statistics(reviews=0, average=0.0, businesses=0, offers=0)

    def test_statistics_remain_independent_after_deletions(self):
        Review.objects.all().delete()
        self.assert_statistics(reviews=0, average=0.0)
        Offer.objects.all().delete()
        self.assert_statistics(reviews=0, average=0.0, offers=0)
        self.make_review(self.owner, self.customer, 5, 1)
        Profile.objects.all().delete()
        self.assert_statistics(reviews=1, average=5.0, businesses=0, offers=0)

    def test_review_creation_and_deletion_update_count_and_average(self):
        review = self.make_review(self.business, self.other, 5, 4)
        self.assert_statistics(reviews=4, average=3.8)
        review.delete()
        self.assert_statistics()

    def test_average_uses_persisted_rating_after_modification(self):
        review = self.reviews[2]
        review.rating = 5
        self.assert_statistics()
        review.save(update_fields=["rating"])
        review.refresh_from_db()
        self.assertEqual(review.rating, 5)
        self.assert_statistics(average=4.7)

    def assert_api_review_saved(self, method, url, payload, status):
        response = getattr(self.client, method)(url, payload, format="json")
        self.assertEqual(response.status_code, status)
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertIs(type(response.json()), dict)
        review = Review.objects.get(pk=response.json()["id"])
        self.assert_record(response.json(), review)
        self.assertEqual(review.reviewer_id, self.other.pk)
        self.assertEqual(review.business_user_id, self.business.pk)
        self.assertEqual(review.rating, payload["rating"])
        self.assertEqual(review.description, "Integration review")
        return reverse("review-detail", args=[review.pk])

    def assert_api_review_deleted(self, url):
        response = self.client.delete(url)
        self.assertEqual(response.status_code, 204)
        self.assertIsNone(response.data)
        self.assertEqual(response.content, b"")
        self.assertFalse(Review.objects.filter(
            pk=resolve(url).kwargs["pk"]).exists())

    def test_review_api_lifecycle_updates_base_info(self):
        self.authenticate(self.other)
        before = self.snapshot()
        payload = dict(business_user=self.business.pk, rating=5,
                       description="Integration review")
        url = self.assert_api_review_saved(
            "post", reverse("review-list"), payload, 201)
        self.assert_statistics(reviews=4, average=3.8)
        self.assert_api_review_saved("patch", url, {"rating": 2}, 200)
        self.assert_statistics(reviews=4, average=3.0)
        self.assert_api_review_deleted(url)
        self.assert_statistics(reviews=3, average=3.3)
        self.assertEqual(self.snapshot(), before)

    def test_offer_creation_and_deletion_update_only_offer_count(self):
        offer = self.make_offer(self.owner)
        self.assert_statistics(offers=3)
        offer.delete()
        self.assert_statistics()

    def test_business_profile_creation_and_deletion_update_only_its_count(
            self):
        user = self.make_user("new-business")
        profile = Profile.objects.create(user=user, type="business")
        self.assert_statistics(businesses=3)
        profile.delete()
        self.assertTrue(User.objects.filter(pk=user.pk).exists())
        self.assert_statistics()

    def test_profile_type_changes_update_persisted_business_count(self):
        profile = self.customer.profile
        persisted_count = 2
        for role, expected in (("business", 3), ("customer", 2)):
            with self.subTest(role=role):
                profile.type = role
                self.assert_statistics(businesses=persisted_count)
                profile.save(update_fields=["type"])
                profile.refresh_from_db()
                self.assertEqual(profile.type, role)
                self.assert_statistics(businesses=expected)
                persisted_count = expected

    def test_unsupported_methods_return_405_without_database_changes(self):
        for method in ("post", "put", "patch", "delete", "head", "trace"):
            with self.subTest(method=method):
                before = self.snapshot()
                response = getattr(self.client, method)(self.url)
                self.assertEqual(response.status_code, 405)
                self.assertEqual(self.snapshot(), before)

    def test_options_is_available_without_database_changes(self):
        before = self.snapshot()
        self.assertEqual(self.client.options(self.url).status_code, 200)
        self.assertEqual(self.snapshot(), before)
