from datetime import datetime, timezone

from django.contrib.auth.models import User
from django.urls import resolve, reverse
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from auth_app.api.views import ProfileDetailView
from auth_app.models import Profile


class ProfileDetailTests(APITestCase):
    fields = [
        "user", "username", "first_name", "last_name", "file", "location",
        "tel", "description", "working_hours", "type", "email", "created_at",
    ]
    empty_fields = [
        "first_name", "last_name", "location", "tel", "description",
        "working_hours",
    ]

    def setUp(self):
        self.customer = User.objects.create_user(username="customer")
        self.create_business_profile()
        self.customer_profile = Profile.objects.create(
            user=self.customer, type="customer"
        )

    def create_business_profile(self):
        self.business = User.objects.create_user(
            username="business", first_name="Max", last_name="Mustermann",
            email="max@example.com",
            date_joined=datetime(2023, 1, 1, 12, tzinfo=timezone.utc),
        )
        self.business_profile = Profile.objects.create(
            user=self.business, type="business", location="Berlin",
            tel="123456789", description="Business description",
            working_hours="9-17", file="profiles/picture.jpg",
        )

    def authenticate(self, user):
        token, _ = Token.objects.get_or_create(user=user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

    def get_profile(self, user_id):
        return self.client.get(reverse("profile-detail", args=[user_id]))

    def test_customer_retrieves_own_empty_profile(self):
        self.authenticate(self.customer)
        response = self.get_profile(self.customer.pk)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["user"], self.customer.pk)
        self.assertEqual(response.data["type"], "customer")
        self.assertIsNone(response.data["file"])
        for field in self.empty_fields:
            with self.subTest(field=field):
                self.assertEqual(response.data[field], "")

    def test_business_retrieves_populated_profile(self):
        self.authenticate(self.business)
        response = self.get_profile(self.business.pk)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, self.expected_business_data())
        self.assertEqual(list(response.data), self.fields)

    def expected_business_data(self):
        return {
            "user": self.business.pk, "username": "business",
            "first_name": "Max", "last_name": "Mustermann",
            "file": "http://testserver/media/profiles/picture.jpg",
            "location": "Berlin", "tel": "123456789",
            "description": "Business description", "working_hours": "9-17",
            "type": "business", "email": "max@example.com",
            "created_at": "2023-01-01T12:00:00Z",
        }

    def test_authenticated_users_retrieve_other_profiles(self):
        for requester, target in (
            (self.customer, self.business), (self.business, self.customer),
        ):
            with self.subTest(requester=requester.username):
                self.authenticate(requester)
                response = self.get_profile(target.pk)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.data["user"], target.pk)
                self.assertEqual(response.data["username"], target.username)

    def test_missing_authentication_returns_401(self):
        response = self.get_profile(self.customer.pk)
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response["WWW-Authenticate"], "Token")

    def test_invalid_token_returns_401(self):
        self.client.credentials(HTTP_AUTHORIZATION="Token invalid")
        self.assertEqual(self.get_profile(self.customer.pk).status_code, 401)

    def test_nonexistent_user_returns_404(self):
        self.authenticate(self.customer)
        self.assertEqual(self.get_profile(999999).status_code, 404)

    def test_user_without_profile_returns_404(self):
        user = User.objects.create_user(username="without_profile")
        self.authenticate(self.customer)
        self.assertEqual(self.get_profile(user.pk).status_code, 404)

    def test_lookup_uses_user_id_instead_of_profile_id(self):
        self.assertNotEqual(self.business.pk, self.business_profile.pk)
        self.assertEqual(self.business.pk, self.customer_profile.pk)
        self.authenticate(self.customer)
        response = self.get_profile(self.business.pk)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, self.expected_business_data())

    def test_url_resolves_to_profile_detail_view(self):
        url = reverse("profile-detail", args=[self.business.pk])
        self.assertEqual(url, f"/api/profile/{self.business.pk}/")
        match = resolve(url)
        self.assertIs(match.func.view_class, ProfileDetailView)
        self.assertEqual(match.kwargs, {"pk": self.business.pk})
