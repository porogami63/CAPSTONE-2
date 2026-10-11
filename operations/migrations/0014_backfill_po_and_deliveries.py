from decimal import Decimal
from django.db import migrations


def backfill_po_and_deliveries(apps, schema_editor):
    PurchaseOrder = apps.get_model("operations", "PurchaseOrder")
    DeliveryLedger = apps.get_model("operations", "DeliveryLedger")
    LogisticsLedger = apps.get_model("operations", "LogisticsLedger")

    for po in PurchaseOrder.objects.all():
        cluster = po.cluster
        if not po.po_reference_number and cluster:
            po.po_reference_number = cluster.reference_code
        if po.total_contracted_mt is None:
            po.total_contracted_mt = po.volume_mt
        if not po.customer_id and cluster:
            po.customer = cluster.client
        po.save()

        # Check existing deliveries
        existing_delivs = DeliveryLedger.objects.filter(purchase_order=po)
        if not existing_delivs.exists() and cluster:
            try:
                log = LogisticsLedger.objects.get(cluster=cluster)
                deliv_vol = log.received_volume_mt or log.loaded_volume_mt
                if deliv_vol and deliv_vol > 0:
                    deliv_date = log.received_at.date() if log.received_at else (log.loaded_at.date() if log.loaded_at else cluster.created_at.date())
                    DeliveryLedger.objects.create(
                        purchase_order=po,
                        supplier=cluster.sugar_mill,
                        delivered_mt=deliv_vol,
                        receiving_location=f"{cluster.client.name} Facility",
                        delivery_date=deliv_date,
                        carrier=log.partner,
                        vessel_or_truck=log.vessel_id or "",
                        notes="Initial fulfillment backfilled from legacy logistics ledger.",
                    )
            except LogisticsLedger.DoesNotExist:
                pass

        # Compute status
        total_delivered = Decimal("0")
        for d in DeliveryLedger.objects.filter(purchase_order=po):
            total_delivered += d.delivered_mt or Decimal("0")

        contracted = po.total_contracted_mt or po.volume_mt or Decimal("0")
        remaining = contracted - total_delivered

        if total_delivered <= Decimal("0"):
            po.po_status = "Open"
        elif remaining <= Decimal("0"):
            po.po_status = "Completed"
        else:
            po.po_status = "Partially Fulfilled"
        po.save(update_fields=["po_status"])


def reverse_backfill(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("operations", "0013_historicalpurchaseorder_customer_and_more"),
    ]

    operations = [
        migrations.RunPython(backfill_po_and_deliveries, reverse_backfill),
    ]
