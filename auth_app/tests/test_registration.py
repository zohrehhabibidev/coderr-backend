from unittest.mock import patch

from django.contrib.auth.hashers import identify_hasher
from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from auth_app.models import Profile


class RegistrationTestBase(APITestCase):
    def setUp(self):
        self.url = reverse("registration")
        self.payload = {
            "username": "sara",
            "email": "sara@example.com",
            "password": "StrongPass123!",
            "repeated_password": "StrongPass123!",
            "type": "customer",
        }

    def counts(self):
        return (
            User.objects.count(),
            Profile.objects.count(),
            Token.objects.count(),
        )

    def assert_rejected(self, payload, field):
        before = self.counts()
        response = self.client.post(self.url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn(field, response.data)
        self.assertEqual(self.counts(), before)

    def assert_registration(self, payload):
        before = self.counts()
        response = self.client.post(self.url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assert_registration_response(response.data, payload)
        user = User.objects.get(pk=response.data["user_id"])
        self.assert_registration_records(user, payload, response.data["token"])
        self.assertEqual(self.counts(), tuple(count + 1 for count in before))
        return user

    def assert_registration_response(self, data, payload):
        self.assertEqual(
            set(data), {"token", "username", "email", "user_id"}
        )
        self.assertIsInstance(data["user_id"], int)
        self.assertIsInstance(data["token"], str)
        self.assertTrue(data["token"])
        self.assertEqual(data["username"], payload["username"])
        self.assertEqual(data["email"], payload.get("email", ""))

    def assert_registration_records(self, user, payload, token):
        self.assertEqual(user.username, payload["username"])
        self.assertEqual(user.email, payload.get("email", ""))
        self.assertEqual(Profile.objects.get(user=user).type, payload["type"])
        self.assertEqual(Token.objects.get(user=user).key, token)


class RegistrationTests(RegistrationTestBase):
    def test_customer_registration(self):
        self.assert_registration(self.payload)

    def test_business_registration(self):
        self.assert_registration({**self.payload, "type": "business"})

    def test_password_is_securely_hashed(self):
        user = self.assert_registration(self.payload)
        self.assertNotEqual(user.password, self.payload["password"])
        self.assertTrue(user.has_usable_password())
        identify_hasher(user.password)
        self.assertTrue(user.check_password(self.payload["password"]))
        self.assertFalse(user.check_password("wrong-password"))

    def test_public_access_without_authentication(self):
        self.assertEqual(self.url, "/api/registration/")
        self.assertNotIn("HTTP_AUTHORIZATION", self.client.defaults)
        self.assert_registration(self.payload)

    def test_mismatched_passwords(self):
        self.assert_rejected(
            {**self.payload, "repeated_password": "DifferentPass123!"},
            "repeated_password",
        )

    def test_invalid_roles(self):
        for role in ("admin", "CUSTOMER", "invalid"):
            with self.subTest(role=role):
                self.assert_rejected({**self.payload, "type": role}, "type")

    def test_missing_required_fields(self):
        # Email requiredness is undocumented; characterize it separately.
        for field in ("username", "password", "repeated_password", "type"):
            with self.subTest(field=field):
                payload = self.payload.copy()
                del payload[field]
                self.assert_rejected(payload, field)

    def test_blank_required_fields(self):
        for field in ("username", "password", "repeated_password", "type"):
            with self.subTest(field=field):
                self.assert_rejected({**self.payload, field: ""}, field)

    def test_null_fields(self):
        for field in self.payload:
            with self.subTest(field=field):
                self.assert_rejected({**self.payload, field: None}, field)

    def test_duplicate_username(self):
        existing = User.objects.create_user(
            username=self.payload["username"],
            email="existing@example.com",
            password="OriginalPass123!",
        )
        original_password = existing.password
        self.assert_rejected(self.payload, "username")
        existing.refresh_from_db()
        self.assertEqual(existing.email, "existing@example.com")
        self.assertEqual(existing.password, original_password)

    def test_invalid_email(self):
        self.assert_rejected(
            {**self.payload, "email": "invalid-email"}, "email"
        )

    def test_token_creation_failure_rolls_back_user_and_profile(self):
        before = self.counts()
        with patch(
            "auth_app.api.serializers.Token.objects.create",
            side_effect=RuntimeError("Simulated token creation failure"),
        ):
            with self.assertRaisesMessage(
                RuntimeError, "Simulated token creation failure"
            ):
                self.client.post(self.url, self.payload, format="json")
        self.assertEqual(self.counts(), before)


class RegistrationEmailContractObservations(RegistrationTestBase):
    """Observe email acceptance without establishing an API requirement."""

    def test_missing_email_is_currently_accepted(self):
        payload = self.payload.copy()
        del payload["email"]
        self.assert_registration(payload)

    def test_blank_email_is_currently_accepted(self):
        self.assert_registration({**self.payload, "email": ""})
