from django.conf import settings
from django.db import models


class Offer(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="offers"
    )

    title = models.CharField(
        max_length=200
    )

    description = models.TextField()

    image = models.ImageField(
        upload_to="offers/",
        blank=True,
        null=True
    )

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title


class OfferDetail(models.Model):
    class OfferType(models.TextChoices):
        BASIC = "basic", "Basic"
        STANDARD = "standard", "Standard"
        PREMIUM = "premium", "Premium"

    offer = models.ForeignKey(
        Offer,
        on_delete=models.CASCADE,
        related_name="details"
    )

    offer_type = models.CharField(
        max_length=10,
        choices=OfferType.choices
    )

    title = models.CharField(
        max_length=200
    )

    revisions = models.PositiveIntegerField()

    delivery_time_in_days = models.PositiveIntegerField()

    price = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    features = models.JSONField(
        default=list
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["offer", "offer_type"],
                name="unique_offer_type_per_offer"
            )
        ]

    def __str__(self):
        return self.title
