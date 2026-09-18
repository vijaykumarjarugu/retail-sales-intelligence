"""
================================================================================
 mysql_schema_and_appender.py
 Automated Retail Inventory Optimization & Dynamic Pricing Engine
 ─────────────────────────────────────────────────────────────────────────────
 Standalone Python script equivalent to the new cells added to:
 07_MySQL_Integration.ipynb

 This script:
   1. Creates 3 MySQL tables with full DDL
   2. Loads cleaned sales data into tbl_raw_sales & tbl_cleaned_sales
   3. Appends inventory forecast KPIs into tbl_inventory_forecasts
      (idempotent — uses run_date to avoid duplicates)

 Prerequisites:
   pip install sqlalchemy mysql-connector-python pandas

 Configuration:
   Update DB_HOST, DB_USER, DB_PASSWORD, DB_NAME below before running.
================================================================================
"""

import pandas as pd
from sqlalchemy import create_engine, text
import os
import warnings
warnings.filterwarnings("ignore")

# ──────────────────────────────────────────────────────────────
# DATABASE CONFIGURATION  ← Update these values
# ──────────────────────────────────────────────────────────────
DB_HOST     = "localhost"
DB_USER     = "root"
DB_PASSWORD = "your_password"
DB_NAME     = "retail_db"
DB_PORT     = 3306

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ──────────────────────────────────────────────────────────────
# SQL DDL — 3 Tables
# ──────────────────────────────────────────────────────────────

DDL_RAW_SALES = """
CREATE TABLE IF NOT EXISTS tbl_raw_sales (
    row_id           INT            PRIMARY KEY,
    order_id         VARCHAR(25)    NOT NULL,
    order_date       DATE           NOT NULL,
    ship_date        DATE,
    ship_mode        VARCHAR(30),
    customer_id      VARCHAR(20),
    customer_name    VARCHAR(120),
    segment          VARCHAR(30),
    country          VARCHAR(60),
    city             VARCHAR(80),
    state            VARCHAR(60),
    postal_code      VARCHAR(15),
    region           VARCHAR(20),
    product_id       VARCHAR(30),
    category         VARCHAR(40),
    sub_category     VARCHAR(40),
    product_name     TEXT,
    sales            DECIMAL(12, 4)  NOT NULL,
    quantity         SMALLINT        NOT NULL,
    discount         DECIMAL(5, 4),
    profit           DECIMAL(12, 4),
    created_at       TIMESTAMP       DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""

DDL_CLEANED_SALES = """
CREATE TABLE IF NOT EXISTS tbl_cleaned_sales (
    row_id               INT            PRIMARY KEY,
    order_id             VARCHAR(25)    NOT NULL,
    order_date           DATE           NOT NULL,
    ship_date            DATE,
    ship_mode            VARCHAR(30),
    customer_id          VARCHAR(20),
    customer_name        VARCHAR(120),
    segment              VARCHAR(30),
    country              VARCHAR(60),
    city                 VARCHAR(80),
    state                VARCHAR(60),
    postal_code          VARCHAR(15),
    region               VARCHAR(20),
    product_id           VARCHAR(30),
    category             VARCHAR(40),
    sub_category         VARCHAR(40),
    product_name         TEXT,
    sales                DECIMAL(12, 4)  NOT NULL,
    quantity             SMALLINT        NOT NULL,
    discount             DECIMAL(5, 4),
    profit               DECIMAL(12, 4),
    -- Engineered Features
    order_year           SMALLINT,
    order_month          TINYINT,
    order_month_name     VARCHAR(12),
    order_quarter        TINYINT,
    order_day            TINYINT,
    weekday              VARCHAR(12),
    is_weekend           TINYINT(1),
    sales_per_quantity   DECIMAL(12, 4),
    profit_margin        DECIMAL(8, 4),
    order_week           TINYINT,
    day_of_week          TINYINT,
    shipping_days        TINYINT,
    discount_flag        TINYINT(1),
    customer_order_count SMALLINT,
    product_order_count  SMALLINT,
    created_at           TIMESTAMP       DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""

DDL_INVENTORY_FORECASTS = """
CREATE TABLE IF NOT EXISTS tbl_inventory_forecasts (
    forecast_id          INT             AUTO_INCREMENT PRIMARY KEY,
    run_date             DATE            NOT NULL,
    category             VARCHAR(40)     NOT NULL,
    sub_category         VARCHAR(40)     NOT NULL,
    region               VARCHAR(20)     NOT NULL,
    record_count         INT,
    total_quantity       INT,
    avg_daily_demand     DECIMAL(12, 4),
    std_daily_demand     DECIMAL(12, 4),
    safety_stock         DECIMAL(12, 4),
    peak_safety_stock    DECIMAL(12, 4),
    reorder_point        DECIMAL(12, 4),
    total_predicted      DECIMAL(14, 2),
    total_actual         DECIMAL(14, 2),
    avg_predicted_sales  DECIMAL(12, 4),
    avg_actual_sales     DECIMAL(12, 4),
    peak_predicted       DECIMAL(12, 4),
    overstock_risk       VARCHAR(10),
    overstock_pct        DECIMAL(5, 1),
    stockout_risk        VARCHAR(10),
    stockout_pct         DECIMAL(5, 1),
    alert_level          VARCHAR(12),
    avg_discount_pct     DECIMAL(6, 2),
    avg_profit_margin    DECIMAL(8, 2),
    lead_time_days       TINYINT,
    service_level_pct    TINYINT,
    generated_at         DATETIME,
    inserted_at          TIMESTAMP       DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_run_date   (run_date),
    INDEX idx_category   (category, sub_category),
    INDEX idx_alert      (alert_level)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""


def get_engine():
    """Create and return SQLAlchemy engine for MySQL."""
    conn_str = (
        f"mysql+mysqlconnector://{DB_USER}:{DB_PASSWORD}"
        f"@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    )
    engine = create_engine(conn_str, echo=False)
    return engine


def create_tables(engine):
    """Create all 3 tables if they don't already exist."""
    print("[1/3] Creating MySQL tables...")
    with engine.connect() as conn:
        conn.execute(text(DDL_RAW_SALES))
        print("      ✓ tbl_raw_sales created (or already exists)")
        conn.execute(text(DDL_CLEANED_SALES))
        print("      ✓ tbl_cleaned_sales created (or already exists)")
        conn.execute(text(DDL_INVENTORY_FORECASTS))
        print("      ✓ tbl_inventory_forecasts created (or already exists)")
        conn.commit()


def load_raw_sales(engine):
    """Load raw Superstore data into tbl_raw_sales."""
    print("\n[2a/3] Loading raw sales data...")
    raw_path = os.path.join(BASE_DIR, "retail_sales_raw_copy.csv")
    if not os.path.exists(raw_path):
        print("      ⚠ retail_sales_raw_copy.csv not found. Skipping.")
        return
    df = pd.read_csv(raw_path)
    df.columns = [c.lower().replace(" ","_").replace("-","_") for c in df.columns]
    df.rename(columns={"sub_category": "sub_category",
                        "row_id": "row_id"}, inplace=True)
    # Map columns to DDL names
    col_map = {
        "row_id": "row_id", "order_id": "order_id",
        "order_date": "order_date", "ship_date": "ship_date",
        "ship_mode": "ship_mode", "customer_id": "customer_id",
        "customer_name": "customer_name", "segment": "segment",
        "country": "country", "city": "city", "state": "state",
        "postal_code": "postal_code", "region": "region",
        "product_id": "product_id", "category": "category",
        "sub_category": "sub_category", "product_name": "product_name",
        "sales": "sales", "quantity": "quantity",
        "discount": "discount", "profit": "profit"
    }
    avail = {k: v for k, v in col_map.items() if k in df.columns}
    df = df[list(avail.keys())].rename(columns=avail)
    df["order_date"] = pd.to_datetime(df["order_date"], errors="coerce")
    df["ship_date"]  = pd.to_datetime(df["ship_date"],  errors="coerce")
    df.to_sql("tbl_raw_sales", con=engine, if_exists="replace",
              index=False, chunksize=500)
    print(f"      ✓ Loaded {len(df):,} rows into tbl_raw_sales")


def load_cleaned_sales(engine):
    """Load feature-engineered sales data into tbl_cleaned_sales."""
    print("\n[2b/3] Loading cleaned/feature-engineered sales data...")
    path = os.path.join(BASE_DIR, "feature_engineered_retail_sales.csv")
    if not os.path.exists(path):
        print("      ⚠ feature_engineered_retail_sales.csv not found. Skipping.")
        return
    df = pd.read_csv(path)
    df.columns = [c.lower().replace("-","_").replace(" ","_") for c in df.columns]
    df.rename(columns={"sub_category": "sub_category"}, inplace=True)
    date_cols = ["order_date", "ship_date"]
    for dc in date_cols:
        if dc in df.columns:
            df[dc] = pd.to_datetime(df[dc], errors="coerce")
    # Only keep columns that exist in the DDL
    ddl_cols = [
        "row_id","order_id","order_date","ship_date","ship_mode","customer_id",
        "customer_name","segment","country","city","state","postal_code","region",
        "product_id","category","sub_category","product_name","sales","quantity",
        "discount","profit","order_year","order_month","order_month_name",
        "order_quarter","order_day","weekday","is_weekend","sales_per_quantity",
        "profit_margin","order_week","day_of_week","shipping_days","discount_flag",
        "customer_order_count","product_order_count"
    ]
    avail_cols = [c for c in ddl_cols if c in df.columns]
    df = df[avail_cols]
    df.to_sql("tbl_cleaned_sales", con=engine, if_exists="replace",
              index=False, chunksize=500)
    print(f"      ✓ Loaded {len(df):,} rows into tbl_cleaned_sales")


def append_inventory_forecasts(engine):
    """
    Append latest inventory KPI results into tbl_inventory_forecasts.
    Avoids duplicate run_date entries by deleting existing rows for today first.
    """
    print("\n[3/3] Appending inventory forecasts to tbl_inventory_forecasts...")
    path = os.path.join(BASE_DIR, "inventory_recommendations.csv")
    if not os.path.exists(path):
        print("      ⚠ inventory_recommendations.csv not found.")
        print("        Run 'python inventory_engine.py' first.")
        return

    df = pd.read_csv(path)
    today_str = pd.Timestamp.today().strftime("%Y-%m-%d")
    df["run_date"] = today_str

    # Column name normalization
    df.columns = [c.lower() for c in df.columns]

    # Remove existing rows for today to allow re-runs (idempotent)
    with engine.connect() as conn:
        result = conn.execute(
            text("DELETE FROM tbl_inventory_forecasts WHERE run_date = :rd"),
            {"rd": today_str}
        )
        conn.commit()
        print(f"      ✓ Cleared {result.rowcount} existing rows for {today_str}")

    df.to_sql("tbl_inventory_forecasts", con=engine, if_exists="append",
              index=False, chunksize=100)
    print(f"      ✓ Appended {len(df)} rows into tbl_inventory_forecasts")
    print(f"      📅 Run date: {today_str}")

    # Verify row count
    with engine.connect() as conn:
        total = conn.execute(
            text("SELECT COUNT(*) FROM tbl_inventory_forecasts")
        ).scalar()
        print(f"      📊 Total rows in tbl_inventory_forecasts: {total}")


def run_business_queries(engine):
    """Run sample business intelligence queries for verification."""
    print("\n── Business Intelligence Queries ──")

    queries = {
        "Critical Inventory Alerts": """
            SELECT category, sub_category, region,
                   reorder_point, safety_stock, alert_level
            FROM tbl_inventory_forecasts
            WHERE alert_level = 'CRITICAL'
            ORDER BY reorder_point DESC
            LIMIT 10
        """,
        "Top Categories by Avg Daily Demand": """
            SELECT category, AVG(avg_daily_demand) AS avg_demand,
                   SUM(total_predicted) AS total_forecast
            FROM tbl_inventory_forecasts
            GROUP BY category
            ORDER BY avg_demand DESC
        """,
        "Stockout Risk Summary": """
            SELECT stockout_risk, COUNT(*) AS groups,
                   AVG(reorder_point) AS avg_rop
            FROM tbl_inventory_forecasts
            GROUP BY stockout_risk
            ORDER BY groups DESC
        """
    }

    for title, sql in queries.items():
        print(f"\n  📊 {title}")
        try:
            df = pd.read_sql(text(sql), engine)
            print(df.to_string(index=False))
        except Exception as e:
            print(f"     Query failed: {e}")


def main():
    """Full pipeline: create tables → load data → append forecasts → query."""
    print("=" * 65)
    print("  MySQL Integration — Retail Inventory Optimization Engine")
    print("=" * 65)

    try:
        engine = get_engine()
        print(f"\n✅ Connected to MySQL: {DB_HOST}/{DB_NAME}")

        create_tables(engine)
        load_raw_sales(engine)
        load_cleaned_sales(engine)
        append_inventory_forecasts(engine)
        run_business_queries(engine)

        print("\n" + "=" * 65)
        print("  ✅ MySQL Integration Complete!")
        print("=" * 65)

    except Exception as e:
        print(f"\n❌ Connection failed: {e}")
        print(f"\nPlease update DB_HOST, DB_USER, DB_PASSWORD, DB_NAME at the")
        print(f"top of this script and ensure MySQL is running.")


if __name__ == "__main__":
    main()
