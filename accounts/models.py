from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        MANAGEMENT = "management", "Management"
        FINANCE = "finance", "Finance Officer"
        OPERATIONS = "operations", "Operations Staff"
        INVOICING = "invoicing", "Invoicing Staff"

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.OPERATIONS,
    )

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"
