import sqlite3
import json

def get_stats():
    # Fix the DB path
    import os
    db_path = os.path.join(os.path.dirname(__file__), "data", "sales.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    # 1. High Level KPIs
    kpis = conn.execute('''
        SELECT 
            COUNT(*) as total_orders,
            SUM(Sales_Amount) as total_revenue,
            SUM(Profit) as total_profit,
            AVG(Sales_Amount) as aov,
            COUNT(DISTINCT Customer_ID) as unique_customers
        FROM sales
    ''').fetchone()
    
    # 2. Regional Performance
    regions = conn.execute('''
        SELECT Region, SUM(Sales_Amount) as rev, SUM(Profit) as pft,
               (SUM(Profit) * 100.0 / SUM(Sales_Amount)) as margin
        FROM sales GROUP BY Region ORDER BY rev DESC
    ''').fetchall()
    
    # 3. Category Performance
    cats = conn.execute('''
        SELECT Category, SUM(Sales_Amount) as rev, SUM(Profit) as pft,
               (SUM(Profit) * 100.0 / SUM(Sales_Amount)) as margin
        FROM sales GROUP BY Category ORDER BY rev DESC
    ''').fetchall()
    
    # 4. Growth Trend (Simulated YoY if only one year, or actual if multiple)
    # We'll just look at the last few months
    trends = conn.execute('''
        SELECT strftime('%Y-%m', Order_Date) as month, SUM(Sales_Amount) as rev
        FROM sales GROUP BY month ORDER BY month DESC LIMIT 6
    ''').fetchall()

    stats = {
        "kpis": dict(kpis),
        "regions": [dict(r) for r in regions],
        "categories": [dict(c) for c in cats],
        "recent_trends": [dict(t) for t in trends]
    }
    
    print(json.dumps(stats, indent=2))
    conn.close()

if __name__ == "__main__":
    get_stats()
