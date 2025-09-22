from django.db import models


class StatusChoices(models.TextChoices):
    OPEN = "OPEN", "Open"
    RESOLVED = "RESOLVED", "Resolved"
    CLOSED = "CLOSED", "Closed"


class Ticket(models.Model):
    id = models.AutoField(primary_key=True)
    title = models.CharField(max_length=255)
    description = models.TextField()
    created = models.DateTimeField(auto_now_add=True)
    resolution_status = models.CharField(
        max_length=8,
        choices=StatusChoices.choices,
        default=StatusChoices.OPEN,
    )

    class Meta:
        ordering = ("-created",)

    def __str__(self) -> str:
        return f"{self.title} ({self.resolution})"
