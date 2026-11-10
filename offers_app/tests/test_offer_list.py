from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils.dateparse import parse_datetime
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from auth_app.models import Profile
from offers_app.models import Offer, OfferDetail


class OfferListTests(APITestCase):
    """Check the Card 22 contract and agreed list policies via HTTP."""

    def setUp(self):
        super().setUp()
        self.url = reverse("offer-list")

    def make_offer(self, price=100, days=7, user=None, **fields):
        user = user or User.objects.get_or_create(username="creator")[0]
        offer = Offer.objects.create(
            user=user, title=fields.pop("title", "Website Design"),
            description=fields.pop("description", "Professional graphics"),
            **fields,
        )
        for index, kind in enumerate(("basic", "standard", "premium")):
            OfferDetail.objects.create(
                offer=offer, offer_type=kind, title=kind, revisions=2,
                price=price + index * 10,
                delivery_time_in_days=days + (2 - index),
            )
        return offer

    def get_page(self, params=None):
        response = self.client.get(self.url, params or {})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, dict)
        self.assertEqual(set(data), {"count", "next", "previous", "results"})
        self.assertIs(type(data["count"]), int)
        self.assertIsInstance(data["results"], list)
        for key in ("next", "previous"):
            self.assertTrue(data[key] is None or isinstance(data[key], str))
        return data

    def assert_ids(self, expected, params=None, count=None):
        data = self.get_page(params)
        self.assertEqual([row["id"] for row in data["results"]], expected)
        count = len(expected) if count is None else count
        self.assertEqual(data["count"], count)
        return data

    def assert_query_error(self, params, field, status=400):
        before = (Offer.objects.count(), OfferDetail.objects.count())
        response = self.client.get(self.url, params)
        self.assertEqual(response.status_code, status)
        self.assertIsInstance(response.data, dict)
        self.assertEqual(set(response.data), {field})
        errors = response.data[field]
        self.assertTrue(errors)
        self.assertIsInstance(errors, list if status == 400 else str)
        if status == 400:
            self.assertTrue(all(isinstance(error, str) for error in errors))
        after = (Offer.objects.count(), OfferDetail.objects.count())
        self.assertEqual(after, before)

    def test_anonymous_user_can_list_offers(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.data, dict)
        self.assertEqual(
            set(response.data.keys()),
            {"count", "next", "previous", "results"},
        )
        self.assertEqual(response.data["count"], 0)
        self.assertIsNone(response.data["next"])
        self.assertIsNone(response.data["previous"])
        self.assertIsInstance(response.data["results"], list)
        self.assertEqual(response.data["results"], [])

    def test_customer_business_and_staff_can_read(self):
        offer = self.make_offer()
        for role, staff in (("customer", False), ("business", False),
                            ("customer", True), ("business", True)):
            with self.subTest(role=role, staff=staff):
                user = User.objects.create_user(username=f"{role}-{staff}")
                Profile.objects.create(user=user, type=role)
                user.is_staff = staff
                user.save()
                token = Token.objects.create(user=user)
                self.client.credentials(
                    HTTP_AUTHORIZATION=f"Token {token.key}",
                )
                self.assert_ids([offer.pk])

    def test_staff_without_profile_can_read(self):
        offer = self.make_offer()
        user = User.objects.create_user(username="staff", is_staff=True)
        token = Token.objects.create(user=user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        self.assert_ids([offer.pk])

    def expected_offer(self, offer):
        return {
            "id": offer.pk, "user": offer.user_id, "title": offer.title,
            "image": None, "description": offer.description,
            "created_at": offer.created_at.isoformat().replace("+00:00", "Z"),
            "updated_at": offer.updated_at.isoformat().replace("+00:00", "Z"),
            "details": [{"id": item.pk, "url": f"/offerdetails/{item.pk}/"}
                        for item in offer.details.order_by("pk")],
            "min_price": 100, "min_delivery_time": 7,
            "user_details": {"first_name": "John", "last_name": "Doe",
                             "username": "creator"},
        }

    def test_nonempty_response_exact_schema_values_and_types(self):
        offer = self.make_offer()
        offer.user.first_name, offer.user.last_name = "John", "Doe"
        offer.user.save()
        data = self.assert_ids([offer.pk])
        row = data["results"][0]
        self.assertEqual(row, self.expected_offer(offer))
        self.assert_row_types(row)
        self.assertIsNone(data["next"])
        self.assertIsNone(data["previous"])

    def assert_row_types(self, row):
        for key in ("id", "user", "min_delivery_time"):
            self.assertIs(type(row[key]), int)
        self.assertIn(type(row["min_price"]), (int, float))
        for key in ("title", "description", "created_at", "updated_at"):
            self.assertIsInstance(row[key], str)
        self.assertIsInstance(row["user_details"], dict)
        values = row["user_details"].values()
        self.assertTrue(all(isinstance(value, str) for value in values))
        self.assert_detail_types(row["details"])

    def assert_detail_types(self, details):
        self.assertIsInstance(details, list)
        self.assertEqual(len(details), 3)
        for detail in details:
            self.assertIsInstance(detail, dict)
            self.assertIs(type(detail["id"]), int)
            self.assertIsInstance(detail["url"], str)

    def test_timestamps_are_iso8601_utc_and_distinct(self):
        offer = self.make_offer()
        created = datetime(2026, 1, 2, 10, 30, tzinfo=timezone.utc)
        updated = created + timedelta(days=2, microseconds=123456)
        Offer.objects.filter(pk=offer.pk).update(
            created_at=created, updated_at=updated,
        )
        row = self.get_page()["results"][0]
        self.assertEqual(row["created_at"], "2026-01-02T10:30:00Z")
        self.assertEqual(row["updated_at"], "2026-01-04T10:30:00.123456Z")
        self.assertEqual(parse_datetime(row["created_at"]), created)
        self.assertEqual(parse_datetime(row["updated_at"]), updated)

    def test_minima_from_different_packages_and_multiple_offers(self):
        first = self.make_offer(price=100.25, days=3)
        second = self.make_offer(price=250.75, days=8)
        data = self.assert_ids([second.pk, first.pk])
        self.assertEqual(
            [(r["min_price"], r["min_delivery_time"])
             for r in data["results"]],
            [(250.75, 8), (100.25, 3)],
        )
        basic = first.details.get(offer_type="basic")
        self.assertEqual(basic.delivery_time_in_days, 5)
        self.assertEqual(first.details.get(offer_type="premium").price, 120.25)

    def test_minima_reflect_related_package_updates(self):
        offer = self.make_offer()
        self.assert_ids([offer.pk], {"min_price": 100, "max_delivery_time": 7})
        offer.details.filter(offer_type="standard").update(
            price=25.5, delivery_time_in_days=1,
        )
        row = self.get_page()["results"][0]
        self.assertEqual(
            (row["min_price"], row["min_delivery_time"]), (25.5, 1),
        )
        self.assert_ids([], {"min_price": 100})
        self.assert_ids([offer.pk], {"max_delivery_time": 1})
        self.assertEqual(offer.details.count(), 3)

    def test_creator_filter_and_unknown_creator(self):
        other = User.objects.create_user(username="other")
        first = self.make_offer()
        second = self.make_offer(user=other)
        self.assert_ids([first.pk], {"creator_id": first.user_id})
        self.assert_ids([second.pk], {"creator_id": other.pk})
        self.assert_ids([], {"creator_id": other.pk + 1000})

    def test_min_price_greater_equal_boundary(self):
        low = self.make_offer(price=99.99)
        exact = self.make_offer(price=100)
        high = self.make_offer(price=100.01)
        self.assert_ids([high.pk, exact.pk], {"min_price": 100})
        self.assert_ids([high.pk, exact.pk, low.pk], {"min_price": 99.99})
        self.assert_ids([], {"min_price": 1000})

    def test_max_delivery_less_equal_boundary(self):
        fast = self.make_offer(days=4)
        exact = self.make_offer(days=5)
        self.make_offer(days=6)
        self.assert_ids([exact.pk, fast.pk], {"max_delivery_time": 5})
        self.assert_ids([fast.pk], {"max_delivery_time": 4})
        self.assert_ids([], {"max_delivery_time": 1})

    def test_filters_combine_with_and(self):
        other = User.objects.create_user(username="other")
        target = self.make_offer(price=100, days=5)
        self.make_offer(price=99, days=5)
        self.make_offer(price=100, days=6)
        self.make_offer(price=100, days=5, user=other)
        params = {"creator_id": target.user_id, "min_price": 100,
                  "max_delivery_time": 5}
        self.assert_ids([target.pk], params)

    def test_invalid_numeric_filters_return_400(self):
        self.make_offer()
        cases = {"creator_id": ("bad", "1.5", ""),
                 "min_price": ("bad", ""),
                 "max_delivery_time": ("bad", "1.5", "")}
        for field, values in cases.items():
            for value in values:
                with self.subTest(field=field, value=value):
                    self.assert_query_error({field: value}, field)

    def test_search_title_description_and_case_insensitivity(self):
        title = self.make_offer(title="Unique LOGO", description="unrelated")
        description = self.make_offer(
            title="unrelated", description="Unique BRAND",
        )
        for query, expected in (("logo", [title.pk]), ("LoGo", [title.pk]),
                                ("brand", [description.pk]), ("absent", [])):
            with self.subTest(query=query):
                self.assert_ids(expected, {"search": query})

    def test_search_combined_with_filters(self):
        target = self.make_offer(title="Logo", price=100, days=5)
        self.make_offer(title="Logo", price=50, days=5)
        self.make_offer(title="Other", price=100, days=5)
        self.assert_ids([target.pk], {"search": "logo", "min_price": 100,
                                     "max_delivery_time": 5,
                                     "creator_id": target.user_id})

    def ordering_offers(self):
        offers = [self.make_offer(price=price) for price in (300, 100, 200)]
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        for offer, day in zip(offers, (2, 3, 1)):
            Offer.objects.filter(pk=offer.pk).update(
                updated_at=base + timedelta(days=day),
            )
        return [offer.pk for offer in offers]

    def test_all_orderings_and_default(self):
        a, b, c = self.ordering_offers()
        cases = (("updated_at", [c, a, b]), ("-updated_at", [b, a, c]),
                 ("min_price", [b, c, a]), ("-min_price", [a, c, b]))
        for ordering, expected in cases:
            with self.subTest(ordering=ordering):
                self.assert_ids(expected, {"ordering": ordering})
        self.assert_ids([b, a, c])

    def test_ordering_ties_use_ascending_pk(self):
        offers = [self.make_offer() for _ in range(3)]
        tied_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
        Offer.objects.update(updated_at=tied_time)
        orders = ("updated_at", "-updated_at", "min_price", "-min_price")
        for ordering in orders:
            with self.subTest(ordering=ordering):
                self.assert_ids([o.pk for o in offers], {"ordering": ordering})
        self.assert_ids([o.pk for o in offers])

    def test_invalid_ordering_returns_400(self):
        for value in ("title", "random", "updated_at,min_price", ""):
            with self.subTest(ordering=value):
                self.assert_query_error({"ordering": value}, "ordering")

    def test_default_page_size_ten(self):
        offers = [self.make_offer() for _ in range(11)]
        ids = [o.pk for o in reversed(offers)]
        data = self.assert_ids(ids[:10], count=11)
        self.assertIsNone(data["previous"])
        self.assertEqual(data["next"], "http://testserver/api/offers/?page=2")
        data = self.assert_ids(ids[10:], {"page": 2}, count=11)
        self.assertIsNone(data["next"])
        self.assertEqual(data["previous"], "http://testserver/api/offers/")

    def assert_link(self, link, params):
        self.assertIsInstance(link, str)
        parsed = urlparse(link)
        self.assertEqual((parsed.scheme, parsed.netloc, parsed.path),
                         ("http", "testserver", self.url))
        self.assertEqual(parse_qs(parsed.query),
                         {key: [str(value)] for key, value in params.items()})

    def test_custom_page_size_first_middle_last(self):
        ids = [self.make_offer().pk for _ in range(5)][::-1]
        for page, start in ((1, 0), (2, 2), (3, 4)):
            with self.subTest(page=page):
                data = self.assert_ids(ids[start:start + 2],
                                       {"page_size": 2, "page": page}, count=5)
                self.assert_pagination_links(data, page, 3, {"page_size": 2})

    def assert_pagination_links(self, data, page, last, params):
        if page == last:
            self.assertIsNone(data["next"])
        else:
            self.assert_link(data["next"], {**params, "page": page + 1})
        if page == 1:
            self.assertIsNone(data["previous"])
        else:
            previous = {**params, "page": page - 1} if page > 2 else params
            self.assert_link(data["previous"], previous)

    def test_maximum_page_size_and_exceeding_cap(self):
        ids = [self.make_offer().pk for _ in range(101)][::-1]
        for size in (100, 101, 1000):
            with self.subTest(page_size=size):
                params = {"page_size": size}
                data = self.assert_ids(ids[:100], params, count=101)
                self.assert_link(data["next"], {"page_size": size, "page": 2})
                self.assertIsNone(data["previous"])
                self.assert_ids(
                    ids[100:], {**params, "page": 2}, count=101,
                )

    def test_invalid_page_sizes_return_400(self):
        for value in (0, -1, "bad", "1.5", ""):
            with self.subTest(page_size=value):
                self.assert_query_error({"page_size": value}, "page_size")

    def test_invalid_pages_follow_drf_404_behavior(self):
        self.make_offer()
        for value in (0, -1, "bad", "1.5", 2, 999):
            with self.subTest(page=value):
                self.assert_query_error({"page": value}, "detail", status=404)

    def test_empty_and_last_page_alias_follow_drf_behavior(self):
        ids = [self.make_offer().pk for _ in range(3)][::-1]
        self.assert_ids(ids, {"page": ""})
        self.assert_ids(ids[2:], {"page": "last", "page_size": 2}, count=3)

    def test_filters_search_and_ordering_across_pages(self):
        ids = [self.make_offer(price=p).pk for p in (100, 120, 110)]
        self.make_offer(price=90)
        self.make_offer(
            price=200, title="Unrelated", description="Unrelated",
        )
        params = {"min_price": 100, "search": "website",
                  "ordering": "min_price",
                  "max_delivery_time": 7, "page_size": 2}
        data = self.assert_ids([ids[0], ids[2]], params, count=3)
        self.assert_link(data["next"], {**params, "page": 2})
        data = self.assert_ids([ids[1]], {**params, "page": 2}, count=3)
        self.assert_link(data["previous"], params)
        self.assertIsNone(data["next"])

    def test_ties_remain_stable_across_pages(self):
        ids = [self.make_offer().pk for _ in range(5)]
        tied_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
        Offer.objects.update(updated_at=tied_time)
        actual = []
        for page in (1, 2, 3):
            data = self.get_page({"page_size": 2, "page": page})
            actual.extend(row["id"] for row in data["results"])
        self.assertEqual(actual, ids)
        self.assertEqual(len(set(actual)), 5)

    def measured_list_queries(self, ids):
        with CaptureQueriesContext(connection) as queries:
            self.assert_ids(ids, {"page_size": 100})
        return len(queries)

    def test_multi_offer_list_has_no_n_plus_one_queries(self):
        ids = [self.make_offer().pk for _ in range(2)]
        small = self.measured_list_queries(ids[::-1])
        for index in range(10):
            user = User.objects.create_user(username=f"creator-{index}")
            ids.append(self.make_offer(user=user).pk)
        large = self.measured_list_queries(ids[::-1])
        self.assertGreater(small, 0)
        self.assertEqual(large, small,
                         "More offers must not add per-row queries")

    def test_get_does_not_change_offers_or_packages(self):
        self.make_offer()
        before = (list(Offer.objects.values()),
                  list(OfferDetail.objects.values()))
        self.get_page()
        self.assertEqual(list(Offer.objects.values()), before[0])
        self.assertEqual(list(OfferDetail.objects.values()), before[1])
