from django.contrib.auth.models import User
from django.db import models


class Review(models.Model):
    business_user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="reviews_received"
    )

    reviewer = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="reviews_written"
    )

    rating = models.IntegerField()

    description = models.TextField()

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["reviewer", "business_user"],
                name="unique_review_per_business"
            )
        ]

    def __str__(self):
        return (
            f"{self.reviewer.username} → {self.business_user.username} "
            f"({self.rating})"
        )
