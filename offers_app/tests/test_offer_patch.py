from copy import deepcopy
from unittest.mock import patch

from django.urls import reverse
from rest_framework.test import APITestCase

from offers_app.models import Offer, OfferDetail
from offers_app.tests import test_offer_create as creation
from offers_app.tests import test_offer_retrieve as retrieval


class OfferPatchTests(APITestCase):
    """Verify Card 25 partial updates via the routed API."""

    make_user = retrieval.OfferRetrieveTests.make_user
    make_offer = retrieval.OfferRetrieveTests.make_offer
    authenticate = retrieval.OfferRetrieveTests.authenticate
    snapshot = retrieval.OfferRetrieveTests.snapshot
    detail = creation.OfferCreateTests.detail
    assert_detail_persisted = creation.OfferCreateTests.assert_detail_persisted
    assert_detail_types = creation.OfferCreateTests.assert_detail_types

    def setUp(self):
        super().setUp()
        self.owner = self.make_user("owner", "business")
        self.offer = self.make_offer(self.owner)
        self.url = reverse("offer-detail", args=[self.offer.pk])
        self.authenticate(self.owner)
        self.expected = self.expected_response()

    def expected_response(self):
        fields = ("id", "title", "revisions", "delivery_time_in_days",
                  "price", "features", "offer_type")
        details = list(self.offer.details.order_by("pk").values(*fields))
        for detail in details:
            detail["price"] = float(detail["price"])
        return {"id": self.offer.pk, "title": self.offer.title,
                "description": self.offer.description, "image": None,
                "details": details}

    def assert_updated(self, payload):
        expected = deepcopy(self.expected)
        by_type = {item["offer_type"]: item for item in expected["details"]}
        for item in payload.get("details", []):
            by_type[item["offer_type"]].update(item)
        expected.update({key: value for key, value in payload.items()
                         if key != "details"})
        response = self.client.patch(self.url, payload, format="json")
        self.assertEqual(response.status_code, 200)
        self.assert_response(response, expected)
        self.assert_persisted(expected)

    def assert_response(self, response, expected):
        actual = response.json()
        self.assertIs(type(actual["id"]), int)
        self.assertIsInstance(actual["details"], list)
        self.assertEqual(len(actual["details"]), 3)
        self.assert_detail_types(response)
        self.assert_response_types(actual)
        for data in (actual, expected):
            data["details"] = sorted(data["details"],
                                     key=lambda item: item["offer_type"])
        self.assertEqual(actual, expected)

    def assert_response_types(self, data):
        for field in ("title", "description"):
            self.assertIsInstance(data[field], str)
        self.assertIsNone(data["image"])
        for detail in data["details"]:
            for field in ("title", "offer_type"):
                self.assertIsInstance(detail[field], str)
            for field in ("revisions", "delivery_time_in_days"):
                self.assertIs(type(detail[field]), int)
            self.assertIsInstance(detail["features"], list)
            for feature in detail["features"]:
                self.assertIsInstance(feature, str)

    def assert_persisted(self, expected):
        self.offer.refresh_from_db()
        self.assertEqual(Offer.objects.count(), 1)
        self.assertEqual(OfferDetail.objects.count(), 3)
        self.assertEqual(self.offer.user_id, self.owner.pk)
        for field in ("title", "description"):
            self.assertEqual(getattr(self.offer, field), expected[field])
        self.assertFalse(self.offer.image)
        for submitted in expected["details"]:
            detail = self.offer.details.get(offer_type=submitted["offer_type"])
            self.assert_detail_persisted(detail, submitted)

    def assert_rejected(self, payload, status=400, url=None, field=None,
                        path=()):
        before = self.snapshot()
        response = self.client.patch(url or self.url, payload, format="json")
        self.assertEqual(response.status_code, status)
        self.assertIsInstance(response.data, dict)
        self.assertTrue(response.data)
        if field:
            self.assertIn(field, response.data)
            self.assertTrue(response.data[field])
            self.assert_error_content(response.data[field], path)
        self.assertEqual(self.snapshot(), before)

    def assert_error_content(self, errors, path):
        for key in path:
            self.assertIsInstance(errors, (dict, list))
            if isinstance(errors, dict):
                self.assertIn(key, errors)
            errors = errors[key]
        if isinstance(errors, str):
            errors = [errors]
        self.assertIsInstance(errors, list)
        self.assertTrue(errors)
        for message in errors:
            self.assertIsInstance(message, str)
            self.assertTrue(message.strip())

    def test_title_only_preserves_all_packages_and_omitted_fields(self):
        self.assert_updated({"title": "Updated design"})

    def test_basic_only_updates_all_package_values_and_preserves_ids(self):
        self.assert_updated({"details": [self.detail("basic")]})

    def test_basic_and_premium_update_independently_in_reverse_order(self):
        self.assert_updated({"details": [self.detail("premium"),
                                         self.detail("basic")]})

    def test_single_package_field_preserves_other_nested_fields(self):
        self.assert_updated({"details": [{"offer_type": "basic",
                                          "price": 42.75}]})

    def test_title_and_basic_update_together(self):
        self.assert_updated({"title": "Updated bundle",
                             "details": [self.detail("basic")]})

    def test_description_only_preserves_title_and_packages(self):
        self.assert_updated({"description": "Updated description"})

    def test_invalid_top_level_values_roll_back(self):
        for field, value in (("title", ""), ("title", None),
                             ("title", "x" * 201), ("description", None),
                             ("image", "not-an-image")):
            with self.subTest(field=field, value=value):
                self.assert_rejected({field: value}, field=field)

    def test_unwritable_top_level_fields_roll_back(self):
        for field in ("id", "user", "created_at", "updated_at", "unknown"):
            with self.subTest(field=field):
                self.assert_rejected({"title": "Must roll back", field: 99},
                                     field=field)

    def test_unwritable_nested_fields_roll_back(self):
        for field in ("id", "offer", "unknown"):
            with self.subTest(field=field):
                self.assert_rejected({"title": "Must roll back", "details": [
                    {"offer_type": "basic", field: 99}]}, field="details",
                    path=(0, field))

    def test_invalid_nested_values_roll_back_title_and_first_package(self):
        cases = (("title", ""), ("title", None), ("title", "x" * 201),
                 ("price", "bad"), ("price", None), ("price", "1.234"),
                 ("revisions", -1), ("revisions", "bad"),
                 ("delivery_time_in_days", -1), ("features", None))
        for field, value in cases:
            with self.subTest(field=field, value=value):
                self.assert_rejected({"title": "Must roll back", "details": [
                    self.detail("basic"),
                    {"offer_type": "premium", field: value}]},
                    field="details", path=(1, field))

    def test_missing_offer_type_rolls_back(self):
        self.assert_rejected({"title": "Must roll back", "details": [
            self.detail("basic"), {"price": 25}]}, field="details",
            path=(1, "offer_type"))

    def test_invalid_features_structure_and_members_roll_back(self):
        cases = ({"invalid": True}, "invalid", 7, True, None,
                 [7], [True], [None], [{}], [[]], ["Valid", 7])
        for features in cases:
            with self.subTest(features=features):
                self.assert_rejected({"title": "Must roll back", "details": [
                    self.detail("basic"),
                    {"offer_type": "premium", "features": features}]},
                    field="details", path=(1, "features"))

    def test_empty_features_list_clears_package_features(self):
        self.assert_updated({"details": [{"offer_type": "basic",
                                          "features": []}]})

    def test_duplicate_offer_type_rolls_back(self):
        self.assert_rejected({"title": "Must roll back", "details": [
            self.detail("basic"), {"offer_type": "basic", "price": 25}]},
            field="details")

    def test_unknown_blank_and_null_offer_type_roll_back(self):
        for kind in ("unknown", "", None):
            with self.subTest(offer_type=kind):
                self.assert_rejected({"title": "Must roll back", "details": [
                    self.detail("basic"), {"offer_type": kind, "price": 25}]},
                    field="details", path=(1, "offer_type"))

    def test_invalid_details_structure_rolls_back(self):
        for details, path in ((None, ()),
                              ("invalid", ("non_field_errors",)),
                              ({}, ("non_field_errors",)),
                              ([7], (0, "non_field_errors"))):
            with self.subTest(details=details):
                self.assert_rejected({"title": "Must roll back",
                                      "details": details}, field="details",
                                     path=path)

    def test_anonymous_patch_returns_401_without_changes(self):
        self.client.credentials()
        self.assert_rejected({"title": "Denied"}, 401, field="detail")

    def test_non_owner_customer_patch_returns_403_without_changes(self):
        self.authenticate(self.make_user("customer", "customer"))
        self.assert_rejected({"title": "Denied"}, 403, field="detail")

    def test_non_owner_business_patch_returns_403_without_changes(self):
        self.authenticate(self.make_user("business", "business"))
        self.assert_rejected({"details": [self.detail("basic")]},
                             403, field="detail")

    def test_nonexistent_offer_returns_404_without_changes(self):
        missing = self.offer.pk + 1000
        self.assertFalse(Offer.objects.filter(pk=missing).exists())
        self.assert_rejected({"title": "Missing"}, 404,
                             reverse("offer-detail", args=[missing]), "detail")

    def test_second_package_save_failure_rolls_back_first_package(self):
        before = self.snapshot()
        original = OfferDetail.save
        with patch.object(OfferDetail, "save", autospec=True,
                          side_effect=lambda detail, *args, **kwargs:
                          self.save_or_fail(original, detail, args, kwargs)):
            with self.assertRaises(RuntimeError):
                self.client.patch(self.url, {"title": "Must roll back",
                                  "details": [self.detail("basic"),
                                              self.detail("premium")]},
                                  format="json")
        self.assertEqual(self.snapshot(), before)

    def save_or_fail(self, original, detail, args, kwargs):
        if detail.offer_type == "premium":
            basic = self.offer.details.get(offer_type="basic")
            self.assertEqual(basic.title, self.detail("basic")["title"])
            raise RuntimeError("Simulated second package save failure")
        return original(detail, *args, **kwargs)
