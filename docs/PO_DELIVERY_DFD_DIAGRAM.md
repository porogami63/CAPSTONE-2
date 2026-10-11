# Data Flow Diagram (DFD): Parent-Child Purchase Order & Incremental Delivery Engine

**System:** HTC Core Trading & Logistics Platform  
**Module:** Purchase Orders & Multi-Source Incremental Delivery Ledger  
**Version:** 2.2.0  
**Status:** Deployed & Verified (Production EC2)  
**Date:** October 11, 2026  

---

## 1. Executive Summary & Context

Prior to this implementation, the platform recorded trade logistics through a flat, single-dispatch assumption (1 Purchase Order = 1 Supplier Delivery). As discovered during stakeholder interviews, real-world raw/refined sugar trade involves:
- **Contract Splitting Across Locations & Customers:** A single contracted PO (e.g., 6,000 MT) is partitioned across multiple drop-off facilities (e.g., 2,000 MT to ADI, 2,000 MT to HTC Tank, 2,000 MT to Balayan, or dynamically dispatched to any active customer destination).
- **Multi-Source Sourcing:** A single customer contract (e.g., ADI 10,000 MT PO) is sourced from multiple sugar mills over time (e.g., 2,000 MT from BUSCO, 3,000 MT from CASA, etc.) depending on mill inventory availability.
- **Multi-Batch Logistics & Dynamic Freight Rates:** Each delivery batch carries distinct trucking routes (₱/MT), marine barging rates (₱/MT), carrier partners, vessel/barge assignments, dispatch departure times, and arrival timestamps.
- **Delivery-Based Suggestive Invoicing:** Customer billing automatically suggests the exact delivered shipment value (`total_delivered_mt * selling_price` or unbilled delivered balance) directly on the invoice panel.
- **Architectural Separation of Concerns:** The PO view retains fulfillment progress and the delivery ledger audit, but raw logistics management is linked directly to the dedicated PO workspace in the Deliveries & Trucking tab (`/operations/deliveries/?po=<PO_REF>`).

---

## 2. Level 0 DFD: Context Diagram

The Context Diagram outlines the external entities interacting with the HTC Core System boundary for PO contracting, fulfillment, and multi-batch logistics.

```mermaid
flowchart TD
    classDef entity fill:#1e293b,stroke:#94a3b8,stroke-width:2px,color:#f8fafc;
    classDef process fill:#0284c7,stroke:#38bdf8,stroke-width:2px,color:#ffffff;
    classDef store fill:#334155,stroke:#cbd5e1,stroke-width:1px,color:#f8fafc;

    Customer["🏢 External Entity:<br/>Customer / Buyer<br/>(e.g., ADI, Universal Robina)"]:::entity
    Supplier["🏭 External Entity:<br/>Sugar Mills / Suppliers<br/>(e.g., BUSCO, CASA, URC-SONEDCO)"]:::entity
    LogisticsUser["👤 External Entity:<br/>Logistics Coordinator /<br/>Operations Manager"]:::entity
    Carriers["🚚/🚢 External Entity:<br/>Logistics Partners<br/>(Trucking Fleets & Marine Barges)"]:::entity
    FinanceUser["💳 External Entity:<br/>Billing & Finance Team"]:::entity

    HTCCore(["⚙️ HTC CORE SYSTEM<br/>PO, Multi-Batch Delivery & Logistics Engine"]):::process

    Customer -->|"Issues Purchase Order (Contracted MT, Specs, Pricing)"| HTCCore
    HTCCore -->|"PO Status Updates, Fulfillment Receipts, Suggested Invoices"| Customer

    LogisticsUser -->|"1. Initiates PO Contract<br/>2. Dispatches Batches with Rates<br/>3. Inputs Timestamps & Carriers"| HTCCore
    HTCCore -->|"Real-Time Balances, Freight Costs, Over-Delivery Rejections"| LogisticsUser

    Supplier -->|"Stock Availability, Mill Delivery Receipts (MDR)"| HTCCore
    Carriers -->|"Waybill, Vessel/Barge Name, Truck Rates (₱/MT), Timestamps"| HTCCore
    HTCCore -->|"Gate Pass, Delivery Schedule Authorization"| Carriers

    FinanceUser -->|"Review Delivered Volumes & Issue Sales Invoices"| HTCCore
    HTCCore -->|"Pre-filled Invoice Input (Delivered MT × Price)"| FinanceUser
```

---

## 3. Level 1 DFD: Process Decomposition Diagram

The Level 1 DFD decomposes the system into operational processes, showcasing how data flows between coordinators, validation guards, multi-batch logistics aggregators, and the invoice suggestion engine.

```mermaid
flowchart TB
    classDef entity fill:#0f172a,stroke:#64748b,stroke-width:2px,color:#f8fafc;
    classDef process fill:#0369a1,stroke:#38bdf8,stroke-width:2px,color:#ffffff;
    classDef datastore fill:#1e293b,stroke:#0ea5e9,stroke-width:2px,color:#e0f2fe;
    classDef validation fill:#b91c1c,stroke:#f87171,stroke-width:2px,color:#ffffff;
    classDef finance fill:#15803d,stroke:#4ade80,stroke-width:2px,color:#ffffff;

    %% Entities
    ClientEnt["🏢 Customer / Client"]:::entity
    OpsUser["👤 Operations Coordinator"]:::entity
    CarrierEnt["🚚/🚢 Hauler & Barge Partners"]:::entity
    FinUser["💳 Billing Specialist"]:::entity

    %% Processes
    P1["1.0<br/>Contract PO<br/>(Contracted MT, Unit Price)"]:::process
    P2["2.0<br/>Prepare Batch Dispatch<br/>(Mill, Customer Dest, Rates)"]:::process
    P3{"3.0<br/>Over-Delivery Guard<br/>(Balance Check Engine)"}:::validation
    P4["4.0<br/>Record Delivery Batch &<br/>Freight Economics"]:::process
    P5["5.0<br/>Recalculate PO Balances<br/>& Multi-Batch Freight"]:::process
    P6["6.0<br/>Deliveries & Trucking<br/>Dedicated Workspace"]:::process
    P7["7.0<br/>Delivery-Based Suggestive<br/>Invoice Pricing Engine"]:::finance

    %% Data Stores
    D1[("D1: PurchaseOrder Store<br/>(total_contracted_mt, po_status)")]:::datastore
    D2[("D2: DeliveryLedger Store<br/>(delivered_mt, rates, timestamps)")]:::datastore
    D3[("D3: Masters Store<br/>(Client, SugarMill, LogisticsPartner)")]:::datastore
    D4[("D4: Historical Audit Log<br/>(HistoricalPurchaseOrder, HistoricalDelivery)")]:::datastore
    D5[("D5: TransactionCluster & Finance<br/>(LogisticsLedger, Invoices, Loans)")]:::datastore

    %% Flows
    ClientEnt -->|"Contract Specs, Volume MT, Selling Price"| P1
    P1 -->|"Insert PO Header (Status: Open)"| D1
    D3 -.->|"Active Client Lookup"| P1

    OpsUser -->|"Select PO, Sugar Mill, Receiving Customer, Truck/Barge Rates"| P2
    CarrierEnt -->|"Timestamps (Dispatched/Received), Vessel Name"| P2
    D3 -.->|"Populate All Active Customers & Hauler Directory"| P2
    P2 -->|"Payload: {po_id, mill, delivered_mt, rates, dates, dest}"| P3

    D1 -->|"Read remaining_mt"| P3
    P3 -->|"REJECT: delivered_mt > remaining_mt (HTTP 400)"| OpsUser
    P3 -->|"PASS: delivered_mt <= remaining_mt"| P4

    P4 -->|"Insert DeliveryLedger Record (UUID, Rates, Timestamps)"| D2
    P4 -.->|"Write Audit Snapshot"| D4
    P4 -->|"Trigger Status & Freight Aggregation"| P5

    D2 -->|"Aggregate SUM(delivered_mt), SUM(trucking_cost), SUM(barge_cost)"| P5
    P5 -->|"Update: remaining_mt, po_status (Open/Partial/Completed)"| D1
    P5 -->|"Sync tracking_fees, barge_fees, loaded/received timestamps"| D5

    OpsUser -->|"Navigate via PO View to ?po=REF"| P6
    D2 -->|"Filter Batch Dispatches for Focused PO"| P6

    FinUser -->|"Open Invoice Panel on PO View"| P7
    D1 -->|"Read selling_price & total_delivered_mt"| P7
    D2 -->|"Read recorded deliveries"| P7
    P7 -->|"Pre-fill Suggestion: total_delivered_mt × selling_price"| FinUser
    P7 -->|"Issue Invoice Record"| D5
```

---

## 4. Multi-Batch Logistics & Rate Architecture

### How Multiple Deliveries / Batches Handle Trucking & Barging Rates:
1. **Per-Batch Granularity:**
   - Each `DeliveryLedger` record stores its own:
     - `trucking_partner` & `trucking_rate_per_mt` (₱/MT).
     - `barge_partner`, `vessel_or_barge_name`, & `barge_rate_per_mt` (₱/MT).
     - `dispatched_at` (mill departure timestamp) & `received_at` (destination arrival timestamp).
2. **Deterministic Cost Computation:**
   - $\text{trucking\_cost} = \text{delivered\_mt} \times \text{trucking\_rate\_per\_mt}$
   - $\text{barge\_cost} = \text{delivered\_mt} \times \text{barge\_rate\_per\_mt}$
   - $\text{total\_freight\_cost} = \text{trucking\_cost} + \text{barge\_cost}$
3. **Automatic Cluster Synchronization:**
   - Upon saving any delivery batch, `sync_cluster_logistics()` recalculates:
     - `cluster.logistics.tracking_fees = SUM(d.trucking_cost for all deliveries)`
     - `cluster.logistics.barge_fees = SUM(d.barge_cost for all deliveries)`
     - `cluster.logistics.loaded_at = MIN(dispatched_at)`
     - `cluster.logistics.received_at = MAX(received_at)`
     - `cluster.logistics.received_volume_mt = po.total_delivered_mt`
   - This keeps executive P&L dashboards, loan prerequisite checks, and financial debriefs 100% accurate without manual data re-entry.

---

## 5. Delivery-Based Suggestive Invoicing Flow

1. **Auto-Suggestion Equation:**
   $$\text{Delivered Total} = \text{total\_delivered\_mt} \times \text{selling\_price}$$
   $$\text{Unbilled Delivered Balance} = \max(0, \text{Delivered Total} - \text{already\_invoiced})$$
2. **Reactive Panel Display:**
   - When recorded deliveries exist and have unbilled balances, the invoice issuance panel on the PO view displays an alert banner detailing:
     - Delivered MT & Customer Unit Price.
     - Total Delivered Sales Value.
     - "Apply Delivered" one-click action button that populates the invoice input field.
3. **Form Pre-Filling:**
   - `InvoiceForm` automatically sets its default initial amount to the unbilled delivered amount when shipment deliveries are present.

---

## 6. Separation of Concerns: PO View vs. Deliveries & Trucking Hub

- **PO View (`cluster_detail.html`):**
  - Displays contracted volume, fulfillment percentage, remaining MT, and an audit table of delivery batches.
  - Legacy standalone logistics edit forms have been removed to eliminate clutter and prevent operational confusion.
  - Features a prominent **"Open Deliveries & Trucking Tab"** link navigating directly to `/operations/deliveries/?po=<PO_REF>`.
- **Deliveries & Trucking Tab (`deliveries_list.html`):**
  - Automatically activates a **"Focused PO Logistics Workspace"** banner when accessed via `?po=<REF>`.
  - Aggregates focused PO metrics: total delivered MT, total land trucking costs, total marine barging costs, and aggregate logistics expenditure.
  - Lists individual batch dispatch/arrival timestamps, carrier assignments, and per-MT rates.
