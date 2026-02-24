"""
Sales Analytics Web App
========================
init_db.py — Run once to create the SQLite database + schema.

Usage:
    python init_db.py
"""
import sqlite3, os

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "sales.db")

def init():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS sales (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        Order_ID     TEXT    NOT NULL,
        Order_Date   DATE    NOT NULL,
        Customer_ID  TEXT    NOT NULL,
        Customer_Name TEXT   NOT NULL DEFAULT '',
        Region       TEXT    NOT NULL,
        Product      TEXT    NOT NULL,
        Category     TEXT    NOT NULL,
        Quantity     INTEGER NOT NULL,
        Unit_Price   REAL    NOT NULL,
        Cost_Price   REAL    NOT NULL,
        Discount     REAL    NOT NULL DEFAULT 0,
        Sales_Amount REAL    NOT NULL,
        Profit       REAL    NOT NULL,
        Payment_Method TEXT,
        Age          INTEGER,
        Gender       TEXT,
        Annual_Income REAL,
        created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE INDEX IF NOT EXISTS idx_date     ON sales(Order_Date);
    CREATE INDEX IF NOT EXISTS idx_region   ON sales(Region);
    CREATE INDEX IF NOT EXISTS idx_product  ON sales(Product);
    CREATE INDEX IF NOT EXISTS idx_customer ON sales(Customer_ID);
    CREATE INDEX IF NOT EXISTS idx_category ON sales(Category);
    CREATE INDEX IF NOT EXISTS idx_pay      ON sales(Payment_Method);
    CREATE INDEX IF NOT EXISTS idx_age      ON sales(Age);
    """)
    # Migration: Add missing columns if they don't exist
    existing_cols = [row[1] for row in c.execute("PRAGMA table_info(sales)").fetchall()]
    migrations = [
        ("Payment_Method", "TEXT"),
        ("Age",            "INTEGER"),
        ("Gender",         "TEXT"),
        ("Annual_Income",  "REAL")
    ]
    for col_name, col_type in migrations:
        if col_name not in existing_cols:
            print(f"Adding missing column: {col_name}")
            c.execute(f"ALTER TABLE sales ADD COLUMN {col_name} {col_type}")

    conn.commit()
    conn.close()
    print(f"✅ Database initialised and migrated: {DB_PATH}")

if __name__ == "__main__":
    init()
