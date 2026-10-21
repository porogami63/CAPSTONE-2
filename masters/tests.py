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


class MastersViewTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        self.user = User.objects.create_user(
            username="ops_user",
            password="password123",
            role=User.Role.OPERATIONS,
        )
        self.client.login(username="ops_user", password="password123")
        self.mill = SugarMill.objects.create(name="Central Azucarera Don Pedro", location="Batangas")
        self.buyer = Client.objects.create(name="San Miguel Corp", tin="123-456-789-000")

    def test_partners_view(self):
        res = self.client.get("/masters/partners/")
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "id=\"partnerSearch\"")
        self.assertContains(res, "id=\"addSupplierModal\"")
        self.assertContains(res, "id=\"addCustomerModal\"")
        self.assertContains(res, "</script>")

    def test_supplier_portfolio_view(self):
        res = self.client.get(f"/masters/suppliers/{self.mill.id}/")
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "Central Azucarera Don Pedro")

    def test_client_portfolio_view(self):
        res = self.client.get(f"/masters/clients/{self.buyer.id}/")
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "San Miguel Corp")

    def test_create_supplier_view(self):
        res = self.client.post("/masters/suppliers/new/", {
            "name": "HAWAIIAN-PHILIPPINE COMPANY",
            "location": "Silay City",
            "contact_person": "Juan dela Cruz",
            "contact_phone": "+63 917 111 2222",
            "email": "info@hawa-phil.com",
            "notes": "Premium sugar mill supplier",
        })
        self.assertEqual(res.status_code, 302)
        mill = SugarMill.objects.get(name="HAWAIIAN-PHILIPPINE COMPANY")
        self.assertIn(f"/masters/suppliers/{mill.id}/", res.url)
        follow_res = self.client.get(res.url)
        self.assertEqual(follow_res.status_code, 200)

    def test_create_client_view(self):
        res = self.client.post("/masters/clients/new/", {
            "name": "Tanduay Distillers Inc",
            "tin": "987-654-321-000",
            "contact_person": "Maria Santos",
            "contact_phone": "+63 918 333 4444",
            "email": "procurement@tanduay.com",
            "address": "Manila, Philippines",
            "notes": "Large volume molasses buyer",
        })
        self.assertEqual(res.status_code, 302)
        client_obj = Client.objects.get(name="Tanduay Distillers Inc")
        self.assertIn(f"/masters/clients/{client_obj.id}/", res.url)
        follow_res = self.client.get(res.url)
        self.assertEqual(follow_res.status_code, 200)

    def test_partners_tabbed_directory_elements(self):
        LogisticsPartner.objects.create(name="Solid Shipping Lines", category="barging", fleet_count=5)
        LogisticsPartner.objects.create(name="FastHaul Trucking", category="trucking", fleet_count=12)

        res = self.client.get("/masters/partners/")
        self.assertEqual(res.status_code, 200)
        # Tab navigation and dropdown
        self.assertContains(res, 'id="partnerTabNav"')
        self.assertContains(res, 'id="btnAddPartnerDropdown"')
        self.assertContains(res, "Add Partner")
        self.assertContains(res, 'id="toggleHideInactive"')
        self.assertContains(res, "Hide inactive (0 MT)")
        # Tab panes
        self.assertContains(res, 'id="tabPaneSuppliers"')
        self.assertContains(res, 'id="tabPaneCustomers"')
        self.assertContains(res, 'id="tabPaneLogistics"')
        # Modals
        self.assertContains(res, 'id="addBargingModal"')
        self.assertContains(res, 'id="addTruckingModal"')
        # Sub-filters
        self.assertContains(res, 'id="logisticsSubFilterGroup"')
        self.assertContains(res, "Solid Shipping Lines")
        self.assertContains(res, "FastHaul Trucking")
        self.assertContains(res, "On-Time")
        self.assertContains(res, "Shrinkage")

    def test_create_logistics_partner_views(self):
        # 1. Test create barging partner
        res_barge = self.client.post("/masters/logistics/new/", {
            "name": "Visayas Ocean Transport",
            "category": "barging",
            "region": "Visayas - Batangas Marine Lane",
            "fleet_count": "6",
            "default_freight_rate": "1150.00",
            "contact_person": "Capt. John Smith",
            "contact_phone": "+63 917 888 9999",
        })
        self.assertEqual(res_barge.status_code, 302)
        barge_partner = LogisticsPartner.objects.get(name="Visayas Ocean Transport")
        self.assertEqual(barge_partner.category, "barging")
        self.assertEqual(barge_partner.fleet_count, 6)
        self.assertEqual(float(barge_partner.default_freight_rate), 1150.00)

        # 2. Test create trucking partner
        res_truck = self.client.post("/masters/logistics/new/", {
            "name": "Batangas Express Lorries",
            "category": "trucking",
            "region": "Batangas Industrial Highway",
            "fleet_count": "20",
            "default_freight_rate": "480.00",
            "contact_person": "Pedro Penduko",
            "contact_phone": "+63 919 777 6655",
        })
        self.assertEqual(res_truck.status_code, 302)
        truck_partner = LogisticsPartner.objects.get(name="Batangas Express Lorries")
        self.assertEqual(truck_partner.category, "trucking")
        self.assertEqual(truck_partner.fleet_count, 20)


