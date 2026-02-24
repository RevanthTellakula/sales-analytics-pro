"""
Sales Analytics Web App
========================
app.py — Flask backend with:
  • REST API for orders, KPIs, chart data
  • Auto data-cleaning pipeline
  • Auto insight generation after every insert/import
  • CSV bulk import

Usage:
    python app.py
Then open: http://localhost:5000
"""

import sqlite3, csv, io, os, re, json
from datetime import date, datetime
from flask import Flask, request, jsonify, render_template, abort

app = Flask(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "sales.db")

# ── DB helpers ────────────────────────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def query(sql, params=()):
    with get_db() as conn:
        cur = conn.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]


def execute(sql, params=()):
    with get_db() as conn:
        cur = conn.execute(sql, params)
        conn.commit()
        return cur.lastrowid


# ── Data cleaning pipeline ────────────────────────────────────────────────────

def clean_record(raw: dict, check_duplicates: bool = True) -> tuple[dict, list[str]]:
    """
    Cleans and validates a single incoming order record.
    Returns (cleaned_dict, list_of_warnings).
    """
    warnings = []
    r = dict(raw)

    # ── Field mapping / aliasing ──────────────────────────────────────
    # If standard keys are missing, look for common aliases
    aliases = {
        "Order_ID":      ["Order ID", "ID", "OrderID", "Order #"],
        "Order_Date":    ["Date", "Order Date", "Timestamp", "Created At"],
        "Customer_Name": ["Customer", "Name", "Buyer", "Client"],
        "Region":        ["Location", "Territory", "State", "Country"],
        "Product":       ["Item", "Product Name", "SKU", "Description"],
        "Category":      ["Cat", "Department", "Type", "Category Name"],
        "Quantity":      ["Qty", "Units", "Amount Sold", "Count"],
        "Unit_Price":    ["Price", "Rate", "Sales Price", "Retail Price"],
        "Cost_Price":    ["Cost", "COGS", "Purchase Price", "Buying Price"],
        "Discount":      ["Disc", "Promo", "Markdown", "Discount %"],
    }
    for target, alt_list in aliases.items():
        if not r.get(target):
            # Check for any of the aliases in the raw keys
            for alt in alt_list:
                # Try exact, lowercase, or space-to-underscore match
                for raw_k in r.keys():
                    if raw_k.strip().lower() == alt.lower().replace("_", " "):
                        r[target] = r[raw_k]
                        break
                if r.get(target): break

    # ── String normalisation ──────────────────────────────────────────

    # ── String normalisation ──────────────────────────────────────────
    for fld in ("Customer_Name", "Region", "Product", "Category", "Customer_ID"):
        if fld in r and r[fld]:
            original = r[fld]
            r[fld] = r[fld].strip().title()
            if r[fld] != original.strip():
                warnings.append(f"'{fld}' normalised to title-case: \"{r[fld]}\"")

    # ── Region whitelist ──────────────────────────────────────────────
    valid_regions = {"North", "South", "East", "West"}
    if r.get("Region") and r["Region"] not in valid_regions:
        # fuzzy-match (e.g. "NORTH " → "North")
        matched = next((v for v in valid_regions
                        if v.lower() in r["Region"].lower()), None)
        if matched:
            warnings.append(f"Region \"{r['Region']}\" corrected to \"{matched}\"")
            r["Region"] = matched
        else:
            warnings.append(f"Unknown region \"{r['Region']}\" kept as-is")

    # ── Numeric coercion ──────────────────────────────────────────────
    def to_num(val, default=0.0):
        if val is None or val == "": return default
        try: return float(str(val).replace(",", "").replace("$", "").replace("%", ""))
        except: return default

    r["Quantity"]   = int(to_num(r.get("Quantity"), 1))
    r["Unit_Price"] = to_num(r.get("Unit_Price"), 0.0)
    r["Cost_Price"] = to_num(r.get("Cost_Price"), 0.0)
    
    disc_raw = to_num(r.get("Discount"), 0.0)
    # If someone types "15" for 15%, convert to 0.15
    r["Discount"]   = disc_raw / 100.0 if disc_raw > 1 else disc_raw

    # ── Range validation ──────────────────────────────────────────────
    if r["Quantity"] <= 0:
        warnings.append("Quantity was ≤0, reset to 1")
        r["Quantity"] = 1
    if r["Unit_Price"] <= 0:
        warnings.append("Unit Price was missing/invalid, set to $100.00")
        r["Unit_Price"] = 100.0
    if r["Cost_Price"] <= 0:
        warnings.append("Cost Price was missing/invalid, set to $60.00")
        r["Cost_Price"] = 60.0
    if r["Discount"] < 0:
        warnings.append("Negative discount set to 0")
        r["Discount"] = 0.0
    if r["Discount"] > 0.80:
        warnings.append(f"Discount capped at 80% (was {r['Discount']*100:.0f}%)")
        r["Discount"] = 0.80
    if r["Cost_Price"] >= r["Unit_Price"]:
        warnings.append("Cost Price ≥ Unit Price — this order will have ≤0 profit")

    # ── Server-side revenue / profit computation ──────────────────────
    r["Sales_Amount"] = round(r["Quantity"] * r["Unit_Price"] * (1 - r["Discount"]), 2)
    r["Profit"]       = round(r["Sales_Amount"] - r["Quantity"] * r["Cost_Price"], 2)

    # ── Date normalisation ────────────────────────────────────────────
    date_raw = str(r.get("Order_Date", date.today().isoformat()))
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y"):
        try:
            r["Order_Date"] = datetime.strptime(date_raw, fmt).date().isoformat()
            break
        except ValueError:
            continue
    else:
        warnings.append(f"Could not parse date \"{date_raw}\", using today")
        r["Order_Date"] = date.today().isoformat()

    # ── Duplicate check ───────────────────────────────────────────────
    if check_duplicates and r.get("Order_ID"):
        existing = query("SELECT id FROM sales WHERE Order_ID=?", (r["Order_ID"],))
        if existing:
            raise ValueError(f"Duplicate Order_ID: {r['Order_ID']}")

    # ── Auto-generate Order_ID if missing ─────────────────────────────
    if not r.get("Order_ID"):
        count = query("SELECT COUNT(*) c FROM sales")[0]["c"] + 1
        r["Order_ID"] = f"ORD-{str(count).zfill(6)}"

    # ── Customer_ID from name if missing ──────────────────────────────
    if not r.get("Customer_ID"):
        slug = re.sub(r"[^A-Z0-9]", "", r.get("Customer_Name", "UNK").upper())[:6]
        r["Customer_ID"] = f"C-{slug}"

    return r, warnings


# ── Insight engine ────────────────────────────────────────────────────────────

def generate_insights(new_record: dict = None) -> list[str]:
    """
    Generates 5–7 natural-language insight bullets from live SQL data.
    If new_record is given, adds record-specific insights.
    """
    insights = []

    # 1. Total summary
    kpi = query("""
        SELECT
          ROUND(SUM(Sales_Amount),2) rev,
          ROUND(SUM(Profit),2)       pft,
          COUNT(DISTINCT Order_ID)   orders,
          COUNT(DISTINCT Customer_ID) custs
        FROM sales
    """)[0]
    insights.append(
        f"📊 Total portfolio: **${kpi['rev']:,.0f}** revenue across **{kpi['orders']:,}** orders "
        f"from **{kpi['custs']:,}** customers."
    )

    # 2. Best performing region
    best_region = query("""
        SELECT Region, ROUND(SUM(Sales_Amount),2) rev
        FROM sales GROUP BY Region ORDER BY rev DESC LIMIT 1
    """)
    if best_region:
        insights.append(
            f"🏆 Top region is **{best_region[0]['Region']}** with **${best_region[0]['rev']:,.0f}** in total revenue."
        )

    # 3. South region warning
    south_repeat = query("""
        WITH co AS (SELECT Customer_ID, COUNT(DISTINCT Order_ID) c FROM sales WHERE Region='South' GROUP BY Customer_ID)
        SELECT ROUND(SUM(CASE WHEN c>=2 THEN 1 ELSE 0 END)*100.0/COUNT(*),1) rate FROM co
    """)
    if south_repeat and south_repeat[0]["rate"] is not None:
        rate = south_repeat[0]["rate"]
        if rate < 60:
            insights.append(
                f"⚠️ South region repeat customer rate is **{rate}%** — below the 60% benchmark. "
                f"Consider a re-engagement campaign for lapsed South buyers."
            )

    # 4. Top product
    top_prod = query("""
        SELECT Product, ROUND(SUM(Sales_Amount),2) rev FROM sales
        GROUP BY Product ORDER BY rev DESC LIMIT 1
    """)
    if top_prod:
        insights.append(
            f"📦 Best-selling product: **{top_prod[0]['Product']}** — **${top_prod[0]['rev']:,.0f}** revenue to date."
        )

    # 5. Discount impact
    disc = query("""
        SELECT
          ROUND(AVG(CASE WHEN Discount>0.15 THEN Profit*100.0/Sales_Amount END),1) high_disc_margin,
          ROUND(AVG(CASE WHEN Discount=0    THEN Profit*100.0/Sales_Amount END),1) no_disc_margin
        FROM sales WHERE Sales_Amount > 0
    """)[0]
    if disc["high_disc_margin"] and disc["no_disc_margin"]:
        diff = round(disc["no_disc_margin"] - disc["high_disc_margin"], 1)
        insights.append(
            f"🔍 Orders with >15% discount average **{disc['high_disc_margin']}%** margin vs "
            f"**{disc['no_disc_margin']}%** for full-price orders — a **{diff}pp** margin compression."
        )

    # 6. Monthly growth
    monthly = query("""
        SELECT STRFTIME('%Y-%m', Order_Date) mo, ROUND(SUM(Sales_Amount),2) rev
        FROM sales GROUP BY mo ORDER BY mo DESC LIMIT 2
    """)
    if len(monthly) == 2:
        curr, prev = monthly[0]["rev"], monthly[1]["rev"]
        pct = round((curr - prev) / prev * 100, 1) if prev else 0
        arrow = "📈" if pct >= 0 else "📉"
        insights.append(
            f"{arrow} Most recent month (**{monthly[0]['mo']}**) revenue is **${curr:,.0f}** — "
            f"{'up' if pct >= 0 else 'down'} **{abs(pct)}%** vs prior month."
        )

    # 7. New-record-specific insight
    if new_record:
        margin = round(new_record["Profit"] / new_record["Sales_Amount"] * 100, 1) \
                 if new_record.get("Sales_Amount") else 0
        insights.append(
            f"✅ New order **{new_record['Order_ID']}** added — "
            f"**${new_record['Sales_Amount']:,.2f}** revenue, "
            f"**${new_record['Profit']:,.2f}** profit (**{margin}%** margin)."
        )

    return insights


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/kpis")
def api_kpis():
    row = query("""
        SELECT
          ROUND(SUM(Sales_Amount),2)                             AS total_revenue,
          ROUND(SUM(Profit),2)                                   AS total_profit,
          ROUND(SUM(Profit)*100.0/SUM(Sales_Amount),2)           AS profit_margin,
          ROUND(SUM(Sales_Amount)/COUNT(DISTINCT Order_ID),2)    AS aov,
          COUNT(DISTINCT Order_ID)                               AS total_orders,
          COUNT(DISTINCT Customer_ID)                            AS unique_customers
        FROM sales
    """)[0]

    # Repeat customer rate
    repeat = query("""
        WITH co AS (SELECT Customer_ID, COUNT(DISTINCT Order_ID) c FROM sales GROUP BY Customer_ID)
        SELECT ROUND(SUM(CASE WHEN c>=2 THEN 1 ELSE 0 END)*100.0/COUNT(*),1) rate FROM co
    """)[0]

    # Top region
    top_reg = query("""
        SELECT Region FROM sales GROUP BY Region ORDER BY SUM(Sales_Amount) DESC LIMIT 1
    """)

    # YoY
    yoy = query("""
        SELECT STRFTIME('%Y',Order_Date) yr, ROUND(SUM(Sales_Amount),2) rev
        FROM sales GROUP BY yr ORDER BY yr
    """)
    yoy_pct = None
    if len(yoy) >= 2:
        a, b = yoy[-2]["rev"], yoy[-1]["rev"]
        yoy_pct = round((b - a) / a * 100, 1) if a else None

    return jsonify({
        **row,
        "repeat_rate":    repeat["rate"],
        "top_region":     top_reg[0]["Region"] if top_reg else "—",
        "yoy_growth":     yoy_pct,
        "record_count":   row["total_orders"],
    })


@app.route("/api/orders", methods=["GET"])
def api_orders_get():
    rows = query("""
        SELECT id, Order_ID, Order_Date, Customer_Name, Region, Product,
               Category, Quantity, Unit_Price, Cost_Price, Discount,
               Sales_Amount, Profit, created_at
        FROM sales ORDER BY id DESC LIMIT 50
    """)
    return jsonify(rows)


@app.route("/api/orders", methods=["POST"])
def api_orders_post():
    data = request.get_json(force=True)
    try:
        cleaned, warnings = clean_record(data)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    execute("""
        INSERT INTO sales
          (Order_ID,Order_Date,Customer_ID,Customer_Name,Region,Product,Category,
           Quantity,Unit_Price,Cost_Price,Discount,Sales_Amount,Profit)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        cleaned["Order_ID"], cleaned["Order_Date"],
        cleaned["Customer_ID"], cleaned["Customer_Name"],
        cleaned["Region"], cleaned["Product"], cleaned["Category"],
        cleaned["Quantity"], cleaned["Unit_Price"], cleaned["Cost_Price"],
        cleaned["Discount"], cleaned["Sales_Amount"], cleaned["Profit"],
    ))

    insights = generate_insights(cleaned)
    return jsonify({
        "success":  True,
        "order":    cleaned,
        "warnings": warnings,
        "insights": insights,
    }), 201


@app.route("/api/orders/<int:order_id>", methods=["DELETE"])
def api_orders_delete(order_id):
    execute("DELETE FROM sales WHERE id=?", (order_id,))
    return jsonify({"success": True})


@app.route("/api/import", methods=["POST"])
def api_import():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    
    clear_data = request.form.get("clear") == "true"
    f = request.files["file"]
    content = f.read().decode("utf-8-sig")
    reader  = csv.DictReader(io.StringIO(content))

    if clear_data:
        execute("DELETE FROM sales")

    inserted, skipped, warn_log = 0, 0, []
    rows_to_insert = []

    for i, row in enumerate(reader, 1):
        try:
            # check_duplicates=False because we use INSERT OR IGNORE below
            cleaned, warns = clean_record(row, check_duplicates=False)
            rows_to_insert.append((
                cleaned["Order_ID"], cleaned["Order_Date"],
                cleaned["Customer_ID"], cleaned["Customer_Name"],
                cleaned["Region"], cleaned["Product"], cleaned["Category"],
                cleaned["Quantity"], cleaned["Unit_Price"], cleaned["Cost_Price"],
                cleaned["Discount"], cleaned["Sales_Amount"], cleaned["Profit"],
            ))
            if warns and len(warn_log) < 50:
                warn_log.append(f"Row {i}: {'; '.join(warns)}")
            inserted += 1
        except Exception as e:
            skipped += 1
            if len(warn_log) < 50:
                warn_log.append(f"Row {i} skipped — {e}")

    if rows_to_insert:
        with get_db() as conn:
            conn.executemany("""
                INSERT OR IGNORE INTO sales
                  (Order_ID,Order_Date,Customer_ID,Customer_Name,Region,Product,Category,
                   Quantity,Unit_Price,Cost_Price,Discount,Sales_Amount,Profit)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, rows_to_insert)
            conn.commit()

    insights = generate_insights()
    return jsonify({
        "inserted": inserted,
        "skipped":  skipped,
        "warnings": warn_log[:20],
        "insights": insights,
    })


@app.route("/api/insights")
def api_insights():
    return jsonify(generate_insights())


@app.route("/api/chart/monthly")
def chart_monthly():
    rows = query("""
        SELECT STRFTIME('%Y-%m', Order_Date) month,
               ROUND(SUM(Sales_Amount),2)   revenue,
               ROUND(SUM(Profit),2)         profit,
               COUNT(DISTINCT Order_ID)     orders
        FROM sales
        GROUP BY month ORDER BY month
    """)
    return jsonify(rows)


@app.route("/api/chart/products")
def chart_products():
    rows = query("""
        SELECT Product,
               ROUND(SUM(Sales_Amount),2) revenue,
               ROUND(SUM(Profit),2)       profit,
               SUM(Quantity)              units
        FROM sales
        GROUP BY Product
        ORDER BY revenue DESC LIMIT 10
    """)
    return jsonify(rows)


@app.route("/api/chart/regions")
def chart_regions():
    rows = query("""
        SELECT Region,
               ROUND(SUM(Sales_Amount),2)                       revenue,
               ROUND(SUM(Profit),2)                             profit,
               COUNT(DISTINCT Customer_ID)                      customers,
               ROUND(SUM(Profit)*100.0/SUM(Sales_Amount),1)     margin
        FROM sales
        GROUP BY Region ORDER BY revenue DESC
    """)
    return jsonify(rows)


@app.route("/api/chart/categories")
def chart_categories():
    rows = query("""
        SELECT Category,
               ROUND(SUM(Sales_Amount),2) revenue,
               ROUND(SUM(Profit),2)       profit
        FROM sales
        GROUP BY Category ORDER BY revenue DESC
    """)
    return jsonify(rows)


@app.route("/api/chart/top5products")
def chart_top5():
    rows = query("""
        SELECT Product, ROUND(SUM(Sales_Amount),2) revenue
        FROM sales GROUP BY Product ORDER BY revenue DESC LIMIT 5
    """)
    return jsonify(rows)


# ── Bootstrap ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    from init_db import init
    init()
    print("\n🚀  Sales Analytics Web App")
    print("   Open: http://localhost:5000\n")
    app.run(debug=True, port=5000)
