from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase


class LoginTests(APITestCase):
    def setUp(self):
        self.url = reverse("login")
        self.user = User.objects.create_user(
            username="sara",
            email="sara@example.com",
            password="StrongPass123!",
        )
        self.payload = {
            "username": self.user.username,
            "password": "StrongPass123!",
        }

    def test_public_access_without_authentication(self):
        self.assertEqual(self.url, "/api/login/")
        self.assertNotIn("HTTP_AUTHORIZATION", self.client.defaults)
        response = self.client.post(self.url, self.payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_successful_login(self):
        response = self.client.post(self.url, self.payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            set(response.data), {"token", "username", "email", "user_id"}
        )
        self.assertEqual(response.data["username"], self.user.username)
        self.assertEqual(response.data["email"], self.user.email)
        self.assertEqual(response.data["user_id"], self.user.id)

    def test_login_creates_token(self):
        self.assertFalse(Token.objects.filter(user=self.user).exists())
        response = self.client.post(self.url, self.payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        token = Token.objects.get(user=self.user)
        self.assertEqual(token.key, response.data["token"])

    def test_login_reuses_existing_token(self):
        token = Token.objects.create(user=self.user)
        response = self.client.post(self.url, self.payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["token"], token.key)
        self.assertEqual(Token.objects.filter(user=self.user).count(), 1)

    def assert_login_error(self, response, field):
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIsInstance(response.data, dict)
        self.assertIn(field, response.data)
        errors = response.data[field]
        self.assertIsInstance(errors, list)
        self.assertTrue(errors)
        for message in errors:
            self.assertIsInstance(message, str)
            self.assertTrue(message.strip())

    def test_login_with_wrong_password(self):
        payload = self.payload.copy()
        payload["password"] = "WrongPass123!"
        response = self.client.post(self.url, payload, format="json")
        self.assert_login_error(response, "non_field_errors")
        self.assertFalse(Token.objects.filter(user=self.user).exists())

    def test_login_with_nonexistent_username(self):
        payload = self.payload.copy()
        payload["username"] = "unknown_user"
        response = self.client.post(self.url, payload, format="json")
        self.assert_login_error(response, "non_field_errors")
        self.assertEqual(Token.objects.count(), 0)

    def test_login_with_missing_required_fields(self):
        for field in ("username", "password"):
            with self.subTest(field=field):
                payload = self.payload.copy()
                payload.pop(field)
                response = self.client.post(self.url, payload, format="json")
                self.assert_login_error(response, field)
                self.assertEqual(Token.objects.count(), 0)

    def test_login_with_blank_required_fields(self):
        for field in ("username", "password"):
            with self.subTest(field=field):
                payload = self.payload.copy()
                payload[field] = ""
                response = self.client.post(self.url, payload, format="json")
                self.assert_login_error(response, field)
                self.assertEqual(Token.objects.count(), 0)

    def test_login_with_null_fields(self):
        for field in ("username", "password"):
            with self.subTest(field=field):
                payload = self.payload.copy()
                payload[field] = None
                response = self.client.post(self.url, payload, format="json")
                self.assert_login_error(response, field)
                self.assertEqual(Token.objects.count(), 0)
