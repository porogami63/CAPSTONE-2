import xml.etree.ElementTree as ET
from xml.dom import minidom
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "docs" / "diagrams"
ARTIFACT_DIR = Path(r"C:\Users\Gigabyte\.gemini\antigravity-ide\brain\473451ac-9352-4fab-b704-595612e0f03b\diagrams")

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
if ARTIFACT_DIR.parent.exists():
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

class DrawIOBuilder:
    def __init__(self, page_width=1800, page_height=1400):
        self.root = ET.Element("mxfile", {
            "host": "app.diagrams.net",
            "modified": "2026-10-23T13:30:00.000Z",
            "agent": "HTC Core Architecture Generator",
            "version": "24.0.0",
            "type": "device"
        })
        self.page_width = page_width
        self.page_height = page_height

    def add_diagram(self, diag_id, name):
        diagram = ET.SubElement(self.root, "diagram", {"id": diag_id, "name": name})
        model = ET.SubElement(diagram, "mxGraphModel", {
            "dx": "1422", "dy": "800", "grid": "1", "gridSize": "10",
            "guides": "1", "tooltips": "1", "connect": "1", "arrows": "1",
            "fold": "1", "page": "1", "pageScale": "1",
            "pageWidth": str(self.page_width), "pageHeight": str(self.page_height),
            "background": "#ffffff", "math": "0", "shadow": "0"
        })
        root_cell = ET.SubElement(model, "root")
        ET.SubElement(root_cell, "mxCell", {"id": "0"})
        ET.SubElement(root_cell, "mxCell", {"id": "1", "parent": "0"})
        return root_cell

    @staticmethod
    def add_cell(parent, cell_id, value, style, x, y, w, h, is_edge=False, source=None, target=None):
        attribs = {
            "id": str(cell_id),
            "value": value,
            "style": style,
            "parent": str(parent.get("id", "1"))
        }
        if is_edge:
            attribs["edge"] = "1"
            if source: attribs["source"] = str(source)
            if target: attribs["target"] = str(target)
        else:
            attribs["vertex"] = "1"

        cell = ET.SubElement(parent, "mxCell", attribs)
        geom = ET.SubElement(cell, "mxGeometry", {"as": "geometry"})
        if is_edge:
            geom.set("relative", "1")
        else:
            geom.set("x", str(x))
            geom.set("y", str(y))
            geom.set("width", str(w))
            geom.set("height", str(h))
        return cell

    @staticmethod
    def add_table_entity(parent, entity_id, title, x, y, width, columns):
        table_style = (
            "swimlane;fontStyle=1;childLayout=stackLayout;horizontal=1;startSize=28;"
            "horizontalStack=0;resizeParent=1;resizeParentMax=0;resizeLast=0;"
            "collapsible=0;marginBottom=0;html=1;rounded=1;shadow=0;"
            "fillColor=#0f172a;strokeColor=#0284c7;strokeWidth=2;fontColor=#ffffff;fontSize=12;"
        )
        total_height = 28 + (len(columns) * 24) + 4
        table_cell = DrawIOBuilder.add_cell(parent, entity_id, title, table_style, x, y, width, total_height)
        
        curr_y = 28
        for idx, (col_name, col_type, is_pk, is_fk) in enumerate(columns):
            badge = ""
            if is_pk: badge = "<b>[PK]</b> "
            elif is_fk: badge = "<b>[FK]</b> "

            val = f"{badge}{col_name}: <i>{col_type}</i>"
            bg = "#f8fafc" if idx % 2 == 0 else "#ffffff"
            row_style = (
                f"text;strokeColor=none;fillColor={bg};align=left;verticalAlign=middle;"
                "spacingLeft=8;spacingRight=8;overflow=hidden;rotatable=0;"
                "portConstraint=eastwest;html=1;fontSize=11;fontColor=#334155;"
            )
            DrawIOBuilder.add_cell(table_cell, f"{entity_id}_r{idx}", val, row_style, 0, curr_y, width, 24)
            curr_y += 24
        return table_cell

    @staticmethod
    def add_edge(parent, edge_id, label, source, target, style=None):
        if style is None:
            style = (
                "edgeStyle=orthogonalEdgeStyle;rounded=1;orthogonalLoop=1;jettySize=auto;html=1;"
                "strokeColor=#0284c7;strokeWidth=2;fontColor=#0f172a;fontSize=11;labelBackgroundColor=#ffffff;"
            )
        return DrawIOBuilder.add_cell(parent, edge_id, label, style, 0, 0, 0, 0, is_edge=True, source=source, target=target)

    def to_xml_string(self):
        raw = ET.tostring(self.root, encoding="utf-8")
        parsed = minidom.parseString(raw)
        return parsed.toprettyxml(indent="  ")


def build_erd_diagram(builder):
    root = builder.add_diagram("erd", "01. ERD - Relational Data Model")

    # Tier Header Labels
    label_style = "text;html=1;strokeColor=none;fillColor=none;align=left;verticalAlign=middle;fontStyle=1;fontSize=14;fontColor=#0369a1;"
    DrawIOBuilder.add_cell(root, "t1_lbl", "TIER 1: MASTER COUNTERPARTIES & IDENTITY", label_style, 50, 20, 500, 30)
    DrawIOBuilder.add_cell(root, "t2_lbl", "TIER 2: COMMERCIAL CONTRACT CORE", label_style, 50, 260, 500, 30)
    DrawIOBuilder.add_cell(root, "t3_lbl", "TIER 3: LOGISTICS EXECUTION & LAB QA", label_style, 50, 570, 500, 30)
    DrawIOBuilder.add_cell(root, "t4_lbl", "TIER 4: INVOICING, TREASURY & RECONCILIATION", label_style, 50, 910, 500, 30)

    # Tier 1 Entities
    DrawIOBuilder.add_table_entity(root, "USER", "USER", 50, 60, 230, [
        ("id", "bigint", True, False),
        ("username", "string", False, False),
        ("role", "string", False, False),
        ("is_active", "boolean", False, False),
        ("is_2fa_enabled", "boolean", False, False)
    ])
    DrawIOBuilder.add_table_entity(root, "SYSTEM_AUDIT_TRAIL", "SYSTEM_AUDIT_TRAIL", 330, 60, 250, [
        ("id", "bigint", True, False),
        ("user_id", "bigint", False, True),
        ("action", "string", False, False),
        ("table_name", "string", False, False),
        ("timestamp", "datetime", False, False)
    ])
    DrawIOBuilder.add_table_entity(root, "CLIENT", "CLIENT", 630, 60, 240, [
        ("id", "bigint", True, False),
        ("name", "string", False, False),
        ("tin", "string", False, False),
        ("contact_person", "string", False, False),
        ("is_active", "boolean", False, False)
    ])
    DrawIOBuilder.add_table_entity(root, "SUGAR_MILL", "SUGAR_MILL", 920, 60, 240, [
        ("id", "bigint", True, False),
        ("name", "string", False, False),
        ("location", "string", False, False),
        ("is_active", "boolean", False, False)
    ])
    DrawIOBuilder.add_table_entity(root, "PLANTER", "PLANTER", 1210, 60, 240, [
        ("id", "bigint", True, False),
        ("name", "string", False, False),
        ("code", "string", False, False),
        ("is_active", "boolean", False, False)
    ])

    # Tier 2 Entities
    DrawIOBuilder.add_table_entity(root, "LOGISTICS_LEDGER", "LOGISTICS_LEDGER", 130, 300, 260, [
        ("id", "bigint", True, False),
        ("cluster_id", "uuid", False, True),
        ("loaded_volume_mt", "decimal", False, False),
        ("received_volume_mt", "decimal", False, False),
        ("tracking_fees", "decimal", False, False),
        ("barge_fees", "decimal", False, False),
        ("variance_percent", "decimal", False, False),
        ("dispute_status", "string", False, False)
    ])
    DrawIOBuilder.add_table_entity(root, "TRANSACTION_CLUSTER", "TRANSACTION_CLUSTER", 450, 300, 260, [
        ("id", "uuid", True, False),
        ("reference_code", "string", False, False),
        ("client_id", "bigint", False, True),
        ("sugar_mill_id", "bigint", False, True),
        ("status", "string", False, False),
        ("mro_file", "string", False, False),
        ("is_archived", "boolean", False, False)
    ])
    DrawIOBuilder.add_table_entity(root, "PURCHASE_ORDER", "PURCHASE_ORDER", 770, 300, 260, [
        ("id", "bigint", True, False),
        ("cluster_id", "uuid", False, True),
        ("po_reference_number", "string", False, False),
        ("total_contracted_mt", "decimal", False, False),
        ("unit_price", "decimal", False, False),
        ("selling_price", "decimal", False, False),
        ("po_status", "string", False, False)
    ])
    DrawIOBuilder.add_table_entity(root, "MOLASSES_RELEASE_ORDER", "MOLASSES_RELEASE_ORDER", 1090, 300, 260, [
        ("id", "bigint", True, False),
        ("mro_number", "string", False, False),
        ("planter_id", "bigint", False, True),
        ("sugar_mill_id", "bigint", False, True),
        ("tons", "decimal", False, False),
        ("crop_year", "string", False, False),
        ("cluster_id", "uuid", False, True)
    ])

    # Tier 3 Entities
    DrawIOBuilder.add_table_entity(root, "LOGISTICS_PARTNER", "LOGISTICS_PARTNER", 450, 610, 240, [
        ("id", "bigint", True, False),
        ("name", "string", False, False),
        ("category", "string", False, False),
        ("default_freight_rate", "decimal", False, False),
        ("is_active", "boolean", False, False)
    ])
    DrawIOBuilder.add_table_entity(root, "DELIVERY_LEDGER", "DELIVERY_LEDGER", 770, 610, 270, [
        ("delivery_id", "uuid", True, False),
        ("purchase_order_id", "bigint", False, True),
        ("supplier_id", "bigint", False, True),
        ("delivered_mt", "decimal", False, False),
        ("receiving_location", "string", False, False),
        ("trucking_partner_id", "bigint", False, True),
        ("trucking_rate_per_mt", "decimal", False, False),
        ("barge_partner_id", "bigint", False, True),
        ("barge_rate_per_mt", "decimal", False, False)
    ])
    DrawIOBuilder.add_table_entity(root, "CHAI_RECORD", "CHAI_RECORD", 1090, 610, 240, [
        ("id", "uuid", True, False),
        ("chai_number", "string", False, False),
        ("chai_value", "decimal", False, False),
        ("cluster_id", "uuid", False, True),
        ("brix_level", "decimal", False, False),
        ("status", "string", False, False)
    ])
    DrawIOBuilder.add_table_entity(root, "MRO_EXTRACTION_JOB", "MRO_EXTRACTION_JOB", 1380, 610, 240, [
        ("id", "uuid", True, False),
        ("cluster_id", "uuid", False, True),
        ("status", "string", False, False),
        ("average_confidence", "float", False, False),
        ("extracted_data", "json", False, False)
    ])

    # Tier 4 Entities
    DrawIOBuilder.add_table_entity(root, "CASH_VOUCHER", "CASH_VOUCHER", 130, 950, 250, [
        ("id", "bigint", True, False),
        ("loan_id", "bigint", False, True),
        ("voucher_number", "string", False, False),
        ("amount", "decimal", False, False),
        ("purpose", "string", False, False),
        ("status", "string", False, False)
    ])
    DrawIOBuilder.add_table_entity(root, "CAPITAL_LOAN", "CAPITAL_LOAN", 450, 950, 260, [
        ("id", "bigint", True, False),
        ("cluster_id", "uuid", False, True),
        ("bank_name", "string", False, False),
        ("principal", "decimal", False, False),
        ("interest_rate_annual", "decimal", False, False),
        ("start_date", "date", False, False),
        ("due_date", "date", False, False),
        ("status", "string", False, False)
    ])
    DrawIOBuilder.add_table_entity(root, "INVOICE", "INVOICE", 770, 950, 250, [
        ("id", "bigint", True, False),
        ("cluster_id", "uuid", False, True),
        ("invoice_number", "string", False, False),
        ("amount", "decimal", False, False),
        ("tax_rate_vat", "decimal", False, False),
        ("tax_rate_ewt", "decimal", False, False),
        ("is_incremental", "boolean", False, False),
        ("status", "string", False, False)
    ])
    DrawIOBuilder.add_table_entity(root, "FINANCIAL_RECONCILIATION", "FINANCIAL_RECONCILIATION", 450, 1220, 260, [
        ("id", "bigint", True, False),
        ("cluster_id", "uuid", False, True),
        ("status", "string", False, False),
        ("matched_payment_amount", "decimal", False, False)
    ])
    DrawIOBuilder.add_table_entity(root, "PAYMENT_EXPENSE_MATCH", "PAYMENT_EXPENSE_MATCH", 770, 1220, 260, [
        ("id", "bigint", True, False),
        ("reconciliation_id", "bigint", False, True),
        ("payment_reference", "string", False, False),
        ("expense_type", "string", False, False),
        ("amount", "decimal", False, False)
    ])

    # Edges
    crows_foot_1n = "edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;startArrow=ERone;endArrow=ERmany;strokeColor=#0284c7;strokeWidth=2;fontSize=11;"
    crows_foot_11 = "edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;startArrow=ERone;endArrow=ERone;strokeColor=#0284c7;strokeWidth=2;fontSize=11;"
    crows_foot_0n = "edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;startArrow=ERzeroToOne;endArrow=ERmany;strokeColor=#0284c7;strokeWidth=2;fontSize=11;"

    DrawIOBuilder.add_edge(root, "e1", "audits (0:N)", "USER", "SYSTEM_AUDIT_TRAIL", crows_foot_0n)
    DrawIOBuilder.add_edge(root, "e2", "contracts (1:N)", "CLIENT", "TRANSACTION_CLUSTER", crows_foot_1n)
    DrawIOBuilder.add_edge(root, "e3", "sources (1:N)", "SUGAR_MILL", "TRANSACTION_CLUSTER", crows_foot_1n)
    DrawIOBuilder.add_edge(root, "e4", "issues (1:N)", "SUGAR_MILL", "MOLASSES_RELEASE_ORDER", crows_foot_1n)
    DrawIOBuilder.add_edge(root, "e5", "quota holder (1:N)", "PLANTER", "MOLASSES_RELEASE_ORDER", crows_foot_1n)

    DrawIOBuilder.add_edge(root, "e6", "commercial terms (1:1)", "TRANSACTION_CLUSTER", "PURCHASE_ORDER", crows_foot_11)
    DrawIOBuilder.add_edge(root, "e7", "aggregates haulage (1:1)", "TRANSACTION_CLUSTER", "LOGISTICS_LEDGER", crows_foot_11)
    DrawIOBuilder.add_edge(root, "e8", "permits (0:N)", "TRANSACTION_CLUSTER", "MOLASSES_RELEASE_ORDER", crows_foot_0n)
    DrawIOBuilder.add_edge(root, "e9", "financed by (0:N)", "TRANSACTION_CLUSTER", "CAPITAL_LOAN", crows_foot_0n)

    DrawIOBuilder.add_edge(root, "e10", "fulfilled by (1:N)", "PURCHASE_ORDER", "DELIVERY_LEDGER", crows_foot_1n)
    DrawIOBuilder.add_edge(root, "e11", "hauls (0:N)", "LOGISTICS_PARTNER", "DELIVERY_LEDGER", crows_foot_0n)
    DrawIOBuilder.add_edge(root, "e12", "OCR intake (0:N)", "MOLASSES_RELEASE_ORDER", "MRO_EXTRACTION_JOB", crows_foot_0n)
    DrawIOBuilder.add_edge(root, "e13", "lab tests (0:N)", "MOLASSES_RELEASE_ORDER", "CHAI_RECORD", crows_foot_0n)

    DrawIOBuilder.add_edge(root, "e14", "billed via (0:N)", "DELIVERY_LEDGER", "INVOICE", crows_foot_0n)
    DrawIOBuilder.add_edge(root, "e15", "disburses expenses (0:N)", "CAPITAL_LOAN", "CASH_VOUCHER", crows_foot_0n)
    DrawIOBuilder.add_edge(root, "e16", "reconciled in (1:1)", "CAPITAL_LOAN", "FINANCIAL_RECONCILIATION", crows_foot_11)
    DrawIOBuilder.add_edge(root, "e17", "matched lines (1:N)", "FINANCIAL_RECONCILIATION", "PAYMENT_EXPENSE_MATCH", crows_foot_1n)


def build_dfd0_diagram(builder):
    root = builder.add_diagram("dfd0", "02. DFD Level 0 - Context Diagram")

    container_style = (
        "swimlane;whiteSpace=wrap;html=1;fontStyle=1;align=center;verticalAlign=top;childLayout=stackLayout;"
        "horizontal=1;startSize=30;horizontalStack=0;resizeParent=0;resizeParentMax=0;resizeLast=0;"
        "collapsible=0;marginBottom=0;rounded=1;shadow=0;fillColor=#f8fafc;strokeColor=#64748b;strokeWidth=1.5;"
        "fontColor=#0f172a;fontSize=12;"
    )

    # 1. Left Container: Internal Users
    left_cont = DrawIOBuilder.add_cell(root, "internal_group", "👥 AUTHENTICATED INTERNAL USERS (Web Portal Accounts)",
                                      container_style, 50, 60, 310, 480)
    user_style = "rounded=1;whiteSpace=wrap;html=1;fillColor=#0f172a;strokeColor=#38bdf8;strokeWidth=2;fontColor=#ffffff;fontSize=11;align=left;spacingLeft=10;"
    DrawIOBuilder.add_cell(left_cont, "Admin", "<b>🛡️ System Administrator</b><br/>• User Approvals &amp; RBAC Roles<br/>• 2FA Security Enforcement<br/>• Immutable Audit Inspection",
                           user_style, 20, 45, 270, 95)
    DrawIOBuilder.add_cell(left_cont, "Ops", "<b>👤 Operations Team</b><br/>• Deal Clusters &amp; PO Contracts<br/>• Multi-Batch Dispatches &amp; Rates<br/>• MRO Upload &amp; Quality Grading<br/>• Transit Shrinkage Disputes",
                           user_style, 20, 165, 270, 110)
    DrawIOBuilder.add_cell(left_cont, "Fin", "<b>💳 Finance &amp; Invoicing</b><br/>• Sourcing Capital Loans<br/>• Daily Dynamic Accruals<br/>• Suggestive Sales Invoicing<br/>• 3-Step Match &amp; Cash Vouchers",
                           user_style, 20, 300, 270, 110)

    # 2. Center: Platform Core
    platform_style = "ellipse;whiteSpace=wrap;html=1;fillColor=#0284c7;strokeColor=#38bdf8;strokeWidth=3;fontColor=#ffffff;fontStyle=1;fontSize=14;align=center;shadow=1;"
    DrawIOBuilder.add_cell(root, "Platform", "⚙️ 0.0<br/><b>HTC CORE PLATFORM</b><br/><font style='font-size:11px;font-weight:normal;'>Trading, Multi-Batch Logistics,<br/>Dynamic Treasury &amp; Document AI</font>",
                           platform_style, 460, 200, 260, 180)

    # 3. Right Container: External Counterparties & Cloud AI
    right_cont = DrawIOBuilder.add_cell(root, "external_group", "🏢 EXTERNAL COUNTERPARTIES & CLOUD SERVICES (Offline / API)",
                                       container_style, 840, 50, 320, 540)
    ext_style = "rounded=1;whiteSpace=wrap;html=1;fillColor=#1e293b;strokeColor=#64748b;strokeWidth=1.5;fontColor=#f8fafc;fontSize=10.5;align=left;spacingLeft=8;"
    cloud_style = "rounded=1;whiteSpace=wrap;html=1;fillColor=#2e1065;strokeColor=#a855f7;strokeWidth=2;fontColor=#ffffff;fontSize=10.5;align=left;spacingLeft=8;"
    
    DrawIOBuilder.add_cell(right_cont, "Cust", "<b>🏢 Clients / Buyers</b><br/>• Contract Purchase Orders<br/>• Receiving Weighbridge Receipts<br/>• Invoices &amp; Billing Statements",
                           ext_style, 20, 45, 280, 80)
    DrawIOBuilder.add_cell(right_cont, "Mills", "<b>🏭 Sugar Mills &amp; Planters</b><br/>• MRO Permits &amp; Mill Quotas<br/>• Mill Delivery Receipts (MDR)<br/>• Brix Laboratory Quality Reports",
                           ext_style, 20, 140, 280, 80)
    DrawIOBuilder.add_cell(right_cont, "Carriers", "<b>🚚 Logistics Carriers</b><br/>• Hauler Gate Passes &amp; Waybills<br/>• Truck / Barge Freight Rates<br/>• Cheque Disbursement Vouchers",
                           ext_style, 20, 235, 280, 80)
    DrawIOBuilder.add_cell(right_cont, "Banks", "<b>🏦 Commercial Lending Banks</b><br/>• Sourcing Loan Terms &amp; Principal<br/>• Daily Interest Rates<br/>• Settlement Clearance Advices",
                           ext_style, 20, 330, 280, 80)
    DrawIOBuilder.add_cell(right_cont, "Textract", "<b>☁️ AWS Textract Document AI</b><br/>• Scanned MRO Document PDFs<br/>• Extracted Tables &amp; Key-Values<br/>• Recognition Confidence Scores",
                           cloud_style, 20, 425, 280, 80)

    # Connections
    edge_style = "edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;strokeColor=#0284c7;strokeWidth=2;fontSize=10;fontColor=#0f172a;labelBackgroundColor=#ffffff;"
    DrawIOBuilder.add_edge(root, "dfd0_e1", "User Approvals & Audit Queries", "Admin", "Platform", edge_style)
    DrawIOBuilder.add_edge(root, "dfd0_e2", "Logistics, MRO & Deal Data", "Ops", "Platform", edge_style)
    DrawIOBuilder.add_edge(root, "dfd0_e3", "Treasury, Invoicing & Loan Data", "Fin", "Platform", edge_style)

    DrawIOBuilder.add_edge(root, "dfd0_e4", "Sales Invoices & Billing Statements", "Platform", "Cust", edge_style)
    DrawIOBuilder.add_edge(root, "dfd0_e5", "Permits, MDRs & Brix Specs", "Platform", "Mills", edge_style)
    DrawIOBuilder.add_edge(root, "dfd0_e6", "Waybills, Rates & Cheque Vouchers", "Platform", "Carriers", edge_style)
    DrawIOBuilder.add_edge(root, "dfd0_e7", "Credit Lines, Payoffs & Advices", "Platform", "Banks", edge_style)
    DrawIOBuilder.add_edge(root, "dfd0_e8", "Automated Cloud OCR API", "Platform", "Textract", edge_style)


def build_dfd1_diagram(builder):
    root = builder.add_diagram("dfd1", "03. DFD Level 1 - Process Decomposition")

    phase_style = (
        "swimlane;whiteSpace=wrap;html=1;fontStyle=1;align=center;verticalAlign=top;startSize=26;"
        "collapsible=0;rounded=1;shadow=0;fillColor=#f8fafc;strokeColor=#94a3b8;strokeWidth=1.5;"
        "fontColor=#0369a1;fontSize=11.5;"
    )
    proc_style = "rounded=1;whiteSpace=wrap;html=1;fillColor=#0284c7;strokeColor=#38bdf8;strokeWidth=2;fontColor=#ffffff;fontSize=11;fontStyle=1;align=center;"
    check_style = "rounded=1;whiteSpace=wrap;html=1;fillColor=#b91c1c;strokeColor=#f87171;strokeWidth=2;fontColor=#ffffff;fontSize=11;fontStyle=1;align=center;"
    fin_style = "rounded=1;whiteSpace=wrap;html=1;fillColor=#15803d;strokeColor=#4ade80;strokeWidth=2;fontColor=#ffffff;fontSize=11;fontStyle=1;align=center;"
    store_style = "shape=partialRectangle;top=0;bottom=0;fillColor=#1e293b;strokeColor=#0ea5e9;strokeWidth=2;fontColor=#e0f2fe;fontStyle=1;fontSize=10.5;align=center;whiteSpace=wrap;html=1;"

    # Phase 1
    p1_box = DrawIOBuilder.add_cell(root, "phase1", "1. COMMERCIAL SOURCING & MASTER DATA SETUP", phase_style, 50, 40, 1140, 120)
    DrawIOBuilder.add_cell(p1_box, "P1", "1.0 Master Data & User RBAC<br/><font style='font-size:10px;font-weight:normal;'>(Clients, Mills, Carriers, RBAC)</font>", proc_style, 30, 40, 220, 60)
    DrawIOBuilder.add_cell(p1_box, "D12", "D1 &amp; D2: Master Catalogs<br/>&amp; User Store", store_style, 310, 40, 210, 60)
    DrawIOBuilder.add_cell(p1_box, "P2", "2.0 Deal &amp; PO Formulation<br/><font style='font-size:10px;font-weight:normal;'>(Cluster Ref, Target MT, Base Price)</font>", proc_style, 590, 40, 230, 60)
    DrawIOBuilder.add_cell(p1_box, "D3", "D3: PurchaseOrder &amp; Deal Store", store_style, 880, 40, 220, 60)

    # Phase 2
    p2_box = DrawIOBuilder.add_cell(root, "phase2", "2. PERMITTING & LAB QUALITY COMPLIANCE", phase_style, 50, 210, 1140, 120)
    DrawIOBuilder.add_cell(p2_box, "P3", "3.0 MRO Document OCR &amp; Intake<br/><font style='font-size:10px;font-weight:normal;'>(Scanned MRO PDF to AWS Textract)</font>", proc_style, 30, 40, 220, 60)
    DrawIOBuilder.add_cell(p2_box, "D5", "D5: MRO Permitting Store", store_style, 310, 40, 210, 60)
    DrawIOBuilder.add_cell(p2_box, "P4", "4.0 CHAI Laboratory Quality Grading<br/><font style='font-size:10px;font-weight:normal;'>(Brix % &amp; Physical Grade)</font>", proc_style, 590, 40, 230, 60)
    DrawIOBuilder.add_cell(p2_box, "D5B", "D5B: Lab Quality Store", store_style, 880, 40, 220, 60)

    # Phase 3
    p3_box = DrawIOBuilder.add_cell(root, "phase3", "3. MULTI-BATCH LOGISTICS & DISPUTE RESOLUTION", phase_style, 50, 380, 1140, 120)
    DrawIOBuilder.add_cell(p3_box, "P5", "5.0 Over-Delivery Balance Guard<br/><font style='font-size:10px;font-weight:normal;'>&amp; Batch Haulage Dispatch</font>", check_style, 30, 40, 220, 60)
    DrawIOBuilder.add_cell(p3_box, "D4", "D4: DeliveryLedger Store", store_style, 310, 40, 210, 60)
    DrawIOBuilder.add_cell(p3_box, "P6", "6.0 Transit Variance Engine<br/><font style='font-size:10px;font-weight:normal;'>(Flag >1.0% Transit Loss)</font>", check_style, 590, 40, 230, 60)
    DrawIOBuilder.add_cell(p3_box, "D4B", "D4B: LogisticsLedger Store", store_style, 880, 40, 220, 60)

    # Phase 4
    p4_box = DrawIOBuilder.add_cell(root, "phase4", "4. DYNAMIC TREASURY, INVOICING & SETTLEMENT", phase_style, 50, 550, 1230, 120)
    DrawIOBuilder.add_cell(p4_box, "P7", "7.0 Suggestive Sales Invoicing<br/><font style='font-size:10px;font-weight:normal;'>(12% VAT + 1% EWT)</font>", fin_style, 20, 40, 180, 60)
    DrawIOBuilder.add_cell(p4_box, "D6", "D6: Billing &amp; Invoices Store", store_style, 220, 40, 160, 60)
    DrawIOBuilder.add_cell(p4_box, "P8", "8.0 Capital Loan Facility<br/><font style='font-size:10px;font-weight:normal;'>&amp; Daily Accrual Engine</font>", fin_style, 410, 40, 180, 60)
    DrawIOBuilder.add_cell(p4_box, "D7", "D7: Capital Loans Facility", store_style, 610, 40, 170, 60)
    DrawIOBuilder.add_cell(p4_box, "P9", "9.0 Auto-Voucher Disbursement<br/><font style='font-size:10px;font-weight:normal;'>&amp; 3-Step Payment Match</font>", fin_style, 810, 40, 200, 60)
    DrawIOBuilder.add_cell(p4_box, "D7B", "D7B: Cash Vouchers Store", store_style, 1030, 40, 180, 60)

    # Phase 5
    p5_box = DrawIOBuilder.add_cell(root, "phase5", "5. ENTERPRISE GOVERNANCE & AUDIT TRAIL", phase_style, 50, 720, 1140, 120)
    DrawIOBuilder.add_cell(p5_box, "P10", "10.0 Immutable Audit Trail &amp; HTC Copilot ORM Engine<br/><font style='font-size:10px;font-weight:normal;'>(Append-only logs &amp; Natural Language-to-SQL Assistant)</font>", proc_style, 220, 40, 380, 60)
    DrawIOBuilder.add_cell(p5_box, "D8", "D8: Audit &amp; Governance Store", store_style, 660, 40, 250, 60)

    # Sequential Major Inter-Phase Highway Edges
    highway_style = "edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;strokeColor=#0284c7;strokeWidth=3;fontSize=11;fontColor=#0f172a;labelBackgroundColor=#ffffff;"
    DrawIOBuilder.add_edge(root, "dfd1_h1", "Approved Deal PO Contract", "phase1", "phase2", highway_style)
    DrawIOBuilder.add_edge(root, "dfd1_h2", "Validated Quotas & Grade Approval", "phase2", "phase3", highway_style)
    DrawIOBuilder.add_edge(root, "dfd1_h3", "Dispatched Dispatches & Waybill Freight", "phase3", "phase4", highway_style)
    DrawIOBuilder.add_edge(root, "dfd1_h4", "Financial Closures & Reconciliation", "phase4", "phase5", highway_style)


def build_dfd2_diagram(builder):
    root = builder.add_diagram("dfd2", "04. DFD Level 2 - Multi-Batch Logistics")

    actor_style = "rounded=1;whiteSpace=wrap;html=1;fillColor=#0f172a;strokeColor=#38bdf8;strokeWidth=2;fontColor=#ffffff;fontSize=11;fontStyle=1;align=center;"
    proc_style = "rounded=1;whiteSpace=wrap;html=1;fillColor=#0284c7;strokeColor=#38bdf8;strokeWidth=2;fontColor=#ffffff;fontSize=11;fontStyle=1;align=center;"
    check_style = "rhombus;whiteSpace=wrap;html=1;fillColor=#b91c1c;strokeColor=#f87171;strokeWidth=2;fontColor=#ffffff;fontSize=11;fontStyle=1;align=center;"
    err_style = "rounded=1;whiteSpace=wrap;html=1;fillColor=#991b1b;strokeColor=#fca5a5;strokeWidth=2;fontColor=#ffffff;fontSize=11;fontStyle=1;align=center;"
    store_style = "shape=partialRectangle;top=0;bottom=0;fillColor=#1e293b;strokeColor=#0ea5e9;strokeWidth=2;fontColor=#e0f2fe;fontStyle=1;fontSize=10.5;align=center;whiteSpace=wrap;html=1;"
    fin_style = "rounded=1;whiteSpace=wrap;html=1;fillColor=#15803d;strokeColor=#4ade80;strokeWidth=2;fontColor=#ffffff;fontSize=11;fontStyle=1;align=center;"
    container_style = (
        "swimlane;whiteSpace=wrap;html=1;fontStyle=1;align=center;verticalAlign=top;startSize=26;"
        "collapsible=0;rounded=1;shadow=0;fillColor=#f8fafc;strokeColor=#0284c7;strokeWidth=1.5;"
        "fontColor=#0f172a;fontSize=12;"
    )

    DrawIOBuilder.add_cell(root, "StartInput", "👤 Operations Coordinator<br/><font style='font-size:10px;font-weight:normal;'>(Submits Delivery Batch Payload)</font>", actor_style, 380, 40, 240, 60)
    DrawIOBuilder.add_cell(root, "P51", "5.1 Parse Batch Parameters<br/><font style='font-size:10px;font-weight:normal;'>(PO, Sourcing Mill, Dest, MT, Dual Freight Rates)</font>", proc_style, 370, 135, 260, 65)
    DrawIOBuilder.add_cell(root, "POStore1", "D3: PurchaseOrder Store<br/><font style='font-size:9.5px;font-weight:normal;'>total_contracted_mt &amp; deliveries</font>", store_style, 680, 225, 210, 60)
    DrawIOBuilder.add_cell(root, "P52", "5.2 Balance Guard<br/>delivered_mt &lt;= remaining_mt?", check_style, 395, 230, 210, 85)
    DrawIOBuilder.add_cell(root, "ErrBlock", "❌ Over-Delivery Validation Error<br/><font style='font-size:10px;font-weight:normal;'>(Transaction Rejected &amp; Blocked)</font>", err_style, 120, 242, 210, 60)
    DrawIOBuilder.add_cell(root, "P53", "5.3 Compute Dual-Mode Freight Economics<br/><font style='font-size:10px;font-weight:normal;'>Trucking = (Delivered MT × Rate) + Flat Fee<br/>Barging = (Delivered MT × Rate) + Flat Fee</font>", proc_style, 360, 345, 280, 75)
    DrawIOBuilder.add_cell(root, "P54", "5.4 Write DeliveryLedger Batch Entry<br/><font style='font-size:10px;font-weight:normal;'>(Store Timestamps, Plates, MDR &amp; Waybill #)</font>", proc_style, 370, 450, 260, 60)
    DrawIOBuilder.add_cell(root, "DelStore", "D4: DeliveryLedger Store<br/><font style='font-size:9.5px;font-weight:normal;'>[UUIDv4 Primary Key]</font>", store_style, 120, 450, 200, 60)

    # Sync Container
    sync_box = DrawIOBuilder.add_cell(root, "sync_box", "⚡ Automated Post-Delivery Synchronization", container_style, 80, 540, 840, 140)
    DrawIOBuilder.add_cell(sync_box, "P55", "5.5 Update PO Fulfillment State<br/><font style='font-size:10px;font-weight:normal;'>(Open / Partially Fulfilled / Completed)</font>", proc_style, 25, 45, 230, 65)
    DrawIOBuilder.add_cell(sync_box, "P56", "5.6 Synchronize LogisticsLedger<br/><font style='font-size:10px;font-weight:normal;'>(Aggregate Origin/Destination MT &amp; Fees)</font>", proc_style, 295, 45, 240, 65)
    DrawIOBuilder.add_cell(sync_box, "P57", "5.7 Trigger Auto-Voucher Outlays<br/><font style='font-size:10px;font-weight:normal;'>(Generate CV-DEL-*-TRK / BRG &amp; 3-Step Match)</font>", fin_style, 575, 45, 240, 65)

    # Stores
    DrawIOBuilder.add_cell(root, "POStore2", "D3: PurchaseOrder Store", store_style, 120, 715, 200, 55)
    DrawIOBuilder.add_cell(root, "LogStore", "D4B: LogisticsLedger Store", store_style, 395, 715, 200, 55)
    DrawIOBuilder.add_cell(root, "FinStore", "D7: Treasury &amp; Voucher Store", store_style, 675, 715, 200, 55)

    # Edges
    edge_style = "edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;strokeColor=#0284c7;strokeWidth=2;fontSize=10;fontColor=#0f172a;labelBackgroundColor=#ffffff;"
    err_edge_style = "edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;strokeColor=#b91c1c;strokeWidth=2;fontSize=10;fontColor=#b91c1c;labelBackgroundColor=#ffffff;"
    
    DrawIOBuilder.add_edge(root, "dfd2_e1", "", "StartInput", "P51", edge_style)
    DrawIOBuilder.add_edge(root, "dfd2_e2", "", "P51", "P52", edge_style)
    DrawIOBuilder.add_edge(root, "dfd2_e3", "Read Remaining Balance", "POStore1", "P52", edge_style)
    DrawIOBuilder.add_edge(root, "dfd2_e4", "NO: Exceeds Quota", "P52", "ErrBlock", err_edge_style)
    DrawIOBuilder.add_edge(root, "dfd2_e5", "YES: Within Quota", "P52", "P53", edge_style)
    DrawIOBuilder.add_edge(root, "dfd2_e6", "", "P53", "P54", edge_style)
    DrawIOBuilder.add_edge(root, "dfd2_e7", "Insert Record", "P54", "DelStore", edge_style)

    DrawIOBuilder.add_edge(root, "dfd2_e8", "", "P54", "P55", edge_style)
    DrawIOBuilder.add_edge(root, "dfd2_e9", "", "P54", "P56", edge_style)
    DrawIOBuilder.add_edge(root, "dfd2_e10", "", "P54", "P57", edge_style)

    DrawIOBuilder.add_edge(root, "dfd2_e11", "Update Status", "P55", "POStore2", edge_style)
    DrawIOBuilder.add_edge(root, "dfd2_e12", "Update Totals", "P56", "LogStore", edge_style)
    DrawIOBuilder.add_edge(root, "dfd2_e13", "Record Vouchers", "P57", "FinStore", edge_style)


def build_use_case_diagram(builder):
    root = builder.add_diagram("use_case", "05. Use Case Diagram & Actor Matrix")

    actor_style = "shape=umlActor;verticalLabelPosition=bottom;verticalAlign=top;html=1;outlineConnect=0;fillColor=#0f172a;strokeColor=#38bdf8;strokeWidth=2;fontColor=#0f172a;fontSize=11;fontStyle=1;"
    boundary_style = "swimlane;whiteSpace=wrap;html=1;fontStyle=1;align=center;verticalAlign=top;startSize=28;collapsible=0;rounded=1;shadow=0;fillColor=#f8fafc;strokeColor=#0284c7;strokeWidth=2;fontColor=#0f172a;fontSize=13;"
    domain_style = "swimlane;whiteSpace=wrap;html=1;fontStyle=1;align=center;verticalAlign=top;startSize=24;collapsible=0;rounded=1;shadow=0;fillColor=#ffffff;strokeColor=#64748b;strokeWidth=1.5;fontColor=#0369a1;fontSize=11.5;"
    pkg_style = "swimlane;whiteSpace=wrap;html=1;fontStyle=1;align=center;verticalAlign=top;startSize=22;collapsible=0;rounded=1;fillColor=#f8fafc;strokeColor=#cbd5e1;strokeWidth=1;fontColor=#334155;fontSize=10.5;"
    uc_style = "ellipse;whiteSpace=wrap;html=1;fillColor=#1e293b;strokeColor=#0ea5e9;strokeWidth=1.5;fontColor=#ffffff;fontSize=10.5;fontStyle=0;align=center;"
    cloud_style = "rounded=1;whiteSpace=wrap;html=1;fillColor=#2e1065;strokeColor=#a855f7;strokeWidth=2;fontColor=#ffffff;fontSize=10.5;fontStyle=1;align=center;"

    # Left Actors
    DrawIOBuilder.add_cell(root, "OpsStaff", "👤 Operations Staff<br/><font style='font-size:9.5px;font-weight:normal;'>(Role: operations)</font>", actor_style, 40, 180, 90, 110)
    DrawIOBuilder.add_cell(root, "OpsMgr", "👤 Operations Manager<br/><font style='font-size:9.5px;font-weight:normal;'>(Role: operations_management)</font>", actor_style, 40, 360, 90, 110)

    # Center Boundary
    boundary = DrawIOBuilder.add_cell(root, "HTCSystem", "⚙️ HTC CORE PLATFORM SYSTEM BOUNDARY", boundary_style, 180, 40, 1140, 960)

    # Ops Domain
    ops_domain = DrawIOBuilder.add_cell(boundary, "OpsDomain", "📦 SOURCING & LOGISTICS DOMAIN", domain_style, 20, 40, 1100, 420)
    
    # Pkg 1
    pkg1 = DrawIOBuilder.add_cell(ops_domain, "Pkg1", "1. Sourcing Deals & PO Contracts", pkg_style, 20, 35, 1060, 80)
    DrawIOBuilder.add_cell(pkg1, "UC1", "UC-01: Formulate Deal Cluster &amp; PO", uc_style, 30, 26, 240, 44)
    DrawIOBuilder.add_cell(pkg1, "UC2", "UC-02: Review / Return Deal Cluster", uc_style, 300, 26, 240, 44)
    DrawIOBuilder.add_cell(pkg1, "UC3", "UC-03: Bulk Excel Operations Intake", uc_style, 570, 26, 240, 44)

    # Pkg 2
    pkg2 = DrawIOBuilder.add_cell(ops_domain, "Pkg2", "2. Multi-Batch Logistics & Disputes", pkg_style, 20, 125, 1060, 130)
    DrawIOBuilder.add_cell(pkg2, "UC4", "UC-04: Dispatch Batch with Dual Freight", uc_style, 30, 26, 240, 44)
    DrawIOBuilder.add_cell(pkg2, "UC5", "UC-05: Enforce Over-Delivery Guard", uc_style, 300, 26, 240, 44)
    DrawIOBuilder.add_cell(pkg2, "UC6", "UC-06: Flag >1.0% Transit Shrinkage", uc_style, 30, 75, 240, 44)
    DrawIOBuilder.add_cell(pkg2, "UC7", "UC-07: Resolve Transit Variance Dispute", uc_style, 300, 75, 240, 44)

    # Pkg 3
    pkg3 = DrawIOBuilder.add_cell(ops_domain, "Pkg3", "3. MRO Permits & Lab Quality", pkg_style, 20, 265, 1060, 140)
    DrawIOBuilder.add_cell(pkg3, "UC8", "UC-08: Upload Scanned MRO Quota PDF", uc_style, 20, 26, 230, 44)
    DrawIOBuilder.add_cell(pkg3, "UC9", "UC-09: Trigger Textract OCR Extraction", uc_style, 270, 26, 230, 44)
    DrawIOBuilder.add_cell(pkg3, "Textract", "☁️ AWS Textract AI<br/><font style='font-size:9.5px;font-weight:normal;'>Cloud Document OCR</font>", cloud_style, 520, 26, 170, 44)
    DrawIOBuilder.add_cell(pkg3, "UC10", "UC-10: Verify &amp; Link MRO to Deal", uc_style, 710, 26, 230, 44)
    DrawIOBuilder.add_cell(pkg3, "UC11", "UC-11: Record Laboratory CHAI Grade &amp; Brix", uc_style, 270, 80, 260, 44)

    # FinGov Domain
    fin_domain = DrawIOBuilder.add_cell(boundary, "FinGovDomain", "💳 TREASURY, INVOICING & GOVERNANCE DOMAIN", domain_style, 20, 475, 1100, 470)

    # Pkg 4
    pkg4 = DrawIOBuilder.add_cell(fin_domain, "Pkg4", "4. Billing & Sales Invoicing Engine", pkg_style, 20, 35, 1060, 80)
    DrawIOBuilder.add_cell(pkg4, "UC12", "UC-12: Generate Suggestive Delivery Invoice", uc_style, 30, 26, 250, 44)
    DrawIOBuilder.add_cell(pkg4, "UC13", "UC-13: Compute 12% VAT &amp; 1% EWT Base", uc_style, 310, 26, 250, 44)
    DrawIOBuilder.add_cell(pkg4, "UC14", "UC-14: Export Official Billing PDF Statement", uc_style, 590, 26, 250, 44)

    # Pkg 5
    pkg5 = DrawIOBuilder.add_cell(fin_domain, "Pkg5", "5. Sourcing Capital Loans & Treasury", pkg_style, 20, 125, 1060, 140)
    DrawIOBuilder.add_cell(pkg5, "UC15", "UC-15: Initiate Sourcing Capital Loan", uc_style, 30, 26, 240, 44)
    DrawIOBuilder.add_cell(pkg5, "UC16", "UC-16: Dual-Auth Loan Creation Approval", uc_style, 300, 26, 240, 44)
    DrawIOBuilder.add_cell(pkg5, "UC17", "UC-17: Track Daily Dynamic Accruals", uc_style, 570, 26, 240, 44)
    DrawIOBuilder.add_cell(pkg5, "UC18", "UC-18: Submit Bank Settlement Advice", uc_style, 30, 80, 240, 44)
    DrawIOBuilder.add_cell(pkg5, "UC19", "UC-19: Dual-Auth Verify &amp; Close Loan", uc_style, 300, 80, 240, 44)
    DrawIOBuilder.add_cell(pkg5, "UC20", "UC-20: 3-Step Match &amp; Auto-Disburse Vouchers", uc_style, 570, 80, 260, 44)

    # Pkg 6
    pkg6 = DrawIOBuilder.add_cell(fin_domain, "Pkg6", "6. Identity, Catalogs & Audit Governance", pkg_style, 20, 275, 1060, 180)
    DrawIOBuilder.add_cell(pkg6, "UC21", "UC-21: Self-Register Account &amp; Setup 2FA", uc_style, 30, 26, 240, 44)
    DrawIOBuilder.add_cell(pkg6, "UC22", "UC-22: Approve User &amp; Assign RBAC Role", uc_style, 300, 26, 240, 44)
    DrawIOBuilder.add_cell(pkg6, "UC23", "UC-23: Maintain Master Entity Catalogs", uc_style, 570, 26, 240, 44)
    DrawIOBuilder.add_cell(pkg6, "UC24", "UC-24: Query HTC Copilot ORM Assistant", uc_style, 160, 80, 240, 44)
    DrawIOBuilder.add_cell(pkg6, "UC25", "UC-25: Inspect Append-Only Audit Trail", uc_style, 440, 80, 240, 44)

    # Right Actors
    DrawIOBuilder.add_cell(root, "Inv", "🧾 Invoicing Specialist<br/><font style='font-size:9.5px;font-weight:normal;'>(Role: invoicing)</font>", actor_style, 1370, 560, 90, 110)
    DrawIOBuilder.add_cell(root, "Fin", "💳 Finance Specialist<br/><font style='font-size:9.5px;font-weight:normal;'>(Role: finance)</font>", actor_style, 1370, 700, 90, 110)
    DrawIOBuilder.add_cell(root, "Admin", "🛡️ System Administrator<br/><font style='font-size:9.5px;font-weight:normal;'>(Role: administrator)</font>", actor_style, 1370, 850, 90, 110)

    # Connectors
    actor_edge = "edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;strokeColor=#0284c7;strokeWidth=1.5;fontSize=10;"
    inc_edge = "edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;dashed=1;strokeColor=#64748b;strokeWidth=1.5;fontSize=10;fontColor=#475569;labelBackgroundColor=#ffffff;"

    # Left Actor Links
    DrawIOBuilder.add_edge(root, "uc_e1", "", "OpsStaff", "UC1", actor_edge)
    DrawIOBuilder.add_edge(root, "uc_e2", "", "OpsStaff", "UC3", actor_edge)
    DrawIOBuilder.add_edge(root, "uc_e3", "", "OpsStaff", "UC4", actor_edge)
    DrawIOBuilder.add_edge(root, "uc_e4", "", "OpsStaff", "UC8", actor_edge)

    DrawIOBuilder.add_edge(root, "uc_e5", "", "OpsMgr", "UC2", actor_edge)
    DrawIOBuilder.add_edge(root, "uc_e6", "", "OpsMgr", "UC7", actor_edge)
    DrawIOBuilder.add_edge(root, "uc_e7", "", "OpsMgr", "UC10", actor_edge)
    DrawIOBuilder.add_edge(root, "uc_e8", "", "OpsMgr", "UC11", actor_edge)

    # Internal Includes
    DrawIOBuilder.add_edge(root, "uc_i1", "«include»", "UC4", "UC5", inc_edge)
    DrawIOBuilder.add_edge(root, "uc_i2", "«include»", "UC4", "UC6", inc_edge)
    DrawIOBuilder.add_edge(root, "uc_i3", "«extend» (>1.0%)", "UC6", "UC7", inc_edge)
    DrawIOBuilder.add_edge(root, "uc_i4", "«include»", "UC8", "UC9", inc_edge)
    DrawIOBuilder.add_edge(root, "uc_i5", "OCR API", "UC9", "Textract", actor_edge)
    DrawIOBuilder.add_edge(root, "uc_i6", "«include»", "UC9", "UC10", inc_edge)
    DrawIOBuilder.add_edge(root, "uc_i7", "«include»", "UC12", "UC13", inc_edge)
    DrawIOBuilder.add_edge(root, "uc_i8", "«include»", "UC15", "UC16", inc_edge)
    DrawIOBuilder.add_edge(root, "uc_i9", "«include»", "UC15", "UC17", inc_edge)
    DrawIOBuilder.add_edge(root, "uc_i10", "«include»", "UC18", "UC19", inc_edge)

    # Right Actor Links
    DrawIOBuilder.add_edge(root, "uc_r1", "", "UC12", "Inv", actor_edge)
    DrawIOBuilder.add_edge(root, "uc_r2", "", "UC13", "Inv", actor_edge)
    DrawIOBuilder.add_edge(root, "uc_r3", "", "UC14", "Inv", actor_edge)

    DrawIOBuilder.add_edge(root, "uc_r4", "", "UC15", "Fin", actor_edge)
    DrawIOBuilder.add_edge(root, "uc_r5", "", "UC16", "Fin", actor_edge)
    DrawIOBuilder.add_edge(root, "uc_r6", "", "UC17", "Fin", actor_edge)
    DrawIOBuilder.add_edge(root, "uc_r7", "", "UC18", "Fin", actor_edge)
    DrawIOBuilder.add_edge(root, "uc_r8", "", "UC19", "Fin", actor_edge)
    DrawIOBuilder.add_edge(root, "uc_r9", "", "UC20", "Fin", actor_edge)

    DrawIOBuilder.add_edge(root, "uc_r10", "", "UC21", "Admin", actor_edge)
    DrawIOBuilder.add_edge(root, "uc_r11", "", "UC22", "Admin", actor_edge)
    DrawIOBuilder.add_edge(root, "uc_r12", "", "UC23", "Admin", actor_edge)
    DrawIOBuilder.add_edge(root, "uc_r13", "", "UC24", "Admin", actor_edge)
    DrawIOBuilder.add_edge(root, "uc_r14", "", "UC25", "Admin", actor_edge)


def generate_all():
    print("Generating comprehensive Draw.io XML files...")

    # 1. Unified multi-tab file
    unified = DrawIOBuilder(page_width=1800, page_height=1400)
    build_erd_diagram(unified)
    build_dfd0_diagram(unified)
    build_dfd1_diagram(unified)
    build_dfd2_diagram(unified)
    build_use_case_diagram(unified)

    unified_xml = unified.to_xml_string()
    unified_file = OUTPUT_DIR / "htc_architecture_diagrams.drawio"
    unified_file.write_text(unified_xml, encoding="utf-8")
    print(f"Generated unified Draw.io notebook: {unified_file.name} ({len(unified_xml) // 1024} KB)")

    if ARTIFACT_DIR.exists():
        (ARTIFACT_DIR / unified_file.name).write_text(unified_xml, encoding="utf-8")

    # 2. Individual files
    configs = [
        ("01_entity_relationship_diagram_erd.drawio", build_erd_diagram),
        ("02_dfd_level0_context_diagram.drawio", build_dfd0_diagram),
        ("03_dfd_level1_process_decomposition.drawio", build_dfd1_diagram),
        ("04_dfd_level2_multi_batch_delivery.drawio", build_dfd2_diagram),
        ("05_use_case_diagram.drawio", build_use_case_diagram)
    ]

    for filename, builder_fn in configs:
        b = DrawIOBuilder(page_width=1800, page_height=1400)
        builder_fn(b)
        xml_content = b.to_xml_string()
        out_path = OUTPUT_DIR / filename
        out_path.write_text(xml_content, encoding="utf-8")
        
        # Also save as .xml extension for direct XML copy/import
        xml_path = OUTPUT_DIR / filename.replace(".drawio", ".xml")
        xml_path.write_text(xml_content, encoding="utf-8")

        print(f"  -> Generated {out_path.name} & {xml_path.name}")
        if ARTIFACT_DIR.exists():
            (ARTIFACT_DIR / out_path.name).write_text(xml_content, encoding="utf-8")
            (ARTIFACT_DIR / xml_path.name).write_text(xml_content, encoding="utf-8")

    print("All Draw.io XML files generated successfully!")

if __name__ == "__main__":
    generate_all()
