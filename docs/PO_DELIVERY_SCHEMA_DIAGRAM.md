# Database Schema Diagram: Purchase Order & Incremental Delivery Ledger

**System:** HTC Core Trading & Logistics Platform  
**Database:** PostgreSQL 16  
**Application Apps:** `operations`, `masters`, `finance`  
**Schema Version:** Post-Migration `operations.0014_backfill_po_and_deliveries`  
**Date:** October 11, 2026  

---

## 1. Entity-Relationship Diagram (ERD)

The following Mermaid diagram maps the database entities, primary keys (`PK`), foreign keys (`FK`), and cardinality relationships for the refactored Parent-Child Purchase Order and Multi-Source Delivery Ledger module.

```mermaid
erDiagram
    CLIENT ||--o{ PURCHASE_ORDER : "issues (1:N)"
    PURCHASE_ORDER ||--|{ DELIVERY_LEDGER : "fulfilled by (1:N)"
    SUGAR_MILL ||--o{ DELIVERY_LEDGER : "sources batch (1:N)"
    LOGISTICS_PARTNER ||--o{ DELIVERY_LEDGER : "transports batch (0:N)"
    
    PURCHASE_ORDER ||--o| TRANSACTION_CLUSTER : "bridges legacy (1:1)"
    TRANSACTION_CLUSTER ||--o{ LOGISTICS_LEDGER : "legacy entries (1:N)"
    LOGISTICS_PARTNER ||--o{ LOGISTICS_LEDGER : "hauls (1:N)"

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
        string receiving_location "e.g. ADI Plant, Balayan, HTC Tank"
        date delivery_date "Actual delivery date"
        int logistics_partner_id FK "Optional References LOGISTICS_PARTNER.id"
        string carrier_name "Hauler company name"
        string plate_number "Truck plate number"
        string waybill_number "Delivery Receipt / Mill MDR"
        string received_by "Receiver at facility"
        text notes "Delivery remarks"
        datetime created_at "Timestamp"
        datetime updated_at "Timestamp"
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
        string company_name "Trucking company name"
        string contact_number "Phone"
        decimal standard_rate_per_mt "Standard hauling rate"
    }

    TRANSACTION_CLUSTER {
        uuid id PK "Cluster Identifier"
        string cluster_number UK "e.g. CLU-2026-0001"
        int po_id FK "OneToOne references PURCHASE_ORDER.id"
        int client_id FK "References CLIENT.id"
        int sugar_mill_id FK "References SUGAR_MILL.id"
        string status "Cluster state"
        decimal contracted_volume_mt "Cluster sync"
        decimal delivered_volume_mt "Cluster sync"
    }

    LOGISTICS_LEDGER {
        uuid id PK "UUIDv4"
        uuid cluster_id FK "References TRANSACTION_CLUSTER.id"
        int partner_id FK "References LOGISTICS_PARTNER.id"
        decimal quantity_mt "12,2"
        string origin "Mill Origin"
        string destination "Drop-off Destination"
        date trip_date "Trip Date"
        decimal actual_cost "Financial P&L"
    }
```

---

## 2. Table Specifications & Schema Definitions

### 2.1. `operations_purchaseorder`
The parent contract header entity representing customer contractual commitments.

| Column Name | SQL Data Type | Nullable | Constraints & Defaults | Description |
| :--- | :--- | :---: | :--- | :--- |
| `id` | `INTEGER` | ❌ | Primary Key, Auto-increment | Unique PO database ID. |
| `po_reference_number` | `VARCHAR(100)` | ❌ | `INDEX`, `DEFAULT=''` | Official business reference number (e.g. `PO-2026-ADI-001`). |
| `customer_id` | `INTEGER` | ✔️ | `FK -> masters_client(id)` | Customer organization ordering the goods. |
| `total_contracted_mt` | `NUMERIC(12,2)` | ❌ | `DEFAULT=0.00`, `CHECK (>= 0)` | Total committed metric tons contracted. |
| `po_status` | `VARCHAR(30)` | ❌ | `INDEX`, `DEFAULT='Open'` | Status: `'Open'`, `'Partially Fulfilled'`, or `'Completed'`. |
| `volume_mt` | `NUMERIC(12,2)` | ❌ | Legacy fallback column | Preserved for 100% backward compatibility. |
| `contract_date` | `DATE` | ✔️ | Nullable | Date contract was finalized. |
| `created_at` | `TIMESTAMPTZ` | ❌ | Auto now add | Creation timestamp. |
| `updated_at` | `TIMESTAMPTZ` | ❌ | Auto now | Last modified timestamp. |

**Calculated Properties (ORM Engine):**
- `total_delivered_mt`: `SUM(deliveries__delivered_mt)` (returns `Decimal(0.00)` if no deliveries).
- `remaining_mt`: `max(0, total_contracted_mt - total_delivered_mt)`.
- `fulfillment_percentage`: `min(100.0, (total_delivered_mt / total_contracted_mt) * 100)`.

---

### 2.2. `operations_deliveryledger`
The child delivery transactional table tracking granular, multi-sourced batch deliveries.

| Column Name | SQL Data Type | Nullable | Constraints & Defaults | Description |
| :--- | :--- | :---: | :--- | :--- |
| `delivery_id` | `UUID` | ❌ | Primary Key, `gen_random_uuid()` | Immutable UUID identifier for each delivery batch. |
| `purchase_order_id` | `INTEGER` | ❌ | `FK -> operations_purchaseorder(id) ON DELETE CASCADE` | Parent Purchase Order being fulfilled. |
| `supplier_id` | `INTEGER` | ❌ | `FK -> masters_sugarmill(id) ON DELETE PROTECT` | Sourcing Sugar Mill (e.g., BUSCO, CASA, etc.). |
| `delivered_mt` | `NUMERIC(12,2)` | ❌ | `CHECK (delivered_mt > 0)` | Net scale metric tons delivered in this batch. |
| `receiving_location` | `VARCHAR(255)` | ❌ | Not null | Facility destination (e.g., ADI Plant, Balayan, HTC Tank). |
| `delivery_date` | `DATE` | ❌ | `DEFAULT=CURRENT_DATE` | Actual date delivered. |
| `carrier_name` | `VARCHAR(150)` | ✔️ | `DEFAULT=''` | Trucking company / hauler name. |
| `plate_number` | `VARCHAR(50)` | ✔️ | `DEFAULT=''` | Vehicle registration plate number. |
| `waybill_number` | `VARCHAR(100)` | ✔️ | `DEFAULT=''` | Delivery Receipt / Mill Waybill number. |
| `received_by` | `VARCHAR(150)` | ✔️ | `DEFAULT=''` | Receiving supervisor at customer plant/tank. |
| `notes` | `TEXT` | ✔️ | `DEFAULT=''` | Operational remarks or scale variance notes. |
| `created_at` | `TIMESTAMPTZ` | ❌ | Auto now add | Record creation timestamp. |
| `updated_at` | `TIMESTAMPTZ` | ❌ | Auto now | Record update timestamp. |

**Indexes & Performance Optimizations:**
- `CREATE INDEX idx_delivery_po ON operations_deliveryledger (purchase_order_id);`
- `CREATE INDEX idx_delivery_supplier ON operations_deliveryledger (supplier_id);`
- `CREATE INDEX idx_delivery_date ON operations_deliveryledger (delivery_date);`

---

## 3. Lifecycle State Machine

The Purchase Order state automatically transitions based on the cumulative delivery sum:

```mermaid
stateDiagram-v2
    [*] --> Open: PO Contract Created (Delivered = 0 MT)
    
    Open --> Partially_Fulfilled: Batch Delivered (0 < Delivered < Contracted)
    Partially_Fulfilled --> Partially_Fulfilled: Subsequent Batch Delivered (Delivered < Contracted)
    Partially_Fulfilled --> Completed: Final Batch Delivered (Delivered >= Contracted)
    
    Open --> Completed: Single 100% Full Batch Delivered
    
    Completed --> Partially_Fulfilled: Delivery Record Deleted or Downward Adjusted
    Partially_Fulfilled --> Open: All Deliveries Deleted
```

---

## 4. Historical Audit Tables (`django-simple-history`)

To meet ISO compliance and internal financial audit requirements, all changes create immutable rows in corresponding historical tables:
- `operations_historicalpurchaseorder`: Logs timestamp, modifying user, diff of contracted volume, and status transitions.
- `operations_historicaldeliveryledger`: Logs timestamp, modifying user, previous delivered MT, previous destination, and carrier adjustments.

---

## 5. Backward Compatibility Bridge Architecture

To prevent regressions across existing modules (e.g., invoices, driver loans, profit/loss calculations):
1. **Model Fallback Property:**
   - Any legacy code calling `po.volume_mt` receives the current `total_contracted_mt`.
2. **Dual-Sourcing Legacy Cluster Bridge:**
   - When a `DeliveryLedger` record is saved, an automated signal triggers `auto_sync_cluster_from_delivery()`.
   - If the PO is tied to a `TransactionCluster`, a synchronized entry is mirrored into `LogisticsLedger` with corresponding mill origin and destination.
   - Financial accounting, hauling expense calculations, and billing reports continue functioning without downtime.
