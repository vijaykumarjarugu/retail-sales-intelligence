"""
================================================================================
 inventory_engine.py
 Automated Retail Inventory Optimization & Dynamic Pricing Engine
 ─────────────────────────────────────────────────────────────────────────────
 Computes Inventory Management KPIs by merging forecast data with cleaned
 retail sales data. Outputs per-category/sub-category/region recommendations
 to inventory_recommendations.csv.

 KPIs Computed:
   • Average Daily Demand (ADD)   = mean(Predicted_Sales) / 7
   • Reorder Point (ROP)          = ADD × Lead_Time + Safety_Stock
   • Safety Stock                 = Z × σ(daily_demand) × √Lead_Time
   • Overstock Risk               = Flagged if Actual < 75% of Predicted (persistently)
   • Stockout Risk                = Flagged if Predicted > 125% of Actual (persistently)
   • Alert Level                  = CRITICAL / WARNING / OK

 Usage:
   python inventory_engine.py
   → Generates: inventory_recommendations.csv
================================================================================
"""

import pandas as pd
import numpy as np
import os
import warnings
warnings.filterwarnings("ignore")

# ──────────────────────────────────────────────────────────────
# CONFIGURATION
# ──────────────────────────────────────────────────────────────

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

FORECAST_CSV        = os.path.join(BASE_DIR, "final_sales_forecast.csv")
CLEANED_SALES_CSV   = os.path.join(BASE_DIR, "cleaned_retail_sales.csv")
OUTPUT_CSV          = os.path.join(BASE_DIR, "inventory_recommendations.csv")

# Inventory parameters
LEAD_TIME_DAYS      = 7       # Supplier lead time in days
SERVICE_LEVEL_Z     = 1.65    # Z-score for 95% service level
DAYS_PER_WEEK       = 7
OVERSTOCK_THRESHOLD = 0.75    # Actual < 75% of Predicted → possible overstock
STOCKOUT_THRESHOLD  = 1.25    # Predicted > 125% of Actual → stockout risk


# ──────────────────────────────────────────────────────────────
# STEP 1: LOAD DATA
# ──────────────────────────────────────────────────────────────

def load_data():
    """Load and merge forecast with cleaned sales data (row-wise alignment)."""
    print("=" * 65)
    print("  Automated Retail Inventory Optimization Engine")
    print("=" * 65)
    print("\n[1/5] Loading data files...")

    forecast_df = pd.read_csv(FORECAST_CSV)
    cleaned_df  = pd.read_csv(CLEANED_SALES_CSV)

    print(f"      Forecast rows  : {len(forecast_df):,}")
    print(f"      Cleaned rows   : {len(cleaned_df):,}")

    # Row-wise merge: both files share the same order from notebook pipeline
    min_rows = min(len(forecast_df), len(cleaned_df))
    forecast_df = forecast_df.iloc[:min_rows].reset_index(drop=True)
    cleaned_df  = cleaned_df.iloc[:min_rows].reset_index(drop=True)

    merged = pd.concat([
        cleaned_df[["Category", "Sub-Category", "Region", "Quantity",
                    "Discount", "Profit", "Sales", "Order_Date",
                    "Order_Month", "Order_Year"]],
        forecast_df[["Actual_Sales", "Predicted_Sales", "Residual"]]
    ], axis=1)

    # Rename for cleaner column names
    merged.rename(columns={"Sub-Category": "Sub_Category"}, inplace=True)

    # Parse date
    if "Order_Date" in merged.columns:
        merged["Order_Date"] = pd.to_datetime(merged["Order_Date"], errors="coerce")

    print(f"      Merged dataset : {len(merged):,} rows")
    print(f"      Columns        : {list(merged.columns)}")
    return merged


# ──────────────────────────────────────────────────────────────
# STEP 2: COMPUTE PER-RECORD DAILY DEMAND
# ──────────────────────────────────────────────────────────────

def compute_daily_demand(df):
    """Convert order-level sales to estimated daily demand figures."""
    print("\n[2/5] Computing daily demand estimates...")
    df["Daily_Predicted"] = df["Predicted_Sales"] / DAYS_PER_WEEK
    df["Daily_Actual"]    = df["Actual_Sales"]    / DAYS_PER_WEEK
    print(f"      Overall mean daily predicted demand: "
          f"${df['Daily_Predicted'].mean():.2f}")
    return df


# ──────────────────────────────────────────────────────────────
# STEP 3: COMPUTE KPIs PER GROUP
# ──────────────────────────────────────────────────────────────

def compute_kpis(df):
    """Aggregate and compute all inventory KPIs per Category/Sub_Category/Region."""
    print("\n[3/5] Computing inventory KPIs per category/sub-category/region...")

    group_cols = ["Category", "Sub_Category", "Region"]

    def kpi_agg(grp):
        n = len(grp)

        # Core demand stats
        avg_daily_demand  = grp["Daily_Predicted"].mean()
        std_daily_demand  = grp["Daily_Predicted"].std(ddof=1) if n > 1 else 0.0

        # Safety Stock: Z × σ × √Lead_Time
        safety_stock      = SERVICE_LEVEL_Z * std_daily_demand * np.sqrt(LEAD_TIME_DAYS)

        # Reorder Point: ADD × Lead_Time + Safety_Stock
        reorder_point     = (avg_daily_demand * LEAD_TIME_DAYS) + safety_stock

        # Total & Average Sales
        total_predicted   = grp["Predicted_Sales"].sum()
        total_actual      = grp["Actual_Sales"].sum()
        avg_predicted     = grp["Predicted_Sales"].mean()
        avg_actual        = grp["Actual_Sales"].mean()
        peak_predicted    = grp["Predicted_Sales"].max()
        total_quantity    = grp["Quantity"].sum()

        # Overstock Risk: actual < 75% of predicted
        overstock_records = (grp["Actual_Sales"] < OVERSTOCK_THRESHOLD * grp["Predicted_Sales"]).sum()
        overstock_pct     = overstock_records / n if n > 0 else 0
        overstock_risk    = "HIGH"   if overstock_pct >= 0.40 else (
                            "MEDIUM" if overstock_pct >= 0.20 else "LOW")

        # Stockout Risk: predicted > 125% of actual
        stockout_records  = (grp["Predicted_Sales"] > STOCKOUT_THRESHOLD * grp["Actual_Sales"]).sum()
        stockout_pct      = stockout_records / n if n > 0 else 0
        stockout_risk     = "HIGH"   if stockout_pct >= 0.40 else (
                            "MEDIUM" if stockout_pct >= 0.20 else "LOW")

        # Alert Level
        if stockout_risk == "HIGH" or overstock_risk == "HIGH":
            alert_level = "CRITICAL"
        elif stockout_risk == "MEDIUM" or overstock_risk == "MEDIUM":
            alert_level = "WARNING"
        else:
            alert_level = "OK"

        # Revenue & Margin
        avg_discount      = grp["Discount"].mean() * 100
        avg_profit_margin = (grp["Profit"].sum() / total_actual * 100
                             if total_actual > 0 else 0)
        peak_safety_stock = SERVICE_LEVEL_Z * std_daily_demand * np.sqrt(LEAD_TIME_DAYS) * 1.5

        return pd.Series({
            "Record_Count"       : n,
            "Total_Quantity"     : total_quantity,
            "Avg_Daily_Demand"   : round(avg_daily_demand, 4),
            "Std_Daily_Demand"   : round(std_daily_demand, 4),
            "Safety_Stock"       : round(safety_stock, 4),
            "Peak_Safety_Stock"  : round(peak_safety_stock, 4),
            "Reorder_Point"      : round(reorder_point, 4),
            "Total_Predicted"    : round(total_predicted, 2),
            "Total_Actual"       : round(total_actual, 2),
            "Avg_Predicted_Sales": round(avg_predicted, 2),
            "Avg_Actual_Sales"   : round(avg_actual, 2),
            "Peak_Predicted"     : round(peak_predicted, 2),
            "Overstock_Risk"     : overstock_risk,
            "Overstock_Pct"      : round(overstock_pct * 100, 1),
            "Stockout_Risk"      : stockout_risk,
            "Stockout_Pct"       : round(stockout_pct * 100, 1),
            "Alert_Level"        : alert_level,
            "Avg_Discount_Pct"   : round(avg_discount, 2),
            "Avg_Profit_Margin"  : round(avg_profit_margin, 2),
        })

    kpi_df = df.groupby(group_cols, as_index=False).apply(kpi_agg)
    kpi_df = kpi_df.reset_index(drop=True)

    # Add metadata columns
    kpi_df["Lead_Time_Days"]    = LEAD_TIME_DAYS
    kpi_df["Service_Level_Pct"] = 95
    kpi_df["Generated_At"]      = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")

    # Sort by alert priority
    alert_order = {"CRITICAL": 0, "WARNING": 1, "OK": 2}
    kpi_df["_sort"] = kpi_df["Alert_Level"].map(alert_order)
    kpi_df = kpi_df.sort_values(["_sort", "Category", "Sub_Category"]).drop(columns=["_sort"])

    print(f"      KPI groups computed: {len(kpi_df)}")
    return kpi_df


# ──────────────────────────────────────────────────────────────
# STEP 4: PRINT SUMMARY REPORT
# ──────────────────────────────────────────────────────────────

def print_summary(kpi_df):
    """Print a console summary of inventory alerts."""
    print("\n[4/5] Inventory KPI Summary")
    print("-" * 65)

    critical = kpi_df[kpi_df["Alert_Level"] == "CRITICAL"]
    warning  = kpi_df[kpi_df["Alert_Level"] == "WARNING"]
    ok       = kpi_df[kpi_df["Alert_Level"] == "OK"]

    print(f"  CRITICAL alerts : {len(critical)}")
    print(f"  WARNING alerts  : {len(warning)}")
    print(f"  OK groups       : {len(ok)}")

    if len(critical) > 0:
        print("\n  -- CRITICAL Groups --")
        for _, row in critical.iterrows():
            print(f"  {row['Category']} > {row['Sub_Category']} [{row['Region']}]")
            print(f"     ROP: {row['Reorder_Point']:.2f} | "
                  f"Safety Stock: {row['Safety_Stock']:.2f} | "
                  f"Stockout: {row['Stockout_Risk']} | "
                  f"Overstock: {row['Overstock_Risk']}")

    print("\n  -- Top 5 by Reorder Point --")
    top5 = kpi_df.nlargest(5, "Reorder_Point")[
        ["Category", "Sub_Category", "Region", "Reorder_Point",
         "Safety_Stock", "Alert_Level"]
    ]
    print(top5.to_string(index=False))


# ──────────────────────────────────────────────────────────────
# STEP 5: SAVE OUTPUT
# ──────────────────────────────────────────────────────────────

def save_output(kpi_df):
    """Save inventory KPIs to CSV."""
    print(f"\n[5/5] Saving output -> {OUTPUT_CSV}")
    kpi_df.to_csv(OUTPUT_CSV, index=False)
    print(f"      Saved {len(kpi_df)} rows x {len(kpi_df.columns)} columns")
    print(f"      Columns: {list(kpi_df.columns)}")


# ──────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────

def run_inventory_engine():
    """Run the complete inventory KPI computation pipeline."""
    merged_df = load_data()
    merged_df = compute_daily_demand(merged_df)
    kpi_df    = compute_kpis(merged_df)
    print_summary(kpi_df)
    save_output(kpi_df)

    print("\n" + "=" * 65)
    print("  Inventory Engine Complete!")
    print("  Output: inventory_recommendations.csv")
    print("=" * 65)

    return kpi_df


if __name__ == "__main__":
    run_inventory_engine()
