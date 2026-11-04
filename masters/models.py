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

    @property
    def origin_indicator(self):
        """
        Origin Indicator Attribute: Strictly attached to and determined by the
        Receiving Customer (destination specifications/zone), NOT the sugar mill.
        """
        addr = (self.address or "").lower()
        name = (self.name or "").lower()
        text = f"{name} {addr}"
        if any(k in text for k in ["batangas", "balayan", "luzon", "manila", "quezon", "laguna", "pampanga", "adi", "absolute distillers"]):
            return "Luzon Hub / Destination Spec"
        elif any(k in text for k in ["negros", "visayas", "cebu", "bacolod", "iloilo"]):
            return "Visayas Corridor / Destination Spec"
        elif any(k in text for k in ["davao", "mindanao", "cagayan", "bukidnon"]):
            return "Mindanao Terminal / Destination Spec"
        elif self.address:
            return f"{self.address.strip()} (Customer Spec)"
        return f"{self.name} Destination Zone"


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
    class Category(models.TextChoices):
        BARGING = "barging", "Barging"
        TRUCKING = "trucking", "Trucking"

    name = models.CharField(max_length=200)
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.BARGING, blank=True)
    region = models.CharField(max_length=150, blank=True, default="Visayas / Luzon Corridor")
    fleet_count = models.PositiveIntegerField(default=0, help_text="Fleet trucks or vessel barge count")
    default_freight_rate = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    contact_person = models.CharField(max_length=120, blank=True)
    contact_phone = models.CharField(max_length=50, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


DEFAULT_LUZON_TRUCKING_COMPANIES = [
    {
        "name": "Royal Cargo Inc. (Tanker & Bulk Land Transport)",
        "category": LogisticsPartner.Category.TRUCKING,
        "region": "Metro Manila (Parañaque) · Batangas · Subic · Greater Luzon",
        "fleet_count": 85,
        "default_freight_rate": "450.00",
        "contact_person": "Luzon Tanker Dispatch",
        "contact_phone": "+63 (02) 8333-3000",
    },
    {
        "name": "Fast Logistics (FastCargo Land Haulage)",
        "category": LogisticsPartner.Category.TRUCKING,
        "region": "Metro Manila · Calabarzon · Central Luzon Corridor",
        "fleet_count": 120,
        "default_freight_rate": "420.00",
        "contact_person": "Greater Luzon Fleet Control",
        "contact_phone": "+63 (02) 8784-3278",
    },
    {
        "name": "2GO Express Land Transport & Tanker Hauling",
        "category": LogisticsPartner.Category.TRUCKING,
        "region": "Port of Manila · Batangas · Laguna · Greater Luzon",
        "fleet_count": 95,
        "default_freight_rate": "460.00",
        "contact_person": "Bulk Liquid Haulage Desk",
        "contact_phone": "+63 (02) 8528-7000",
    },
    {
        "name": "Airspeed International Corp. (Luzon Land Freight)",
        "category": LogisticsPartner.Category.TRUCKING,
        "region": "Metro Manila (Pasay) · Southern & Northern Luzon",
        "fleet_count": 60,
        "default_freight_rate": "440.00",
        "contact_person": "Land Freight Dispatch",
        "contact_phone": "+63 (02) 8854-1284",
    },
    {
        "name": "Magsaysay Transport & Logistics (MTLC Trucking)",
        "category": LogisticsPartner.Category.TRUCKING,
        "region": "Manila North Harbor · Cavite · Batangas · Bulacan",
        "fleet_count": 70,
        "default_freight_rate": "435.00",
        "contact_person": "Luzon Fleet Operations",
        "contact_phone": "+63 (02) 8526-8888",
    },
    {
        "name": "RV Marzan International Forwarders & Trucking",
        "category": LogisticsPartner.Category.TRUCKING,
        "region": "Manila Port Area · Bulacan · Pampanga · Tarlac",
        "fleet_count": 55,
        "default_freight_rate": "410.00",
        "contact_person": "Heavy Hauling Dispatch",
        "contact_phone": "+63 (02) 8527-6111",
    },
    {
        "name": "Gothong Southern Land Transport (Luzon Hub)",
        "category": LogisticsPartner.Category.TRUCKING,
        "region": "Tondo Manila · Calamba · Batangas Industrial Corridor",
        "fleet_count": 48,
        "default_freight_rate": "425.00",
        "contact_person": "Luzon Trucking Desk",
        "contact_phone": "+63 (02) 8245-1100",
    },
    {
        "name": "F2 Logistics Philippines Inc. (Land Freight)",
        "category": LogisticsPartner.Category.TRUCKING,
        "region": "Metro Manila (Taguig) · Batangas · Greater Luzon",
        "fleet_count": 90,
        "default_freight_rate": "445.00",
        "contact_person": "Luzon Operations Center",
        "contact_phone": "+63 (02) 8887-3256",
    },
]


def ensure_default_trucking_partners():
    """Ensures sample popular Metro Manila & Greater Luzon trucking companies exist
    so Trucking Partner dropdowns are populated and separated from Barging partners.
    """
    from decimal import Decimal
    try:
        existing_trucking = LogisticsPartner.objects.filter(
            category=LogisticsPartner.Category.TRUCKING,
            is_active=True,
        ).count()
        if existing_trucking < 3:
            for item in DEFAULT_LUZON_TRUCKING_COMPANIES:
                LogisticsPartner.objects.update_or_create(
                    name=item["name"],
                    defaults={
                        "category": item["category"],
                        "region": item["region"],
                        "fleet_count": item["fleet_count"],
                        "default_freight_rate": Decimal(item["default_freight_rate"]),
                        "contact_person": item["contact_person"],
                        "contact_phone": item["contact_phone"],
                        "is_active": True,
                    },
                )
    except Exception:
        pass


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


class Planter(models.Model):
    name = models.CharField(max_length=200, unique=True)
    code = models.CharField(max_length=50, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


