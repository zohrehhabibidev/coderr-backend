"""Card 38 order lifecycle and count separation fixtures."""

from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from auth_app.tests import test_registration as registration
from offers_app.models import Offer
from offers_app.tests import test_offer_create as offers
from offers_app.tests.helpers import OfferTestHelpers
from orders_app.models import Order
from orders_app.tests import test_order_list as listing
from reviews_app.models import Review
from reviews_app.tests import test_base_info as statistics
from reviews_app.tests.helpers import ReviewTestHelpers


class OrderLifecycleTests(OfferTestHelpers, APITestCase):
    """Prepare two businesses for the API lifecycle scenario."""

    package_snapshot = listing.OrderListTests.package_snapshot
    package_fields = listing.OrderListTests.package_fields
    assert_response_types = listing.OrderListTests.assert_response_types
    assert_timestamp = listing.OrderListTests.assert_timestamp
    assert_order = listing.OrderListTests.assert_order

    def setUp(self):
        super().setUp()
        self.started = timezone.now()
        self.owner = self.make_user("seller", "business")
        self.other = self.make_user("other-seller", "business")
        self.customer = self.make_user("buyer", "customer")
        self.staff = self.make_user("staff", staff=True)
        self.offer = self.make_offer(self.owner)
        self.detail = self.offer.details.get(offer_type="basic")
        other_offer = self.make_offer(self.other)
        other_detail = other_offer.details.get(offer_type="basic")
        self.other_order = self.make_order(other_detail, "in_progress")
        self.url = reverse("order-list")
        self.authenticate(self.customer)

    def assert_order_count(self, business, expected):
        url = reverse("order-count", args=[business.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIs(type(data), dict)
        self.assertEqual(data, {"order_count": expected})
        self.assertIs(type(data["order_count"]), int)

    def assert_completed_count(self, business, expected):
        url = reverse("completed-order-count", args=[business.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")
        data = response.json()
        self.assertIs(type(data), dict)
        self.assertEqual(data, {"completed_order_count": expected})
        self.assertIs(type(data["completed_order_count"]), int)

    def assert_counts(self, active, completed):
        self.assert_order_count(self.owner, active)
        self.assert_completed_count(self.owner, completed)
        self.assert_order_count(self.other, 1)
        self.assert_completed_count(self.other, 0)

    def create_order(self):
        response = self.client.post(
            self.url, {"offer_detail_id": self.detail.pk}, format="json",
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertIs(type(data), dict)
        self.assertEqual(data["customer_user"], self.customer.pk)
        self.assertEqual(data["business_user"], self.owner.pk)
        self.assertEqual(data["status"], "in_progress")
        order = Order.objects.get(pk=data["id"])
        self.assertEqual(order.offer_detail_id, self.detail.pk)
        return order

    def complete_order(self, order):
        self.authenticate(self.owner)
        url = reverse("order-detail", args=[order.pk])
        response = self.client.patch(url, {"status": "completed"},
                                     format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertIs(type(response.json()), dict)
        order.refresh_from_db()
        self.assertEqual(order.status, "completed")
        self.assertEqual(order.customer_user_id, self.customer.pk)
        self.assertEqual(order.business_user_id, self.owner.pk)
        self.assertEqual(order.offer_detail_id, self.detail.pk)
        self.assert_order(response.json(), order)

    def delete_order(self, order):
        self.authenticate(self.staff)
        url = reverse("order-detail", args=[order.pk])
        response = self.client.delete(url)
        self.assertEqual(response.status_code, 204)
        self.assertIsNone(response.data)
        self.assertIs(type(response.content), bytes)
        self.assertEqual(response.content, b"")
        self.assertFalse(Order.objects.filter(pk=order.pk).exists())

    def test_order_lifecycle(self):
        other = Order.objects.filter(pk=self.other_order.pk)
        original = other.values().get()
        order = self.create_order()
        self.assert_counts(1, 0)
        self.complete_order(order)
        self.assert_counts(0, 1)
        self.assertEqual(other.values().get(), original)
        self.delete_order(order)
        self.authenticate(self.customer)
        self.assert_counts(0, 0)
        self.assertTrue(other.exists())
        self.assertEqual(other.values().get(), original)

    def change_package_price(self):
        self.authenticate(self.owner)
        price = self.detail.price + 50
        url = reverse("offer-detail", args=[self.offer.pk])
        payload = {"details": [{"offer_type": "basic", "price": str(price)}]}
        response = self.client.patch(url, payload, format="json")
        self.assertEqual(response.status_code, 200)
        details = {row["offer_type"]: row
                   for row in response.json()["details"]}
        self.assertEqual(details["basic"]["id"], self.detail.pk)
        self.assertEqual(details["basic"]["price"], float(price))
        self.detail.refresh_from_db()
        self.assertEqual(self.detail.price, price)

    def test_offer_price_patch_preserves_purchased_order_snapshot(self):
        order = self.create_order()
        before = Order.objects.values().get(pk=order.pk)
        self.assertEqual(self.package_snapshot(order),
                         self.package_snapshot(self.detail))
        self.change_package_price()
        self.authenticate(self.customer)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertIs(type(response.json()), list)
        rows = {row["id"]: row for row in response.json()}
        self.assert_order(rows[order.pk], order)
        self.assertEqual(Order.objects.values().get(pk=order.pk), before)


class MultiRoleIntegrationTests(ReviewTestHelpers, APITestCase):
    """Run the registered customer and business journey through the API."""

    detail = offers.OfferCreateTests.detail
    add_detail_ids = offers.OfferCreateTests.add_detail_ids
    assert_detail_types = offers.OfferCreateTests.assert_detail_types
    assert_creation_response = offers.OfferCreateTests.assert_creation_response
    assert_offer_persisted = offers.OfferCreateTests.assert_offer_persisted
    assert_details_persisted = offers.OfferCreateTests.assert_details_persisted
    assert_detail_persisted = offers.OfferCreateTests.assert_detail_persisted
    package_fields = listing.OrderListTests.package_fields
    package_snapshot = listing.OrderListTests.package_snapshot
    assert_response_types = listing.OrderListTests.assert_response_types
    assert_order = listing.OrderListTests.assert_order
    assert_registration_response = (
        registration.RegistrationTestBase.assert_registration_response)
    assert_registration_records = (
        registration.RegistrationTestBase.assert_registration_records)
    assert_statistic_types = statistics.BaseInfoTests.assert_statistic_types

    def setUp(self):
        super().setUp()
        self.started = timezone.now()

    def request(self, method, route, status=200, payload=None, args=None):
        response = getattr(self.client, method)(
            reverse(route, args=args), payload or {}, format="json")
        self.assertEqual(response.status_code, status, response.data)
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertIs(type(response.json()), dict)
        return response

    def register(self, role):
        payload = dict(username=f"journey-{role}", type=role,
                       email=f"{role}@example.com", password="StrongPass123!",
                       repeated_password="StrongPass123!")
        data = self.request("post", "registration", 201, payload).json()
        self.assert_registration_response(data, payload)
        return payload, data

    def login(self, account):
        payload, registered = account
        credentials = {key: payload[key] for key in ("username", "password")}
        data = self.request("post", "login", payload=credentials).json()
        self.assert_registration_response(data, payload)
        self.assertEqual(data["user_id"], registered["user_id"])
        self.assertTrue(data["token"])
        user = User.objects.get(pk=data["user_id"])
        self.assert_registration_records(user, payload, data["token"])
        self.assertTrue(user.check_password(payload["password"]))
        return user, data["token"]

    def use_token(self, token):
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token}")

    def read_profile(self, user, token):
        self.use_token(token)
        data = self.request("get", "profile-detail", args=[user.pk]).json()
        expected = dict(user=user.pk, username=user.username, email=user.email,
                        type=user.profile.type, file=None)
        expected.update({field: "" for field in (
            "first_name", "last_name", "location", "tel", "description",
            "working_hours")})
        self.assert_timestamp(data["created_at"], user.date_joined)
        self.assertEqual(data, dict(expected, created_at=data["created_at"]))

    def publish_offer(self):
        self.payload = dict(title="Design", image=None, description="Logo",
                            details=[self.detail(kind) for kind in
                                     ("basic", "standard", "premium")])
        response = self.request("post", "offer-list", 201, self.payload)
        data = response.json()
        package = next(detail for detail in data["details"]
                       if detail["offer_type"] == "standard")
        offer = Offer.objects.get(pk=data["id"])
        self.assert_creation_response(response, offer)
        self.assert_offer_persisted(offer)
        self.assert_details_persisted(offer)
        return package

    def purchase(self, package):
        data = self.request("post", "order-list", 201,
                            {"offer_detail_id": package["id"]}).json()
        order = Order.objects.get(pk=data["id"])
        self.assertEqual(order.customer_user_id, self.customer.pk)
        self.assertEqual(order.business_user_id, self.business.pk)
        self.assertEqual(order.offer_detail_id, package["id"])
        self.assertEqual(order.status, "in_progress")
        snapshot = self.package_snapshot(order)
        self.assertEqual(dict(snapshot, price=float(order.price)),
                         {key: package[key] for key in self.package_fields})
        self.assert_order(data, order)
        return order

    def finish(self, order):
        before = Order.objects.values().get(pk=order.pk)
        data = self.request("patch", "order-detail", payload={
            "status": "completed"}, args=[order.pk]).json()
        order.refresh_from_db()
        self.assertEqual(order.status, "completed")
        after = Order.objects.values().get(pk=order.pk)
        self.assertEqual(after, dict(before, status="completed",
                                     updated_at=order.updated_at))
        self.assert_order(data, order)

    def review(self):
        payload = dict(business_user=self.business.pk, rating=4,
                       description="Great design")
        data = self.request("post", "review-list", 201, payload).json()
        review = Review.objects.get(pk=data["id"])
        self.assertEqual(review.reviewer_id, self.customer.pk)
        self.assertEqual(review.business_user_id, self.business.pk)
        self.assertEqual(review.rating, payload["rating"])
        self.assertEqual(review.description, payload["description"])
        self.assert_record(data, review)

    def read_statistics(self):
        before = self.snapshot()
        for route, field, count in (
                ("order-count", "order_count", 0),
                ("completed-order-count", "completed_order_count", 1)):
            data = self.request("get", route, args=[self.business.pk]).json()
            self.assertEqual(data, {field: count})
            self.assertIs(type(data[field]), int)
        self.read_base_info()
        self.assertEqual(self.snapshot(), before)

    def read_base_info(self):
        data = self.request("get", "base-info").json()
        self.assertEqual(data, dict(review_count=1, average_rating=4.0,
                                   business_profile_count=1, offer_count=1))
        self.assert_statistic_types(data)

    def test_registered_customer_and_business_complete_order_and_review(self):
        buyer, seller = self.register("customer"), self.register("business")
        self.customer, customer_token = self.login(buyer)
        self.business, business_token = self.login(seller)
        self.read_profile(self.customer, customer_token)
        self.read_profile(self.business, business_token)
        package = self.publish_offer()
        self.use_token(customer_token)
        order = self.purchase(package)
        self.use_token(business_token)
        self.finish(order)
        self.use_token(customer_token)
        self.review()
        self.read_statistics()
