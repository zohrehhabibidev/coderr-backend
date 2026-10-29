from django.conf import settings
from django.db import models
from offers_app.models import OfferDetail


class Order(models.Model):
    customer_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="customer_orders"
    )

    business_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="business_orders"
    )

    offer_detail = models.ForeignKey(
        OfferDetail,
        on_delete=models.PROTECT,
        related_name="orders"
    )

    price = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    delivery_time_in_days = models.PositiveIntegerField()

    revisions = models.PositiveIntegerField()

    features = models.JSONField(
        default=list
    )

    class OrderStatus(models.TextChoices):
        IN_PROGRESS = "in_progress", "In Progress"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    status = models.CharField(
        max_length=20,
        choices=OrderStatus.choices,
        default=OrderStatus.IN_PROGRESS
    )

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Order #{self.pk}"
