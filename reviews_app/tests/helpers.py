"""Shared Review fixtures, snapshots and response assertions."""

from datetime import datetime, timedelta, timezone as datetime_timezone

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from offers_app.tests.helpers import OfferTestHelpers
from reviews_app.models import Review


class ReviewTestHelpers(OfferTestHelpers):
    """Provide reusable Review helpers without defining a test case."""

    def snapshot(self):
        return super().snapshot() + [
            list(Review.objects.order_by("pk").values())]

    def make_review(self, business, reviewer, rating, days):
        review = Review.objects.create(
            business_user=business, reviewer=reviewer, rating=rating,
            description=f"Review {rating}\nVielen Dank! \u2605")
        created = datetime(2024, 1, 1, tzinfo=datetime_timezone.utc)
        Review.objects.filter(pk=review.pk).update(
            created_at=created, updated_at=created + timedelta(days=days))
        review.refresh_from_db()
        return review

    def assert_record(self, data, review):
        expected = dict(id=review.pk, business_user=review.business_user_id,
                        reviewer=review.reviewer_id, rating=review.rating,
                        description=review.description)
        for name in ("created_at", "updated_at"):
            self.assert_timestamp(data[name], getattr(review, name))
            expected[name] = data[name]
        self.assertEqual(data, expected)
        for name in ("id", "business_user", "reviewer", "rating"):
            self.assertIs(type(data[name]), int)
        self.assertIs(type(data["description"]), str)

    def assert_error_content(self, errors, code):
        if isinstance(errors, list):
            self.assertTrue(errors)
        for error in errors if isinstance(errors, list) else [errors]:
            self.assertIsInstance(error, str)
            self.assertTrue(error)
            self.assertEqual(error.code, code)

    def assert_timestamp(self, value, persisted, started=None):
        self.assertIs(type(value), str)
        parsed = parse_datetime(value)
        self.assertIsNotNone(parsed)
        self.assertTrue(timezone.is_aware(parsed))
        self.assertEqual(parsed, persisted)
        if started is not None:
            self.assertLessEqual(started, parsed)
            self.assertLessEqual(parsed, timezone.now())
