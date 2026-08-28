from django.test import TestCase
from django.contrib.auth import get_user_model

from masters.models import Client, SugarMill
from operations.models import TransactionCluster
from chat.models import ChatMessage
from chat.views import send_system_notification

User = get_user_model()


class ChatModuleTests(TestCase):
    def setUp(self):
        self.user1 = User.objects.create_user(username="alice", password="password123", role=User.Role.ADMINISTRATOR)
        self.user2 = User.objects.create_user(username="bob", password="password123", role=User.Role.OPERATIONS_MANAGEMENT)

        self.client_obj = Client.objects.create(name="Test Client")
        self.mill = SugarMill.objects.create(name="Test Sugar Mill")
        self.cluster = TransactionCluster.objects.create(
            reference_code="HTC-2026-001",
            client=self.client_obj,
            sugar_mill=self.mill,
        )

    def test_create_chat_message(self):
        msg = ChatMessage.objects.create(
            sender=self.user1,
            recipient=self.user2,
            message="Hello Bob!",
        )
        self.assertFalse(msg.is_read)
        self.assertFalse(msg.is_system)
        self.assertIn("alice to bob", str(msg))

    def test_send_system_notification(self):
        msg = send_system_notification(self.cluster, "Logistics variance detected!", sender_user=self.user1)
        self.assertIsNotNone(msg)
        self.assertTrue(msg.is_system)
        self.assertEqual(msg.cluster, self.cluster)
        self.assertEqual(msg.message, "Logistics variance detected!")

    def test_chat_room_view(self):
        self.client.login(username="alice", password="password123")
        res = self.client.get("/chat/")
        self.assertEqual(res.status_code, 200)

        # Room view with active recipient
        res2 = self.client.get(f"/chat/?user={self.user2.id}")
        self.assertEqual(res2.status_code, 200)

        # Room view with active cluster thread
        res3 = self.client.get(f"/chat/?cluster={self.cluster.id}")
        self.assertEqual(res3.status_code, 200)

    def test_api_send_message(self):
        self.client.login(username="alice", password="password123")
        res = self.client.post("/chat/api/send/", {
            "message": "Direct message via API",
            "recipient_id": self.user2.id,
        })
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["message"]["message"], "Direct message via API")

    def test_api_fetch_messages_and_unread(self):
        # Bob sends message to Alice
        ChatMessage.objects.create(
            sender=self.user2,
            recipient=self.user1,
            message="Hi Alice!",
        )

        # Alice checks unread count API
        self.client.login(username="alice", password="password123")
        res_unread = self.client.get("/chat/api/unread/")
        self.assertEqual(res_unread.status_code, 200)
        self.assertEqual(res_unread.json()["unread_count"], 1)

        # Alice fetches direct messages with Bob
        res_fetch = self.client.get(f"/chat/api/messages/?user_id={self.user2.id}")
        self.assertEqual(res_fetch.status_code, 200)
        self.assertEqual(len(res_fetch.json()["messages"]), 1)

        # Unread count should now be 0 after fetching
        res_unread2 = self.client.get("/chat/api/unread/")
        self.assertEqual(res_unread2.json()["unread_count"], 0)
