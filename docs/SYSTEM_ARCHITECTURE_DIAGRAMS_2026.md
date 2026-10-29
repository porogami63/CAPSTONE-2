# HTC Core — Comprehensive System Architecture, ERD, DFD, Database Schema & Use Case Diagrams

**System Name:** HTC Core Trading & Logistics Management Platform (Capstone 2)  
**Client Organization:** Heindrich Trading Corporation (HTC)  
**Document Classification:** Official Technical Architecture Specification  
**Architecture Version:** v2.3.0 (Post-Parent PO, Multi-Batch Haulage, MRO Document AI & Cloud EC2 Deployment)  
**Date:** October 2026  

---

## Executive Overview: The Drastic System Evolution

Following the recent architectural overhauls (Milestones 1 through 5, Phase 1.5 UAT, and the Multi-Batch Logistics & Document AI upgrades), the HTC Core platform has transformed from a simple flat-dispatch prototype into an **enterprise-grade, multi-entity commodity trading and logistics engine**. 

### Key Architectural Shifts Reflected in These Diagrams:
1. **Parent-Child Contract Splitting (1:N)**: A single contracted customer Purchase Order (`PurchaseOrder`) is no longer a single delivery event. It is now fulfilled incrementally across multiple sourcing sugar mills (`SugarMill`), multiple receiving customer destinations, and multiple delivery batches (`DeliveryLedger`).
2. **Multi-Batch Freight Economics & Dual Logistics Modes**: Land trucking and marine barging costs are dynamically tracked per batch with independent freight rates (₱/MT) and flat fees, automatically aggregating into the transaction cluster's `LogisticsLedger`.
3. **Automated Cross-Module Financial Event Synchronization**: When a delivery batch is saved, the engine automatically calculates land freight, sea freight, and raw sugar sourcing costs, auto-generating pending `CashVoucher` records and `PaymentExpenseMatch` items linked to active `CapitalLoan` facilities.
4. **MRO Lifecycle & AWS Textract Document AI OCR**: Molasses Release Orders (`MolassesReleaseOrder`) are directly bound to transaction clusters, backed by an asynchronous OCR pipeline (`MROExtractionJob`) with confidence scoring and side-by-side scan previews.
5. **Quality Grading & Chemical Verification (CHAI)**: Integrated `CHAIRecord` tracking numerical grades (1.0 to 5.0), Brix %, apparent purity %, total sugars %, and executive approval gating.
6. **Dynamic Financial Treasury & Dual Authorization**: Real-time daily accrued interest calculation (`accrued_interest`) on high-interest sourcing loans, 50% logistics deposit tracking, dual-auth creation/settlement workflows, and suggestive customer invoicing with automated 12% VAT and 1% EWT tax splits.
7. **Security Hardening & Enterprise Audit**: Strict RBAC across 5 distinct roles, Administrator registration approval gating, TOTP Two-Factor Authentication (2FA) with single-use recovery codes, and append-only immutable audit trails (`SystemAuditTrail`).

> 📐 **Master Draw.io Multi-Tab Notebook:** [Download htc_architecture_diagrams.drawio](diagrams/htc_architecture_diagrams.drawio) (Contains all 5 architecture diagrams in a single multi-page project ready for [app.diagrams.net](https://app.diagrams.net))

---

## 1. Entity-Relationship Diagram (ERD)

The following diagram captures all 17 primary database entities across the 6 core Django applications (`accounts`, `masters`, `operations`, `finance`, `audit`, and `chat`), documenting primary keys (`PK`), foreign keys (`FK`), and cardinalities.

> 🖼️ **Rendered Diagram Image:** [Download High-Res PNG](diagrams/01_entity_relationship_diagram_erd.png) | [Vector SVG](diagrams/01_entity_relationship_diagram_erd.svg) | [Draw.io File](diagrams/01_entity_relationship_diagram_erd.drawio) | [Raw XML](diagrams/01_entity_relationship_diagram_erd.xml)
>
> ![HTC Core Entity-Relationship Diagram](diagrams/01_entity_relationship_diagram_erd.png)

```mermaid
erDiagram
    %% Tier 1: Master Counterparties & Auth
    USER ||--o{ SYSTEM_AUDIT_TRAIL : "audits (0:N)"
    CLIENT ||--o{ TRANSACTION_CLUSTER : "contracts (1:N)"
    SUGAR_MILL ||--o{ TRANSACTION_CLUSTER : "sources (1:N)"
    SUGAR_MILL ||--o{ MOLASSES_RELEASE_ORDER : "issues (1:N)"
    PLANTER ||--o{ MOLASSES_RELEASE_ORDER : "quota holder (1:N)"

    %% Tier 2: Commercial Contract Core
    TRANSACTION_CLUSTER ||--|| PURCHASE_ORDER : "commercial terms (1:1)"
    TRANSACTION_CLUSTER ||--|| LOGISTICS_LEDGER : "aggregates haulage (1:1)"
    TRANSACTION_CLUSTER ||--o{ MOLASSES_RELEASE_ORDER : "permits (0:N)"
    TRANSACTION_CLUSTER ||--o{ CAPITAL_LOAN : "financed by (0:N)"

    %% Tier 3: Logistics Execution & Lab QA
    PURCHASE_ORDER ||--|{ DELIVERY_LEDGER : "fulfilled by (1:N)"
    LOGISTICS_PARTNER ||--o{ DELIVERY_LEDGER : "hauls (0:N)"
    MOLASSES_RELEASE_ORDER ||--o{ MRO_EXTRACTION_JOB : "OCR intake (0:N)"
    MOLASSES_RELEASE_ORDER ||--o{ CHAI_RECORD : "lab tests (0:N)"

    %% Tier 4: Invoicing, Outlays & Reconciliation
    DELIVERY_LEDGER ||--o{ INVOICE : "billed via (0:N)"
    CAPITAL_LOAN ||--o{ CASH_VOUCHER : "disburses expenses (0:N)"
    CAPITAL_LOAN ||--|| FINANCIAL_RECONCILIATION : "reconciled in (1:1)"
    FINANCIAL_RECONCILIATION ||--|{ PAYMENT_EXPENSE_MATCH : "matched lines (1:N)"

    CLIENT {
        bigint id PK
        string name "Customer / Buyer Name"
        string tin "Tax Identification Number"
        string contact_person "Representative"
        boolean is_active "Active Status"
    }
    SUGAR_MILL {
        bigint id PK
        string name "Mill Name (BUSCO, CASA, etc.)"
        string location "Geographic Site"
        boolean is_active "Operational Status"
    }
    PLANTER {
        bigint id PK
        string name UK "Planter / Association"
        string code "Planter Code"
        boolean is_active "Active Status"
    }
    LOGISTICS_PARTNER {
        bigint id PK
        string name "Carrier / Hauler Name"
        string category "trucking | barging"
        decimal default_freight_rate "Baseline ₱/MT"
        boolean is_active "Active Status"
    }
    USER {
        bigint id PK
        string username UK
        string role "administrator | ops | finance | invoicing"
        boolean is_active "Approval Gating"
        boolean is_2fa_enabled "TOTP 2FA Status"
    }
    SYSTEM_AUDIT_TRAIL {
        bigint id PK
        bigint user_id FK
        string action "create | update | delete"
        string table_name "Target Table"
        datetime timestamp "Append-only Timestamp"
    }
    TRANSACTION_CLUSTER {
        uuid id PK
        string reference_code UK "TRX-20261010-001"
        bigint client_id FK "Customer"
        bigint sugar_mill_id FK "Origin Mill"
        string status "draft | approved | active | delivered | closed"
        string mro_file "Consolidated Scan PDF"
        boolean is_archived "Archival Flag"
    }
    PURCHASE_ORDER {
        bigint id PK
        uuid cluster_id FK "1:1 with Cluster"
        string po_reference_number UK "PO-ADI-2026-001"
        decimal total_contracted_mt "Target Contract MT"
        decimal unit_price "Supplier Price ₱/MT"
        decimal selling_price "Customer Billed Price ₱/MT"
        string po_status "Open | Partially Fulfilled | Completed"
    }
    LOGISTICS_LEDGER {
        bigint id PK
        uuid cluster_id FK "1:1 with Cluster"
        decimal loaded_volume_mt "Aggregated Origin MT"
        decimal received_volume_mt "Aggregated Received MT"
        decimal tracking_fees "Sum Trucking Fees"
        decimal barge_fees "Sum Barging Fees"
        decimal variance_percent "Transit Shrinkage %"
        boolean variance_exceeds_tolerance "> 1.0% Threshold"
        string dispute_status "NONE | DISPUTED | RESOLVED"
    }
    MOLASSES_RELEASE_ORDER {
        bigint id PK
        string mro_number "Official Permit #"
        bigint planter_id FK "Planter"
        bigint sugar_mill_id FK "Origin Mill"
        decimal tons "Authorized Quota MT"
        string crop_year "e.g. 2024 - 2025"
        uuid cluster_id FK "Covered Cluster"
    }
    DELIVERY_LEDGER {
        uuid delivery_id PK
        bigint purchase_order_id FK "Parent PO"
        bigint supplier_id FK "Sourcing Mill"
        decimal delivered_mt "Batch Dispatched MT"
        string receiving_location "Customer Drop-off Site"
        bigint trucking_partner_id FK "Land Carrier"
        decimal trucking_rate_per_mt "₱/MT Rate + Flat Fee"
        bigint barge_partner_id FK "Marine Carrier"
        decimal barge_rate_per_mt "₱/MT Rate + Flat Fee"
    }
    CHAI_RECORD {
        uuid id PK
        string chai_number UK "CHAI-20261010-001"
        decimal chai_value "Grade: 1.0 to 5.0"
        uuid cluster_id FK "Deal Cluster"
        decimal brix_level "Laboratory Brix %"
        string status "approved | pending | rejected"
    }
    MRO_EXTRACTION_JOB {
        uuid id PK
        uuid cluster_id FK "Deal Cluster"
        string status "queued | processing | completed | failed"
        float average_confidence "Textract Confidence"
        json extracted_data "Parsed Key-Values"
    }
    INVOICE {
        bigint id PK
        uuid cluster_id FK "Deal Cluster"
        string invoice_number UK
        decimal amount "Gross Invoiced ₱"
        decimal tax_rate_vat "12% Output VAT"
        decimal tax_rate_ewt "1% Creditable EWT"
        boolean is_incremental "Progress Billing Flag"
        string status "draft | issued | paid | returned"
    }
    CAPITAL_LOAN {
        bigint id PK
        uuid cluster_id FK "Financed Deal"
        string bank_name "Commercial Lending Bank"
        decimal principal "Funded Sourcing Balance"
        decimal interest_rate_annual "Annual Interest Rate %"
        date start_date
        date due_date
        string status "active | closed | pending_settlement"
    }
    CASH_VOUCHER {
        bigint id PK
        bigint loan_id FK "Backing Loan Facility"
        string voucher_number UK "CV-DEL-08AF21-TRK"
        decimal amount "Disbursed Expense ₱"
        string purpose "Trucking, Barge, or Sourcing"
        string status "pending | issued | cancelled"
    }
    FINANCIAL_RECONCILIATION {
        bigint id PK
        uuid cluster_id FK "1:1 with Cluster"
        string status "draft | finalized"
        decimal matched_payment_amount "Matched Total ₱"
    }
    PAYMENT_EXPENSE_MATCH {
        bigint id PK
        bigint reconciliation_id FK
        string payment_reference "Voucher / Cheque Ref"
        string expense_type "sourcing | trucking | barge | deposit"
        decimal amount "Matched Amount ₱"
    }
```

---

## 2. Data Flow Diagrams (DFD)

> [!IMPORTANT]
> **Internal Staff Access Boundary (No External User Accounts):**
> HTC Core is strictly a private, role-based internal enterprise system. **External commercial counterparties—specifically Financing Banks, Customers, Sugar Mills, and Logistics Haulers—do NOT have user accounts or web portal access.**
> All real-world offline inputs—such as physical Bank Clearance Advices (`settlement_receipt_number`), paper cheques, customer purchase contracts, mill delivery receipts (MDR), and carrier waybills—are received via physical, phone, or email channels and entered directly into the portal by authorized HTC internal staff (`operations_management`, `operations`, `finance`, `invoicing`).

### 2.1 Level 0 DFD: Context Diagram
The Level 0 Context Diagram maps how data flows across the system boundary between authenticated internal staff, automated cloud microservices, and offline external business counterparties.

> 🖼️ **Rendered Diagram Image:** [Download High-Res PNG](diagrams/02_dfd_level0_context_diagram.png) | [Vector SVG](diagrams/02_dfd_level0_context_diagram.svg) | [Draw.io File](diagrams/02_dfd_level0_context_diagram.drawio) | [Raw XML](diagrams/02_dfd_level0_context_diagram.xml)
>
> ![HTC Core Level 0 Context Diagram](diagrams/02_dfd_level0_context_diagram.png)

```mermaid
flowchart LR
    classDef staff fill:#0f172a,stroke:#38bdf8,stroke-width:2px,color:#f8fafc;
    classDef core fill:#0284c7,stroke:#38bdf8,stroke-width:3px,color:#ffffff;
    classDef ext fill:#1e293b,stroke:#64748b,stroke-width:1.5px,color:#f1f5f9;
    classDef cloud fill:#2e1065,stroke:#a855f7,stroke-width:2px,color:#ffffff;

    subgraph InternalStaff ["👥 AUTHENTICATED INTERNAL USERS (Web Portal Accounts)"]
        direction TB
        Admin["🛡️ System Administrator<br/><small>• User Approvals & RBAC Roles<br/>• 2FA Security Enforcement<br/>• Immutable Audit Inspection</small>"]:::staff
        Ops["👤 Operations Team<br/><small>• Deal Clusters & PO Contracts<br/>• Multi-Batch Dispatches & Rates<br/>• MRO Upload & Quality Grading<br/>• Transit Shrinkage Disputes</small>"]:::staff
        Fin["💳 Finance & Invoicing<br/><small>• Sourcing Capital Loans<br/>• Daily Dynamic Accruals<br/>• Suggestive Sales Invoicing<br/>• 3-Step Match & Cash Vouchers</small>"]:::staff
    end

    Platform(("⚙️ 0.0<br/>HTC CORE PLATFORM<br/><small>Trading, Multi-Batch Logistics,<br/>Dynamic Treasury & Document AI</small>")):::core

    subgraph ExternalEntities ["🏢 EXTERNAL COUNTERPARTIES & CLOUD SERVICES (Offline / API)"]
        direction TB
        Cust["🏢 Clients / Buyers<br/><small>• Contract Purchase Orders<br/>• Receiving Weighbridge Receipts<br/>• Invoices & Statements of Account</small>"]:::ext
        Mills["🏭 Sugar Mills & Planters<br/><small>• MRO Permits & Mill Quotas<br/>• Mill Delivery Receipts (MDR)<br/>• Brix Laboratory Quality Reports</small>"]:::ext
        Carriers["🚚 Logistics Carriers<br/><small>• Hauler Gate Passes & Waybills<br/>• Truck / Barge Freight Rates<br/>• Cheque Disbursement Vouchers</small>"]:::ext
        Banks["🏦 Commercial Lending Banks<br/><small>• Sourcing Loan Terms & Principal<br/>• Daily Interest Rates<br/>• Settlement Clearance Advices</small>"]:::ext
        Textract["☁️ AWS Textract Document AI<br/><small>• Scanned MRO Document PDFs<br/>• Extracted Tables & Key-Values<br/>• Confidence Scores</small>"]:::cloud
    end

    %% Internal Web Interactions
    Admin <-->|"User Approvals & Audit Queries"| Platform
    Ops <-->|"Logistics, MRO & Deal Data"| Platform
    Fin <-->|"Treasury, Invoicing & Loan Data"| Platform

    %% External & Cloud Interactions
    Platform <-->|"Sales Invoices & Billing Statements"| Cust
    Platform <-->|"Permits, MDRs & Brix Specs"| Mills
    Platform <-->|"Waybills, Rates & Cheque Vouchers"| Carriers
    Platform <-->|"Credit Lines, Payoffs & Advices"| Banks
    Platform <-->|"Automated Cloud OCR API"| Textract
```

---

### 2.2 Level 1 DFD: Process Decomposition Diagram
The Level 1 DFD decomposes HTC Core into its **10 major operational sub-processes**, showing data flows driven by internal authenticated staff and automated services across the 8 data stores.

> 🖼️ **Rendered Diagram Image:** [Download High-Res PNG](diagrams/03_dfd_level1_process_decomposition.png) | [Vector SVG](diagrams/03_dfd_level1_process_decomposition.svg) | [Draw.io File](diagrams/03_dfd_level1_process_decomposition.drawio) | [Raw XML](diagrams/03_dfd_level1_process_decomposition.xml)
>
> ![HTC Core Level 1 Process Decomposition DFD](diagrams/03_dfd_level1_process_decomposition.png)

```mermaid
flowchart TD
    classDef proc fill:#0284c7,stroke:#38bdf8,stroke-width:2px,color:#ffffff;
    classDef check fill:#b91c1c,stroke:#f87171,stroke-width:2px,color:#ffffff;
    classDef fin fill:#15803d,stroke:#4ade80,stroke-width:2px,color:#ffffff;
    classDef store fill:#1e293b,stroke:#0ea5e9,stroke-width:2px,color:#e0f2fe;
    classDef actor fill:#0f172a,stroke:#38bdf8,stroke-width:2px,color:#f8fafc;

    subgraph Phase1 ["1. COMMERCIAL SOURCING & MASTER DATA SETUP"]
        direction LR
        P1["1.0 Master Data & User RBAC<br/>(Clients, Mills, Carriers, RBAC)"]:::proc <--> D12[("D1 & D2: Master Catalogs<br/>& User Store")]:::store
        P1 -->|"Active Partners & Pricing"| P2["2.0 Deal & PO Formulation<br/>(Cluster Reference, Target MT, Base Price)"]:::proc
        P2 <--> D3[("D3: PurchaseOrder & Deal Store")]:::store
    end

    subgraph Phase2 ["2. PERMITTING & LAB QUALITY COMPLIANCE"]
        direction LR
        P3["3.0 MRO Document OCR & Intake<br/>(Scanned MRO PDF to AWS Textract)"]:::proc <--> D5[("D5: MRO Permitting Store")]:::store
        P3 -->|"Verified MRO Quota"| P4["4.0 CHAI Laboratory Quality Grading<br/>(Brix % & Physical Inspection Grade)"]:::proc
        P4 <--> D5B[("D5B: Lab Quality Store")]:::store
    end

    subgraph Phase3 ["3. MULTI-BATCH LOGISTICS & DISPUTE RESOLUTION"]
        direction LR
        P5{"5.0 Over-Delivery Balance Guard<br/>& Batch Haulage Dispatch"}:::check <--> D4[("D4: DeliveryLedger Store")]:::store
        P5 -->|"Delivered MT & Freight Rates"| P6{"6.0 Transit Variance Engine<br/>(Flag >1.0% Transit Loss)"}:::check
        P6 <--> D4B[("D4B: LogisticsLedger Store")]:::store
    end

    subgraph Phase4 ["4. DYNAMIC TREASURY, INVOICING & SETTLEMENT"]
        direction LR
        P7["7.0 Suggestive Sales Invoicing<br/>(12% VAT + 1% EWT Computation)"]:::fin <--> D6[("D6: Billing & Invoices Store")]:::store
        P7 -->|"Billed Revenue Base"| P8["8.0 Capital Loan Facility<br/>& Daily Accrual Engine"]:::fin
        P8 <--> D7[("D7: Capital Loans Facility")]:::store
        P8 -->|"Principal & Interest Outlays"| P9["9.0 Auto-Voucher Disbursement<br/>& 3-Step Payment Match"]:::fin
        P9 <--> D7B[("D7B: Cash Vouchers & Match Store")]:::store
    end

    subgraph Phase5 ["5. ENTERPRISE GOVERNANCE & AUDIT TRAIL"]
        direction LR
        P10["10.0 Immutable Audit Trail & HTC Copilot ORM Engine<br/>(Append-only logs & NL-to-SQL Assistant)"]:::proc <--> D8[("D8: Audit & Governance Store")]:::store
    end

    %% Sequential Main Pipeline Flow
    Phase1 ==>|"Approved Deal PO Contract"| Phase2
    Phase2 ==>|"Validated Quotas & Grade Approval"| Phase3
    Phase3 ==>|"Dispatched Dispatches & Waybill Freight"| Phase4
    Phase4 ==>|"Financial Closures & Reconciliation"| Phase5
```

---

### 2.3 Level 2 DFD: Process 5.0 (Parent PO & Incremental Multi-Batch Delivery Execution)
To highlight the drastic changes made to parent-child PO logistics, this Level 2 DFD drills directly into **Process 5.0**.

> 🖼️ **Rendered Diagram Image:** [Download High-Res PNG](diagrams/04_dfd_level2_multi_batch_delivery.png) | [Vector SVG](diagrams/04_dfd_level2_multi_batch_delivery.svg) | [Draw.io File](diagrams/04_dfd_level2_multi_batch_delivery.drawio) | [Raw XML](diagrams/04_dfd_level2_multi_batch_delivery.xml)
>
> ![HTC Core Level 2 Multi-Batch Delivery DFD](diagrams/04_dfd_level2_multi_batch_delivery.png)

```mermaid
flowchart TD
    classDef actor fill:#0f172a,stroke:#38bdf8,stroke-width:2px,color:#f8fafc;
    classDef proc fill:#0284c7,stroke:#38bdf8,stroke-width:2px,color:#ffffff;
    classDef check fill:#b91c1c,stroke:#f87171,stroke-width:2px,color:#ffffff;
    classDef store fill:#1e293b,stroke:#0ea5e9,stroke-width:2px,color:#e0f2fe;
    classDef fin fill:#15803d,stroke:#4ade80,stroke-width:2px,color:#ffffff;
    classDef err fill:#991b1b,stroke:#fca5a5,stroke-width:2px,color:#ffffff;

    StartInput["👤 Operations Coordinator<br/>(Submits Delivery Batch Payload)"]:::actor

    P51["5.1 Parse Batch Parameters<br/>(PO, Sugar Mill, Receiving Destination, Dispatched MT, Dual Freight Rates)"]:::proc

    POStore1[("D3: PurchaseOrder Store<br/>total_contracted_mt & deliveries")]:::store

    P52{"5.2 Over-Delivery Balance Guard<br/>Is delivered_mt <= remaining_contract_mt?"}:::check

    ErrBlock["❌ Over-Delivery Validation Error<br/>(Transaction Rejected & Blocked)"]:::err

    P53["5.3 Compute Dual-Mode Freight Economics<br/>Trucking Cost = (Delivered MT × Rate) + Flat Fee<br/>Barging Cost = (Delivered MT × Rate) + Flat Fee"]:::proc

    P54["5.4 Write DeliveryLedger Batch Entry<br/>(Store Timestamps, Plates, MDR & Waybill #)"]:::proc

    DelStore[("D4: DeliveryLedger Store<br/>[UUIDv4 Primary Key]")]:::store

    subgraph PostDeliverySync ["⚡ Automated Post-Delivery Synchronization"]
        direction LR
        P55["5.5 Update PO Fulfillment State<br/>(Open / Partially Fulfilled / Completed)"]:::proc
        P56["5.6 Synchronize LogisticsLedger<br/>(Aggregate Origin/Destination MT & Fees)"]:::proc
        P57["5.7 Trigger Auto-Voucher Outlays<br/>(Generate CV-DEL-*-TRK / BRG & 3-Step Match)"]:::fin
    end

    POStore2[("D3: PurchaseOrder Store")]:::store
    LogStore[("D4B: LogisticsLedger Store")]:::store
    FinStore[("D7: Treasury & Voucher Store")]:::store

    %% Flowchart Wiring
    StartInput --> P51
    P51 --> P52
    POStore1 -->|"Read Remaining Balance"| P52

    P52 -->|"NO: Exceeds Quota"| ErrBlock
    P52 -->|"YES: Within Contract Quota"| P53

    P53 --> P54
    P54 -->|"Insert Record"| DelStore

    P54 --> P55
    P54 --> P56
    P54 --> P57

    P55 -->|"Update Status"| POStore2
    P56 -->|"Update Totals"| LogStore
    P57 -->|"Record Vouchers"| FinStore
```

---

## 3. Comprehensive Database Schema Specification

This schema dictionary represents the **PostgreSQL 16** production database architecture backing HTC Core.

> 🖼️ **Rendered Schema Table Sheet:** [Download High-Res PNG](diagrams/06_database_schema_summary_tables.png)
>
> ![HTC Core Database Schema Summary Sheet](diagrams/06_database_schema_summary_tables.png)

### 3.1 `accounts_user` (Custom User & Identity Model)
Inherits from Django `AbstractUser`, adding role-based security, 2FA, and registration gating.

| Column | Data Type | Nullable | Default | Constraints / Index | Business Role & Logic |
|---|---|---|---|---|---|
| `id` | `BIGSERIAL` | No | Auto | `PK` | Unique user account ID |
| `username` | `VARCHAR(150)` | No | — | `UNIQUE, INDEX` | Corporate login username |
| `email` | `VARCHAR(254)` | Yes | `""` | — | User contact & notification email |
| `password` | `VARCHAR(128)` | No | — | — | PBKDF2 SHA-256 hashed password |
| `role` | `VARCHAR(30)` | No | `'operations'` | `INDEX` | Choices: `administrator`, `operations_management`, `operations`, `finance`, `invoicing` |
| `is_active` | `BOOLEAN` | No | `False` | `INDEX` | **Registration Gate**: Set to `False` upon signup until explicitly approved by Administrator |
| `is_2fa_enabled` | `BOOLEAN` | No | `False` | — | Indicates whether TOTP 2FA is enforced upon session login |
| `otp_secret` | `VARCHAR(32)` | Yes | `NULL` | — | Base32-encoded cryptographic TOTP secret for authenticator apps |
| `backup_codes` | `JSONB` | No | `'[]'` | — | Array of 5 hashed single-use emergency recovery codes |
| `avatar` | `VARCHAR(100)` | Yes | `NULL` | — | Path to uploaded user profile image in media storage |

---

### 3.2 `masters_*` (Master Data Catalog)

#### `masters_client` (Customer Directory)
| Column | Data Type | Nullable | Default | Constraints | Description |
|---|---|---|---|---|---|
| `id` | `BIGSERIAL` | No | Auto | `PK` | Client primary key |
| `name` | `VARCHAR(200)` | No | — | `INDEX` | Customer organization name (e.g. San Miguel Corp) |
| `tin` | `VARCHAR(50)` | Yes | `""` | — | Bureau of Internal Revenue Tax Identification Number |
| `address` | `TEXT` | Yes | `""` | — | Official billing and drop-off facility address |
| `contact_person` | `VARCHAR(120)` | Yes | `""` | — | Authorized commercial representative |
| `contact_phone` | `VARCHAR(50)` | Yes | `""` | — | Representative direct telephone / mobile |
| `email` | `VARCHAR(254)` | Yes | `""` | — | Invoicing destination email |
| `is_active` | `BOOLEAN` | No | `True` | `INDEX` | Active status in dropdown lookups |

#### `masters_sugarmill` (Origin Suppliers)
| Column | Data Type | Nullable | Default | Constraints | Description |
|---|---|---|---|---|---|
| `id` | `BIGSERIAL` | No | Auto | `PK` | Sugar mill primary key |
| `name` | `VARCHAR(200)` | No | — | `INDEX` | Mill name (e.g. BUSCO, CASA, HPCo, Lopez Sugar) |
| `location` | `VARCHAR(200)` | Yes | `""` | — | Geographic site (e.g. Bukidnon, Negros Occidental) |
| `contact_person` | `VARCHAR(120)` | Yes | `""` | — | Resident logistics coordinator / warehouseman |
| `is_active` | `BOOLEAN` | No | `True` | `INDEX` | Sourcing operational status |

#### `masters_logisticspartner` (Carriers & Fleets)
| Column | Data Type | Nullable | Default | Constraints | Description |
|---|---|---|---|---|---|
| `id` | `BIGSERIAL` | No | Auto | `PK` | Carrier primary key |
| `name` | `VARCHAR(200)` | No | — | `INDEX` | Hauler name (e.g. Solid Haulers, FastBarge Inc) |
| `category` | `VARCHAR(20)` | No | `'barging'` | — | Enum: `trucking` (Land) or `barging` (Marine) |
| `region` | `VARCHAR(150)` | Yes | `'Visayas / Luzon'` | — | Primary transit corridor |
| `fleet_count` | `INTEGER` | No | `0` | — | Active trucks or marine barge vessel count |
| `default_freight_rate`| `NUMERIC(12,2)`| No | `0.00` | — | Baseline quotation rate (₱/MT) |
| `is_active` | `BOOLEAN` | No | `True` | `INDEX` | Carrier dispatch eligibility |

---

### 3.3 `operations_*` (Core Trading, PO, Multi-Batch & Logistics)

#### `operations_transactioncluster` (Master Transaction Envelope)
| Column | Data Type | Nullable | Default | Constraints | Business Logic & Rules |
|---|---|---|---|---|---|
| `id` | `UUID` | No | `gen_random_uuid()` | `PK` | Unique transaction cluster UUID |
| `reference_code` | `VARCHAR(50)` | No | — | `UNIQUE, INDEX` | Auto-generated code (e.g. `TRX-20261010-001`) |
| `client_id` | `BIGINT` | No | — | `FK -> masters_client` | Primary purchasing customer |
| `sugar_mill_id` | `BIGINT` | No | — | `FK -> masters_sugarmill` | Primary origin sugar mill |
| `status` | `VARCHAR(20)` | No | `'draft'` | `INDEX` | Workflow: `draft` -> `pending_approval` -> `approved` -> `active` -> `delivered` -> `closed` (or `returned`) |
| `submitted_at` | `TIMESTAMPTZ` | Yes | `NULL` | — | Submission timestamp for manager review |
| `approved_at` | `TIMESTAMPTZ` | Yes | `NULL` | — | Executive approval timestamp |
| `approved_by_id`| `BIGINT` | Yes | `NULL` | `FK -> accounts_user` | Operations Manager / Admin who approved deal |
| `rejection_comments`| `TEXT` | No | `""` | — | Mandatory comments if deal is returned / rejected |
| `mro_file` | `VARCHAR(100)` | Yes | `NULL` | — | Scanned PDF soft-copy of consolidated MRO release |
| `is_archived` | `BOOLEAN` | No | `False` | `INDEX` | True when closed, fully settled & archived |

#### `operations_purchaseorder` (Parent PO Contract)
| Column | Data Type | Nullable | Default | Constraints | Business Logic & Formulas |
|---|---|---|---|---|---|
| `id` | `BIGSERIAL` | No | Auto | `PK` | Purchase order header primary key |
| `cluster_id` | `UUID` | No | — | `UNIQUE, FK -> cluster` | 1:1 binding to master transaction cluster |
| `po_reference_number`| `VARCHAR(50)`| Yes | `NULL` | `UNIQUE, INDEX` | Standard customer PO ref (e.g. `PO-ADI-2026-001`) |
| `customer_id` | `BIGINT` | Yes | `NULL` | `FK -> masters_client` | Direct client pointer (mirrors cluster client) |
| `total_contracted_mt`| `NUMERIC(14,3)`| Yes | `NULL` | — | Total agreed contract volume (e.g. 10,000.000 MT) |
| `po_status` | `VARCHAR(30)` | No | `'Open'` | `INDEX` | State: `Open`, `Partially Fulfilled`, `Completed` |
| `volume_mt` | `NUMERIC(14,3)`| No | — | — | Baseline volume MT field |
| `unit_price` | `NUMERIC(12,2)`| No | — | — | Sourcing purchase price paid to mill (₱/MT) |
| `selling_price` | `NUMERIC(12,2)`| Yes | `NULL` | — | Gross billing price charged to customer (₱/MT) |
| `brix_level` | `NUMERIC(5,2)` | Yes | `NULL` | — | Target contractual sugar Brix percentage |

> **Dynamic PO Properties:**
> * `total_delivered_mt = SUM(deliveries.delivered_mt)`
> * `remaining_mt = max(0, total_contracted_mt - total_delivered_mt)`
> * `update_status()`: Auto-triggers on batch save: Sets `Completed` when `remaining_mt == 0`, `Partially Fulfilled` when `delivered_mt > 0`, and updates parent Cluster status to `DELIVERED`.

#### `operations_deliveryledger` (Multi-Batch Fulfillment Ledger)
| Column | Data Type | Nullable | Default | Constraints | Business Logic & Freight Formulas |
|---|---|---|---|---|---|
| `delivery_id` | `UUID` | No | `gen_random_uuid()` | `PK` | Delivery batch primary key |
| `purchase_order_id`| `BIGINT` | No | — | `FK -> purchaseorder` | Parent PO contract being fulfilled |
| `supplier_id` | `BIGINT` | No | — | `FK -> masters_sugarmill`| Mill origin sourcing this specific batch |
| `delivered_mt` | `NUMERIC(14,3)`| No | — | — | Batch quantity in MT (Validated `<= remaining_mt`) |
| `receiving_location`| `VARCHAR(200)`| No | — | — | Drop-off point (e.g. Balayan, ADI, Tank Farm) |
| `delivery_date` | `DATE` | No | `CURRENT_DATE` | — | Scheduled / actual arrival date |
| `dispatched_at` | `TIMESTAMPTZ` | Yes | `NULL` | — | Exact mill gate departure timestamp |
| `received_at` | `TIMESTAMPTZ` | Yes | `NULL` | — | Exact customer destination arrival timestamp |
| `trucking_partner_id`| `BIGINT` | Yes | `NULL` | `FK -> carrier` | Land hauler assigned to batch |
| `trucking_rate_per_mt`| `NUMERIC(12,2)`| No | `0.00` | — | Land freight rate (₱/MT) |
| `flat_trucking_fee`| `NUMERIC(12,2)`| No | `0.00` | — | Lump-sum flat land transport fee |
| `barge_partner_id` | `BIGINT` | Yes | `NULL` | `FK -> carrier` | Marine barging hauler assigned to batch |
| `vessel_or_barge_name`| `VARCHAR(100)`| Yes | `""` | — | Barge or tugboat identification |
| `barge_rate_per_mt` | `NUMERIC(12,2)`| No | `0.00` | — | Marine freight rate (₱/MT) |
| `flat_barge_fee` | `NUMERIC(12,2)`| No | `0.00` | — | Lump-sum flat marine transport fee |
| `mro_permit_id` | `BIGINT` | Yes | `NULL` | `FK -> mro` | Linked Molasses Release Order permit |
| `dr_number` | `VARCHAR(100)` | Yes | `""` | — | Delivery Receipt (DR) / Weighbridge ticket # |
| `waybill_number` | `VARCHAR(100)` | Yes | `""` | — | Mill Waybill / MDR reference # |

> **Freight Calculation Properties:**
> * `trucking_cost = (delivered_mt * trucking_rate_per_mt) + flat_trucking_fee`
> * `barge_cost = (delivered_mt * barge_rate_per_mt) + flat_barge_fee`
> * `total_freight_cost = trucking_cost + barge_cost`
> * `clean()`: Automatically rejects save if `delivered_mt > po.remaining_mt`.
> * `save()`: Auto-triggers `sync_cluster_logistics()` and `sync_delivery_expense_vouchers()`.

#### `operations_logisticsledger` (Aggregated Logistics & Dispute Engine)
| Column | Data Type | Nullable | Default | Constraints | Description |
|---|---|---|---|---|---|
| `id` | `BIGSERIAL` | No | Auto | `PK` | Logistics ledger primary key |
| `cluster_id` | `UUID` | No | — | `UNIQUE, FK -> cluster` | 1:1 binding to master transaction cluster |
| `loaded_volume_mt` | `NUMERIC(14,3)`| No | — | — | Sum of origin loaded MT across batches |
| `received_volume_mt`| `NUMERIC(14,3)`| Yes | `NULL` | — | Sum of received weighbridge MT |
| `tracking_fees` | `NUMERIC(12,2)`| No | `0.00` | — | Sum of all batch land trucking costs |
| `barge_fees` | `NUMERIC(12,2)`| No | `0.00` | — | Sum of all batch marine barging costs |
| `variance_percent` | `NUMERIC(8,4)` | Yes | `NULL` | — | `(|loaded_mt - received_mt| / loaded_mt) * 100` |
| `variance_exceeds_tolerance`| `BOOLEAN`| No | `False` | — | Flagged `True` if `variance_percent > 1.0%` |
| `dispute_status` | `VARCHAR(20)` | No | `'NONE'` | — | Choices: `NONE`, `DISPUTED`, `RESOLVED` |
| `resolution_type` | `VARCHAR(30)` | Yes | `NULL` | — | `CONCEDED`, `BILLING_ADJUSTED`, `BARGE_PENALTY`, `WAIVED` |
| `resolution_notes` | `TEXT` | No | `""` | — | Mandatory explanation for dispute settlement |

#### `operations_molassesreleaseorder` (MRO Permits)
| Column | Data Type | Nullable | Default | Constraints | Description |
|---|---|---|---|---|---|
| `id` | `BIGSERIAL` | No | Auto | `PK` | MRO permit primary key |
| `mro_number` | `VARCHAR(50)` | No | — | `INDEX` | Official MRO code printed on permit |
| `planter_id` | `BIGINT` | No | — | `FK -> masters_planter`| Planter / Association allocating volume |
| `sugar_mill_id` | `BIGINT` | Yes | `NULL` | `FK -> masters_sugarmill`| Issuing sugar mill |
| `tons` | `NUMERIC(14,5)`| No | — | — | Quota volume in Metric Tons (5 decimal precision) |
| `crop_year` | `VARCHAR(30)` | No | — | `INDEX` | Normalized milling season (e.g. `2024 - 2025`) |
| `cluster_id` | `UUID` | Yes | `NULL` | `FK -> cluster` | Parent cluster contract linkage |
| `scanned_file` | `VARCHAR(100)` | Yes | `NULL` | — | Scanned soft-copy document (PDF/Image) |

#### `operations_chairecord` (Quality Lab Inspection)
| Column | Data Type | Nullable | Default | Constraints | Description |
|---|---|---|---|---|---|
| `id` | `UUID` | No | `gen_random_uuid()` | `PK` | CHAI record UUID |
| `chai_number` | `VARCHAR(50)` | No | — | `UNIQUE, INDEX` | Official certificate code (e.g. `CHAI-20261010-001`) |
| `chai_value` | `NUMERIC(4,1)` | No | `1.0` | — | Standard numerical grade (1.0 to 5.0) |
| `cluster_id` | `UUID` | Yes | `NULL` | `FK -> cluster` | Associated transaction cluster |
| `sugar_mill_id` | `BIGINT` | Yes | `NULL` | `FK -> masters_sugarmill`| Tested origin sugar mill |
| `brix_level` | `NUMERIC(5,2)` | No | `85.00` | — | Laboratory measured Brix % |
| `purity_percent` | `NUMERIC(5,2)` | Yes | `NULL` | — | Apparent purity % |
| `total_sugars_percent`| `NUMERIC(5,2)`| Yes | `NULL` | — | Total fermentable sugars % |
| `status` | `VARCHAR(20)` | No | `'approved'`| — | Inspection status: `approved`, `pending`, `rejected` |

#### `operations_mroextractionjob` (AWS Textract Document AI OCR)
| Column | Data Type | Nullable | Default | Constraints | Description |
|---|---|---|---|---|---|
| `id` | `UUID` | No | `gen_random_uuid()` | `PK` | OCR extraction job UUID |
| `cluster_id` | `UUID` | No | — | `FK -> cluster` | Target cluster for extracted MRO lines |
| `document` | `VARCHAR(100)` | No | — | — | Uploaded raw scanned document file |
| `status` | `VARCHAR(20)` | No | `'queued'` | `INDEX` | Status: `queued`, `processing`, `completed`, `failed` |
| `average_confidence`| `FLOAT` | Yes | `NULL` | — | Average OCR block recognition confidence % |
| `extracted_data` | `JSONB` | Yes | `NULL` | — | Key-value blocks and parsed table rows |
| `error_message` | `TEXT` | No | `""` | — | Error log if Textract execution fails |

---

### 3.4 `finance_*` (Treasury, Invoicing, Vouchers & Loans)

#### `finance_invoice` (Suggestive Billing & Tax Ledger)
| Column | Data Type | Nullable | Default | Constraints | Description |
|---|---|---|---|---|---|
| `id` | `BIGSERIAL` | No | Auto | `PK` | Sales invoice primary key |
| `cluster_id` | `UUID` | No | — | `FK -> cluster` | Sourced transaction cluster |
| `invoice_number` | `VARCHAR(50)` | No | — | `UNIQUE, INDEX` | Official sales invoice reference number |
| `amount` | `NUMERIC(14,2)`| No | — | — | Gross billed amount (₱) |
| `issued_at` | `DATE` | No | `CURRENT_DATE` | — | Billing issue date |
| `due_date` | `DATE` | Yes | `NULL` | — | Receivable payment due date |
| `status` | `VARCHAR(20)` | No | `'draft'` | `INDEX` | Choices: `draft`, `issued`, `paid`, `returned` |
| `tax_rate_vat` | `NUMERIC(5,2)` | No | `12.00` | — | Output Value Added Tax rate (Default 12.00%) |
| `tax_rate_ewt` | `NUMERIC(5,2)` | No | `1.00` | — | Creditable Expanded Withholding Tax rate (Default 1.00%) |
| `is_incremental` | `BOOLEAN` | No | `False` | — | Indicates partial / milestone progress billing |
| `incremental_percentage`| `NUMERIC(5,2)`| Yes | `NULL` | — | Specified milestone % (e.g. 50.00%, 25.00%) |
| `logistics_fee` | `NUMERIC(14,2)`| No | `0.00` | — | Billable logistics fee parsed from deliveries |

> **Tax Calculation Formulas:**
> * `net_vat_base = amount / (1.00 + (tax_rate_vat / 100)) = amount / 1.12`
> * `vat_amount = amount - net_vat_base`
> * `ewt_amount = net_vat_base * (tax_rate_ewt / 100)`
> * `net_amount_after_tax = amount - ewt_amount` (Expected Cash Collection)

#### `finance_cashvoucher` (Cheque Expense Disbursements)
| Column | Data Type | Nullable | Default | Constraints | Description |
|---|---|---|---|---|---|
| `id` | `BIGSERIAL` | No | Auto | `PK` | Cash voucher primary key |
| `cluster_id` | `UUID` | No | — | `FK -> cluster` | Associated transaction cluster |
| `loan_id` | `BIGINT` | Yes | `NULL` | `FK -> capitalloan`| Backing capital financing facility |
| `voucher_number` | `VARCHAR(50)` | No | — | `UNIQUE, INDEX` | Unique code (e.g. `CV-DEL-08AF21-TRK`) |
| `amount` | `NUMERIC(14,2)`| No | — | — | Disbursed expense amount (₱) |
| `purpose` | `VARCHAR(200)` | No | — | — | Description of land freight, barge, or sourcing |
| `status` | `VARCHAR(20)` | No | `'pending'` | — | Choices: `pending`, `issued`, `cancelled` |
| `cheque_number` | `VARCHAR(50)` | Yes | `""` | — | Physical bank cheque reference number |
| `cheque_date` | `DATE` | Yes | `NULL` | — | Physical cheque issuance date |

#### `finance_capitalloan` (Financing & Dynamic Accruals)
| Column | Data Type | Nullable | Default | Constraints | Description |
|---|---|---|---|---|---|
| `id` | `BIGSERIAL` | No | Auto | `PK` | Capital loan facility primary key |
| `cluster_id` | `UUID` | No | — | `FK -> cluster` | Sourced transaction cluster funded |
| `bank_name` | `VARCHAR(120)` | No | — | — | Lending institution (e.g. BDO, BPI, Security Bank) |
| `principal` | `NUMERIC(14,2)`| No | — | — | Funded principal sourcing balance |
| `interest_rate_annual`| `NUMERIC(6,4)`| No | — | — | Annual interest rate (e.g. 12.5000%) |
| `start_date` | `DATE` | No | — | — | Loan release date |
| `due_date` | `DATE` | No | — | — | Facility maturity date |
| `cheque_number` | `VARCHAR(50)` | Yes | `""` | — | Originating cheque reference number |
| `bank_account_number`| `VARCHAR(50)` | Yes | `""` | — | Originating bank account # |
| `logistics_deposit_percentage`| `NUMERIC(5,2)`| No | `50.00`| — | Deposit percentage (Default 50.00%) |
| `status` | `VARCHAR(30)` | No | `'pending_creation'`| — | `pending_creation` -> `active` -> `pending_settlement` -> `closed` (or `overdue` / `rejected`) |
| `settlement_receipt_number`| `VARCHAR(100)`| Yes | `""`| — | Bank official clearance / release advice # |
| `settlement_document`| `VARCHAR(100)`| Yes | `NULL` | — | Scanned PDF of bank settlement clearance |
| `verified_by_id` | `BIGINT` | Yes | `NULL` | `FK -> accounts_user`| Ops Manager / Admin dual-auth verification |
| `verified_at` | `TIMESTAMPTZ` | Yes | `NULL` | — | Dual-authorization verification timestamp |

> **Dynamic Daily Accrual Formulas:**
> * `days_outstanding = max((CURRENT_DATE - start_date), 0)` (Or capped at `due_date` once closed)
> * `daily_interest_cost = principal * (interest_rate_annual / 100 / 365)`
> * `accrued_interest = daily_interest_cost * days_outstanding`
> * `total_liability = principal + accrued_interest`
> * `funded_logistics_deposit = (logistics.tracking_fees + logistics.barge_fees) * 50%`

#### `finance_financialreconciliation` & `finance_paymentexpensematch`
* `FinancialReconciliation`: 1:1 anchor per cluster managing payment match state (`draft` vs `finalized`) and aggregate `matched_payment_amount`.
* `PaymentExpenseMatch`: Granular 3-step reconciliation records linking payment references to exact expense buckets (`sourcing`, `trucking`, `barge`, `logistics_deposit`, `other`).

---

### 3.5 `audit_*` & `chat_*` (Cross-Cutting Concerns)

#### `audit_systemaudittrail` (Immutable Append-Only Audit Log)
| Column | Data Type | Nullable | Default | Constraints | Description |
|---|---|---|---|---|---|
| `id` | `BIGSERIAL` | No | Auto | `PK` | Audit entry ID |
| `user_id` | `BIGINT` | Yes | `NULL` | `FK -> accounts_user`| User executing mutation (SET_NULL on user delete) |
| `action` | `VARCHAR(10)` | No | — | — | Mutation verb: `create`, `update`, `delete` |
| `table_name` | `VARCHAR(100)` | No | — | `INDEX` | Name of affected table (e.g. `operations_purchaseorder`) |
| `record_id` | `VARCHAR(64)` | No | — | `INDEX` | Record primary key (UUID or Integer string) |
| `old_values` | `JSONB` | No | `'{}'` | — | Full JSON snapshot prior to mutation |
| `new_values` | `JSONB` | No | `'{}'` | — | Full JSON snapshot after mutation |
| `timestamp` | `TIMESTAMPTZ` | No | `CURRENT_TIMESTAMP` | `INDEX` | Append-only execution timestamp |

> **Immutability Enforcement:** The model overrides `.save()` and `.delete()` to throw `ValueError("Audit trail entries are append-only and cannot be updated or deleted.")`.

#### `audit_notification` (Role-Targeted Alerts)
Stores operational and financial alerts categorized across `approval`, `variance`, `logistics`, `loan`, and `system` with severity levels (`info`, `warning`, `success`, `danger`).

#### `chat_chatmessage` (Contextual Team Collaboration)
Allows direct messages between users and context-threaded discussions anchored directly to specific `TransactionCluster` records (`cluster_id` FK).

---

## 4. Use Case Diagram

The Use Case Diagram maps the functional interactions between the **6 system actors** (5 authenticated internal staff roles + 1 automated cloud microservice) and the **9 functional use case packages**.

> 🖼️ **Rendered Diagram Image:** [Download High-Res PNG](diagrams/05_use_case_diagram.png) | [Vector SVG](diagrams/05_use_case_diagram.svg) | [Draw.io File](diagrams/05_use_case_diagram.drawio) | [Raw XML](diagrams/05_use_case_diagram.xml)
>
> ![HTC Core Use Case Diagram](diagrams/05_use_case_diagram.png)

> [!NOTE]
> **Actors in HTC Core are 100% Internal Staff + AWS Textract:**
> External business institutions (Financing Banks, Customers, Mills, Fleets) are real-world counterparties, not actors on the website. For instance, when a bank issues an offline loan clearance advice, the **Finance Specialist** inputs the receipt number and uploads the clearance scan (`UC-25`), and the **Operations Manager / Administrator** reviews and executes dual-authorization verification (`UC-26`).

```mermaid
flowchart LR
    classDef actor fill:#0f172a,stroke:#38bdf8,stroke-width:2px,color:#f8fafc;
    classDef usecase fill:#1e293b,stroke:#0ea5e9,stroke-width:1.5px,color:#ffffff;
    classDef cloud fill:#2e1065,stroke:#a855f7,stroke-width:2px,color:#ffffff;

    subgraph OpsActors ["👥 Operations Workforce"]
        direction TB
        OpsStaff["👤 Operations Staff<br/><small>(Role: operations)</small>"]:::actor
        OpsMgr["👤 Operations Manager<br/><small>(Role: operations_management)</small>"]:::actor
    end

    subgraph HTCSystem ["⚙️ HTC CORE PLATFORM SYSTEM BOUNDARY"]
        direction TB

        subgraph OpsDomain ["📦 SOURCING & LOGISTICS DOMAIN"]
            direction TB
            subgraph Pkg1 ["1. Sourcing Deals & PO Contracts"]
                direction LR
                UC1("UC-01: Formulate Deal Cluster & PO"):::usecase
                UC2("UC-02: Review / Return Deal Cluster"):::usecase
                UC3("UC-03: Bulk Excel Operations Intake"):::usecase
            end

            subgraph Pkg2 ["2. Multi-Batch Logistics & Disputes"]
                direction TB
                subgraph DispatchSub ["Dispatch Execution"]
                    direction LR
                    UC4("UC-04: Dispatch Batch with Dual Freight"):::usecase
                    UC5("UC-05: Enforce Over-Delivery Guard"):::usecase
                end
                subgraph DisputeSub ["Shrinkage & Dispute Engine"]
                    direction LR
                    UC6("UC-06: Flag >1.0% Transit Shrinkage"):::usecase
                    UC7("UC-07: Resolve Transit Variance Dispute"):::usecase
                end
            end

            subgraph Pkg3 ["3. MRO Permits & Lab Quality"]
                direction TB
                subgraph OCRSub ["Permit Intake & Cloud OCR Pipeline"]
                    direction LR
                    UC8("UC-08: Upload Scanned MRO Quota PDF"):::usecase
                    UC9("UC-09: Trigger Textract OCR Extraction"):::usecase
                    Textract["☁️ AWS Textract AI<br/><small>(Cloud Document OCR)</small>"]:::cloud
                    UC10("UC-10: Verify & Link MRO to Deal Cluster"):::usecase
                end
                subgraph LabSub ["Quality Assurance"]
                    direction LR
                    UC11("UC-11: Record Laboratory CHAI Grade & Brix"):::usecase
                end
            end
        end

        subgraph FinGovDomain ["💳 TREASURY, INVOICING & GOVERNANCE DOMAIN"]
            direction TB
            subgraph Pkg4 ["4. Billing & Sales Invoicing Engine"]
                direction LR
                UC12("UC-12: Generate Suggestive Delivery Invoice"):::usecase
                UC13("UC-13: Compute 12% VAT & 1% EWT Tax Base"):::usecase
                UC14("UC-14: Export Official Billing PDF Statement"):::usecase
            end

            subgraph Pkg5 ["5. Sourcing Capital Loans & Treasury"]
                direction TB
                subgraph LoanFacility ["Capital Loan Facility & Accruals"]
                    direction LR
                    UC15("UC-15: Initiate Sourcing Capital Loan"):::usecase
                    UC16("UC-16: Dual-Auth Loan Creation Approval"):::usecase
                    UC17("UC-17: Track Daily Dynamic Interest Accrual"):::usecase
                end
                subgraph LoanSettlement ["Settlement & Cash Vouchers"]
                    direction LR
                    UC18("UC-18: Submit Bank Settlement Advice"):::usecase
                    UC19("UC-19: Dual-Auth Verify & Close Loan"):::usecase
                    UC20("UC-20: 3-Step Match & Auto-Disburse Vouchers"):::usecase
                end
            end

            subgraph Pkg6 ["6. Identity, Catalogs & Audit Governance"]
                direction LR
                UC21("UC-21: Self-Register Account & Setup 2FA"):::usecase
                UC22("UC-22: Approve User & Assign RBAC Role"):::usecase
                UC23("UC-23: Maintain Master Entity Catalogs"):::usecase
                UC24("UC-24: Query HTC Copilot ORM Assistant"):::usecase
                UC25("UC-25: Inspect Append-Only Audit Trail"):::usecase
            end
        end
    end

    subgraph RightActors ["👥 Finance, Invoicing & Admin Users"]
        direction TB
        Inv["🧾 Invoicing Specialist<br/><small>(Role: invoicing)</small>"]:::actor
        Fin["💳 Finance Specialist<br/><small>(Role: finance)</small>"]:::actor
        Admin["🛡️ System Administrator<br/><small>(Role: administrator)</small>"]:::actor
    end

    %% Left Actor Links (Ops Workforce)
    OpsStaff --> UC1
    OpsStaff --> UC3
    OpsStaff --> UC4
    OpsStaff --> UC8

    OpsMgr --> UC2
    OpsMgr --> UC7
    OpsMgr --> UC10
    OpsMgr --> UC11

    %% Use Case Internal Includes & Extends
    UC4 -.->|"«include»"| UC5
    UC4 -.->|"«include»"| UC6
    UC6 -.->|"«extend» (>1.0%)"| UC7

    UC8 -.->|"«include»"| UC9
    UC9 <-->|"OCR API"| Textract
    UC9 -.->|"«include»"| UC10

    UC12 -.->|"«include»"| UC13
    UC15 -.->|"«include»"| UC16
    UC15 -.->|"«include»"| UC17
    UC18 -.->|"«include»"| UC19

    %% Right Actor Links (Direct, Zero Crossing)
    UC12 <--> Inv
    UC13 <--> Inv
    UC14 <--> Inv

    UC15 <--> Fin
    UC16 <--> Fin
    UC17 <--> Fin
    UC18 <--> Fin
    UC19 <--> Fin
    UC20 <--> Fin

    UC21 <--> Admin
    UC22 <--> Admin
    UC23 <--> Admin
    UC24 <--> Admin
    UC25 <--> Admin
```

---

## 5. Traceability Matrix: What Changed and Why

| Subsystem | Previous Legacy Architecture | Current Post-Upgrade Architecture | Technical Rationale & Business Impact |
|---|---|---|---|
| **Contract Fulfillment** | Flat 1:1 single-dispatch model (`1 PO = 1 Delivery`). | **Parent PO (1:N) Multi-Batch Delivery Engine** (`PurchaseOrder` -> `DeliveryLedger[]`). | Accommodates real-world industrial sugar trading: 10,000 MT contracts are fulfilled over months across multiple sugar mills and drop-off customer sites. |
| **Logistics & Freight** | Single unclassified hauler name with flat estimated fees. | **Dual-Carrier Classification** (Dedicated land `trucking_partner` and marine `barge_partner` with ₱/MT rates and flat fees). | Prevents shipping cost distortion; enables exact freight accruals and profit margin calculation per batch. |
| **Shrinkage & Variance** | Late manual spreadsheet comparison of transit loss. | **Automated 1.0% Variance Guard & Dispute Workflow** (`NONE`, `DISPUTED`, `RESOLVED` with 4 resolution actions). | Eliminates unmonitored loss during sea/land transit; automatically alerts managers and enforces financial resolution before archiving. |
| **MRO Release Permits** | Loose paper permits filed manually without cluster linkage. | **Direct MRO Cluster Binding & AWS Textract OCR Pipeline** (`MROExtractionJob` with side-by-side scan preview). | Prevents double-allocation or expired release orders; provides rapid digital verification directly from the PO workspace. |
| **Quality Control** | Simple unstructured text note for Brix. | **Formal CHAI Quality Certification Model** (`CHAIRecord` with 1.0 to 5.0 grades, Brix %, purity %, and approval gating). | Enforces strict sugar specifications required by premium industrial distillers and food manufacturers. |
| **Customer Invoicing** | Manual calculation prone to volume and tax formula errors. | **Suggestive Delivery Billing Engine** (`delivered_mt * selling_price`, automatic 12% VAT and 1% EWT breakdown). | Accelerates time-to-invoice from weeks to minutes, matching actual delivered weighbridge tonnage directly. |
| **Capital Financing** | Static loan records without interest progression. | **Dynamic Daily Interest Accruals** (`accrued_interest` calculated daily, 50% logistics deposit funding, dual-auth creation/settlement). | Guarantees exact repayment liabilities to commercial banks, avoiding surprise interest penalties upon loan settlement. |
| **Authentication & RBAC** | Simple Django admin login with immediate open access. | **Admin Gating + TOTP 2FA + Single-Use Recovery Codes + 5 Distinct Roles**. | Enterprise security compliance protecting high-value transactions; zero unauthorized access for new sign-ups. |
| **User Experience** | Standard default web layout difficult for senior executives. | **Persistent High-Legibility Mode (`A+`) & High-Contrast Themes**. | Tailored for senior commodity traders and operational executives, ensuring effortless readability on factory floors and remote desks. |
