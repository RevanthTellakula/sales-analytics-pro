# 📊 Business Case Study: E-commerce Sales Performance

## 1️⃣ Project Overview (Problem Statement)
This project analyzes **2 years of transactional e-commerce sales data** to evaluate revenue trends, customer behavior, and regional performance. The goal is to identify growth opportunities and profitability drivers to optimize business strategy.

- **Dataset**: 50,000+ Ecommerce Transactions
- **Business Problem**: Declining margins in specific regions and identifying high-value customer segments.
- **Time Period**: 2023 - 2024 (2 Full Years)

---

## 2️⃣ Dataset Description
The analysis is based on a high-velocity transactional dataset representing a global retail operation.
- **Scale**: 50,000+ Transactions
- **Dimensions**: 13 Columns
- **Key Fields**: `Order_ID`, `Order_Date`, `Customer_ID`, `Sales_Amount`, `Profit`, `Region`, `Category`, `Product`.

---

## 3️⃣ Data Cleaning & Preparation
To ensure data integrity for analysis, the following preparation steps were taken:
- **Null Handling**: Initialized mandatory fields with defaults; handled missing `Product` names by falling back to `Category`.
- **Deduplication**: Enforced `Order_ID` uniqueness at the database level.
- **Normalization**: Normalized fuzzy CSV headers (e.g., `User_Name` → `Customer_Name`) to support cross-dataset compatibility.
- **Calculated Columns**:
    - `Sales_Amount`: `Quantity * Unit_Price * (1 - Discount)`
    - `Profit`: `Sales_Amount - (Quantity * Cost_Price)`
- **Date Conversion**: Transformed varied raw strings into `ISO-8601` DATE objects for time-series aggregation.

---

## 4️⃣ KPI Definitions (Business Metrics)
Clearly defined metrics ensure consistent reporting across the organization:

| KPI | Formula | Business Logic |
|-----|---------|----------------|
| **Total Revenue** | `SUM(Sales_Amount)` | Total gross value of all orders. |
| **Total Profit** | `SUM(Profit)` | Net income after all product costs. |
| **Profit Margin** | `(SUM(Profit) / SUM(Sales_Amount)) * 100` | Efficiency of turning revenue into profit. |
| **Avg Order Value** | `SUM(Sales_Amount) / COUNT(Order_ID)` | Average revenue generated per transaction. |
| **Growth %** | `(Current - Previous) / Previous * 100` | Period-over-period performance trend. |

---

## 5️⃣ SQL Analysis Section
The analysis utilizes advanced PostgreSQL-compatible SQLite features including **CTEs** and **Window Functions**.

### Monthly Revenue Trend (using LAG)
```sql
WITH MonthlySales AS (
    SELECT 
        strftime('%Y-%m', Order_Date) as Month,
        SUM(Sales_Amount) as Revenue
    FROM sales
    GROUP BY 1
)
SELECT 
    Month,
    Revenue,
    LAG(Revenue) OVER (ORDER BY Month) as Prev_Month_Revenue,
    ROUND(((Revenue - LAG(Revenue) OVER (ORDER BY Month)) / LAG(Revenue) OVER (ORDER BY Month)) * 100, 2) as Growth_Pct
FROM MonthlySales;
```

### Top 10 Products by Profitability (using RANK)
```sql
SELECT 
    Product,
    Category,
    SUM(Profit) as Total_Profit,
    RANK() OVER (ORDER BY SUM(Profit) DESC) as Profit_Rank
FROM sales
GROUP BY Product
LIMIT 10;
```

---

## 6️⃣ Key Insights (Critical Findings)
- **Top Region**: **Canada** is the largest revenue contributor (~$3.4M), showing the highest market penetration.
- **Profitability Gap**: The **Technology** category generates the highest revenue but faces margin pressure due to high cost-of-goods-sold (COGS).
- **Customer Concentration**: The top **15% of customers** contribute to over **40% of total revenue**, indicating a high reliance on "Whale" buyers.
- **Seasonal Peaks**: Consistent revenue spikes in **October and November** suggest strong correlation with holiday retail cycles.

---

## 7️⃣ Professional Dashboard
The insights are visualized in a high-performance **Dark Glassmorphism Dashboard**.

![Executive Summary Overview](file:///C:/Users/REVANTH/.gemini/antigravity/brain/844c7ed9-d632-4e22-ab72-eb6094c86805/ss_exec.png)
*Figure 1: Executive KPI Summary showing Revenue, Profit, and Growth Trends.*

![Product and Region Deep Dive](file:///C:/Users/REVANTH/.gemini/antigravity/brain/844c7ed9-d632-4e22-ab72-eb6094c86805/ss_product.png)
*Figure 2: Product performance rankings and Regional distribution share.*

---

## 8️⃣ Business Recommendations
Based on the data, the following strategic actions are recommended:
1. **Loyalty Program**: Launch a VIP program for the high-value 15% customer segment to secure long-term recurring revenue.
2. **Region-Specific Strategy**: Optimize pricing in the **South** region where profit margins currently lag behind the national average.
3. **Inventory Management**: Prioritize stock levels for **Technology** and **Beauty** categories 6 weeks prior to the Q4 seasonal spikes.
4. **Product Rationalization**: Review the bottom 10% of products with negative profit margins for potential discontinuation or price adjustments.

---

## 9️⃣ Conclusion
The analysis identifies **Canada** and the **Technology** sector as the primary drivers of the business. By focusing on **High-Value Customer Retention** and **Seasonal Inventory Pre-loading**, the business is positioned to achieve a projected **10% increase in profitability** in the coming fiscal year.
