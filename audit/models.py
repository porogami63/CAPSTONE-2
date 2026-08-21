import json

from django.contrib.auth import get_user_model
from django.db import models

User = get_user_model()


class AuditLogManager(models.Manager):
    def create_entry(self, *, user, action, table_name, record_id, old_values=None, new_values=None):
        return super().create(
            user=user,
            action=action,
            table_name=table_name,
            record_id=str(record_id),
            old_values=old_values or {},
            new_values=new_values or {},
        )


class SystemAuditTrail(models.Model):
    class Action(models.TextChoices):
        CREATE = "create", "Create"
        UPDATE = "update", "Update"
        DELETE = "delete", "Delete"

    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="audit_entries")
    action = models.CharField(max_length=10, choices=Action.choices)
    table_name = models.CharField(max_length=100)
    record_id = models.CharField(max_length=64)
    old_values = models.JSONField(default=dict, blank=True)
    new_values = models.JSONField(default=dict, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    objects = AuditLogManager()

    class Meta:
        ordering = ["-timestamp"]
        verbose_name = "System audit trail entry"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValueError("Audit trail entries are append-only and cannot be updated.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("Audit trail entries are append-only and cannot be deleted.")

    def __str__(self):
        return f"{self.action} {self.table_name}:{self.record_id} @ {self.timestamp:%Y-%m-%d %H:%M}"


class Notification(models.Model):
    class Level(models.TextChoices):
        INFO = "info", "Information"
        WARNING = "warning", "Warning"
        SUCCESS = "success", "Success"
        DANGER = "danger", "Alert"

    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifications")
    title = models.CharField(max_length=255)
    message = models.TextField()
    level = models.CharField(max_length=20, choices=Level.choices, default=Level.INFO)
    link = models.CharField(max_length=255, blank=True, null=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "User Notification"
        verbose_name_plural = "User Notifications"

    def __str__(self):
        return f"[{self.level.upper()}] {self.recipient.username}: {self.title}"
