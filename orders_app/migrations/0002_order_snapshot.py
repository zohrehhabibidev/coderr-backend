"""Snapshot linked detail data without changing existing order values."""

import django.db.models.deletion
from django.db import migrations, models


OFFER_TYPE_CHOICES = [
    ("basic", "Basic"),
    ("standard", "Standard"),
    ("premium", "Premium"),
]


def snapshot_values(order, details):
    """Reject missing or invalid sources rather than inventing snapshots."""
    values = details.filter(pk=order.offer_detail_id).values_list(
        "title", "offer_type"
    ).first()
    if values is None:
        raise RuntimeError(f"Order {order.pk}: missing OfferDetail snapshot.")
    title, offer_type = values
    if not isinstance(title, str) or not 1 <= len(title) <= 200:
        raise RuntimeError(f"Order {order.pk}: invalid OfferDetail title.")
    if offer_type not in dict(OFFER_TYPE_CHOICES):
        raise RuntimeError(f"Order {order.pk}: invalid source offer_type.")
    return {"title": title, "offer_type": offer_type}


def backfill_snapshots(apps, schema_editor):
    """Update new fields only, bypassing auto_now to preserve timestamps."""
    alias = schema_editor.connection.alias
    orders = apps.get_model("orders_app", "Order").objects.using(alias)
    details = apps.get_model("offers_app", "OfferDetail").objects.using(alias)
    for order in orders.all().iterator():
        values = snapshot_values(order, details)
        orders.filter(pk=order.pk).update(**values)


def validate_snapshots(apps, schema_editor):
    """Check persisted snapshots against their sources before NOT NULL."""
    alias = schema_editor.connection.alias
    orders = apps.get_model("orders_app", "Order").objects.using(alias)
    details = apps.get_model("offers_app", "OfferDetail").objects.using(alias)
    for order in orders.all().iterator():
        values = snapshot_values(order, details)
        if order.title != values["title"] or (
            order.offer_type != values["offer_type"]
        ):
            raise RuntimeError(f"Order {order.pk}: snapshot mismatch.")


class Migration(migrations.Migration):
    # Reversal would lose snapshots and may encounter deleted source details.
    atomic = True

    dependencies = [
        ("orders_app", "0001_initial"),
        ("offers_app", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="title",
            field=models.CharField(max_length=200, null=True),
        ),
        migrations.AddField(
            model_name="order",
            name="offer_type",
            field=models.CharField(
                choices=OFFER_TYPE_CHOICES, max_length=10, null=True,
            ),
        ),
        migrations.RunPython(backfill_snapshots),
        migrations.RunPython(validate_snapshots),
        migrations.AlterField(
            model_name="order",
            name="title",
            field=models.CharField(max_length=200),
        ),
        migrations.AlterField(
            model_name="order",
            name="offer_type",
            field=models.CharField(
                choices=OFFER_TYPE_CHOICES, max_length=10,
            ),
        ),
        migrations.AlterField(
            model_name="order",
            name="offer_detail",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="orders",
                to="offers_app.offerdetail",
            ),
        ),
    ]
