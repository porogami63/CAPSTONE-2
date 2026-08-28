from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMINISTRATOR = "administrator", "Administrator"
        OPERATIONS_MANAGEMENT = "operations_management", "Operations Management"
        FINANCE = "finance", "Finance"
        INVOICING = "invoicing", "Invoicing"

    role = models.CharField(
        max_length=30,
        choices=Role.choices,
        default=Role.OPERATIONS_MANAGEMENT,
    )
    avatar = models.ImageField(upload_to="avatars/", null=True, blank=True)

    @property
    def avatar_url(self):
        if self.avatar:
            return self.avatar.url
        return None

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"


# Class aliases for backward compatibility if referenced dynamically
User.Role.MANAGEMENT = User.Role.ADMINISTRATOR
User.Role.OPERATIONS_MANAGER = User.Role.OPERATIONS_MANAGEMENT
User.Role.OPERATIONS = User.Role.OPERATIONS_MANAGEMENT


