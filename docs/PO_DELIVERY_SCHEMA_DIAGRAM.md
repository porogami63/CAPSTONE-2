# Database Schema Diagram: Purchase Order, Multi-Batch Delivery Ledger & Freight Economics

**System:** HTC Core Trading & Logistics Platform  
**Database:** PostgreSQL 16  
**Application Apps:** `operations`, `masters`, `finance`  
**Schema Version:** Post-Migration `operations.0015_deliveryledger_barge_partner_and_more`  
**Date:** October 11, 2026  

---

## 1. Entity-Relationship Diagram (ERD)

The following Mermaid diagram maps the database entities, primary keys (`PK`), foreign keys (`FK`), and cardinality relationships for the refactored Parent-Child Purchase Order, Multi-Source Delivery Ledger, and Multi-Batch Freight Rate Economics module.

```mermaid
erDiagram
    CLIENT ||--o{ PURCHASE_ORDER : "issues contract (1:N)"
    CLIENT ||--o{ DELIVERY_LEDGER : "receives batch destination (0:N)"
    PURCHASE_ORDER ||--|{ DELIVERY_LEDGER : "fulfilled by batches (1:N)"
    SUGAR_MILL ||--o{ DELIVERY_LEDGER : "sources batch (1:N)"
    LOGISTICS_PARTNER ||--o{ DELIVERY_LEDGER : "trucks batch (0:N)"
    LOGISTICS_PARTNER ||--o{ DELIVERY_LEDGER : "barges batch (0:N)"
    
    PURCHASE_ORDER ||--o| TRANSACTION_CLUSTER : "bridges operations (1:1)"
    TRANSACTION_CLUSTER ||--o| LOGISTICS_LEDGER : "aggregated logistics (1:1)"
    TRANSACTION_CLUSTER ||--o{ INVOICE : "bills customer (1:N)"
    TRANSACTION_CLUSTER ||--o{ CAPITAL_LOAN : "finances trade (1:N)"

    CLIENT {
        int id PK "Auto Primary Key"
        string company_name "Indexed"
        string tin_number "Tax ID"
        string address "Billing Address"
        string contact_person "Representative"
        boolean is_active "Active Status"
    }

    PURCHASE_ORDER {
        int id PK "Auto Primary Key"
        string po_reference_number UK "Indexed, e.g. PO-ADI-2026-001"
        int customer_id FK "References CLIENT.id (on_delete=SET_NULL)"
        decimal total_contracted_mt "12,2 - Contracted Metric Tons"
        decimal selling_price "12,2 - Agreed Customer Price per MT"
        string po_status "Enum: Open | Partially Fulfilled | Completed"
        decimal volume_mt "Legacy fallback field"
        date contract_date "Date PO was executed"
        datetime created_at "Timestamp"
        datetime updated_at "Timestamp"
    }

    DELIVERY_LEDGER {
        uuid delivery_id PK "UUIDv4 Primary Key"
        int purchase_order_id FK "References PURCHASE_ORDER.id (CASCADE)"
        int supplier_id FK "References SUGAR_MILL.id (PROTECT)"
        decimal delivered_mt "12,2 - Metric tons delivered"
        string receiving_location "Dynamic Client destination / plant site"
        date delivery_date "Actual delivery date"
        datetime dispatched_at "Departure timestamp from mill"
        datetime received_at "Arrival timestamp at customer site"
        int trucking_partner_id FK "References LOGISTICS_PARTNER.id (SET_NULL)"
        decimal trucking_rate_per_mt "12,2 - Land transport rate (₱/MT)"
        int barge_partner_id FK "References LOGISTICS_PARTNER.id (SET_NULL)"
        string vessel_or_barge_name "Vessel, Tugboat, or Barge identifier"
        decimal barge_rate_per_mt "12,2 - Marine barging rate (₱/MT)"
        string carrier_name "Hauler / Fleet name"
        string plate_number "Truck plate number"
        string waybill_number "Delivery Receipt / Mill MDR"
        string received_by "Receiver at facility"
        text notes "Delivery remarks"
        datetime created_at "Timestamp"
        datetime updated_at "Timestamp"
    }

    LOGISTICS_LEDGER {
        int id PK "Auto Primary Key"
        int cluster_id FK "1:1 with TRANSACTION_CLUSTER"
        decimal loaded_volume_mt "Aggregated origin volume"
        decimal received_volume_mt "Aggregated received volume"
        datetime loaded_at "Earliest batch dispatched_at"
        datetime received_at "Latest batch received_at"
        decimal tracking_fees "Sum of all batch trucking costs"
        decimal barge_fees "Sum of all batch barging costs"
        string dispute_status "None | Disputed | Resolved"
    }

    SUGAR_MILL {
        int id PK "Auto Primary Key"
        string name "e.g. BUSCO, CASA, URC-SONEDCO"
        string location "Geographic location"
        decimal default_base_price "Historical base"
        boolean is_active "Operational status"
    }

    LOGISTICS_PARTNER {
        int id PK "Auto Primary Key"
        string company_name "e.g. Solid Haulers, FastBarge Inc"
        string partner_type "Trucking | Barging | Combined"
        string contact_person "Representative"
        boolean is_active "Operational status"
    }
```

---

## 2. Table Schemas & Data Constraints

### 2.1 Table: `operations_deliveryledger`

| Column Name | Data Type | Nullable | Default | Description & Constraints |
| :--- | :--- | :---: | :---: | :--- |
| `delivery_id` | `uuid` | No | `uuid4()` | **Primary Key** |
| `purchase_order_id` | `bigint` | No | — | **FK** $\to$ `operations_purchaseorder.id` on `CASCADE` |
| `supplier_id` | `bigint` | No | — | **FK** $\to$ `masters_sugarmill.id` on `PROTECT` |
| `delivered_mt` | `numeric(12,2)` | No | `0.00` | Metric tons delivered. Guarded by `clean()` against PO balance. |
| `receiving_location` | `varchar(255)` | No | — | Drop-off destination (populated from `Client.name`). |
| `delivery_date` | `date` | No | `now()` | Date delivery was completed. |
| `dispatched_at` | `timestamptz` | Yes | `null` | Exact departure timestamp from the source sugar mill. |
| `received_at` | `timestamptz` | Yes | `null` | Exact arrival/intake timestamp at customer facility. |
| `trucking_partner_id`| `bigint` | Yes | `null` | **FK** $\to$ `masters_logisticspartner.id` on `SET_NULL` |
| `trucking_rate_per_mt`| `numeric(12,2)`| No | `0.00` | Land freight rate (₱/MT). |
| `barge_partner_id` | `bigint` | Yes | `null` | **FK** $\to$ `masters_logisticspartner.id` on `SET_NULL` |
| `vessel_or_barge_name`| `varchar(100)`| No | `''` | Marine vessel name / barge identifier. |
| `barge_rate_per_mt` | `numeric(12,2)`| No | `0.00` | Marine freight rate (₱/MT). |
| `carrier_name` | `varchar(150)` | No | `''` | Hauler name / fleet description. |
| `plate_number` | `varchar(50)` | No | `''` | Tractor or trailer license plate. |
| `waybill_number` | `varchar(100)` | No | `''` | Mill Delivery Receipt / Waybill number. |
| `received_by` | `varchar(100)` | No | `''` | Receiving checker / warehouse supervisor. |
| `notes` | `text` | No | `''` | Operational remarks. |

### 2.2 Calculated & Derived Properties on `DeliveryLedger`

```python
@property
def trucking_cost(self) -> Decimal:
    """Delivered volume MT multiplied by land trucking rate per MT."""
    return (self.delivered_mt * (self.trucking_rate_per_mt or Decimal("0.00"))).quantize(Decimal("0.01"))

@property
def barge_cost(self) -> Decimal:
    """Delivered volume MT multiplied by marine barge rate per MT."""
    return (self.delivered_mt * (self.barge_rate_per_mt or Decimal("0.00"))).quantize(Decimal("0.01"))

@property
def total_freight_cost(self) -> Decimal:
    """Total combined logistics cost for this individual delivery batch."""
    return self.trucking_cost + self.barge_cost
```

---

## 3. Database Indices & Optimization Strategy

1. **`purchase_order_id` Index:**
   - Enables sub-millisecond aggregation of all delivery batches for a Purchase Order (`deliveries.all()`).
2. **`supplier_id` Index:**
   - Enables real-time reporting of volumes sourced by sugar mill across all active contracts.
3. **`dispatched_at` & `received_at` Indices:**
   - Powers chronological sorting and earliest/latest transit milestone derivation for cluster synchronization.
