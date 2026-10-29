import os
import re
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE_DIR = Path(__file__).resolve().parent.parent
DOCS_FILE = BASE_DIR / "docs" / "SYSTEM_ARCHITECTURE_DIAGRAMS_2026.md"
OUTPUT_DIR = BASE_DIR / "docs" / "diagrams"
ARTIFACT_DIR = Path(r"C:\Users\Gigabyte\.gemini\antigravity-ide\brain\473451ac-9352-4fab-b704-595612e0f03b")

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
if ARTIFACT_DIR.exists():
    (ARTIFACT_DIR / "diagrams").mkdir(parents=True, exist_ok=True)

def extract_mermaid_blocks(md_path):
    content = md_path.read_text(encoding="utf-8")
    pattern = r"```mermaid\s*\n(.*?)\n```"
    matches = re.findall(pattern, content, re.DOTALL)
    return matches

diagram_metadata = [
    {
        "id": "01_entity_relationship_diagram_erd",
        "title": "HTC Core — Entity-Relationship Diagram (ERD)",
        "subtitle": "Complete relational schema mapping across Identity, Master Data, Operations, MRO, and Finance",
        "card_width": "2200px"
    },
    {
        "id": "02_dfd_level0_context_diagram",
        "title": "HTC Core — Level 0 Data Flow Diagram (Context Diagram)",
        "subtitle": "System Boundary, Authenticated Staff Roles, Cloud AI Service & Offline Counterparties",
        "card_width": "1600px"
    },
    {
        "id": "03_dfd_level1_process_decomposition",
        "title": "HTC Core — Level 1 Data Flow Diagram (Process Decomposition)",
        "subtitle": "Decomposition across 10 operational engines and 8 relational data stores",
        "card_width": "1400px"
    },
    {
        "id": "04_dfd_level2_multi_batch_delivery",
        "title": "HTC Core — Level 2 Data Flow Diagram (Multi-Batch Logistics Engine)",
        "subtitle": "Process 5.0: Over-delivery validation, dual-mode freight economics, and auto-voucher sync",
        "card_width": "1400px"
    },
    {
        "id": "05_use_case_diagram",
        "title": "HTC Core — Use Case Diagram & Actor Matrix",
        "subtitle": "Functional packages mapped across internal staff roles and AWS Textract OCR",
        "card_width": "2200px"
    }
]

def render_all():
    blocks = extract_mermaid_blocks(DOCS_FILE)
    print(f"Extracted {len(blocks)} diagrams from documentation.")

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(
            viewport={"width": 2600, "height": 2000},
            device_scale_factor=2.0
        )
        page = context.new_page()

        for idx, (meta, code) in enumerate(zip(diagram_metadata, blocks)):
            name = meta["id"]
            title = meta["title"]
            subtitle = meta["subtitle"]
            card_width = meta.get("card_width", "1800px")
            print(f"Rendering [{idx+1}/{len(diagram_metadata)}] {name}...")

            render_html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>{title}</title>
    <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
    <style>
        body {{
            margin: 0;
            padding: 30px;
            background: #ffffff;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            display: flex;
            justify-content: center;
        }}
        #card {{
            background: #ffffff;
            padding: 28px 36px;
            border-radius: 10px;
            border: 1px solid #cbd5e1;
            box-shadow: 0 4px 20px rgba(0,0,0,0.05);
            display: inline-block;
            width: {card_width};
            max-width: 96vw;
        }}
        .header {{
            margin-bottom: 20px;
            border-bottom: 2px solid #0284c7;
            padding-bottom: 10px;
        }}
        .header h1 {{
            margin: 0 0 4px 0;
            font-size: 20px;
            color: #0f172a;
            font-weight: 700;
        }}
        .header p {{
            margin: 0;
            font-size: 13px;
            color: #64748b;
        }}
        #chart-target {{
            display: flex;
            justify-content: center;
            overflow: visible;
        }}
        svg {{
            max-width: 100% !important;
            height: auto !important;
        }}
    </style>
</head>
<body>
    <div id="card">
        <div class="header">
            <h1>{title}</h1>
            <p>{subtitle} • HTC Core v2.3.0</p>
        </div>
        <div id="chart-target"></div>
    </div>
    <script>
        const diagramCode = {repr(code.strip())};
        mermaid.initialize({{
            startOnLoad: false,
            theme: 'default',
            securityLevel: 'loose',
            fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif',
            er: {{
                useMaxWidth: false,
                entityPadding: 15
            }}
        }});
        mermaid.render('generated-svg', diagramCode).then(result => {{
            document.getElementById('chart-target').innerHTML = result.svg;
            window.__MERMAID_DONE__ = true;
        }}).catch(err => {{
            console.error(err);
            document.getElementById('chart-target').innerHTML = '<div style="color:red;padding:20px;">' + err.message + '</div>';
            window.__MERMAID_DONE__ = true;
        }});
    </script>
</body>
</html>"""

            temp_path = OUTPUT_DIR / f"{name}_temp.html"
            temp_path.write_text(render_html, encoding="utf-8")

            page.goto(f"file:///{temp_path.as_posix()}", wait_until="networkidle")
            page.wait_for_function("window.__MERMAID_DONE__ === true", timeout=20000)
            time.sleep(1.0)

            card = page.locator("#card")
            png_file = OUTPUT_DIR / f"{name}.png"
            svg_file = OUTPUT_DIR / f"{name}.svg"

            card.screenshot(path=str(png_file))

            # Extract SVG
            svg_html = page.inner_html("#chart-target")
            svg_file.write_text(svg_html, encoding="utf-8")

            print(f"  -> Successfully generated {png_file.name} ({png_file.stat().st_size // 1024} KB)")

            # Copy to artifact dir
            if ARTIFACT_DIR.exists():
                (ARTIFACT_DIR / "diagrams" / png_file.name).write_bytes(png_file.read_bytes())
                (ARTIFACT_DIR / "diagrams" / svg_file.name).write_text(svg_file.read_text(encoding="utf-8"), encoding="utf-8")

            if temp_path.exists():
                temp_path.unlink()

        # Next: Render Beautiful Database Schema Tables Image
        print("Rendering [6/6] Database Schema Tables visual sheet...")
        render_schema_tables(page)

        browser.close()

def render_schema_tables(page):
    schema_html = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>HTC Core Database Schema Tables</title>
    <style>
        body {
            margin: 0;
            padding: 40px;
            background: #f8fafc;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            color: #0f172a;
        }
        .container {
            max-width: 1800px;
            margin: 0 auto;
            background: #ffffff;
            padding: 40px;
            border-radius: 12px;
            box-shadow: 0 4px 25px rgba(0,0,0,0.07);
            border: 1px solid #e2e8f0;
        }
        .header {
            border-bottom: 3px solid #0284c7;
            padding-bottom: 16px;
            margin-bottom: 30px;
        }
        .header h1 {
            font-size: 26px;
            margin: 0 0 6px 0;
            color: #0f172a;
        }
        .header p {
            margin: 0;
            color: #64748b;
            font-size: 14px;
        }
        .grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 28px;
        }
        .table-card {
            border: 1px solid #cbd5e1;
            border-radius: 8px;
            overflow: hidden;
            background: #ffffff;
        }
        .table-card-header {
            background: #0f172a;
            color: #f8fafc;
            padding: 10px 16px;
            font-size: 14px;
            font-weight: 600;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .table-card-header .app-badge {
            font-size: 11px;
            background: #0284c7;
            padding: 2px 8px;
            border-radius: 12px;
            text-transform: uppercase;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            font-size: 11.5px;
        }
        th {
            background: #f1f5f9;
            text-align: left;
            padding: 8px 10px;
            color: #475569;
            border-bottom: 1px solid #cbd5e1;
            font-weight: 600;
        }
        td {
            padding: 7px 10px;
            border-bottom: 1px solid #f1f5f9;
            color: #334155;
        }
        tr:nth-child(even) {
            background: #fafafa;
        }
        .col-name {
            font-weight: 600;
            color: #0f172a;
            font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
        }
        .col-type {
            color: #0369a1;
            font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
            font-size: 10.5px;
        }
        .badge {
            display: inline-block;
            font-size: 9.5px;
            padding: 1px 5px;
            border-radius: 4px;
            font-weight: 600;
            font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
        }
        .badge-pk { background: #fee2e2; color: #991b1b; border: 1px solid #fca5a5; }
        .badge-fk { background: #e0e7ff; color: #3730a3; border: 1px solid #c7d2fe; }
        .badge-uk { background: #fef3c7; color: #92400e; border: 1px solid #fde68a; }
        .badge-req { background: #f1f5f9; color: #475569; }
    </style>
</head>
<body>
    <div class="container" id="schema-container">
        <div class="header">
            <h1>HTC Core — Relational Database Schema Data Dictionary</h1>
            <p>PostgreSQL 16 Relational Tables, Data Types, Primary/Foreign Keys, and Structural Constraints</p>
        </div>
        <div class="grid">
            <!-- Table 1: PurchaseOrder -->
            <div class="table-card">
                <div class="table-card-header">
                    <span>operations_purchaseorder (Parent PO Contract)</span>
                    <span class="app-badge">operations</span>
                </div>
                <table>
                    <thead><tr><th>Column</th><th>Type</th><th>Key/Constraint</th><th>Description</th></tr></thead>
                    <tbody>
                        <tr><td class="col-name">id</td><td class="col-type">BIGSERIAL</td><td><span class="badge badge-pk">PK</span></td><td>Auto Primary Key</td></tr>
                        <tr><td class="col-name">cluster_id</td><td class="col-type">UUID</td><td><span class="badge badge-fk">FK</span> <span class="badge badge-uk">1:1</span></td><td>Bound Transaction Cluster</td></tr>
                        <tr><td class="col-name">po_reference_number</td><td class="col-type">VARCHAR(50)</td><td><span class="badge badge-uk">UNIQUE</span></td><td>PO Code (e.g. PO-ADI-2026-001)</td></tr>
                        <tr><td class="col-name">customer_id</td><td class="col-type">BIGINT</td><td><span class="badge badge-fk">FK</span></td><td>Buyer Client FK</td></tr>
                        <tr><td class="col-name">total_contracted_mt</td><td class="col-type">NUMERIC(14,3)</td><td><span class="badge badge-req">NOT NULL</span></td><td>Contract Target Volume (MT)</td></tr>
                        <tr><td class="col-name">unit_price</td><td class="col-type">NUMERIC(12,2)</td><td><span class="badge badge-req">NOT NULL</span></td><td>Mill Sourcing Purchase Price (₱/MT)</td></tr>
                        <tr><td class="col-name">selling_price</td><td class="col-type">NUMERIC(12,2)</td><td><span class="badge badge-req">NOT NULL</span></td><td>Customer Billed Price (₱/MT)</td></tr>
                        <tr><td class="col-name">po_status</td><td class="col-type">VARCHAR(30)</td><td>—</td><td>Open | Partially Fulfilled | Completed</td></tr>
                        <tr><td class="col-name">brix_level</td><td class="col-type">NUMERIC(5,2)</td><td>—</td><td>Target Contract Brix Quality %</td></tr>
                    </tbody>
                </table>
            </div>

            <!-- Table 2: DeliveryLedger -->
            <div class="table-card">
                <div class="table-card-header">
                    <span>operations_deliveryledger (Multi-Batch Logistics)</span>
                    <span class="app-badge">operations</span>
                </div>
                <table>
                    <thead><tr><th>Column</th><th>Type</th><th>Key/Constraint</th><th>Description</th></tr></thead>
                    <tbody>
                        <tr><td class="col-name">delivery_id</td><td class="col-type">UUID</td><td><span class="badge badge-pk">PK</span></td><td>UUIDv4 Primary Key</td></tr>
                        <tr><td class="col-name">purchase_order_id</td><td class="col-type">BIGINT</td><td><span class="badge badge-fk">FK</span></td><td>Parent Purchase Order (CASCADE)</td></tr>
                        <tr><td class="col-name">supplier_id</td><td class="col-type">BIGINT</td><td><span class="badge badge-fk">FK</span></td><td>Sourcing Sugar Mill (PROTECT)</td></tr>
                        <tr><td class="col-name">delivered_mt</td><td class="col-type">NUMERIC(14,3)</td><td><span class="badge badge-req">NOT NULL</span></td><td>Batch MT (Validated &le; remaining_mt)</td></tr>
                        <tr><td class="col-name">receiving_location</td><td class="col-type">VARCHAR(200)</td><td><span class="badge badge-req">NOT NULL</span></td><td>Drop-off Customer Plant Site</td></tr>
                        <tr><td class="col-name">trucking_partner_id</td><td class="col-type">BIGINT</td><td><span class="badge badge-fk">FK</span></td><td>Land Transport Logistics Partner</td></tr>
                        <tr><td class="col-name">trucking_rate_per_mt</td><td class="col-type">NUMERIC(12,2)</td><td>—</td><td>Land Haulage Rate (₱/MT)</td></tr>
                        <tr><td class="col-name">barge_partner_id</td><td class="col-type">BIGINT</td><td><span class="badge badge-fk">FK</span></td><td>Marine Transport Logistics Partner</td></tr>
                        <tr><td class="col-name">barge_rate_per_mt</td><td class="col-type">NUMERIC(12,2)</td><td>—</td><td>Marine Barging Rate (₱/MT)</td></tr>
                        <tr><td class="col-name">mro_permit_id</td><td class="col-type">BIGINT</td><td><span class="badge badge-fk">FK</span></td><td>Covering Molasses Release Order</td></tr>
                    </tbody>
                </table>
            </div>

            <!-- Table 3: CapitalLoan -->
            <div class="table-card">
                <div class="table-card-header">
                    <span>finance_capitalloan (Financing & Accruals)</span>
                    <span class="app-badge">finance</span>
                </div>
                <table>
                    <thead><tr><th>Column</th><th>Type</th><th>Key/Constraint</th><th>Description</th></tr></thead>
                    <tbody>
                        <tr><td class="col-name">id</td><td class="col-type">BIGSERIAL</td><td><span class="badge badge-pk">PK</span></td><td>Auto Primary Key</td></tr>
                        <tr><td class="col-name">cluster_id</td><td class="col-type">UUID</td><td><span class="badge badge-fk">FK</span></td><td>Funded Transaction Cluster</td></tr>
                        <tr><td class="col-name">bank_name</td><td class="col-type">VARCHAR(120)</td><td><span class="badge badge-req">NOT NULL</span></td><td>Commercial Lending Bank</td></tr>
                        <tr><td class="col-name">principal</td><td class="col-type">NUMERIC(14,2)</td><td><span class="badge badge-req">NOT NULL</span></td><td>Financed Loan Principal Balance</td></tr>
                        <tr><td class="col-name">interest_rate_annual</td><td class="col-type">NUMERIC(6,4)</td><td><span class="badge badge-req">NOT NULL</span></td><td>Annual Interest Rate (e.g. 12.5000%)</td></tr>
                        <tr><td class="col-name">start_date / due_date</td><td class="col-type">DATE</td><td><span class="badge badge-req">NOT NULL</span></td><td>Facility Tenure Window</td></tr>
                        <tr><td class="col-name">status</td><td class="col-type">VARCHAR(30)</td><td>—</td><td>pending_creation | active | closed</td></tr>
                        <tr><td class="col-name">settlement_receipt_number</td><td class="col-type">VARCHAR(100)</td><td>—</td><td>Official Bank Clearance Advice #</td></tr>
                        <tr><td class="col-name">verified_by_id</td><td class="col-type">BIGINT</td><td><span class="badge badge-fk">FK</span></td><td>Dual-Auth Verifying Manager</td></tr>
                    </tbody>
                </table>
            </div>

            <!-- Table 4: Invoice -->
            <div class="table-card">
                <div class="table-card-header">
                    <span>finance_invoice (Suggestive Billing)</span>
                    <span class="app-badge">finance</span>
                </div>
                <table>
                    <thead><tr><th>Column</th><th>Type</th><th>Key/Constraint</th><th>Description</th></tr></thead>
                    <tbody>
                        <tr><td class="col-name">id</td><td class="col-type">BIGSERIAL</td><td><span class="badge badge-pk">PK</span></td><td>Auto Primary Key</td></tr>
                        <tr><td class="col-name">cluster_id</td><td class="col-type">UUID</td><td><span class="badge badge-fk">FK</span></td><td>Billed Transaction Cluster</td></tr>
                        <tr><td class="col-name">invoice_number</td><td class="col-type">VARCHAR(50)</td><td><span class="badge badge-uk">UNIQUE</span></td><td>Official Sales Invoice Number</td></tr>
                        <tr><td class="col-name">amount</td><td class="col-type">NUMERIC(14,2)</td><td><span class="badge badge-req">NOT NULL</span></td><td>Gross Invoiced Total (₱)</td></tr>
                        <tr><td class="col-name">tax_rate_vat</td><td class="col-type">NUMERIC(5,2)</td><td>Default 12.00</td><td>Value Added Tax (12%)</td></tr>
                        <tr><td class="col-name">tax_rate_ewt</td><td class="col-type">NUMERIC(5,2)</td><td>Default 1.00</td><td>Expanded Withholding Tax (1%)</td></tr>
                        <tr><td class="col-name">status</td><td class="col-type">VARCHAR(20)</td><td>—</td><td>draft | issued | paid | returned</td></tr>
                        <tr><td class="col-name">logistics_fee</td><td class="col-type">NUMERIC(14,2)</td><td>—</td><td>Billable Delivery Freight Portion</td></tr>
                        <tr><td class="col-name">is_incremental</td><td class="col-type">BOOLEAN</td><td>Default False</td><td>Milestone / Progress Billing Indicator</td></tr>
                    </tbody>
                </table>
            </div>
        </div>
    </div>
</body>
</html>"""

    table_temp = OUTPUT_DIR / "schema_table_temp.html"
    table_temp.write_text(schema_html, encoding="utf-8")

    page.goto(f"file:///{table_temp.as_posix()}", wait_until="networkidle")
    time.sleep(0.5)

    container = page.locator("#schema-container")
    table_png = OUTPUT_DIR / "06_database_schema_summary_tables.png"
    container.screenshot(path=str(table_png))
    print(f"  -> Generated: {table_png.name} ({table_png.stat().st_size // 1024} KB)")

    if ARTIFACT_DIR.exists():
        (ARTIFACT_DIR / "diagrams" / table_png.name).write_bytes(table_png.read_bytes())

    if table_temp.exists():
        table_temp.unlink()

if __name__ == "__main__":
    render_all()
