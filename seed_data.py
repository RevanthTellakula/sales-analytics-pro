"""
seed_data.py — Pre-populate the webapp DB with the 52K generated records.

Usage:
    python seed_data.py
"""
import sqlite3, csv, os, sys, random

DB_PATH  = os.path.join(os.path.dirname(__file__), "data", "sales.db")
CSV_PATH = os.path.join(os.path.dirname(__file__), "..", "sales-analytics", "data", "sales.csv")

if not os.path.exists(CSV_PATH):
    print(f"⚠  CSV not found at {CSV_PATH}")
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
pay_methods = ["Credit Card", "PayPal", "Bank Transfer", "Wallet", "Debit Card"]

with open(CSV_PATH, newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    rows = []
    for r in reader:
        pm = random.choice(pay_methods)
        age = random.randint(18, 75)
        
        rows.append((
            r["Order_ID"], r["Order_Date"],
            r["Customer_ID"], r.get("Customer_Name", r["Customer_ID"]),
            r["Region"], r["Product"], r["Category"],
            int(r["Quantity"]), float(r["Unit_Price"]), float(r["Cost_Price"]),
            float(r["Discount"]), float(r["Sales_Amount"]), float(r["Profit"]),
            pm, age
        ))

cur.executemany("""
INSERT INTO sales
  (Order_ID,Order_Date,Customer_ID,Customer_Name,Region,Product,Category,
   Quantity,Unit_Price,Cost_Price,Discount,Sales_Amount,Profit,Payment_Method,Age)
VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
""", rows)
conn.commit()
conn.close()
print(f"✅  Seeded {len(rows):,} rows.")
