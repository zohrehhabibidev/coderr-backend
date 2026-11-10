"""Test the irreversible snapshot migration on the runner's database."""

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.recorder import MigrationRecorder
from django.test import TransactionTestCase


class OrderSnapshotMigrationTests(TransactionTestCase):
    """Use historical models and restore leaf migrations before flush."""

    migrate_from = [("orders_app", "0001_initial")]
    migrate_to = [("orders_app", "0002_order_snapshot")]

    def setUp(self):
        super().setUp()
        self.latest = MigrationExecutor(connection).loader.graph.leaf_nodes()
        self.rebuild_order_table()
        self.old_apps = self.migrate(self.migrate_from)
        self.Order = self.old_apps.get_model("orders_app", "Order")
        self.Detail = self.old_apps.get_model("offers_app", "OfferDetail")
        self.create_sources()

    def migrate(self, targets):
        """Reload the graph so recorder changes never leave stale state."""
        executor = MigrationExecutor(connection)
        executor.migrate(targets)
        return executor.loader.project_state(targets).apps

    def rebuild_order_table(self):
        """Reset the test Order table; 0002 has no reverse data operation."""
        self.assert_test_database()
        self.addCleanup(self.restore_latest)
        executor = MigrationExecutor(connection)
        apps = executor.loader.project_state(self.latest).apps
        with connection.schema_editor() as editor:
            editor.delete_model(apps.get_model("orders_app", "Order"))
        recorder = MigrationRecorder(connection)
        for name in ("0002_order_snapshot", "0001_initial"):
            recorder.record_unapplied("orders_app", name)

    def assert_test_database(self):
        self.assertEqual(connection.vendor, "sqlite")
        name = str(connection.settings_dict["NAME"])
        expected = str(connection.creation._get_test_db_name())
        self.assertNotEqual(
            Path(name).resolve(), (settings.BASE_DIR / "db.sqlite3").resolve(),
        )
        memory = f"file:memorydb_{connection.alias}?mode=memory&cache=shared"
        self.assertTrue(
            name == expected == memory or (
                not name.startswith("file:") and
                Path(name).resolve() == Path(expected).resolve()
            )
        )

    def restore_latest(self):
        """Discard invalid fixtures before retrying an atomic migration."""
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM orders_app_order")
        self.migrate(self.latest)
        executor = MigrationExecutor(connection)
        self.assertEqual(executor.migration_plan(self.latest), [])

    def create_sources(self):
        User = self.old_apps.get_model("auth", "User")
        self.customer = User.objects.create(username="snapshot-customer")
        self.business = User.objects.create(username="snapshot-business")
        Offer = self.old_apps.get_model("offers_app", "Offer")
        self.offer = Offer.objects.create(
            user_id=self.business.pk, title="Parent", description="Offer",
        )
        self.detail = self.Detail.objects.create(
            offer_id=self.offer.pk, title="Logo Design – ویژه",
            offer_type="basic",
            price=Decimal("999.99"), revisions=99, delivery_time_in_days=99,
            features=["Current package feature"],
        )

    def create_order(self, **overrides):
        values = dict(
            customer_user_id=self.customer.pk,
            business_user_id=self.business.pk,
            offer_detail_id=self.detail.pk, price=Decimal("150.25"),
            revisions=3, delivery_time_in_days=5,
            features=["Original logo", "کارت"], status="completed",
        )
        order = self.Order.objects.create(**(values | overrides))
        self.Order.objects.filter(pk=order.pk).update(
            created_at=datetime(2024, 9, 29, 10, tzinfo=timezone.utc),
            updated_at=datetime(2024, 9, 30, 12, tzinfo=timezone.utc),
        )
        return self.Order.objects.get(pk=order.pk)

    def migrated_order(self, order):
        apps = self.migrate(self.migrate_to)
        return apps.get_model("orders_app", "Order").objects.get(pk=order.pk)

    def assert_snapshot(self, order, title, offer_type):
        self.assertIs(type(order.title), str)
        self.assertEqual(order.title, title)
        self.assertIs(type(order.offer_type), str)
        self.assertEqual(order.offer_type, offer_type)

    def test_backfills_exact_detail_title_and_type(self):
        order = self.migrated_order(self.create_order())
        self.assert_snapshot(order, "Logo Design – ویژه", "basic")

    def test_preserves_every_existing_order_field_and_type(self):
        original = self.create_order()
        before = self.Order.objects.values().get(pk=original.pk)
        migrated = self.migrated_order(original)
        for name, expected in before.items():
            with self.subTest(field=name):
                actual = getattr(migrated, name)
                self.assertIs(type(actual), type(expected))
                self.assertEqual(actual, expected)

    def test_backfills_all_package_types_and_multiple_orders_per_detail(self):
        expected = {}
        for kind in ("basic", "standard", "premium"):
            detail = self.package_detail(kind)
            for _ in range(2):
                order = self.create_order(offer_detail_id=detail.pk)
                expected[order.pk] = (detail.title, kind)
        apps = self.migrate(self.migrate_to)
        orders = apps.get_model("orders_app", "Order").objects.all()
        self.assertEqual(orders.count(), 6)
        for order in orders:
            self.assert_snapshot(order, *expected[order.pk])

    def package_detail(self, kind):
        if kind == "basic":
            return self.detail
        return self.Detail.objects.create(
            offer_id=self.offer.pk, title=kind, offer_type=kind,
            price=1, revisions=0, delivery_time_in_days=1, features=[],
        )

    def test_accepts_maximum_length_source_title(self):
        self.Detail.objects.filter(pk=self.detail.pk).update(title="é" * 200)
        order = self.migrated_order(self.create_order())
        self.assert_snapshot(order, "é" * 200, "basic")

    def test_migrates_an_empty_order_table(self):
        apps = self.migrate(self.migrate_to)
        Order = apps.get_model("orders_app", "Order")
        self.assertEqual(Order.objects.count(), 0)

    def test_offer_detail_is_nullable_in_schema_and_persistence(self):
        order = self.migrated_order(self.create_order())
        self.assertTrue(order._meta.get_field("offer_detail").null)
        with connection.cursor() as cursor:
            columns = connection.introspection.get_table_description(
                cursor, "orders_app_order",
            )
        self.assertTrue(next(c.null_ok for c in columns
                             if c.name == "offer_detail_id"))
        order.offer_detail = None
        order.save(update_fields=["offer_detail"])
        order.refresh_from_db()
        self.assertIsNone(order.offer_detail_id)

    def test_snapshot_fields_reject_database_nulls(self):
        order = self.migrated_order(self.create_order())
        for field in ("title", "offer_type"):
            with self.subTest(field=field):
                self.assertFalse(order._meta.get_field(field).null)
                with self.assertRaises(IntegrityError), transaction.atomic():
                    type(order).objects.filter(pk=order.pk).update(
                        **{field: None},
                    )

    def assert_rejected_source(self, changes, message):
        original = self.create_order()
        before = self.Order.objects.values().get(pk=original.pk)
        self.Detail.objects.filter(pk=self.detail.pk).update(**changes)
        with self.assertRaisesRegex(RuntimeError, message):
            self.migrate(self.migrate_to)
        applied = MigrationRecorder(connection).applied_migrations()
        self.assertNotIn(self.migrate_to[0], applied)
        after = self.Order.objects.values().get(pk=original.pk)
        self.assertEqual(after, before)
        self.assert_legacy_schema()

    def assert_legacy_schema(self):
        with connection.cursor() as cursor:
            columns = connection.introspection.get_table_description(
                cursor, "orders_app_order",
            )
        for name in ("title", "offer_type"):
            self.assertNotIn(name, [column.name for column in columns])

    def test_invalid_later_order_rolls_back_earlier_backfill(self):
        self.create_order()
        invalid = self.package_detail("standard")
        self.create_order(offer_detail_id=invalid.pk)
        before = list(self.Order.objects.order_by("pk").values())
        self.Detail.objects.filter(pk=invalid.pk).update(title="")
        with self.assertRaisesRegex(RuntimeError, "invalid OfferDetail title"):
            self.migrate(self.migrate_to)
        self.assert_legacy_schema()
        self.assertEqual(
            list(self.Order.objects.order_by("pk").values()), before,
        )

    def test_rejects_empty_source_title_and_rolls_back(self):
        self.assert_rejected_source({"title": ""}, "invalid OfferDetail title")

    def test_rejects_overlong_source_title_and_rolls_back(self):
        self.assert_rejected_source(
            {"title": "x" * 201}, "invalid OfferDetail title",
        )

    def test_rejects_unknown_source_package_type_and_rolls_back(self):
        self.assert_rejected_source({"offer_type": "unknown"}, "offer_type")

    def test_rejects_dangling_source_and_rolls_back(self):
        order = self.create_order()
        with connection.constraint_checks_disabled():
            self.Order.objects.filter(pk=order.pk).update(
                offer_detail_id=999999,
            )
            try:
                self.assert_missing_source_rejected()
            finally:
                self.Order.objects.filter(pk=order.pk).update(
                    offer_detail_id=self.detail.pk,
                )

    def assert_missing_source_rejected(self):
        # SQLite's schema-exit FK check otherwise masks the source error.
        with patch.object(connection, "check_constraints"):
            with self.assertRaisesRegex(RuntimeError, "missing OfferDetail"):
                self.migrate(self.migrate_to)

    def test_cleanup_restores_latest_after_simulated_setup_failure(self):
        with patch.object(self, "create_sources", side_effect=RuntimeError):
            with self.assertRaises(RuntimeError):
                self.setUp()
        self.assertTrue(self.doCleanups())
        executor = MigrationExecutor(connection)
        self.assertEqual(executor.migration_plan(self.latest), [])
        apps = executor.loader.project_state(self.latest).apps
        Order = apps.get_model("orders_app", "Order")
        self.assertEqual(list(Order.objects.values("title", "offer_type")), [])
