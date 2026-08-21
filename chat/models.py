from django.contrib.auth import get_user_model
from django.db import models
from operations.models import TransactionCluster

User = get_user_model()


class ChatMessage(models.Model):
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name="sent_messages")
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, related_name="received_messages")
    cluster = models.ForeignKey(
        TransactionCluster,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="chat_messages",
        help_text="Optional transaction cluster discussion thread",
    )
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    is_system = models.BooleanField(default=False, help_text="System-generated operational alert")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name = "Team Chat Message"
        verbose_name_plural = "Team Chat Messages"

    def __str__(self):
        target = f"to {self.recipient.username}" if self.recipient else (f"on Cluster #{self.cluster.reference_code}" if self.cluster else "in General Team Chat")
        return f"{self.sender.username} {target}: {self.message[:30]}"
