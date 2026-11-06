from io import BytesIO
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from PIL import Image
from rest_framework.test import APITestCase

from auth_app.models import Profile
from . import test_profile


class ProfilePatchTests(APITestCase):
    fields = test_profile.ProfileDetailTests.fields

    def setUp(self):
        self.customer = User.objects.create_user(username="customer")
        self.business = User.objects.create_user(
            username="business", first_name="Max", last_name="Mustermann",
            email="max@example.com",
        )
        self.business_profile = Profile.objects.create(
            user=self.business, type="business", location="Berlin",
            tel="123", description="Description", working_hours="9-17",
        )
        self.customer_profile = Profile.objects.create(
            user=self.customer, type="customer"
        )

    authenticate = test_profile.ProfileDetailTests.authenticate

    def update_profile(self, user, data, format="json"):
        return self.client.patch(
            reverse("profile-detail", args=[user.pk]), data, format=format
        )

    def snapshot(self, user):
        return self.client.get(
            reverse("profile-detail", args=[user.pk])
        ).data

    def test_both_owner_types_update_all_writable_text_fields(self):
        data = {
            "first_name": "New", "last_name": "Name", "email": "new@test.de",
            "location": "Hamburg", "tel": "987", "description": "Updated",
            "working_hours": "10-18",
        }
        for user in (self.customer, self.business):
            with self.subTest(type=user.profile.type):
                self.authenticate(user)
                response = self.update_profile(user, data)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(list(response.data), self.fields)
                self.assert_persisted_fields(user, data, response.data)

    def assert_persisted_fields(self, user, data, response):
        user.refresh_from_db()
        profile = Profile.objects.get(user=user)
        for field, value in data.items():
            source = (
                user if field in ("first_name", "last_name", "email")
                else profile
            )
            self.assertEqual(getattr(source, field), value)
            self.assertEqual(response[field], value)

    def test_single_fields_and_empty_payload_preserve_other_values(self):
        self.authenticate(self.business)
        for data in ({"location": "Hamburg"}, {"first_name": "New"},
                     {"email": "new@test.de"}, {}):
            with self.subTest(data=data):
                expected = dict(self.snapshot(self.business))
                expected.update(data)
                response = self.update_profile(self.business, data)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.data, expected)
                self.assertEqual(self.snapshot(self.business), expected)

    def test_other_user_is_forbidden_without_mutation(self):
        self.authenticate(self.customer)
        before = self.snapshot(self.business)
        response = self.update_profile(self.business, {"location": "Changed"})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.snapshot(self.business), before)

    def test_missing_authentication_returns_401(self):
        response = self.update_profile(self.customer, {"location": "Changed"})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response["WWW-Authenticate"], "Token")

    def test_missing_user_or_profile_returns_404(self):
        missing_profile = User.objects.create_user(username="no_profile")
        self.authenticate(self.customer)
        for user in (missing_profile, User(pk=999999)):
            with self.subTest(pk=user.pk):
                response = self.update_profile(user, {})
                self.assertEqual(response.status_code, 404)

    def test_empty_text_fields_are_strings(self):
        self.authenticate(self.customer)
        response = self.update_profile(self.customer, {})
        self.assertEqual(response.status_code, 200)
        for field in test_profile.ProfileDetailTests.empty_fields:
            self.assertEqual(response.data[field], "")

    def test_protected_and_unlisted_fields_are_ignored(self):
        self.authenticate(self.business)
        before = self.snapshot(self.business)
        response = self.update_profile(self.business, {
            "user": self.customer.pk, "username": "hacked", "type": "customer",
            "created_at": "2000-01-01T00:00:00Z", "is_staff": True,
            "password": "hacked",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, before)
        self.assertEqual(self.snapshot(self.business), before)
        self.business.refresh_from_db()
        self.assertFalse(self.business.is_staff)
        self.assertFalse(self.business.check_password("hacked"))

    def test_lookup_uses_user_id_even_when_profile_ids_differ(self):
        self.assertNotEqual(self.business.pk, self.business_profile.pk)
        self.assertEqual(self.business.pk, self.customer_profile.pk)
        self.authenticate(self.business)
        response = self.update_profile(self.business, {"location": "Hamburg"})
        self.assertEqual(response.status_code, 200)
        self.customer_profile.refresh_from_db()
        self.assertEqual(self.customer_profile.location, "")
        self.assertEqual(response.data["user"], self.business.pk)

    def test_invalid_data_does_not_partially_update_either_model(self):
        self.authenticate(self.business)
        before = self.snapshot(self.business)
        for data in ({"email": "invalid", "location": "Changed"},
                     {"first_name": "Changed", "tel": "x" * 31},
                     {"location": None}, {"first_name": None}):
            with self.subTest(data=data):
                response = self.update_profile(self.business, data)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(self.snapshot(self.business), before)

    def test_profile_save_failure_rolls_back_user_update(self):
        self.authenticate(self.business)
        before = self.snapshot(self.business)
        failure = RuntimeError("save failed")
        with patch.object(Profile, "save", side_effect=failure):
            with self.assertRaises(RuntimeError):
                self.update_profile(self.business, {"first_name": "Changed"})
        self.assertEqual(self.snapshot(self.business), before)

    def image_upload(self):
        image = BytesIO()
        Image.new("RGB", (2, 2)).save(image, format="PNG")
        return SimpleUploadedFile("avatar.png", image.getvalue(), "image/png")

    @override_settings(STORAGES={"default": {
        "BACKEND": "django.core.files.storage.InMemoryStorage"}})
    def test_owner_multipart_upload_preserves_omitted_fields(self):
        self.authenticate(self.business)
        before = dict(self.snapshot(self.business))
        response = self.update_profile(
            self.business, {"file": self.image_upload()}, "multipart"
        )
        self.assertEqual(response.status_code, 200)
        self.business_profile.refresh_from_db()
        self.assertTrue(self.business_profile.file.storage.exists(
            self.business_profile.file.name))
        before["file"] = response.data["file"]
        self.assertEqual(response.data, before)

    def test_nonowner_cannot_upload_file(self):
        self.authenticate(self.customer)
        response = self.update_profile(
            self.business, {"file": self.image_upload()}, "multipart"
        )
        self.assertEqual(response.status_code, 403)
        self.business_profile.refresh_from_db()
        self.assertFalse(self.business_profile.file)
