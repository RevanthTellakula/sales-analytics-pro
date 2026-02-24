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

# Normalise keys: lowercase + remove non-alphanumeric (strips _, spaces, -, etc)
def norm(s) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def get_header_mapping(csv_headers: list) -> dict:
    """
    Returns a map of { internal_field: actual_csv_header }.
    Uses fuzzy logic and aliases.
    """
    mapping = {}
    raw_norm = {norm(h): h for h in csv_headers if h}

    aliases = {
        "Order_ID":      ["Order ID", "ID", "OrderID", "Order #", "Transaction", "Trans ID", "Car_id"],
        "Order_Date":    ["Date", "Order Date", "Timestamp", "Created At", "Transaction Date", "Time"],
        "Customer_Name": ["Customer", "Name", "Buyer", "Client", "User Name", "User", "Customer N", "Customer Name"],
        "Region":        ["Location", "Territory", "State", "Country", "Region Name", "Dealer_Region", "Dealer_Region"],
        "Product":       ["Item", "Product Name", "SKU", "Description", "Product", "Model", "Company"],
        "Category":      ["Cat", "Department", "Type", "Category Name", "Product Category", "Body Style"],
        "Quantity":      ["Qty", "Units", "Amount Sold", "Count", "Quantity Purchased"],
        "Unit_Price":    ["Price", "Rate", "Sales Price", "Retail Price", "Revenue", "Purchase Amount", "Amount", "Total", "Price ($)"],
        "Cost_Price":    ["Cost", "COGS", "Purchase Price", "Buying Price"],
        "Discount":      ["Disc", "Promo", "Markdown", "Discount %"],
        "Payment_Method":["Payment", "Method", "Payment Method", "Payment_Method", "Type", "Transmission"],
        "Age":           ["Age", "Customer Age", "Buyer Age"],
        "Gender":        ["Gender", "Sex"],
        "Annual_Income": ["Income", "Annual Income", "Annual Inco"],
    }

    for target, alt_list in aliases.items():
        for alt in [target] + alt_list:
            n_alt = norm(alt)
            if n_alt in raw_norm:
                mapping[target] = raw_norm[n_alt]
                break
    return mapping


def clean_record(raw: dict, check_duplicates: bool = True, next_order_num: int = None, header_mapping: dict = None) -> tuple[dict, list[str]]:
    """
    Cleans and validates a single incoming order record.
    Returns (cleaned_dict, list_of_warnings).
    """
    warnings = []
    
    # ── 1. Alias Mapping ─────────────────────────────────────────────
    internal_data = {}
    
    if header_mapping:
        for target, csv_h in header_mapping.items():
            internal_data[target] = raw.get(csv_h)
    else:
        # Fallback for individual POSTs where mapping isn't pre-computed
        temp_mapping = get_header_mapping(list(raw.keys()))
        for target, csv_h in temp_mapping.items():
            internal_data[target] = raw.get(csv_h)

    # ── 2. Local Variable Cleaning ────────────────────────────────────
    # Strings
    c_name = str(internal_data.get("Customer_Name") or "Unknown Customer").strip().title()
    region = str(internal_data.get("Region") or "Unknown").strip().title()
    cat    = str(internal_data.get("Category") or "Other").strip().title()
    
    # If Product is missing, try to fallback to Category (e.g. if we only have Product_Category)
    prod_val = internal_data.get("Product")
    if not prod_val and cat != "Other":
        prod_val = cat
    prod = str(prod_val or "Unknown Product").strip().title()

    # Region normalization
    valid_regions = {"North", "South", "East", "West"}
    if region not in valid_regions:
        matched = next((v for v in valid_regions if v.lower() in region.lower()), None)
        if matched:
            region = matched
        else:
            warnings.append(f"Region '{region}' is non-standard")

    # Helper for numeric cleaning
    def to_f(val, default_val: float) -> float:
        if val is None or str(val).strip() == "": return float(default_val)
        try:
            s = str(val).replace(",", "").replace("$", "").replace("%", "").strip()
            return float(s)
        except: return float(default_val)

    u_price = to_f(internal_data.get("Unit_Price"), 100.0)
    
    # Smart Cost Price for Car Sales (if missing, assume 70% of price)
    raw_cost = internal_data.get("Cost_Price")
    if raw_cost is None or str(raw_cost).strip() == "":
        c_price = round(float(u_price) * 0.7, 2)
    else:
        c_price = to_f(raw_cost, 60.0)

    qty_f  = to_f(internal_data.get("Quantity"), 1.0)
    disc_f = to_f(internal_data.get("Discount"), 0.0)
    
    # Validation & Logic
    qty = int(qty_f) if qty_f > 0 else 1
    u_price = u_price if u_price > 0 else 100.0
    c_price = c_price if c_price > 0 else 60.0
    
    # Handle discount logic (15 vs 0.15)
    discount = disc_f / 100.0 if disc_f > 1.0 else disc_f
    if discount < 0: discount = 0.0
    if discount > 0.9: discount = 0.9

    # Computed fields
    sales_amt = round(float(qty) * float(u_price) * (1.0 - float(discount)), 2)
    profit    = round(float(sales_amt) - (float(qty) * float(c_price)), 2)

    # Date
    date_str = str(internal_data.get("Order_Date") or "").strip()
    parsed_dt = None
    if date_str:
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%Y/%m/%d"):
            try:
                parsed_dt = datetime.strptime(date_str, fmt).date()
                break
            except: continue
    
    o_date = parsed_dt.isoformat() if parsed_dt else date.today().isoformat()
    if not parsed_dt and date_str:
        warnings.append(f"Date '{date_str}' invalid, used today")

    # Order ID
    o_id = str(internal_data.get("Order_ID") or "").strip()
    if check_duplicates and o_id:
        if query("SELECT 1 FROM sales WHERE Order_ID=?", (o_id,)):
            raise ValueError(f"Duplicate Order_ID: {o_id}")

    if not o_id:
        num = next_order_num if next_order_num is not None else (query("SELECT COUNT(*) c FROM sales")[0]["c"] + 1)
        o_id = f"ORD-{str(num).zfill(6)}"

    # Customer ID (Slug)
    name_clean = re.sub(r"[^A-Z0-9]", "", c_name.upper()) or "CUST"
    c_id = f"C-{name_clean[:6]}"

    # Ecommerce / Car Sales Specifics
    pay_method = str(internal_data.get("Payment_Method") or "Unknown").strip().title()
    age = int(to_f(internal_data.get("Age"), 0))
    gender = str(internal_data.get("Gender") or "Unknown").strip().title()
    income = to_f(internal_data.get("Annual_Income"), 0.0)

    # ── 3. Build the Final Dict ───────────────────────────────────────
    return {
        "Order_ID":      o_id,
        "Order_Date":    o_date,
        "Customer_ID":   c_id,
        "Customer_Name": c_name,
        "Region":        region,
        "Product":       prod,
        "Category":      cat,
        "Quantity":      qty,
        "Unit_Price":    u_price,
        "Cost_Price":    c_price,
        "Discount":      discount,
        "Sales_Amount":  sales_amt,
        "Profit":        profit,
        "Payment_Method": pay_method,
        "Age":           age,
        "Gender":        gender,
        "Annual_Income": income
    }, warnings


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
          COALESCE(SUM(Sales_Amount), 0) rev,
          COALESCE(SUM(Profit), 0)       pft,
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
          COALESCE(AVG(CASE WHEN Discount>0.15 THEN Profit*100.0/NULLIF(Sales_Amount,0) END), 0) high_disc_margin,
          COALESCE(AVG(CASE WHEN Discount=0    THEN Profit*100.0/NULLIF(Sales_Amount,0) END), 0) no_disc_margin
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

    # 7. Payment method insight
    pay_insight = query("""
        SELECT Payment_Method, ROUND(AVG(Sales_Amount),2) avg_rev
        FROM sales GROUP BY Payment_Method ORDER BY avg_rev DESC LIMIT 1
    """)
    if pay_insight:
        insights.append(
            f"💳 High-value choice: Customers paying with **{pay_insight[0]['Payment_Method']}** "
            f"have the highest Average Order Value (**${pay_insight[0]['avg_rev']:,.2f}**)."
        )

    # 8. Demographic insight
    age_insight = query("""
        SELECT 
            CASE WHEN Age < 30 THEN 'Younger (<30)' ELSE 'Established (30+)' END as demo,
            ROUND(SUM(Sales_Amount),2) rev
        FROM sales GROUP BY demo ORDER BY rev DESC LIMIT 1
    """)
    if age_insight:
        insights.append(
            f"👥 The **{age_insight[0]['demo']}** demographic is your primary revenue driver."
        )

    # 9. Gender-based insight
    gender_insight = query("""
        SELECT Gender, COUNT(*) c, ROUND(SUM(Sales_Amount),2) rev
        FROM sales GROUP BY Gender ORDER BY rev DESC LIMIT 1
    """)
    if gender_insight and gender_insight[0]["Gender"] != "Unknown":
        insights.append(
            f"🚻 **{gender_insight[0]['Gender']}** buyers represent your largest segment by revenue."
        )

    # 10. High-income segment
    income_insight = query("""
        SELECT ROUND(AVG(Sales_Amount),2) avg_rev
        FROM sales WHERE Annual_Income > 1000000
    """)
    if income_insight and income_insight[0]["avg_rev"]:
        insights.append(
            f"💎 High-income bracket (>$1M) average purchase: **${income_insight[0]['avg_rev']:,.0f}**."
        )

    # 11. New-record-specific insight
    if new_record:
        margin = round(new_record["Profit"] / new_record["Sales_Amount"] * 100, 1) \
                 if new_record.get("Sales_Amount") else 0
        insights.append(
            f"✅ New order **{new_record['Order_ID']}** added — "
            f"**${new_record['Sales_Amount']:,.2f}** revenue via **{new_record['Payment_Method']}**."
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
          COALESCE(SUM(Sales_Amount), 0)                          AS total_revenue,
          COALESCE(SUM(Profit), 0)                                AS total_profit,
          COALESCE(SUM(Profit)*100.0/NULLIF(SUM(Sales_Amount),0), 0) AS profit_margin,
          COALESCE(SUM(Sales_Amount)/NULLIF(COUNT(DISTINCT Order_ID),0), 0) AS aov,
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
           Quantity,Unit_Price,Cost_Price,Discount,Sales_Amount,Profit,Payment_Method,Age,Gender,Annual_Income)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        cleaned["Order_ID"], cleaned["Order_Date"],
        cleaned["Customer_ID"], cleaned["Customer_Name"],
        cleaned["Region"], cleaned["Product"], cleaned["Category"],
        cleaned["Quantity"], cleaned["Unit_Price"], cleaned["Cost_Price"],
        cleaned["Discount"], cleaned["Sales_Amount"], cleaned["Profit"],
        cleaned["Payment_Method"], cleaned["Age"],
        cleaned["Gender"], cleaned["Annual_Income"]
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
    
    # Get current count once to speed up Order_ID generation
    curr_count = query("SELECT COUNT(*) c FROM sales")[0]["c"]

    inserted, skipped, warn_log = 0, 0, []
    rows_to_insert = []

    # Pre-calculate mapping for speed
    fieldnames = list(reader.fieldnames) if (reader.fieldnames is not None) else []
    mapping = get_header_mapping(fieldnames)

    for i, row in enumerate(reader, 1):
        try:
            cleaned, warns = clean_record(row, check_duplicates=False, 
                                          next_order_num=curr_count + inserted + 1,
                                          header_mapping=mapping)
            
            # Final validation before DB insert to avoid NOT NULL errors
            # If these essential fields are still empty, skip the row
            if not cleaned.get("Region") or not cleaned.get("Product") or not cleaned.get("Order_Date"):
                raise ValueError(f"Missing essential fields: Region={cleaned.get('Region')}, Product={cleaned.get('Product')}, Date={cleaned.get('Order_Date')}")

            rows_to_insert.append((
                cleaned["Order_ID"], cleaned["Order_Date"],
                cleaned["Customer_ID"], cleaned["Customer_Name"],
                cleaned["Region"], cleaned["Product"], cleaned["Category"],
                cleaned["Quantity"], cleaned["Unit_Price"], cleaned["Cost_Price"],
                cleaned["Discount"], cleaned["Sales_Amount"], cleaned["Profit"],
                cleaned["Payment_Method"], cleaned["Age"],
                cleaned["Gender"], cleaned["Annual_Income"]
            ))
            if warns and len(warn_log) < 50:
                warn_log.append(f"Row {i}: {'; '.join(warns)}")
            inserted += 1
        except Exception as e:
            skipped += 1
            if len(warn_log) < 50:
                import traceback
                error_detail = traceback.format_exception_only(type(e), e)[0].strip()
                warn_log.append(f"Row {i} skipped — {error_detail}")

    if rows_to_insert:
        with get_db() as conn:
            conn.executemany("""
                INSERT OR IGNORE INTO sales
                  (Order_ID,Order_Date,Customer_ID,Customer_Name,Region,Product,Category,
                   Quantity,Unit_Price,Cost_Price,Discount,Sales_Amount,Profit,Payment_Method,Age,Gender,Annual_Income)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, rows_to_insert)
            conn.commit()

    insights = generate_insights()
    return jsonify({
        "inserted": inserted,
        "skipped":  skipped,
        "warnings": warn_log, # Show all logs for debugging
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


@app.route("/api/chart/payment")
def chart_payment():
    rows = query("""
        SELECT Payment_Method, ROUND(SUM(Sales_Amount),2) rev
        FROM sales GROUP BY Payment_Method ORDER BY rev DESC
    """)
    return jsonify(rows)


@app.route("/api/chart/age")
def chart_age():
    rows = query("""
        SELECT 
            CASE 
                WHEN Age < 25 THEN '18-24'
                WHEN Age < 35 THEN '25-34'
                WHEN Age < 45 THEN '35-44'
                WHEN Age < 55 THEN '45-54'
                ELSE '55+'
            END as age_bucket,
            COUNT(*) as count,
            ROUND(SUM(Sales_Amount),2) rev
        FROM sales 
        GROUP BY age_bucket ORDER BY age_bucket
    """)
    return jsonify(rows)


# ── Bootstrap ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("\n🚀  Sales Analytics Web App")
    print("   Open: http://localhost:5000\n")
    app.run(debug=True, port=5000)
