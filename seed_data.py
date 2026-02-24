"""
seed_data.py — Pre-populate the webapp DB with the 52K generated records.

Usage:
    python seed_data.py
"""
import sqlite3, csv, os, sys

DB_PATH  = os.path.join(os.path.dirname(__file__), "data", "sales.db")
CSV_PATH = os.path.join(os.path.dirname(__file__), "..", "sales-analytics", "data", "sales.csv")

if not os.path.exists(CSV_PATH):
    print(f"⚠  CSV not found at {CSV_PATH}")
    print("   Run  python ../sales-analytics/data/generate_data.py  first, OR skip seeding.")
    sys.exit(0)

conn = sqlite3.connect(DB_PATH)
cur  = conn.cursor()

cur.execute("SELECT COUNT(*) FROM sales")
existing = cur.fetchone()[0]
if existing > 0:
    print(f"ℹ  Database already has {existing:,} rows. Skipping seed.")
    conn.close()
    sys.exit(0)

print(f"📥  Seeding from {CSV_PATH} ...")
with open(CSV_PATH, newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    rows = []
    for r in reader:
        rows.append((
            r["Order_ID"], r["Order_Date"],
            r["Customer_ID"], r.get("Customer_Name", r["Customer_ID"]),
            r["Region"], r["Product"], r["Category"],
            int(r["Quantity"]), float(r["Unit_Price"]), float(r["Cost_Price"]),
            float(r["Discount"]), float(r["Sales_Amount"]), float(r["Profit"])
        ))

cur.executemany("""
INSERT INTO sales
  (Order_ID,Order_Date,Customer_ID,Customer_Name,Region,Product,Category,
   Quantity,Unit_Price,Cost_Price,Discount,Sales_Amount,Profit)
VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
""", rows)
conn.commit()
conn.close()
print(f"✅  Seeded {len(rows):,} rows into {DB_PATH}")
