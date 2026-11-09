from django.contrib.auth.models import User
from django.urls import resolve, reverse
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from auth_app.api.views import BusinessProfileListView
from auth_app.models import Profile


class BusinessProfileListTests(APITestCase):
    """Verify the business list contract using authenticated API requests."""

    fields = [
        "user", "username", "first_name", "last_name", "file",
        "location", "tel", "description", "working_hours", "type",
    ]
    text_values = {
        "first_name": "Max", "last_name": "Mustermann",
        "location": "Berlin", "tel": "030123456",
        "description": "Business description", "working_hours": "9-17",
    }

    def setUp(self):
        self.business = User.objects.create_user(
            username="business", first_name="Max", last_name="Mustermann",
        )
        self.create_business_profile()
        self.customer = User.objects.create_user(username="customer")
        Profile.objects.create(user=self.customer, type="customer")
        self.url = reverse("business-profiles")

    def create_business_profile(self):
        Profile.objects.create(
            user=self.business, type="business", location="Berlin",
            tel="030123456", description="Business description",
            working_hours="9-17",
        )

    def authenticate(self, user):
        token = Token.objects.create(user=user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

    def assert_profile_schema(self, response):
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.json(), list)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(list(response.data[0]), self.fields)
        self.assertEqual(response.data[0]["user"], self.business.pk)
        self.assertEqual(response.data[0]["username"], "business")
        self.assertEqual(response.data[0]["type"], "business")
        self.assertIsNone(response.data[0]["file"])

    def test_customer_can_access_business_profiles(self):
        self.authenticate(self.customer)
        response = self.client.get(self.url)
        self.assert_profile_schema(response)
        for field, value in self.text_values.items():
            with self.subTest(field=field):
                self.assertEqual(response.data[0][field], value)

    def test_unset_text_fields_return_empty_strings(self):
        self.business.first_name = self.business.last_name = ""
        self.business.save(update_fields=["first_name", "last_name"])
        Profile.objects.filter(user=self.business).delete()
        Profile.objects.create(user=self.business, type="business")
        self.authenticate(self.customer)
        response = self.client.get(self.url)
        self.assert_profile_schema(response)
        for field in self.text_values:
            with self.subTest(field=field):
                self.assertEqual(response.data[0][field], "")

    def test_unauthenticated_user_returns_401(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 401)

    def test_invalid_token_returns_401(self):
        self.client.credentials(HTTP_AUTHORIZATION="Token invalid")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 401)

    def test_business_can_access_business_profiles(self):
        self.authenticate(self.business)
        response = self.client.get(self.url)
        self.assert_profile_schema(response)

    def test_no_business_profiles_returns_empty_list(self):
        Profile.objects.filter(type="business").delete()
        self.authenticate(self.customer)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    def test_business_profiles_url_resolves_to_list_view(self):
        self.assertEqual(self.url, "/api/profiles/business/")
        self.assertIs(
            resolve(self.url).func.view_class, BusinessProfileListView,
        )
