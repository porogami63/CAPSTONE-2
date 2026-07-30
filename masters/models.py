from django.conf import settings
from django.db import models


class Client(models.Model):
    name = models.CharField(max_length=200)
    tin = models.CharField("TIN", max_length=50, blank=True)
    address = models.TextField(blank=True)
    contact_person = models.CharField(max_length=120, blank=True)
    contact_phone = models.CharField(max_length=50, blank=True)
    email = models.EmailField(blank=True)
    avatar = models.ImageField(upload_to="avatars/clients/", null=True, blank=True)
    notes = models.TextField(blank=True, help_text="Relationship & operational overview notes")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class SugarMill(models.Model):
    name = models.CharField(max_length=200)
    location = models.CharField(max_length=200, blank=True)
    contact_person = models.CharField(max_length=120, blank=True)
    contact_phone = models.CharField(max_length=50, blank=True)
    email = models.EmailField(blank=True)
    avatar = models.ImageField(upload_to="avatars/mills/", null=True, blank=True)
    notes = models.TextField(blank=True, help_text="Capability & supply relationship notes")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class LogisticsPartner(models.Model):
    name = models.CharField(max_length=200)
    default_freight_rate = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    contact_person = models.CharField(max_length=120, blank=True)
    contact_phone = models.CharField(max_length=50, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class PartnerNote(models.Model):
    client = models.ForeignKey(Client, on_delete=models.CASCADE, null=True, blank=True, related_name="activity_notes")
    sugar_mill = models.ForeignKey(SugarMill, on_delete=models.CASCADE, null=True, blank=True, related_name="activity_notes")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        partner = self.client.name if self.client else (self.sugar_mill.name if self.sugar_mill else "Unknown")
        return f"Note for {partner} by {self.author.username} at {self.created_at.strftime('%Y-%m-%d')}"

