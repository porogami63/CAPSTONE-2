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

    def test_category_counts_and_filtering_across_more_than_50_items(self):
        self.client.login(username="adminuser", password="password123")
        # 1. Bulk create 60 system / chat notifications
        notifs = [
            Notification(
                recipient=self.admin,
                title=f"New Message {i}",
                message="General chat update",
                link="/chat/",
                category=Notification.Category.SYSTEM,
            )
            for i in range(60)
        ]
        # 2. Add 5 specific loan notifications
        notifs.extend([
            Notification(
                recipient=self.admin,
                title=f"Loan Facility {i}",
                message="Review loan proposal",
                link="/finance/loans/",
                category=Notification.Category.LOAN,
            )
            for i in range(5)
        ]
        )
        Notification.objects.bulk_create(notifs)

        # Total unread is 65
        res_all = self.client.get(reverse("audit:api_notifications"))
        self.assertEqual(res_all.status_code, 200)
        data_all = res_all.json()
        self.assertEqual(data_all["unread_count"], 65)
        self.assertEqual(data_all["category_counts"]["all"], 65)
        self.assertEqual(data_all["category_counts"]["loan"], 5)
        self.assertEqual(data_all["category_counts"]["system"], 60)
        self.assertEqual(len(data_all["notifications"]), 50)

        # Category filter: loan returns all 5 loan items without being blocked by the 60 chat items
        res_loan = self.client.get(reverse("audit:api_notifications") + "?category=loan")
        self.assertEqual(res_loan.status_code, 200)
        data_loan = res_loan.json()
        self.assertEqual(data_loan["unread_count"], 65)
        self.assertEqual(data_loan["category_counts"]["loan"], 5)
        self.assertEqual(len(data_loan["notifications"]), 5)
        for item in data_loan["notifications"]:
            self.assertEqual(item["category"], "loan")

    def test_chat_notifications_do_not_pollute_operational_categories(self):
        # A chat notification that mentions loan, interest, and variance keywords
        n = Notification.objects.create(
            recipient=self.admin,
            title="Message from opsuser",
            message="Can we check the loan interest calculation and barge variance?",
            link="/chat/?user=2",
            category=Notification.Category.SYSTEM,
        )
        self.assertEqual(n.get_classified_category(), Notification.Category.SYSTEM)
