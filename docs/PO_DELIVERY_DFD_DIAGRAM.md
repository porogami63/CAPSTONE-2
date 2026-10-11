# Data Flow Diagram (DFD): Parent-Child Purchase Order & Incremental Delivery Engine

**System:** HTC Core Trading & Logistics Platform  
**Module:** Purchase Orders & Multi-Source Incremental Delivery Ledger  
**Version:** 2.1.0  
**Status:** Deployed & Verified (Production EC2)  
**Date:** October 11, 2026  

---

## 1. Executive Summary & Context

Prior to this implementation, the platform recorded trade logistics through a flat, single-dispatch assumption (1 Purchase Order = 1 Supplier Delivery). As discovered during stakeholder interviews, real-world raw/refined sugar trade involves:
- **Contract Splitting Across Locations:** A single contracted PO (e.g., 6,000 MT) is often partitioned across multiple drop-off facilities (e.g., 2,000 MT to ADI, 2,000 MT to HTC Tank, 2,000 MT to Balayan).
- **Multi-Source Sourcing:** A single customer contract (e.g., ADI 10,000 MT PO) is sourced from multiple sugar mills over time (e.g., 2,000 MT from BUSCO, 3,000 MT from CASA, etc.) depending on mill inventory availability.
- **Incremental Fulfillment Lifecycles:** Deliveries do not occur all at once. Fulfillment occurs incrementally across weeks or months, progressing from `Open` to `Partially Fulfilled` to `Completed`.

This document illustrates the **Data Flow Architecture** at Level 0 (Context Diagram) and Level 1 (Decomposition Diagram), documenting data transformations, inputs/outputs, validation boundaries, and persistence data stores.

---

## 2. Level 0 DFD: Context Diagram

The Context Diagram outlines the external entities interacting with the HTC Core System boundary for PO contracting and fulfillment.

```mermaid
flowchart TD
    classDef entity fill:#1e293b,stroke:#94a3b8,stroke-width:2px,color:#f8fafc;
    classDef process fill:#0284c7,stroke:#38bdf8,stroke-width:2px,color:#ffffff;
    classDef store fill:#334155,stroke:#cbd5e1,stroke-width:1px,color:#f8fafc;

    Customer["🏢 External Entity:<br/>Customer / Buyer<br/>(e.g., ADI, Universal Robina)"]:::entity
    Supplier["🏭 External Entity:<br/>Sugar Mills / Suppliers<br/>(e.g., BUSCO, CASA, URC-SONEDCO)"]:::entity
    LogisticsUser["👤 External Entity:<br/>Logistics Coordinator /<br/>Operations Manager"]:::entity
    Carrier["🚚 External Entity:<br/>Logistics Partner /<br/>Trucking Fleet"]:::entity

    HTCCore(["⚙️ HTC CORE SYSTEM<br/>PO & Incremental Delivery Ledger Engine"]):::process

    Customer -->|"Issues Purchase Order (Contracted MT, Specs, Pricing)"| HTCCore
    HTCCore -->|"PO Status Updates, Fulfillment Receipts, Invoices"| Customer

    LogisticsUser -->|"1. Initiates PO Contract<br/>2. Dispatches Batches<br/>3. Inputs Delivery Records"| HTCCore
    HTCCore -->|"Real-Time Balances, Over-Delivery Rejections, Audit Alerts"| LogisticsUser

    Supplier -->|"Stock Availability, Mill Delivery Receipts (MDR)"| HTCCore
    Carrier -->|"Waybill, Plate Number, Driver Details, Scale Weight"| HTCCore
    HTCCore -->|"Gate Pass, Delivery Schedule Authorization"| Carrier
```

---

## 3. Level 1 DFD: Process Decomposition Diagram

The Level 1 DFD decomposes the system into 6 core operational processes, showcasing how data flows between coordinators, validation guards, persistence stores, and legacy financial adapters.

```mermaid
flowchart TB
    classDef entity fill:#0f172a,stroke:#64748b,stroke-width:2px,color:#f8fafc;
    classDef process fill:#0369a1,stroke:#38bdf8,stroke-width:2px,color:#ffffff;
    classDef datastore fill:#1e293b,stroke:#0ea5e9,stroke-width:2px,color:#e0f2fe;
    classDef validation fill:#b91c1c,stroke:#f87171,stroke-width:2px,color:#ffffff;
    classDef legacy fill:#475569,stroke:#94a3b8,stroke-width:1px,color:#cbd5e1;

    %% Entities
    ClientEnt["🏢 Customer / Client"]:::entity
    OpsUser["👤 Operations Coordinator"]:::entity
    CarrierEnt["🚚 Hauler / Carrier"]:::entity

    %% Processes
    P1["1.0<br/>Create & Contract<br/>Purchase Order"]:::process
    P2["2.0<br/>Select PO & Prepare<br/>Batch Dispatch"]:::process
    P3{"3.0<br/>Over-Delivery Validation Guard<br/>(Balance Check Engine)"}:::validation
    P4["4.0<br/>Record Batch Delivery<br/>in DeliveryLedger"]:::process
    P5["5.0<br/>Recalculate PO Balances<br/>& Update State"]:::process
    P6["6.0<br/>Update Operational Dashboard<br/>& Legacy Bridge"]:::process

    %% Data Stores
    D1[("D1: PurchaseOrder Store<br/>(total_contracted_mt, po_status)")]:::datastore
    D2[("D2: DeliveryLedger Store<br/>(delivered_mt, supplier_id, loc)")]:::datastore
    D3[("D3: Masters Store<br/>(Client, SugarMill, LogisticsPartner)")]:::datastore
    D4[("D4: Historical Audit Log<br/>(HistoricalPurchaseOrder, HistoricalDelivery)")]:::datastore
    D5[("D5: TransactionCluster & Finance<br/>(LogisticsLedger, Invoices, Loans)")]:::legacy

    %% Process 1.0 Flow
    ClientEnt -->|"Contract Specs, Volume MT, Delivery Terms"| P1
    OpsUser -->|"Enter Contracted MT & Assign Customer"| P1
    D3 -.->|"Lookup Customer Record"| P1
    P1 -->|"Insert PO Header (Status: Open)"| D1
    P1 -.->|"Write Initial Audit Log"| D4

    %% Process 2.0 Flow
    OpsUser -->|"Select PO Reference & Enter Dispatch Data"| P2
    CarrierEnt -->|"Provide Plate No, Waybill, Scale Weight"| P2
    D1 -->|"Read total_contracted_mt & Current Deliveries"| P2
    D3 -->|"Provide Mill Supplier List (BUSCO/CASA)"| P2
    P2 -->|"Payload: {PO_ID, Supplier_ID, Delivered_MT, Location}"| P3

    %% Process 3.0 Flow (Validation)
    D1 -->|"Query remaining_mt"| P3
    P3 -->|"REJECT: delivered_mt > remaining_mt<br/>(HTTP 400: OVER_DELIVERY_NOT_PERMITTED)"| OpsUser
    P3 -->|"PASS: delivered_mt <= remaining_mt"| P4

    %% Process 4.0 Flow
    P4 -->|"Insert DeliveryLedger Record (UUID, Mill, MT, Loc, Date)"| D2
    P4 -.->|"Write Delivery Audit Snapshot"| D4
    P4 -->|"Trigger Status & Balance Recalculation"| P5

    %% Process 5.0 Flow
    D2 -->|"Aggregate SUM(delivered_mt) for PO"| P5
    P5 -->|"Update: remaining_mt = contracted_mt - SUM(delivered)<br/>Compute: Open | Partially Fulfilled | Completed"| D1
    P5 -->|"Live Status Event & Summary Metrics"| P6

    %% Process 6.0 Flow
    P6 -->|"Render Reactive Progress Bar & Real-Time Balance"| OpsUser
    P6 -.->|"Auto-Sync to Legacy LogisticsLedger for Cash Flow/P&L"| D5
```

---

## 4. Data Dictionary & Element Breakdown

| Data Element | Type | Source | Destination | Validation / Business Rules |
| :--- | :--- | :--- | :--- | :--- |
| `po_reference_number` | String (100) | Customer / Operations | `PurchaseOrder` (D1) | Unique business reference (e.g. `PO-ADI-2026-001`). Indexed. |
| `customer` | Foreign Key | `Client` (D3) | `PurchaseOrder` (D1) | Must reference active corporate client. |
| `total_contracted_mt` | Decimal(12,2) | Contract Terms | `PurchaseOrder` (D1) | Must be strictly > 0.00 MT. Backward-compatible with `volume_mt`. |
| `delivered_mt` | Decimal(12,2) | Scale Ticket / Hauler | `DeliveryLedger` (D2) | Must be > 0.00 MT and $\le$ `remaining_mt`. |
| `supplier` | Foreign Key | `SugarMill` (D3) | `DeliveryLedger` (D2) | Dynamic per delivery batch (e.g., BUSCO, CASA, URC). |
| `receiving_location` | String (255) | Shipping Instructions | `DeliveryLedger` (D2) | Physical receiving destination (e.g. ADI Plant, HTC Tank, Balayan). |
| `po_status` | Enum String | System Engine (P5) | `PurchaseOrder` (D1) | - `Open`: Delivered = 0 MT<br/>- `Partially Fulfilled`: 0 < Delivered < Contracted<br/>- `Completed`: Delivered $\ge$ Contracted |
| `remaining_mt` | Calculated | System Engine (P5) | API / UI (P6) | Formula: $\max(0, \text{total\_contracted\_mt} - \sum \text{delivered\_mt})$. |

---

## 5. Security & Boundary Guard Rails

1. **Client-Side Reactive Guard:**
   - Real-time JavaScript event listeners on `#id_delivered_mt` dynamically read data attributes `data-remaining-mt`.
   - Disables submission button and renders red warning banners if the user attempts to enter a value higher than the available balance.

2. **Server-Side Transactional Integrity (`clean()` & `save()`):**
   - Django ORM `clean()` method calculates `existing_delivered = SUM(all other deliveries for PO)`.
   - Prevents race conditions and guarantees no over-deliveries can be committed via ORM or Direct SQL.

3. **RESTful API Validation (`POST /deliveries`):**
   - Evaluates payload before serialization.
   - Throws deterministic HTTP `400 Bad Request` with standardized payload:
     ```json
     {
       "error": "Delivered quantity (4000.00 MT) exceeds remaining PO contracted quantity (2000.00 MT).",
       "code": "OVER_DELIVERY_NOT_PERMITTED",
       "remaining_mt": 2000.00
     }
     ```

4. **Audit Trail Immutability:**
   - Powered by `django-simple-history`.
   - Every delivery addition, adjustment, or cancellation creates immutable change snapshots in `HistoricalDeliveryLedger` and updates `HistoricalPurchaseOrder`.
