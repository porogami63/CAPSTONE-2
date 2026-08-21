from django.test import TestCase
from django.urls import reverse
from accounts.models import User
from audit.models import Notification
from audit.services import notify_user, notify_roles


class NotificationSystemTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="adminuser",
            password="password123",
            role=User.Role.ADMINISTRATOR
        )
        self.ops = User.objects.create_user(
            username="opsuser",
            password="password123",
            role=User.Role.OPERATIONS_MANAGEMENT
        )

    def test_notify_services(self):
        notify_user(self.admin, title="Test Admin Notif", message="Direct message", level="info")
        self.assertEqual(Notification.objects.filter(recipient=self.admin).count(), 1)

        notify_roles([User.Role.OPERATIONS_MANAGEMENT], title="Role Alert", message="Ops alert", level="warning")
        self.assertEqual(Notification.objects.filter(recipient=self.ops).count(), 1)

    def test_api_notifications_and_mark_read(self):
        notify_user(self.admin, title="Unread Alert", message="Check this", level="danger")
        self.client.login(username="adminuser", password="password123")

        response = self.client.get(reverse("audit:api_notifications"))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["unread_count"], 1)

        mark_resp = self.client.post(reverse("audit:api_mark_notifications_read"))
        self.assertEqual(mark_resp.status_code, 200)
        self.assertEqual(Notification.objects.filter(recipient=self.admin, is_read=False).count(), 0)
