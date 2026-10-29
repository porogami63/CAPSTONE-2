# HTC Core — Comprehensive Diagram Explanations & Technical Architecture Guide
**Location:** `C:\Users\Gigabyte\CAPSTONE-2\docs\diagrams\New folder\`  
**Project:** HTC Core Trading & Logistics Management Platform (Capstone 2)  
**Client:** Heindrich Trading Corporation (HTC)  
**Version:** Architecture v2.3.0  
**Target Audience:** Capstone Defense Panel, Technical Evaluators, Enterprise Developers, System Auditors  

---

## Table of Contents
1. [Executive Summary & Architecture Context](#1-executive-summary--architecture-context)
2. [Diagram 01: Entity-Relationship Diagram (ERD)](#2-diagram-01-entity-relationship-diagram-erd)
3. [Diagram 02: DFD Level 0 — Context Diagram](#3-diagram-02-dfd-level-0--context-diagram)
4. [Diagram 03: DFD Level 1 — Process Decomposition](#4-diagram-03-dfd-level-1--process-decomposition)
5. [Diagram 04: DFD Level 2 — Multi-Batch Delivery Execution](#5-diagram-04-dfd-level-2--multi-batch-delivery-execution)
6. [Diagram 05: Use Case Diagram & Actor Matrix](#6-diagram-05-use-case-diagram--actor-matrix)
7. [Master Draw.io Notebook (`htc_architecture_diagrams.drawio`)](#7-master-drawio-notebook-htc_architecture_diagramsdrawio)
8. [Panel Defense Q&A Cheatsheet](#8-panel-defense-qa-cheatsheet)

---

## 1. Executive Summary & Architecture Context

The files in `docs/diagrams/New folder/` represent the official architectural blueprint of the **HTC Core Platform** following its major upgrades (Milestones 1–5, Phase 1.5 UAT, Parent-Child PO Multi-Batch Haulage, AWS Textract Document AI, and Treasury Dynamic Accruals).

### Why the Architecture Had to Evolve
In industrial raw sugar and molasses trading, a single commercial contract (e.g., 10,000 Metric Tons) is never executed in a single delivery. Instead:
1. It is sourced across **multiple sugar mills** (e.g., BUSCO, CASA, HPCo, Lopez Sugar).
2. It is fulfilled over several weeks or months through **dozens of discrete delivery batches**.
3. It utilizes **dual-mode logistics** (inter-island marine barging + local land trucking).
4. Sourcing is financed via **multi-million peso bank capital loans** that incur daily compound interest.
5. Sourcing requires government quotas and mill permits known as **Molasses Release Orders (MROs)**.

The diagrams in this folder explain how HTC Core models, processes, validates, and audits this entire lifecycle.

---

## 2. Diagram 01: Entity-Relationship Diagram (ERD)

### File References
- Draw.io file: `01_entity_relationship_diagram_erd.drawio`
- Raw XML: `01_entity_relationship_diagram_erd.xml`
- Master tab: Tab 1 in `htc_architecture_diagrams.drawio`

### Purpose & Scope
The ERD defines the **relational database schema** (PostgreSQL 16) backing HTC Core. It organizes 17 primary entities across **4 logical architectural tiers** to ensure high cohesion, low coupling, data integrity, and complete financial auditability.

```
+---------------------------------------------------------------------------------+
| TIER 1: MASTER COUNTERPARTIES & IDENTITY                                        |
|   USER <== audits ==> SYSTEM_AUDIT_TRAIL                                        |
|   CLIENT, SUGAR_MILL, PLANTER, LOGISTICS_PARTNER                                |
+---------------------------------------------------------------------------------+
                                       |
                                       v
+---------------------------------------------------------------------------------+
| TIER 2: COMMERCIAL CONTRACT CORE                                                |
|   TRANSACTION_CLUSTER (Master Deal Envelope)                                    |
|   ├── PURCHASE_ORDER (1:1 Commercial Terms)                                     |
|   ├── LOGISTICS_LEDGER (1:1 Aggregated Metrics)                                 |
|   ├── MOLASSES_RELEASE_ORDER (0:N SRA Quota Permits)                            |
|   └── CAPITAL_LOAN (0:N Bank Credit Facilities)                                 |
+---------------------------------------------------------------------------------+
                                       |
                                       v
+---------------------------------------------------------------------------------+
| TIER 3: LOGISTICS EXECUTION & LAB QA                                            |
|   PURCHASE_ORDER ───(1:N)───> DELIVERY_LEDGER (Batch Haulage)                   |
|   LOGISTICS_PARTNER ───(0:N)───> DELIVERY_LEDGER                                |
|   MOLASSES_RELEASE_ORDER ───(0:N)───> MRO_EXTRACTION_JOB (AWS Textract OCR)     |
|   MOLASSES_RELEASE_ORDER ───(0:N)───> CHAI_RECORD (Lab Brix & Grade)            |
+---------------------------------------------------------------------------------+
                                       |
                                       v
+---------------------------------------------------------------------------------+
| TIER 4: INVOICING, TREASURY & RECONCILIATION                                    |
|   DELIVERY_LEDGER ───(0:N)───> INVOICE (12% VAT + 1% EWT Suggestive Billing)   |
|   CAPITAL_LOAN ───(0:N)───> CASH_VOUCHER (Cheque Outlays)                       |
|   CAPITAL_LOAN ───(1:1)───> FINANCIAL_RECONCILIATION                            |
|                                     └──(1:N)──> PAYMENT_EXPENSE_MATCH           |
+---------------------------------------------------------------------------------+
```

### Detailed Tier Walkthrough

#### Tier 1: Master Counterparties & Identity
1. **`USER` (`accounts_user`)**: Custom authentication model inheriting Django `AbstractUser`. Contains role-based access control (`administrator`, `operations_management`, `operations`, `finance`, `invoicing`), registration approval gating (`is_active=False` by default), and TOTP 2FA fields (`is_2fa_enabled`, `otp_secret`, `backup_codes`).
2. **`SYSTEM_AUDIT_TRAIL` (`audit_systemaudittrail`)**: Append-only compliance log. Every entity creation, update, or deletion captures user ID, table name, record ID, and exact JSON diffs (`old_values`, `new_values`). Enforced immutable at the model level.
3. **`CLIENT` (`masters_client`)**: Master corporate buyers (e.g., industrial food manufacturers, distilleries). Holds BIR Tax Identification Number (TIN), billing address, and authorized contact person.
4. **`SUGAR_MILL` (`masters_sugarmill`)**: Origin sourcing facilities (e.g., BUSCO, CASA, HPCo, Lopez Sugar) holding raw molasses inventory.
5. **`PLANTER` (`masters_planter`)**: Sugar planters and planters' associations who own sugarcane quotas under the Sugar Regulatory Administration (SRA).
6. **`LOGISTICS_PARTNER` (`masters_logisticspartner`)**: Carrier fleet operators categorized as `trucking` (land) or `barging` (marine) with baseline freight rate configurations (₱/MT).

#### Tier 2: Commercial Contract Core
1. **`TRANSACTION_CLUSTER` (`operations_transactioncluster`)**: The master transaction envelope (UUID primary key). Groups the commercial purchase order, logistics ledger, loan facilities, and MRO permits under an auto-generated reference code (e.g., `TRX-20261010-001`). Governed by a strict state machine (`draft` -> `pending_approval` -> `approved` -> `active` -> `delivered` -> `closed`).
2. **`PURCHASE_ORDER` (`operations_purchaseorder`)**: 1:1 commercial terms attached to the cluster. Defines total contracted tonnage (`total_contracted_mt`), purchase price (`unit_price`), selling price (`selling_price`), target Brix specification, and fulfillment status (`Open`, `Partially Fulfilled`, `Completed`).
3. **`LOGISTICS_LEDGER` (`operations_logisticsledger`)**: 1:1 ledger tracking aggregated loaded vs. received volumes across all delivery batches, total land trucking fees, marine barging fees, transit variance %, and dispute state (`NONE`, `DISPUTED`, `RESOLVED`).
4. **`MOLASSES_RELEASE_ORDER` (`operations_molassesreleaseorder`)**: Official SRA transfer permits allocating specific tonnage quotas from a planter and issuing sugar mill to the cluster.
5. **`CAPITAL_LOAN` (`finance_capitalloan`)**: Sourcing credit lines extended by commercial banks (e.g., BDO, BPI, Security Bank) to fund commodity acquisition and a 50% logistics freight advance.

#### Tier 3: Logistics Execution & Lab QA
1. **`DELIVERY_LEDGER` (`operations_deliveryledger`)**: 1:N discrete fulfillment batches. Connects to the parent PO, origin mill, drop-off destination, and carriers. Calculates land trucking and sea barging costs independently per batch.
2. **`MRO_EXTRACTION_JOB` (`operations_mroextractionjob`)**: Asynchronous OCR job queue for scanned MRO permits processed through AWS Textract Document AI, capturing confidence scores and parsed JSON tables.
3. **`CHAI_RECORD` (`operations_chairecord`)**: Formal chemical inspection certificate recording numerical grade (1.0 to 5.0), laboratory Brix %, apparent purity %, and total fermentable sugars %.

#### Tier 4: Invoicing, Treasury & Reconciliation
1. **`INVOICE` (`finance_invoice`)**: Suggestive customer billing engine. Derives billed amount directly from delivered tonnage multiplied by contracted selling price, computing official Philippine tax splits (12% Output VAT and 1% Creditable EWT).
2. **`CASH_VOUCHER` (`finance_cashvoucher`)**: Disbursement vouchers for carrier freight cheques and mill payments, automatically generated upon delivery batch submission.
3. **`FINANCIAL_RECONCILIATION` & `PAYMENT_EXPENSE_MATCH`**: 3-step accounting reconciliation module that matches cheque and bank payment references directly against sourcing, trucking, barge, and deposit liabilities.

---

## 3. Diagram 02: DFD Level 0 — Context Diagram

### File References
- Draw.io file: `02_dfd_level0_context_diagram.drawio`
- Raw XML: `02_dfd_level0_context_diagram.xml`
- Master tab: Tab 2 in `htc_architecture_diagrams.drawio`

### Purpose & Scope
The Level 0 Context Diagram establishes the **system boundaries** of the HTC Core platform (`Process 0.0`), identifying all incoming and outgoing data flows between authenticated internal users, external counterparties, and cloud microservices.

### Critical Architecture Rule: Internal Staff Boundary
A common misconception during architectural evaluation is assuming external counterparties log into the portal.
> **Key Architecture Fact:** External commercial institutions (Commercial Banks, Clients/Buyers, Sugar Mills, and Logistics Haulers) **DO NOT possess portal login accounts**. 
> All physical counterpart documents (paper contracts, bank clearance advices, delivery receipts, hauler waybills) are received offline (via phone, email, or physical courier) and transcribed into HTC Core by authorized **internal staff members**.

### Diagram Elements & Interaction Matrix

| Actor / Entity | Boundary Type | Role / Purpose | Inbound Data to Platform | Outbound Data from Platform |
|---|---|---|---|---|
| **System Administrator** | Internal Staff | Identity governance & security | User approvals, role assignments, 2FA policy enforcement | Audit log inspection, security telemetry |
| **Operations Team** (`operations`, `operations_management`) | Internal Staff | Trading & logistics execution | Deal contract parameters, batch dispatches, freight rates, MRO uploads | Deal approval workflows, dispute alerts, fulfillment progress |
| **Finance & Invoicing** (`finance`, `invoicing`) | Internal Staff | Financial treasury & settlement | Loan terms, interest rates, bank clearances, voucher sign-offs | Suggestive invoices, tax splits, daily accrual totals, payment matching |
| **Clients / Buyers** | External (Offline) | Counterparty purchasing molasses | Purchase contracts, weighbridge drop-off receipts | Official sales invoices, Statements of Account (SOA) |
| **Sugar Mills & Planters** | External (Offline) | Origin supplier & quota holder | Mill Delivery Receipts (MDR), physical MRO permits, lab Brix specs | Purchase contract commitments, payment vouchers |
| **Logistics Carriers** | External (Offline) | Freight transport fleet | Waybills, hauler gate passes, freight rate quotes | Cheque disbursement vouchers, dispatch manifests |
| **Commercial Lending Banks** | External (Offline) | Sourcing capital financer | Promissory notes, lending terms, settlement clearance advice | Loan payoff transactions, disbursement tracking |
| **AWS Textract AI** | Cloud Service (API) | Automated document OCR | Extracted key-value pairs, table rows, confidence metrics | Uploaded MRO scanned document binaries (PDF/PNG) |

---

## 4. Diagram 03: DFD Level 1 — Process Decomposition

### File References
- Draw.io file: `03_dfd_level1_process_decomposition.drawio` (or `.xml`)
- Master tab: Tab 3 in `htc_architecture_diagrams.drawio`

### Purpose & Scope
The Level 1 DFD decomposes `Process 0.0` into **10 major operational sub-processes** organized sequentially across **5 enterprise business phases**. It demonstrates how data flows across the system's **8 primary data stores** (`D1` through `D8`).

```
PHASE 1: COMMERCIAL SOURCING & MASTER DATA SETUP
  [1.0 Master Data & User RBAC] <=======> [D1: Masters & D2: Users]
             |
             v
  [2.0 Deal & PO Formulation] <========> [D3: PurchaseOrder & Deal Store]
             |
             v (Approved Deal PO Contract)
PHASE 2: PERMITTING & LAB QUALITY COMPLIANCE
  [3.0 MRO Document OCR & Intake] <=====> [D5: MRO Permitting Store]
             |
             v
  [4.0 CHAI Laboratory Quality] <=======> [D5B: Lab Quality Store]
             |
             v (Validated Quotas & Grade Approval)
PHASE 3: MULTI-BATCH LOGISTICS & DISPUTE RESOLUTION
  [5.0 Over-Delivery Balance Guard] <===> [D4: DeliveryLedger Store]
             |
             v
  [6.0 Transit Variance Engine] <=======> [D4B: LogisticsLedger Store]
             |
             v (Dispatched Dispatches & Waybill Freight)
PHASE 4: DYNAMIC TREASURY, INVOICING & SETTLEMENT
  [7.0 Suggestive Sales Invoicing] <====> [D6: Billing & Invoices Store]
             |
             v
  [8.0 Capital Loan Facility Engine] <==> [D7: Capital Loans Facility]
             |
             v
  [9.0 Auto-Voucher Disbursement] <=====> [D7B: Cash Vouchers Store]
             |
             v (Financial Closures & Reconciliation)
PHASE 5: ENTERPRISE GOVERNANCE & AUDIT TRAIL
  [10.0 Immutable Audit Trail & HTC Copilot ORM Engine] <====> [D8: Audit Store]
```

### Process Decomposition Breakdown

#### Phase 1: Commercial Sourcing & Master Data Setup
- **Process 1.0 (Master Data & User RBAC)**: Maintains corporate directories of clients, sugar mills, planters, and logistics carriers in `D1`, while administering internal staff credentials, TOTP 2FA, and RBAC permissions in `D2`.
- **Process 2.0 (Deal & PO Formulation)**: An Operations Specialist creates a `TransactionCluster` and binds a `PurchaseOrder` with contracted tonnage, supplier unit price, and customer selling price. Stored in `D3`.

#### Phase 2: Permitting & Lab Quality Compliance
- **Process 3.0 (MRO Document OCR & Intake)**: Uploads scanned SRA quota documents, triggers AWS Textract OCR, parses key tabular data, and saves confirmed quotas to `D5`.
- **Process 4.0 (CHAI Laboratory Quality Grading)**: Records laboratory Brix %, apparent purity %, and numerical quality grades (1.0 to 5.0) in `D5B`. Prevents dispatch if quality fails customer contract specifications.

#### Phase 3: Multi-Batch Logistics & Dispute Resolution
- **Process 5.0 (Over-Delivery Balance Guard & Batch Haulage Dispatch)**: Validates each batch against remaining contracted tonnage (`remaining_mt`). Computes dual freight costs and records dispatches in `D4`. *(Detailed in Level 2 DFD)*.
- **Process 6.0 (Transit Variance Engine)**: Compares mill loaded volume vs. customer received volume. If transit shrinkage exceeds the strict **1.0% tolerance threshold**, the transaction is automatically flagged as `DISPUTED` in `D4B`, requiring formal resolution before closure.

#### Phase 4: Dynamic Treasury, Invoicing & Settlement
- **Process 7.0 (Suggestive Sales Invoicing)**: Generates customer invoices in `D6` based on delivered weighbridge tonnage, automatically splitting 12% Output VAT and 1% Creditable Withholding Tax (EWT).
- **Process 8.0 (Capital Loan Facility & Daily Accrual Engine)**: Tracks high-value bank credit lines in `D7`. Computes daily accrued interest dynamically until official bank settlement receipt verification.
- **Process 9.0 (Auto-Voucher Disbursement & 3-Step Match)**: Automatically generates pending `CashVoucher` records in `D7B` for land and sea freight costs upon batch save, linking them into 3-step payment reconciliation.

#### Phase 5: Enterprise Governance & Audit Trail
- **Process 10.0 (Immutable Audit Trail & HTC Copilot ORM Engine)**: Every transaction event is committed to `D8` with immutable append-only constraints. Provides an integrated Natural Language-to-SQL Copilot allowing authorized executives to query operational telemetry.

---

## 5. Diagram 04: DFD Level 2 — Multi-Batch Delivery Execution

### File References
- Draw.io file: `04_dfd_level2_multi_batch_delivery.drawio`
- Raw XML: `04_dfd_level2_multi_batch_delivery.xml`
- Master tab: Tab 4 in `htc_architecture_diagrams.drawio`

### Purpose & Scope
This Level 2 DFD drills directly into **Process 5.0** to illustrate the core technical mechanisms governing incremental multi-batch logistics execution, over-delivery prevention, freight economics, and automated post-delivery ledger synchronization.

```
              [ Operations Coordinator ]
                         │ Submits Batch Payload
                         ▼
        [ 5.1 Parse Delivery Batch Parameters ]
                         │
                         ▼
           [ 5.2 Over-Delivery Guard ] <─────── [ D3: PurchaseOrder ]
                         │                      (Read remaining_mt)
        ┌────────────────┴────────────────┐
        │                                 │
 [ Exceeds Balance ]              [ Within Quota ]
        │                                 │
        ▼                                 ▼
[ Over-Delivery Error ]         [ 5.3 Compute Dual Freight ]
(Transaction Blocked)           - Trucking Cost = (MT × Rate) + Fee
                                - Barging Cost = (MT × Rate) + Fee
                                          │
                                          ▼
                                [ 5.4 Write DeliveryLedger ] ───► [ D4: Delivery ]
                                          │
                 ┌────────────────────────┼────────────────────────┐
                 │                        │                        │
                 ▼                        ▼                        ▼
       [ 5.5 Update PO State ]   [ 5.6 Sync Logistics ]   [ 5.7 Trigger Vouchers ]
                 │                        │                        │
                 ▼                        ▼                        ▼
        [ D3: PurchaseOrder ]    [ D4B: LogisticsLedger ]   [ D7: Treasury Store ]
        (Completed / Partial)    (Sum MT & Freight Fees)    (Generate CV & Match)
```

### Step-by-Step Logic & Mathematical Formulas

#### Step 5.1: Parse Batch Parameters
The Operations Coordinator inputs delivery parameters: parent PO reference, origin sugar mill, destination drop-off point, scheduled delivery date, dispatched tonnage (`delivered_mt`), land carrier ID, trucking rate per MT, flat trucking fee, marine barge carrier ID, vessel name, barge rate per MT, flat barge fee, and mill Delivery Receipt (DR) / Waybill numbers.

#### Step 5.2: Over-Delivery Balance Guard (Model Validation)
Before any database write occurs, the model validates that the batch tonnage does not breach remaining contract commitments:
$$\text{total\_delivered\_mt} = \sum (\text{previous batch delivered\_mt})$$
$$\text{remaining\_contract\_mt} = \max(0, \text{total\_contracted\_mt} - \text{total\_delivered\_mt})$$
$$\text{Condition: } \text{delivered\_mt} \le \text{remaining\_contract\_mt}$$

If `delivered_mt > remaining_contract_mt`, the transaction is aborted with a `ValidationError`, preventing accidental over-delivery.

#### Step 5.3: Compute Dual-Mode Freight Economics
Unlike legacy systems that used flat freight estimates, HTC Core dynamically computes land and marine logistics costs:
$$\text{Trucking Cost} = (\text{delivered\_mt} \times \text{trucking\_rate\_per\_mt}) + \text{flat\_trucking\_fee}$$
$$\text{Barging Cost} = (\text{delivered\_mt} \times \text{barge\_rate\_per\_mt}) + \text{flat\_barge\_fee}$$
$$\text{Total Freight Cost} = \text{Trucking Cost} + \text{Barging Cost}$$

#### Step 5.4: Write DeliveryLedger Batch Entry
The record is persisted in `DeliveryLedger` with a unique UUIDv4 primary key and UTC dispatch timestamps.

#### Steps 5.5–5.7: Automated Post-Delivery Synchronization (Django Signal Pipeline)
Upon persisting the delivery batch, the engine triggers three automated downstream synchronization routines:
1. **5.5 PO Fulfillment State Update**:
   - If $\text{remaining\_contract\_mt} == 0 \implies \text{po\_status} = \text{'Completed'}$, parent Cluster status becomes $\text{'delivered'}$.
   - If $\text{delivered\_mt} > 0 \implies \text{po\_status} = \text{'Partially Fulfilled'}$.
2. **5.6 LogisticsLedger Aggregation**:
   - Updates `loaded_volume_mt` $=\sum(\text{delivered\_mt})$.
   - Aggregates `tracking_fees` and `barge_fees`.
   - Computes transit variance percentage:
     $$\text{variance\_percent} = \frac{|\text{loaded\_volume\_mt} - \text{received\_volume\_mt}|}{\text{loaded\_volume\_mt}} \times 100$$
   - If $\text{variance\_percent} > 1.0\% \implies \text{variance\_exceeds\_tolerance} = \text{True}$ and $\text{dispute\_status} = \text{'DISPUTED'}$.
3. **5.7 Treasury Auto-Voucher Outlay**:
   - Automatically generates pending `CashVoucher` records: `CV-DEL-[UUID]-TRK` for land hauler freight and `CV-DEL-[UUID]-BRG` for marine barge freight.
   - Creates corresponding `PaymentExpenseMatch` items linked to the active sourcing `CapitalLoan`.

---

## 6. Diagram 05: Use Case Diagram & Actor Matrix

### File References
- Draw.io file: `05_use_case_diagram.drawio`
- Raw XML: `05_use_case_diagram.xml`
- Master tab: Tab 5 in `htc_architecture_diagrams.drawio`

### Purpose & Scope
The Use Case Diagram defines the functional scope of HTC Core, mapping **25 system use cases** across **6 functional packages** to **5 internal staff roles** and **1 cloud microservice**.

```
+---------------------------------------------------------------------------------------+
| ACTORS & PACKAGES INTERACTION MAP                                                     |
|                                                                                       |
| [ Operations Staff ] ───────────► [ Pkg 1: Sourcing Deals & PO Contracts ]            |
| [ Operations Manager ] ─────────► [ Pkg 2: Multi-Batch Logistics & Disputes ]         |
| [ AWS Textract AI ] ◄───────────► [ Pkg 3: MRO Permits & Lab Quality (OCR) ]           |
|                                                                                       |
| [ Invoicing Specialist ] ───────► [ Pkg 4: Billing & Sales Invoicing Engine ]         |
| [ Finance Specialist ] ─────────► [ Pkg 5: Sourcing Capital Loans & Treasury ]        |
| [ System Administrator ] ───────► [ Pkg 6: Identity, Catalogs & Audit Governance ]   |
+---------------------------------------------------------------------------------------+
```

### Complete Use Case Specification Matrix

| Package | Use Case ID & Name | Primary Actor | Description & Technical Rules | Relationships |
|---|---|---|---|---|
| **Pkg 1: Sourcing Deals & PO Contracts** | **UC-01**: Formulate Deal Cluster & PO | Operations Staff | Creates transaction envelope, sets contracted MT, unit and selling price | Extends to manager review |
| | **UC-02**: Review / Return Deal Cluster | Operations Manager | Reviews proposed commercial margin; approves or returns with comments | Pre-requisite for dispatch |
| | **UC-03**: Bulk Excel Operations Intake | Operations Staff | Uploads multi-row legacy spreadsheet batches via automated parser | Validates rows against masters |
| **Pkg 2: Multi-Batch Logistics & Disputes** | **UC-04**: Dispatch Batch with Dual Freight | Operations Staff | Dispatches truck/barge haulage batch with independent freight rates | `«include»` UC-05, UC-06 |
| | **UC-05**: Enforce Over-Delivery Guard | System Engine | Validates that batch tonnage does not exceed `remaining_contract_mt` | Included by UC-04 |
| | **UC-06**: Flag >1.0% Transit Shrinkage | System Engine | Computes transit variance; triggers dispute if shrinkage exceeds 1.0% | `«extend»` UC-07 (>1.0%) |
| | **UC-07**: Resolve Transit Variance Dispute | Operations Manager | Selects resolution: `CONCEDED`, `BILLING_ADJUSTED`, `BARGE_PENALTY`, `WAIVED` | Extends UC-06 |
| **Pkg 3: MRO Permits & Lab Quality** | **UC-08**: Upload Scanned MRO Quota PDF | Operations Staff | Uploads SRA Molasses Release Order soft-copy scan | `«include»` UC-09 |
| | **UC-09**: Trigger Textract OCR Extraction | AWS Textract AI | Cloud AI asynchronously parses tables, text blocks, and confidence scores | Included by UC-08; `«include»` UC-10 |
| | **UC-10**: Verify & Link MRO to Deal | Operations Manager | Inspects extracted MRO quota side-by-side with scan; binds to deal cluster | Included by UC-09 |
| | **UC-11**: Record Laboratory CHAI Grade | Operations Manager | Records numerical grade (1.0 to 5.0), Brix %, purity %, and total sugars % | Quality certification |
| **Pkg 4: Billing & Sales Invoicing Engine** | **UC-12**: Generate Suggestive Delivery Invoice | Invoicing Specialist | Generates sales invoice based on actual delivered weighbridge tonnage | `«include»` UC-13 |
| | **UC-13**: Compute 12% VAT & 1% EWT Base | System Engine | Calculates Philippine tax split: Net VAT Base $= \text{Amount} / 1.12$, EWT $= \text{Base} \times 1\%$ | Included by UC-12 |
| | **UC-14**: Export Official Billing PDF Statement | Invoicing Specialist | Renders downloadable corporate Statement of Account with QR verification | Customer billing document |
| **Pkg 5: Sourcing Capital Loans & Treasury** | **UC-15**: Initiate Sourcing Capital Loan | Finance Specialist | Enters bank facility, principal amount, annual rate, and maturity date | `«include»` UC-16, UC-17 |
| | **UC-16**: Dual-Auth Loan Creation Approval | Operations Manager / Admin | Second-tier authorization verifying loan promissory note before activation | Included by UC-15 |
| | **UC-17**: Track Daily Dynamic Interest Accrual | System Engine | Accrues daily interest: $\text{Principal} \times (\text{Rate} / 365) \times \text{Days}$ | Included by UC-15 |
| | **UC-18**: Submit Bank Settlement Advice | Finance Specialist | Uploads bank clearance advice scan and enters official clearance number | `«include»` UC-19 |
| | **UC-19**: Dual-Auth Verify & Close Loan | Operations Manager / Admin | Inspects clearance advice, locks accrued interest, transitions loan to `closed` | Included by UC-18 |
| | **UC-20**: 3-Step Match & Auto-Disburse Vouchers | Finance Specialist | Reconciles pending vouchers and matches cheque outlays against loan balance | Treasury closure |
| **Pkg 6: Identity, Catalogs & Audit Governance** | **UC-21**: Self-Register Account & Setup 2FA | Any New User | Self-registers; scans QR code for TOTP 2FA; receives single-use recovery codes | Gated until approved |
| | **UC-22**: Approve User & Assign RBAC Role | System Administrator | Inspects pending registration queue; assigns role (`ops`, `finance`, etc.); activates | Security authorization |
| | **UC-23**: Maintain Master Entity Catalogs | System Administrator | CRUD maintenance of Clients, Sugar Mills, Planters, and Hauler fleets | Master data integrity |
| | **UC-24**: Query HTC Copilot ORM Assistant | Any Authenticated User | Natural Language interface translating business questions to Django ORM queries | Read-only executive telemetry |
| | **UC-25**: Inspect Append-Only Audit Trail | System Administrator | Audits tamper-proof JSON change logs across all entities, users, and timestamps | Compliance inspection |

---

## 7. Master Draw.io Notebook (`htc_architecture_diagrams.drawio`)

### What This File Is
The file `htc_architecture_diagrams.drawio` is a **multi-tab consolidated workbook** containing all 5 architecture diagrams in a single file.

### How to Open and Edit
1. Open your web browser and navigate to **[app.diagrams.net](https://app.diagrams.net/)** (formerly Draw.io).
2. Click **Open Existing Diagram**.
3. Select `C:\Users\Gigabyte\CAPSTONE-2\docs\diagrams\New folder\htc_architecture_diagrams.drawio`.
4. At the bottom of the canvas, you will see 5 interactive navigation tabs:
   - **Tab 1:** `01. ERD - Relational Data Model`
   - **Tab 2:** `02. DFD Level 0 - Context Diagram`
   - **Tab 3:** `03. DFD Level 1 - Process Decomposition`
   - **Tab 4:** `04. DFD Level 2 - Multi-Batch Logistics`
   - **Tab 5:** `05. Use Case Diagram & Actor Matrix`

---

## 8. Panel Defense Q&A Cheatsheet

### Q1: "Why is TransactionCluster separate from PurchaseOrder in your ERD?"
> **Answer:** "In industrial trading, commercial terms are distinct from legal deal governance. The `TransactionCluster` acts as the master transaction envelope grouping multiple contracts, SRA quota release orders (`MolassesReleaseOrder`), bank financing facilities (`CapitalLoan`), and laboratory inspections (`CHAIRecord`). Separating `PurchaseOrder` maintains strict 1st Normal Form (1NF) while allowing future support for master contract amendments without corrupting the overarching deal cluster lifecycle."

### Q2: "In your Level 0 DFD, why don't Clients or Sugar Mills have user login accounts?"
> **Answer:** "HTC Core is engineered strictly as an internal Enterprise Resource Planning (ERP) platform for HTC trading executives. In the Philippine sugar industry, external counterparties—such as sugar mills, planters' associations, and banks—do not integrate via direct portal logins due to corporate security boundaries and manual offline paperwork. Internal HTC staff (`operations` and `finance`) receive physical or email instruments (MDRs, waybills, promissory notes) and transcribe them into the system, enforcing internal accountability."

### Q3: "How does your system prevent over-delivery when fulfilling a 10,000 MT contract?"
> **Answer:** "As shown in our Level 2 DFD (Process 5.2), whenever a delivery batch is saved, the engine executes an Over-Delivery Balance Guard. It calculates $\text{remaining\_mt} = \text{total\_contracted\_mt} - \sum(\text{delivered\_mt})$. If the batch tonnage exceeds this remaining balance, the transaction is rejected with a `ValidationError` at both the form and database clean levels before any record is created."

### Q4: "How does HTC Core handle transit losses and shrinkage during maritime transport?"
> **Answer:** "Process 6.0 in our Level 1 DFD automatically computes the variance percentage between loaded volume at the mill and received volume at the customer drop-off point:
> $$\text{variance\_percent} = \frac{|\text{loaded\_volume\_mt} - \text{received\_volume\_mt}|}{\text{loaded\_volume\_mt}} \times 100$$
> If this variance exceeds our 1.0% tolerance threshold, the system flags the cluster as `DISPUTED`. The Operations Manager must formally resolve the dispute via one of four pre-defined resolution types (`CONCEDED`, `BILLING_ADJUSTED`, `BARGE_PENALTY`, `WAIVED`) with mandatory audit notes before the cluster can proceed to closure."

### Q5: "How does your financial module calculate dynamic interest on sourcing loans?"
> **Answer:** "Rather than using a static interest amount, our engine computes real-time daily accrued interest based on active days outstanding:
> $$\text{daily\_interest\_cost} = \text{principal} \times \left(\frac{\text{interest\_rate\_annual}}{100 \times 365}\right)$$
> $$\text{accrued\_interest} = \text{daily\_interest\_cost} \times \max(0, (\text{CURRENT\_DATE} - \text{start\_date}))$$
> Interest accrues dynamically each day until the Finance Specialist uploads an official bank settlement clearance advice and the Operations Manager executes dual-authorization verification, locking the final interest liability."

### Q6: "Why did you implement TOTP 2FA and registration approval gating?"
> **Answer:** "HTC Core handles high-value transactions involving multi-million peso commodity deals and capital financing. Standard username/password authentication is vulnerable to credential stuffing and phishing. We implemented RFC 6238 TOTP Two-Factor Authentication with 5 single-use recovery codes, combined with Administrator approval gating (`is_active=False` on registration) to guarantee zero unauthorized access."
