from django.db.models.deletion import ProtectedError
from django.test import TestCase

from masters.models import Client, LogisticsPartner, SugarMill
from operations.models import TransactionCluster


class MastersModelTests(TestCase):
    def test_client_creation_and_str(self):
        client = Client.objects.create(name="Universal Robina Corp", contact_person="John Doe", address="Quezon City")
        self.assertEqual(str(client), "Universal Robina Corp")
        self.assertTrue(client.is_active)

    def test_sugar_mill_creation_and_str(self):
        mill = SugarMill.objects.create(name="BUSCO Sugar Milling", location="Bukidnon")
        self.assertEqual(str(mill), "BUSCO Sugar Milling")

    def test_logistics_partner_creation_and_str(self):
        partner = LogisticsPartner.objects.create(name="Fastcat Logistics")
        self.assertEqual(str(partner), "Fastcat Logistics")

    def test_protected_deletion_on_cluster_reference(self):
        client = Client.objects.create(name="San Miguel Corp")
        mill = SugarMill.objects.create(name="SONEDCO")
        TransactionCluster.objects.create(
            reference_code="PO-TEST-99",
            client=client,
            sugar_mill=mill,
        )

        with self.assertRaises(ProtectedError):
            client.delete()

        with self.assertRaises(ProtectedError):
            mill.delete()
