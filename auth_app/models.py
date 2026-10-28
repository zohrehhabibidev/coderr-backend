from django.db import models


class Profile(models.Model):
    class UserType(models.TextChoices):
        CUSTOMER = "customer", "Customer"
        BUSINESS = "business", "Business"

    user = models.OneToOneField(
        "auth.User",
        on_delete=models.CASCADE,
        related_name="profile"
    )

    type = models.CharField(
        max_length=10,
        choices=UserType.choices
    )

    location = models.CharField(
        max_length=100,
        blank=True,
        default=""
    )

    tel = models.CharField(
        max_length=30,
        blank=True,
        default=""
    )

    description = models.TextField(
        blank=True,
        default=""
    )

    working_hours = models.CharField(
        max_length=100,
        blank=True,
        default=""
    )

    file = models.ImageField(
        upload_to="profiles/",
        blank=True,
        null=True
    )

    def __str__(self):
        return self.user.username
