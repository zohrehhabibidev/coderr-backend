from django.contrib.auth.models import User
from django.urls import resolve, reverse
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from auth_app.api.views import CustomerProfileListView
from auth_app.models import Profile


class CustomerProfileListTests(APITestCase):
    """Verify customer profiles with the teacher-approved flexible schema."""

    fields = [
        "user", "username", "first_name", "last_name", "file", "type",
    ]

    def setUp(self):
        self.customer = User.objects.create_user(username="customer")
        Profile.objects.create(user=self.customer, type="customer")
        self.business = User.objects.create_user(username="business")
        Profile.objects.create(user=self.business, type="business")
        self.url = reverse("customer-profiles")

    def authenticate(self, user):
        token = Token.objects.create(user=user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

    def assert_profile_schema(self, response):
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.json(), list)
        self.assertEqual(len(response.data), 1)
        self.assertTrue(set(self.fields).issubset(response.data[0]))
        self.assertEqual(self.user_id(response.data[0]), self.customer.pk)
        self.assert_name_types(response.data[0])
        self.assertEqual(response.data[0]["username"], "customer")
        self.assertEqual(response.data[0]["type"], "customer")
        self.assertIsNone(response.data[0]["file"])

    def user_id(self, profile):
        """Accept an integer or a user object while checking its identity."""
        user = profile["user"]
        self.assertIn(type(user), (int, dict))
        user_id = user["id"] if isinstance(user, dict) else user
        self.assertIs(type(user_id), int)
        return user_id

    def assert_name_types(self, profile):
        for field in ("username", "first_name", "last_name"):
            with self.subTest(field=field):
                self.assertIsInstance(profile[field], str)

    def test_customer_can_access_customer_profiles(self):
        self.authenticate(self.customer)
        response = self.client.get(self.url)
        self.assert_profile_schema(response)

    def test_business_can_access_customer_profiles(self):
        self.authenticate(self.business)
        response = self.client.get(self.url)
        self.assert_profile_schema(response)

    def test_unauthenticated_user_returns_401(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 401)

    def test_invalid_token_returns_401(self):
        self.client.credentials(HTTP_AUTHORIZATION="Token invalid")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 401)

    def test_list_contains_all_customers_and_no_business_profiles(self):
        other = User.objects.create_user(username="other_customer")
        Profile.objects.create(user=other, type="customer")
        self.authenticate(self.customer)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.json(), list)
        self.assertCountEqual(
            [self.user_id(profile) for profile in response.data],
            [self.customer.pk, other.pk],
        )
        self.assertTrue(all(p["type"] == "customer" for p in response.data))

    def test_unset_names_return_empty_strings(self):
        self.authenticate(self.customer)
        response = self.client.get(self.url)
        self.assert_profile_schema(response)
        for field in ("first_name", "last_name"):
            with self.subTest(field=field):
                self.assertEqual(response.data[0][field], "")

    def test_populated_names_are_returned(self):
        self.customer.first_name = "Jane"
        self.customer.last_name = "Doe"
        self.customer.save(update_fields=["first_name", "last_name"])
        self.authenticate(self.business)
        response = self.client.get(self.url)
        self.assert_profile_schema(response)
        self.assertEqual(response.data[0]["first_name"], "Jane")
        self.assertEqual(response.data[0]["last_name"], "Doe")

    def test_no_customer_profiles_returns_empty_list(self):
        Profile.objects.filter(type="customer").delete()
        self.authenticate(self.business)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    def test_customer_profiles_url_resolves_to_list_view(self):
        self.assertEqual(self.url, "/api/profiles/customer/")
        self.assertIs(
            resolve(self.url).func.view_class, CustomerProfileListView,
        )
