# 📊 Sales Analytics Pro

A full-stack, interactive Sales Analytics Web Application designed for data analysts and business intelligence professionals. This project demonstrates a complete data lifecycle from raw transactional data to actionable insights.

![Dashboard Preview](https://github.com/RevanthTellakula/sales-analytics-pro/blob/main/screenshot.png?raw=true)

## 🚀 Key Features

- **Live Dashboard**: Real-time KPI tracking (Revenue, Profit, Margin, AOV) with dynamic Chart.js visualizations.
- **"Work on My Data" Mode**: Upload your own CSV and the dashboard transforms instantly.
- **Smart Data Cleaning**: Backend pipeline handles title-casing, date formatting, and range validation automatically.
- **Fuzzy Column Mapping**: Automatically detects and maps divergent column names (e.g., "Item" → "Product").
- **AI-Generated Insights**: SQL-driven engine detects regional risks and growth trends on-the-fly.
- **Dark Glassmorphism UI**: High-end UX designed to make data engagement intuitive and visually stunning.

## 🛠️ Tech Stack

- **Backend**: Python, Flask
- **Database**: SQLite
- **Frontend**: Vanilla JavaScript, CSS (Custom Design System), Chart.js
- **Analysis**: Advanced SQL (Window Functions, CTEs, Cohort Analysis)

## 📂 Project Structure

```text
sales-webapp/
├── app.py                  # Flask Core: API + Insights Engine
├── init_db.py              # Database Schema & Indexing
├── seed_data.py            # Initial seed of 50K transactional rows
├── static/
│   ├── style.css           # Premium Dark UI Design
│   └── app.js              # SPA Logic & Chart Lifecycle
└── templates/
    └── index.html          # Interactive Dashboard Template
```

## ⚙️ Quick Start

1. **Clone & Install**:
   ```bash
   git clone https://github.com/RevanthTellakula/sales-analytics-pro.git
   cd sales-analytics-pro
   pip install flask
   ```

2. **Initialize & Seed**:
   ```bash
   python init_db.py
   python seed_data.py
   ```

3. **Run**:
   ```bash
   python app.py
   # Open http://localhost:5000 in your browser
   ```

## 📊 Sample SQL Techniques Used
- **Window Functions**: `RANK()`, `LAG()`, `NTILE()` for growth and Pareto analysis.
- **CTEs**: For readable multi-step transformations.
- **CASE Statements**: For complex regional pivots and discount impact studies.

---
*Created as a high-performance Data Analyst portfolio piece.*
