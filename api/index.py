import os
import sqlite3
import json
from typing import Optional, List, Dict, Any
import pandas as pd
from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="Fashion Size & Fit Pain-Point Intelligence",
    description="Product Analytics & PM Strategy API for Women's E-Commerce Clothing Reviews",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------------------------------------------------------
# Database & In-Memory Analytics Engine
# -----------------------------------------------------------------------------
DB_CONN = None
METRICS_CACHE = {}
ALL_REVIEWS_DF = None

def get_data_path() -> str:
    candidates = [
        os.path.join(os.path.dirname(__file__), "..", "data", "reviews.csv"),
        os.path.join(os.getcwd(), "data", "reviews.csv"),
        os.path.join(os.path.dirname(__file__), "data", "reviews.csv"),
        "data/reviews.csv"
    ]
    for path in candidates:
        if os.path.exists(path):
            return os.path.abspath(path)
    return candidates[0]

def initialize_data():
    global DB_CONN, METRICS_CACHE, ALL_REVIEWS_DF
    if METRICS_CACHE:
        return

    csv_path = get_data_path()
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"Dataset not found at {csv_path}. Please run download_data.py first.")

    df = pd.read_csv(csv_path)
    df.columns = [c.strip() for c in df.columns]

    df["Title_Clean"] = df["Title"].fillna("")
    df["Review_Text_Clean"] = df["Review Text"].fillna("")
    df["Full_Text"] = (df["Title_Clean"] + " " + df["Review_Text_Clean"]).str.lower()

    # Define Age Cohorts
    def assign_cohort(age):
        if pd.isna(age):
            return "Unknown"
        if age <= 25:
            return "18-25"
        elif age <= 35:
            return "26-35"
        elif age <= 45:
            return "36-45"
        elif age <= 55:
            return "46-55"
        else:
            return "56+"

    df["Age_Cohort"] = df["Age"].apply(assign_cohort)

    # Keywords matching exact project definitions
    keywords = [
        "size", "sizing", "fit", "fits", "fitted", "tight", "loose",
        "small", "large", "run small", "runs small", "run large", "runs large",
        "length", "short", "long", "waist", "bust", "shoulder", "shoulders",
        "return", "returned"
    ]
    pattern_fit = "|".join(keywords)
    df["is_size_fit"] = df["Full_Text"].str.contains(pattern_fit, regex=True, na=False)

    df["cause_small"] = df["Full_Text"].str.contains(r"small|run small|runs small|tight|snug|squeeze", regex=True, na=False)
    df["cause_large"] = df["Full_Text"].str.contains(r"large|run large|runs large|loose|huge|baggy|swimming", regex=True, na=False)
    df["cause_prop"] = df["Full_Text"].str.contains(r"length|short|long|waist|bust|shoulder|shoulders|torso|hips|petite|tall", regex=True, na=False)
    df["cause_return"] = df["Full_Text"].str.contains(r"return|returned", regex=True, na=False)

    ALL_REVIEWS_DF = df

    # In-memory SQLite
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    df.to_sql("reviews", conn, index=False, if_exists="replace")
    DB_CONN = conn

    cursor = conn.cursor()

    # 1. Overall KPIs
    cursor.execute("""
    SELECT
        COUNT(*) AS total_reviews,
        ROUND(AVG("Rating"), 2) AS avg_rating,
        ROUND(100.0 * SUM(CASE WHEN "Recommended IND" = 1 THEN 1 ELSE 0 END) / COUNT(*), 2) AS rec_rate_pct,
        SUM(CASE WHEN "Rating" <= 2 THEN 1 ELSE 0 END) AS neg_count,
        ROUND(100.0 * SUM(CASE WHEN "Rating" <= 2 THEN 1 ELSE 0 END) / COUNT(*), 2) AS neg_rate_pct,
        SUM(CASE WHEN "Rating" >= 4 THEN 1 ELSE 0 END) AS pos_count,
        ROUND(100.0 * SUM(CASE WHEN "Rating" >= 4 THEN 1 ELSE 0 END) / COUNT(*), 2) AS pos_rate_pct
    FROM reviews;
    """)
    tot_rev, avg_rat, rec_pct, neg_cnt, neg_pct, pos_cnt, pos_pct = cursor.fetchone()

    # 2. Size & Fit Share in Negatives
    cursor.execute("""
    SELECT
        SUM(is_size_fit) AS fit_neg_count,
        ROUND(100.0 * SUM(is_size_fit) / COUNT(*), 2) AS fit_neg_pct,
        SUM(cause_small) AS small_count,
        ROUND(100.0 * SUM(cause_small) / COUNT(*), 2) AS small_pct,
        SUM(cause_large) AS large_count,
        ROUND(100.0 * SUM(cause_large) / COUNT(*), 2) AS large_pct,
        SUM(cause_prop) AS prop_count,
        ROUND(100.0 * SUM(cause_prop) / COUNT(*), 2) AS prop_pct
    FROM reviews
    WHERE "Rating" <= 2;
    """)
    fit_neg_cnt, fit_neg_pct, small_cnt, small_pct, large_cnt, large_pct, prop_cnt, prop_pct = cursor.fetchone()

    # 3. Department Breakdown
    cursor.execute("""
    SELECT
        COALESCE("Department Name", 'Unspecified') AS dept,
        COUNT(*) AS total_rev,
        ROUND(AVG("Rating"), 2) AS avg_rat,
        ROUND(100.0 * SUM(CASE WHEN "Recommended IND" = 1 THEN 1 ELSE 0 END) / COUNT(*), 2) AS rec_pct,
        SUM(CASE WHEN "Rating" <= 2 THEN 1 ELSE 0 END) AS neg_rev,
        ROUND(100.0 * SUM(CASE WHEN "Rating" <= 2 THEN 1 ELSE 0 END) / COUNT(*), 2) AS neg_pct,
        SUM(CASE WHEN "Rating" <= 2 AND is_size_fit = 1 THEN 1 ELSE 0 END) AS fit_neg,
        ROUND(100.0 * SUM(CASE WHEN "Rating" <= 2 AND is_size_fit = 1 THEN 1 ELSE 0 END) / NULLIF(SUM(CASE WHEN "Rating" <= 2 THEN 1 ELSE 0 END), 0), 2) AS fit_in_neg_pct
    FROM reviews
    GROUP BY "Department Name"
    HAVING COUNT(*) >= 10
    ORDER BY neg_pct DESC;
    """)
    dept_rows = cursor.fetchall()
    departments = [
        {
            "department": r[0],
            "total_reviews": r[1],
            "avg_rating": r[2],
            "recommendation_rate_pct": r[3],
            "negative_reviews": r[4],
            "negative_review_rate_pct": r[5],
            "fit_complaints": r[6],
            "fit_in_neg_pct": r[7]
        }
        for r in dept_rows
    ]

    # 4. Age Cohort Breakdown
    cursor.execute("""
    SELECT
        Age_Cohort,
        COUNT(*) AS total_rev,
        ROUND(AVG("Rating"), 2) AS avg_rat,
        ROUND(100.0 * SUM(CASE WHEN "Recommended IND" = 1 THEN 1 ELSE 0 END) / COUNT(*), 2) AS rec_pct,
        SUM(CASE WHEN "Rating" <= 2 THEN 1 ELSE 0 END) AS neg_rev,
        ROUND(100.0 * SUM(CASE WHEN "Rating" <= 2 THEN 1 ELSE 0 END) / COUNT(*), 2) AS neg_pct,
        SUM(CASE WHEN "Rating" <= 2 AND is_size_fit = 1 THEN 1 ELSE 0 END) AS fit_neg,
        ROUND(100.0 * SUM(CASE WHEN "Rating" <= 2 AND is_size_fit = 1 THEN 1 ELSE 0 END) / NULLIF(SUM(CASE WHEN "Rating" <= 2 THEN 1 ELSE 0 END), 0), 2) AS fit_in_neg_pct
    FROM reviews
    GROUP BY Age_Cohort
    ORDER BY
        CASE Age_Cohort
            WHEN '18-25' THEN 1
            WHEN '26-35' THEN 2
            WHEN '36-45' THEN 3
            WHEN '46-55' THEN 4
            WHEN '56+' THEN 5
            ELSE 6
        END;
    """)
    cohort_rows = cursor.fetchall()
    age_cohorts = [
        {
            "cohort": r[0],
            "total_reviews": r[1],
            "avg_rating": r[2],
            "recommendation_rate_pct": r[3],
            "negative_reviews": r[4],
            "negative_review_rate_pct": r[5],
            "fit_complaints": r[6],
            "fit_in_neg_pct": r[7]
        }
        for r in cohort_rows
    ]

    # 5. Top Classes Breakdown
    cursor.execute("""
    SELECT
        COALESCE("Class Name", 'Unspecified') AS class_name,
        COALESCE("Department Name", 'Unspecified') AS department,
        COUNT(*) AS total_rev,
        SUM(CASE WHEN "Rating" <= 2 THEN 1 ELSE 0 END) AS neg_count,
        SUM(CASE WHEN "Rating" <= 2 AND cause_small = 1 THEN 1 ELSE 0 END) AS small_cnt,
        SUM(CASE WHEN "Rating" <= 2 AND cause_large = 1 THEN 1 ELSE 0 END) AS large_cnt,
        SUM(CASE WHEN "Rating" <= 2 AND cause_prop = 1 THEN 1 ELSE 0 END) AS prop_cnt
    FROM reviews
    WHERE "Rating" <= 2
    GROUP BY "Class Name", "Department Name"
    HAVING COUNT(*) >= 50
    ORDER BY neg_count DESC
    LIMIT 8;
    """)
    class_rows = cursor.fetchall()
    top_classes = [
        {
            "class_name": r[0],
            "department": r[1],
            "negative_reviews": r[3],
            "runs_small": r[4],
            "runs_large": r[5],
            "proportion_length": r[6]
        }
        for r in class_rows
    ]

    # 6. Rating Distribution
    cursor.execute("""
    SELECT "Rating", COUNT(*)
    FROM reviews
    GROUP BY "Rating"
    ORDER BY "Rating" ASC;
    """)
    rating_rows = cursor.fetchall()
    rating_dist = [{"rating": r[0], "count": r[1], "pct": round(r[1]/tot_rev*100, 1)} for r in rating_rows]

    METRICS_CACHE.clear()
    METRICS_CACHE.update({
        "overall": {
            "total_reviews": tot_rev,
            "avg_rating": avg_rat,
            "recommendation_rate_pct": rec_pct,
            "negative_reviews_count": neg_cnt,
            "negative_review_rate_pct": neg_pct,
            "positive_reviews_count": pos_cnt,
            "positive_review_rate_pct": pos_pct,
            "size_fit_complaint_count": fit_neg_cnt,
            "size_fit_complaint_pct": fit_neg_pct
        },
        "root_causes": {
            "runs_small_count": small_cnt,
            "runs_small_pct": small_pct,
            "runs_large_count": large_cnt,
            "runs_large_pct": large_pct,
            "proportion_length_count": prop_cnt,
            "proportion_length_pct": prop_pct
        },
        "departments": departments,
        "age_cohorts": age_cohorts,
        "top_classes": top_classes,
        "rating_distribution": rating_dist
    })

# -----------------------------------------------------------------------------
# Lifespan / Startup Hook
# -----------------------------------------------------------------------------
@app.on_event("startup")
def on_startup():
    try:
        initialize_data()
    except Exception as e:
        print(f"Startup data init warning: {e}")

# -----------------------------------------------------------------------------
# API Endpoints
# -----------------------------------------------------------------------------
@app.get("/api/metrics")
def get_metrics():
    if not METRICS_CACHE:
        initialize_data()
    return JSONResponse(content=METRICS_CACHE)

@app.get("/api/reviews")
def get_reviews(
    department: Optional[str] = None,
    cause: Optional[str] = None,
    search: Optional[str] = None,
    max_rating: int = 2,
    limit: int = 20
):
    if ALL_REVIEWS_DF is None:
        initialize_data()

    df = ALL_REVIEWS_DF[ALL_REVIEWS_DF["Rating"] <= max_rating]

    if department and department != "All":
        df = df[df["Department Name"] == department]

    if cause:
        c = cause.lower()
        if c == "small":
            df = df[df["cause_small"]]
        elif c == "large":
            df = df[df["cause_large"]]
        elif c == "proportion":
            df = df[df["cause_prop"]]
        elif c == "return":
            df = df[df["cause_return"]]

    if search and search.strip():
        q = search.strip().lower()
        df = df[df["Full_Text"].str.contains(q, na=False)]

    records = []
    for _, row in df.head(min(limit, 100)).iterrows():
        badges = []
        if row["cause_small"]:
            badges.append("Runs Small / Tight")
        if row["cause_large"]:
            badges.append("Runs Large / Baggy")
        if row["cause_prop"]:
            badges.append("Proportion / Length")
        if row["cause_return"]:
            badges.append("Return Triggered")

        if not badges:
            badges.append("General Fit Mismatch")

        records.append({
            "clothing_id": int(row["Clothing ID"]) if pd.notna(row["Clothing ID"]) else None,
            "title": str(row["Title"]) if pd.notna(row["Title"]) and str(row["Title"]).strip() else "Customer Review",
            "body": str(row["Review Text"]) if pd.notna(row["Review Text"]) else "No review text provided.",
            "rating": int(row["Rating"]),
            "department": str(row["Department Name"]) if pd.notna(row["Department Name"]) else "Unspecified",
            "class_name": str(row["Class Name"]) if pd.notna(row["Class Name"]) else "Unspecified",
            "age": int(row["Age"]) if pd.notna(row["Age"]) else "N/A",
            "helpful": int(row["Positive Feedback Count"]) if pd.notna(row["Positive Feedback Count"]) else 0,
            "badges": badges
        })

    return JSONResponse(content={
        "total_matching": len(df),
        "limit": limit,
        "reviews": records
    })

# -----------------------------------------------------------------------------
# HTML SPA Dashboard (Tailwind CSS + Chart.js)
# -----------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def serve_dashboard():
    if not METRICS_CACHE:
        initialize_data()

    metrics_json = json.dumps(METRICS_CACHE)

    html_content = f"""<!DOCTYPE html>
<html lang="en" class="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Size & Fit Pain-Point Intelligence | Product Analytics Portfolio</title>
  <!-- Tailwind CSS CDN -->
  <script src="https://cdn.tailwindcss.com"></script>
  <!-- Chart.js CDN -->
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <script>
    tailwind.config = {{
      darkMode: 'class',
      theme: {{
        extend: {{
          colors: {{
            brand: {{
              50: '#eff6ff',
              500: '#3b82f6',
              600: '#2563eb',
              900: '#1e3a8a',
            }}
          }}
        }}
      }}
    }}
  </script>
  <style>
    body {{
      background-color: #0b0f19;
      color: #f3f4f6;
      font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
    }}
    .kpi-card {{
      background: linear-gradient(145deg, #111827 0%, #161f30 100%);
      border: 1px solid #1f2937;
    }}
    .tab-active {{
      border-bottom: 2px solid #ef4444;
      color: #f9fafb;
    }}
    .tab-inactive {{
      border-bottom: 2px solid transparent;
      color: #9ca3af;
    }}
    .tab-inactive:hover {{
      color: #d1d5db;
      border-bottom: 2px solid #374151;
    }}
  </style>
</head>
<body class="min-h-screen flex flex-col">

  <!-- Top Navbar -->
  <header class="border-b border-gray-800 bg-gray-900/80 backdrop-blur sticky top-0 z-50">
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-3.5 flex items-center justify-between">
      <div class="flex items-center space-x-3">
        <span class="text-2xl">👗</span>
        <div>
          <h1 class="text-lg font-bold text-gray-100 leading-tight">Women's Apparel Size & Fit Pain-Point Intelligence</h1>
          <p class="text-xs text-gray-400">Product Analytics & PM Strategy Portfolio | Vercel Serverless Edition</p>
        </div>
      </div>
      <div class="flex items-center space-x-3">
        <a href="https://github.com/Charan-Kadamati" target="_blank" class="text-xs bg-gray-800 hover:bg-gray-700 text-gray-300 px-3 py-1.5 rounded-lg border border-gray-700 flex items-center gap-1.5 transition">
          <svg class="w-4 h-4 fill-current" viewBox="0 0 24 24"><path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z"/></svg>
          GitHub Profile
        </a>
      </div>
    </div>
  </header>

  <!-- Navigation Tabs -->
  <div class="border-b border-gray-800 bg-gray-900/40">
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
      <nav class="flex space-x-8" aria-label="Tabs">
        <button onclick="switchTab(1)" id="tab-btn-1" class="tab-active py-4 px-1 text-sm font-semibold flex items-center gap-2 transition">
          📊 <span>Executive KPI Overview</span>
        </button>
        <button onclick="switchTab(2)" id="tab-btn-2" class="tab-inactive py-4 px-1 text-sm font-semibold flex items-center gap-2 transition">
          🔬 <span>Size & Fit Root-Cause Deep Dive</span>
        </button>
        <button onclick="switchTab(3)" id="tab-btn-3" class="tab-inactive py-4 px-1 text-sm font-semibold flex items-center gap-2 transition">
          🚀 <span>Product Proposal & A/B Test Simulator</span>
        </button>
      </nav>
    </div>
  </div>

  <!-- Main Container -->
  <main class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 flex-1 w-full">

    <!-- ===================================================================== -->
    <!-- TAB 1: Executive KPI Overview -->
    <!-- ===================================================================== -->
    <div id="tab-content-1" class="space-y-8">
      <!-- 4 KPI Cards -->
      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
        <div class="kpi-card p-5 rounded-xl shadow-lg">
          <p class="text-xs font-semibold uppercase tracking-wider text-gray-400">Total Reviews Analyzed</p>
          <p class="text-3xl font-bold text-gray-100 mt-2" id="kpi-total">23,486</p>
          <p class="text-xs text-gray-500 mt-1">Full verified catalog volume</p>
        </div>
        <div class="kpi-card p-5 rounded-xl shadow-lg">
          <p class="text-xs font-semibold uppercase tracking-wider text-gray-400">Average Rating</p>
          <p class="text-3xl font-bold text-gray-100 mt-2 flex items-center gap-1.5">
            <span id="kpi-rating">4.20</span>
            <span class="text-amber-400 text-xl">★</span>
          </p>
          <p class="text-xs text-gray-500 mt-1">Catalog baseline score (out of 5)</p>
        </div>
        <div class="kpi-card p-5 rounded-xl shadow-lg">
          <p class="text-xs font-semibold uppercase tracking-wider text-gray-400">Recommendation Rate</p>
          <p class="text-3xl font-bold text-gray-100 mt-2" id="kpi-rec">82.2%</p>
          <p class="text-xs text-gray-500 mt-1">Customers recommending purchase</p>
        </div>
        <div class="kpi-card p-5 rounded-xl shadow-lg border-l-4 border-l-red-500">
          <p class="text-xs font-semibold uppercase tracking-wider text-gray-400">Size/Fit Share in Negatives</p>
          <p class="text-3xl font-bold text-red-500 mt-2" id="kpi-fit">76.4%</p>
          <p class="text-xs text-gray-500 mt-1">1,839 of 2,407 1-2★ reviews cite fit</p>
        </div>
      </div>

      <!-- Executive Callout Banner -->
      <div class="bg-blue-950/40 border border-blue-800/60 rounded-xl p-4 text-sm text-blue-200 flex items-start gap-3">
        <span class="text-xl">💡</span>
        <div>
          <strong class="text-blue-100">Executive Takeaway:</strong> While the platform maintains an overall <strong class="text-white">82.2% recommendation rate</strong>, <strong class="text-red-400">76.4% of all dissatisfied reviews (1-2★)</strong> explicitly pinpoint sizing, proportion, and fit failure. Sizing ambiguity is the single largest driver of customer returns and unit margin erosion.
        </div>
      </div>

      <!-- Two Column Charts -->
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <!-- Department Negative Review Rate Chart -->
        <div class="kpi-card p-6 rounded-xl shadow-lg">
          <h3 class="text-base font-bold text-gray-100 mb-1">Department Vulnerability & Negative Rate</h3>
          <p class="text-xs text-gray-400 mb-4">% of reviews rated 1-2 stars by department</p>
          <div class="h-72">
            <canvas id="chart-dept"></canvas>
          </div>
        </div>

        <!-- Age Cohorts Chart -->
        <div class="kpi-card p-6 rounded-xl shadow-lg">
          <h3 class="text-base font-bold text-gray-100 mb-1">Customer Age Cohort Sentiment</h3>
          <p class="text-xs text-gray-400 mb-4">Recommendation Rate (%) vs. Negative Review Rate (%)</p>
          <div class="h-72">
            <canvas id="chart-cohort"></canvas>
          </div>
        </div>
      </div>

      <!-- Rating Distribution -->
      <div class="kpi-card p-6 rounded-xl shadow-lg">
        <h3 class="text-base font-bold text-gray-100 mb-1">Star Rating Volume & Sentiment Distribution</h3>
        <p class="text-xs text-gray-400 mb-4">Review distribution from 1 to 5 stars</p>
        <div class="h-64">
          <canvas id="chart-ratings"></canvas>
        </div>
      </div>
    </div>

    <!-- ===================================================================== -->
    <!-- TAB 2: Size & Fit Root-Cause Deep Dive -->
    <!-- ===================================================================== -->
    <div id="tab-content-2" class="hidden space-y-8">
      <div>
        <h2 class="text-xl font-bold text-gray-100">🔬 Size & Fit Root-Cause Classification (Negative Reviews)</h2>
        <p class="text-sm text-gray-400 mt-1">Granular natural-language failure modes inside 1-2 star reviews: Runs Small, Runs Large, and Proportion/Length Discrepancy.</p>
      </div>

      <!-- Root cause breakdown -->
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <!-- Donut Chart -->
        <div class="kpi-card p-6 rounded-xl shadow-lg flex flex-col items-center">
          <h3 class="text-base font-bold text-gray-100 mb-4 self-start">Root Cause Distribution in Negative Reviews</h3>
          <div class="h-64 w-64 relative flex items-center justify-center">
            <canvas id="chart-donut"></canvas>
          </div>
        </div>

        <!-- Analytical Breakdown Card -->
        <div class="kpi-card p-6 rounded-xl shadow-lg flex flex-col justify-between">
          <div>
            <h3 class="text-base font-bold text-gray-100 mb-3">📋 Root Cause Analytical Summary</h3>
            <ul class="space-y-3.5 text-sm">
              <li class="flex items-start gap-2.5">
                <span class="w-3 h-3 rounded-full bg-red-500 mt-1 flex-shrink-0"></span>
                <div>
                  <strong class="text-gray-100">'Runs Small' / Tight Mismatch:</strong>
                  <span class="text-red-400 font-semibold">655 reviews (27.2%)</span>
                  <p class="text-xs text-gray-400 mt-0.5">Severe constriction across chest, waist, and armpits forcing returns.</p>
                </div>
              </li>
              <li class="flex items-start gap-2.5">
                <span class="w-3 h-3 rounded-full bg-blue-500 mt-1 flex-shrink-0"></span>
                <div>
                  <strong class="text-gray-100">'Runs Large' / Loose Silhouette:</strong>
                  <span class="text-blue-400 font-semibold">636 reviews (26.4%)</span>
                  <p class="text-xs text-gray-400 mt-0.5">Shapeless, oversized cuts requiring customers to downsize 1–2 tiers.</p>
                </div>
              </li>
              <li class="flex items-start gap-2.5">
                <span class="w-3 h-3 rounded-full bg-amber-500 mt-1 flex-shrink-0"></span>
                <div>
                  <strong class="text-gray-100">'Proportion / Length' Mismatch:</strong>
                  <span class="text-amber-400 font-semibold">1,060 reviews (44.0%)</span>
                  <p class="text-xs text-gray-400 mt-0.5">The #1 failure mode: awkward hem drags, ill-placed waists, and torso length flaws.</p>
                </div>
              </li>
            </ul>
          </div>
          <div class="mt-6 pt-4 border-t border-gray-800 text-xs text-gray-400">
            <strong class="text-gray-200">Category Vulnerability:</strong> Dresses represent the highest volume of fit complaints (<strong class="text-white">546</strong> complaints; 79.3% of negative dress reviews).
          </div>
        </div>
      </div>

      <!-- Stacked Bar Chart for Classes -->
      <div class="kpi-card p-6 rounded-xl shadow-lg">
        <h3 class="text-base font-bold text-gray-100 mb-1">Root Cause Breakdown by Product Class</h3>
        <p class="text-xs text-gray-400 mb-4">Volume of small vs large vs proportion issues across leading product classes</p>
        <div class="h-72">
          <canvas id="chart-classes"></canvas>
        </div>
      </div>

      <!-- Searchable Negative Review Explorer -->
      <div class="kpi-card p-6 rounded-xl shadow-lg space-y-5">
        <div class="border-b border-gray-800 pb-4">
          <h3 class="text-lg font-bold text-gray-100">🔎 Searchable Negative Customer Review Explorer</h3>
          <p class="text-xs text-gray-400 mt-0.5">Filter actual 1-2 star customer reviews by keyword, fit mode, or apparel department.</p>
        </div>

        <!-- Filter Controls -->
        <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <label class="block text-xs font-semibold text-gray-400 mb-1">Search Keywords</label>
            <input type="text" id="review-search" oninput="debounceFetchReviews()" placeholder="e.g. tight, shoulders, petite, return..." class="w-full bg-gray-800 border border-gray-700 rounded-lg px-3.5 py-2 text-sm text-gray-100 focus:outline-none focus:border-blue-500">
          </div>
          <div>
            <label class="block text-xs font-semibold text-gray-400 mb-1">Fit Failure Mode</label>
            <select id="review-cause" onchange="fetchReviews()" class="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-100 focus:outline-none focus:border-blue-500">
              <option value="">All Negative Reviews</option>
              <option value="small">Runs Small / Tight</option>
              <option value="large">Runs Large / Baggy</option>
              <option value="proportion">Proportion / Length</option>
              <option value="return">Return Triggered</option>
            </select>
          </div>
          <div>
            <label class="block text-xs font-semibold text-gray-400 mb-1">Department</label>
            <select id="review-dept" onchange="fetchReviews()" class="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-100 focus:outline-none focus:border-blue-500">
              <option value="All">All Departments</option>
              <option value="Dresses">Dresses</option>
              <option value="Tops">Tops</option>
              <option value="Bottoms">Bottoms</option>
              <option value="Jackets">Jackets</option>
              <option value="Intimate">Intimate</option>
              <option value="Trend">Trend</option>
            </select>
          </div>
        </div>

        <div id="reviews-count" class="text-xs text-gray-400 font-medium">Loading customer reviews...</div>

        <!-- Review Cards Container -->
        <div id="reviews-list" class="space-y-3 pt-2">
          <!-- Dynamic cards injected via JS -->
        </div>
      </div>
    </div>

    <!-- ===================================================================== -->
    <!-- TAB 3: Product Proposal & A/B Test Simulator -->
    <!-- ===================================================================== -->
    <div id="tab-content-3" class="hidden space-y-8">
      <div>
        <h2 class="text-xl font-bold text-gray-100">🚀 Feature Proposal: Smart Size & Fit Guidance (PDP Widget)</h2>
        <p class="text-sm text-gray-400 mt-1">Based on empirical review data showing that <strong class="text-red-400">76.4% of negative reviews relate to sizing uncertainty</strong>, we propose deploying an AI-assisted Smart Size & Fit Assistant directly on the Product Detail Page.</p>
      </div>

      <!-- ROI Simulator Box -->
      <div class="kpi-card p-6 rounded-xl shadow-lg space-y-6">
        <div>
          <h3 class="text-lg font-bold text-gray-100">🧮 Interactive Return Reduction & Business ROI Simulator</h3>
          <p class="text-xs text-gray-400 mt-0.5">Adjust brand volume and operational levers to project net savings from reducing size-related returns:</p>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div class="space-y-4">
            <div>
              <div class="flex justify-between text-xs text-gray-300 font-semibold mb-1">
                <span>Annual Apparel GMV ($)</span>
                <span id="label-gmv" class="text-blue-400 font-mono">$25,000,000</span>
              </div>
              <input type="range" id="input-gmv" min="5000000" max="100000000" step="1000000" value="25000000" oninput="calculateROI()" class="w-full h-1.5 bg-gray-700 rounded-lg appearance-none cursor-pointer accent-blue-500">
            </div>
            <div>
              <div class="flex justify-between text-xs text-gray-300 font-semibold mb-1">
                <span>Average Order Value ($)</span>
                <span id="label-aov" class="text-blue-400 font-mono">$115</span>
              </div>
              <input type="range" id="input-aov" min="40" max="250" step="5" value="115" oninput="calculateROI()" class="w-full h-1.5 bg-gray-700 rounded-lg appearance-none cursor-pointer accent-blue-500">
            </div>
          </div>

          <div class="space-y-4">
            <div>
              <div class="flex justify-between text-xs text-gray-300 font-semibold mb-1">
                <span>Baseline Return Rate (%)</span>
                <span id="label-ret-rate" class="text-red-400 font-mono">28.0%</span>
              </div>
              <input type="range" id="input-ret-rate" min="15" max="45" step="0.5" value="28.0" oninput="calculateROI()" class="w-full h-1.5 bg-gray-700 rounded-lg appearance-none cursor-pointer accent-red-500">
            </div>
            <div>
              <div class="flex justify-between text-xs text-gray-300 font-semibold mb-1">
                <span>Returns Due to Size/Fit (%)</span>
                <span id="label-fit-share" class="text-red-400 font-mono">76.4%</span>
              </div>
              <input type="range" id="input-fit-share" min="40" max="90" step="0.5" value="76.4" oninput="calculateROI()" class="w-full h-1.5 bg-gray-700 rounded-lg appearance-none cursor-pointer accent-red-500">
            </div>
          </div>

          <div class="space-y-4">
            <div>
              <div class="flex justify-between text-xs text-gray-300 font-semibold mb-1">
                <span>Target Return Reduction (%)</span>
                <span id="label-reduction" class="text-emerald-400 font-mono">20.0%</span>
              </div>
              <input type="range" id="input-reduction" min="5" max="40" step="1" value="20.0" oninput="calculateROI()" class="w-full h-1.5 bg-gray-700 rounded-lg appearance-none cursor-pointer accent-emerald-500">
            </div>
            <div>
              <div class="flex justify-between text-xs text-gray-300 font-semibold mb-1">
                <span>Reverse Logistics Cost / Return ($)</span>
                <span id="label-cost" class="text-emerald-400 font-mono">$15.00</span>
              </div>
              <input type="range" id="input-cost" min="8" max="35" step="1" value="15.0" oninput="calculateROI()" class="w-full h-1.5 bg-gray-700 rounded-lg appearance-none cursor-pointer accent-emerald-500">
            </div>
          </div>
        </div>

        <!-- Calculated Output Cards -->
        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 pt-4 border-t border-gray-800">
          <div class="bg-gray-950 p-4 rounded-xl border-l-4 border-l-emerald-500">
            <p class="text-xs uppercase font-semibold text-gray-400">Avoided Returns</p>
            <p id="out-returns" class="text-2xl font-bold text-emerald-400 mt-1">9,300</p>
            <p class="text-xs text-gray-500 mt-0.5">Fewer return packages processed</p>
          </div>
          <div class="bg-gray-950 p-4 rounded-xl border-l-4 border-l-emerald-500">
            <p class="text-xs uppercase font-semibold text-gray-400">Logistics Cost Savings</p>
            <p id="out-logistics" class="text-2xl font-bold text-emerald-400 mt-1">$139,513</p>
            <p class="text-xs text-gray-500 mt-0.5">Direct freight & restocking saved</p>
          </div>
          <div class="bg-gray-950 p-4 rounded-xl border-l-4 border-l-blue-500">
            <p class="text-xs uppercase font-semibold text-gray-400">Retained Net Sales</p>
            <p id="out-sales" class="text-2xl font-bold text-blue-400 mt-1">$1,069,600</p>
            <p class="text-xs text-gray-500 mt-0.5">Revenue kept vs refunded</p>
          </div>
          <div class="bg-gray-950 p-4 rounded-xl border-l-4 border-l-gray-600">
            <p class="text-xs uppercase font-semibold text-gray-400">Projected Return Rate</p>
            <p id="out-rate" class="text-2xl font-bold text-gray-100 mt-1">23.72%</p>
            <p class="text-xs text-gray-500 mt-0.5">Down from 28.0% baseline</p>
          </div>
        </div>
      </div>

      <!-- PRD Accordions -->
      <div class="space-y-4">
        <h3 class="text-lg font-bold text-gray-100">📄 Product Requirements Document (PRD) Specifications</h3>

        <!-- Accordion 1 -->
        <details open class="kpi-card rounded-xl p-5 group cursor-pointer">
          <summary class="text-sm font-bold text-gray-200 flex justify-between items-center select-none">
            <span>1. Executive Summary & Problem Validation</span>
            <span class="text-gray-400 group-open:rotate-180 transition-transform">▼</span>
          </summary>
          <div class="mt-4 text-xs text-gray-300 space-y-2 border-t border-gray-800 pt-3 leading-relaxed">
            <p>• <strong class="text-gray-100">Problem:</strong> Analysis of 23,486 clothing reviews proves that <strong class="text-red-400">76.4% of dissatisfied customer reviews (1-2★)</strong> cite sizing or fit failure as the primary reason for rating a garment poorly.</p>
            <p>• <strong class="text-gray-100">Commercial Friction:</strong> Sizing mismatch drives high return rates (~28%), damages customer lifetime value, and leads to costly "bracketing" (ordering multiple sizes intending to return all but one).</p>
            <p>• <strong class="text-gray-100">Proposed Solution:</strong> A low-friction, data-driven Product Detail Page widget ("Smart Size & Fit Assistant") combining crowd-sourced consensus gauges and body profile matching.</p>
          </div>
        </details>

        <!-- Accordion 2 -->
        <details class="kpi-card rounded-xl p-5 group cursor-pointer">
          <summary class="text-sm font-bold text-gray-200 flex justify-between items-center select-none">
            <span>2. Target User Personas</span>
            <span class="text-gray-400 group-open:rotate-180 transition-transform">▼</span>
          </summary>
          <div class="mt-4 text-xs text-gray-300 space-y-3 border-t border-gray-800 pt-3 leading-relaxed">
            <div>
              <strong class="text-blue-400">1. Maya, 29 (The Hesitant First-Time Shopper):</strong>
              <p class="text-gray-400 mt-0.5">Loves a dress but hesitates to purchase due to vanity sizing across brands. Needs instant consensus feedback on whether the dress runs small or true to size.</p>
            </div>
            <div>
              <strong class="text-blue-400">2. Claire, 42 (The Multi-Size Bracketing Buyer):</strong>
              <p class="text-gray-400 mt-0.5">Time-poor professional who orders both Medium and Large to ensure a fit, incurring high return overhead. Needs personalized size matching.</p>
            </div>
            <div>
              <strong class="text-blue-400">3. Elena, 54 (The Proportion-Sensitive Shopper):</strong>
              <p class="text-gray-400 mt-0.5">Highly conscious of hem lengths, armhole tightness, and torso fit. Needs contextual alerts for styles running exceptionally long or short.</p>
            </div>
          </div>
        </details>

        <!-- Accordion 3 -->
        <details class="kpi-card rounded-xl p-5 group cursor-pointer">
          <summary class="text-sm font-bold text-gray-200 flex justify-between items-center select-none">
            <span>3. Functional Requirements (P0 / P1)</span>
            <span class="text-gray-400 group-open:rotate-180 transition-transform">▼</span>
          </summary>
          <div class="mt-4 overflow-x-auto border-t border-gray-800 pt-3">
            <table class="w-full text-left text-xs text-gray-300 border-collapse">
              <thead>
                <tr class="border-b border-gray-800 text-gray-400">
                  <th class="py-2 pr-4 font-semibold">Priority</th>
                  <th class="py-2 pr-4 font-semibold">Feature Component</th>
                  <th class="py-2 font-semibold">Functional Specification</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-gray-800">
                <tr>
                  <td class="py-2.5 pr-4 font-bold text-red-400">P0</td>
                  <td class="py-2.5 pr-4 font-semibold text-gray-100">Aggregated Fit Gauge</td>
                  <td class="py-2.5 text-gray-400">Real-time slider on PDP showing <em>"Runs True to Size (72%)"</em>, <em>"Runs Small (21%)"</em>, <em>"Runs Large (7%)"</em>.</td>
                </tr>
                <tr>
                  <td class="py-2.5 pr-4 font-bold text-red-400">P0</td>
                  <td class="py-2.5 pr-4 font-semibold text-gray-100">1-Click Fit Predictor</td>
                  <td class="py-2.5 text-gray-400">Modal accepting height, weight, and fit preference to output recommended size with confidence rating.</td>
                </tr>
                <tr>
                  <td class="py-2.5 pr-4 font-bold text-amber-400">P1</td>
                  <td class="py-2.5 pr-4 font-semibold text-gray-100">Review Filter by Body Twin</td>
                  <td class="py-2.5 text-gray-400">Filter customer review stream by customer age, height range, and cup/waist measurements.</td>
                </tr>
                <tr>
                  <td class="py-2.5 pr-4 font-bold text-amber-400">P1</td>
                  <td class="py-2.5 pr-4 font-semibold text-gray-100">Proportion Alert Badges</td>
                  <td class="py-2.5 text-gray-400">Contextual warnings when &gt;30% of reviews note a style runs long, short, or narrow in the bust.</td>
                </tr>
              </tbody>
            </table>
          </div>
        </details>

        <!-- Accordion 4 -->
        <details class="kpi-card rounded-xl p-5 group cursor-pointer">
          <summary class="text-sm font-bold text-gray-200 flex justify-between items-center select-none">
            <span>4. A/B Testing & Experimentation Roadmap</span>
            <span class="text-gray-400 group-open:rotate-180 transition-transform">▼</span>
          </summary>
          <div class="mt-4 text-xs text-gray-300 space-y-2 border-t border-gray-800 pt-3 leading-relaxed">
            <p>• <strong class="text-gray-100">Design:</strong> Randomized Controlled Trial (50/50 split) across web & mobile PDPs for 4 weeks.</p>
            <p>• <strong class="text-gray-100">Control (A):</strong> Standard PDP with static alphanumeric size guide modal.</p>
            <p>• <strong class="text-gray-100">Treatment (B):</strong> PDP with Smart Size & Fit Guidance Widget and Dynamic Consensus Meter.</p>
            <p>• <strong class="text-gray-100">Primary Success Metric:</strong> Size-Related Return Rate — Target <strong class="text-emerald-400">-15% to -20% reduction</strong> (p &lt; 0.01).</p>
            <p>• <strong class="text-gray-100">Guardrail Metric:</strong> PDP-to-Cart Conversion Rate (&ge; 0.0% non-inferiority).</p>
          </div>
        </details>
      </div>
    </div>
  </main>

  <!-- Footer -->
  <footer class="border-t border-gray-800 bg-gray-900/50 py-5 text-center text-xs text-gray-500">
    Product Analytics Portfolio Project | Built with FastAPI, SQLite, Tailwind CSS & Chart.js | Deployable on Vercel
  </footer>

  <!-- Client-side Logic & Data Initialization -->
  <script>
    const metricsData = {metrics_json};

    // Tab Switching
    function switchTab(tabId) {{
      for (let i = 1; i <= 3; i++) {{
        const btn = document.getElementById('tab-btn-' + i);
        const content = document.getElementById('tab-content-' + i);
        if (i === tabId) {{
          btn.className = 'tab-active py-4 px-1 text-sm font-semibold flex items-center gap-2 transition';
          content.classList.remove('hidden');
        }} else {{
          btn.className = 'tab-inactive py-4 px-1 text-sm font-semibold flex items-center gap-2 transition';
          content.classList.add('hidden');
        }}
      }}
      if (tabId === 2 && !window.reviewsLoaded) {{
        fetchReviews();
      }}
    }}

    // Render Charts on Load
    window.addEventListener('DOMContentLoaded', () => {{
      renderCharts();
      calculateROI();
    }});

    function renderCharts() {{
      // Chart 1: Department Negative Rate
      const depts = metricsData.departments || [];
      new Chart(document.getElementById('chart-dept'), {{
        type: 'bar',
        data: {{
          labels: depts.map(d => d.department),
          datasets: [{{
            label: 'Negative Review Rate (%)',
            data: depts.map(d => d.negative_review_rate_pct),
            backgroundColor: depts.map(d => d.negative_review_rate_pct > 15 ? '#ef4444' : d.negative_review_rate_pct > 10 ? '#f87171' : '#fca5a5'),
            borderRadius: 6
          }}]
        }},
        options: {{
          responsive: true,
          maintainAspectRatio: false,
          plugins: {{
            legend: {{ display: false }},
            tooltip: {{
              callbacks: {{
                afterBody: (items) => {{
                  const idx = items[0].dataIndex;
                  return 'Total Reviews: ' + depts[idx].total_reviews.toLocaleString() + '\\nFit Share in Neg: ' + depts[idx].fit_in_neg_pct + '%';
                }}
              }}
            }}
          }},
          scales: {{
            y: {{
              beginAtZero: true,
              grid: {{ color: '#1f2937' }},
              ticks: {{ color: '#9ca3af', callback: v => v + '%' }}
            }},
            x: {{
              grid: {{ display: false }},
              ticks: {{ color: '#9ca3af' }}
            }}
          }}
        }}
      }});

      // Chart 2: Age Cohorts
      const cohorts = metricsData.age_cohorts || [];
      new Chart(document.getElementById('chart-cohort'), {{
        data: {{
          labels: cohorts.map(c => c.cohort),
          datasets: [
            {{
              type: 'bar',
              label: 'Recommendation Rate (%)',
              data: cohorts.map(c => c.recommendation_rate_pct),
              backgroundColor: '#3b82f6',
              yAxisID: 'y',
              borderRadius: 6
            }},
            {{
              type: 'line',
              label: 'Negative Review Rate (%)',
              data: cohorts.map(c => c.negative_review_rate_pct),
              borderColor: '#ef4444',
              backgroundColor: '#ef4444',
              borderWidth: 3,
              pointRadius: 5,
              yAxisID: 'y1'
            }}
          ]
        }},
        options: {{
          responsive: true,
          maintainAspectRatio: false,
          plugins: {{
            legend: {{ labels: {{ color: '#9ca3af' }} }}
          }},
          scales: {{
            y: {{
              type: 'linear',
              position: 'left',
              min: 60,
              max: 100,
              grid: {{ color: '#1f2937' }},
              ticks: {{ color: '#9ca3af', callback: v => v + '%' }}
            }},
            y1: {{
              type: 'linear',
              position: 'right',
              min: 0,
              max: 20,
              grid: {{ display: false }},
              ticks: {{ color: '#ef4444', callback: v => v + '%' }}
            }},
            x: {{
              grid: {{ display: false }},
              ticks: {{ color: '#9ca3af' }}
            }}
          }}
        }}
      }});

      // Chart 3: Star Rating Distribution
      const dist = metricsData.rating_distribution || [];
      new Chart(document.getElementById('chart-ratings'), {{
        type: 'bar',
        data: {{
          labels: dist.map(d => d.rating + ' ★'),
          datasets: [{{
            label: 'Review Count',
            data: dist.map(d => d.count),
            backgroundColor: ['#ef4444', '#f97316', '#eab308', '#84cc16', '#10b981'],
            borderRadius: 6
          }}]
        }},
        options: {{
          responsive: true,
          maintainAspectRatio: false,
          plugins: {{
            legend: {{ display: false }},
            tooltip: {{
              callbacks: {{
                afterBody: items => 'Share: ' + dist[items[0].dataIndex].pct + '%'
              }}
            }}
          }},
          scales: {{
            y: {{
              beginAtZero: true,
              grid: {{ color: '#1f2937' }},
              ticks: {{ color: '#9ca3af', callback: v => v.toLocaleString() }}
            }},
            x: {{
              grid: {{ display: false }},
              ticks: {{ color: '#9ca3af' }}
            }}
          }}
        }}
      }});

      // Chart 4: Root Cause Donut
      const rc = metricsData.root_causes || {{}};
      new Chart(document.getElementById('chart-donut'), {{
        type: 'doughnut',
        data: {{
          labels: ['Runs Small / Tight', 'Runs Large / Baggy', 'Proportion / Length'],
          datasets: [{{
            data: [rc.runs_small_count || 655, rc.runs_large_count || 636, rc.proportion_length_count || 1060],
            backgroundColor: ['#ef4444', '#3b82f6', '#f59e0b'],
            borderWidth: 0
          }}]
        }},
        options: {{
          responsive: true,
          maintainAspectRatio: false,
          plugins: {{
            legend: {{
              position: 'bottom',
              labels: {{ color: '#9ca3af', font: {{ size: 11 }} }}
            }}
          }},
          cutout: '68%'
        }}
      }});

      // Chart 5: Stacked Classes Breakdown
      const classes = metricsData.top_classes || [];
      new Chart(document.getElementById('chart-classes'), {{
        type: 'bar',
        data: {{
          labels: classes.map(c => c.class_name),
          datasets: [
            {{
              label: 'Runs Small / Tight',
              data: classes.map(c => c.runs_small),
              backgroundColor: '#ef4444'
            }},
            {{
              label: 'Runs Large / Baggy',
              data: classes.map(c => c.runs_large),
              backgroundColor: '#3b82f6'
            }},
            {{
              label: 'Proportion / Length',
              data: classes.map(c => c.proportion_length),
              backgroundColor: '#f59e0b'
            }}
          ]
        }},
        options: {{
          responsive: true,
          maintainAspectRatio: false,
          plugins: {{
            legend: {{ labels: {{ color: '#9ca3af' }} }}
          }},
          scales: {{
            x: {{
              stacked: true,
              grid: {{ display: false }},
              ticks: {{ color: '#9ca3af' }}
            }},
            y: {{
              stacked: true,
              grid: {{ color: '#1f2937' }},
              ticks: {{ color: '#9ca3af' }}
            }}
          }}
        }}
      }});
    }}

    // ROI Simulator Calculation
    function calculateROI() {{
      const gmv = parseFloat(document.getElementById('input-gmv').value);
      const aov = parseFloat(document.getElementById('input-aov').value);
      const retRate = parseFloat(document.getElementById('input-ret-rate').value);
      const fitShare = parseFloat(document.getElementById('input-fit-share').value);
      const reduction = parseFloat(document.getElementById('input-reduction').value);
      const cost = parseFloat(document.getElementById('input-cost').value);

      document.getElementById('label-gmv').innerText = '$' + Number(gmv).toLocaleString();
      document.getElementById('label-aov').innerText = '$' + Number(aov).toLocaleString();
      document.getElementById('label-ret-rate').innerText = retRate.toFixed(1) + '%';
      document.getElementById('label-fit-share').innerText = fitShare.toFixed(1) + '%';
      document.getElementById('label-reduction').innerText = reduction.toFixed(1) + '%';
      document.getElementById('label-cost').innerText = '$' + cost.toFixed(2);

      const totalOrders = gmv / aov;
      const totalReturns = totalOrders * (retRate / 100);
      const fitReturns = totalReturns * (fitShare / 100);

      const avoided = fitReturns * (reduction / 100);
      const logisticsSaved = avoided * cost;
      const salesSaved = avoided * aov;
      const newRate = ((totalReturns - avoided) / totalOrders) * 100;

      document.getElementById('out-returns').innerText = Math.round(avoided).toLocaleString();
      document.getElementById('out-logistics').innerText = '$' + Math.round(logisticsSaved).toLocaleString();
      document.getElementById('out-sales').innerText = '$' + Math.round(salesSaved).toLocaleString();
      document.getElementById('out-rate').innerText = newRate.toFixed(2) + '%';
    }}

    // Reviews Fetching & Rendering
    let debounceTimer = null;
    function debounceFetchReviews() {{
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(fetchReviews, 300);
    }}

    async function fetchReviews() {{
      const search = document.getElementById('review-search').value;
      const cause = document.getElementById('review-cause').value;
      const dept = document.getElementById('review-dept').value;

      const params = new URLSearchParams();
      if (search) params.set('search', search);
      if (cause) params.set('cause', cause);
      if (dept && dept !== 'All') params.set('department', dept);
      params.set('limit', '25');

      const countEl = document.getElementById('reviews-count');
      const listEl = document.getElementById('reviews-list');
      countEl.innerText = 'Searching customer feedback...';

      try {{
        const res = await fetch('/api/reviews?' + params.toString());
        const data = await res.json();
        window.reviewsLoaded = true;

        countEl.innerHTML = `Showing <strong>${{data.reviews.length}}</strong> of <strong>${{data.total_matching.toLocaleString()}}</strong> matching negative reviews:`;

        if (data.reviews.length === 0) {{
          listEl.innerHTML = `<div class="bg-gray-900 border border-gray-800 rounded-xl p-8 text-center text-sm text-gray-400">No reviews found matching your search. Try a broader search term like 'fit', 'tight', or 'size'.</div>`;
          return;
        }}

        listEl.innerHTML = data.reviews.map(r => {{
          const stars = '★'.repeat(r.rating) + '☆'.repeat(5 - r.rating);
          const badgesHtml = r.badges.map(b => {{
            if (b.includes('Small')) return `<span class="bg-red-500/15 text-red-400 border border-red-500/30 px-2.5 py-0.5 rounded-full text-xs font-semibold">${{b}}</span>`;
            if (b.includes('Large')) return `<span class="bg-blue-500/15 text-blue-400 border border-blue-500/30 px-2.5 py-0.5 rounded-full text-xs font-semibold">${{b}}</span>`;
            if (b.includes('Proportion')) return `<span class="bg-amber-500/15 text-amber-400 border border-amber-500/30 px-2.5 py-0.5 rounded-full text-xs font-semibold">${{b}}</span>`;
            if (b.includes('Return')) return `<span class="bg-rose-500/20 text-rose-300 border border-rose-500/40 px-2.5 py-0.5 rounded-full text-xs font-semibold">${{b}}</span>`;
            return `<span class="bg-gray-800 text-gray-400 border border-gray-700 px-2.5 py-0.5 rounded-full text-xs font-semibold">${{b}}</span>`;
          }}).join(' ');

          return `
            <div class="kpi-card p-4 rounded-xl shadow border border-gray-800 space-y-2">
              <div class="flex items-center justify-between">
                <span class="font-bold text-gray-100 text-sm">${{escapeHtml(r.title)}}</span>
                <span class="text-red-500 font-bold text-sm tracking-wider">${{stars}} (${{r.rating}}/5)</span>
              </div>
              <p class="text-xs text-gray-300 leading-relaxed font-normal">"${{escapeHtml(r.body)}}"</p>
              <div class="flex flex-wrap items-center justify-between gap-2 pt-2 border-t border-gray-800/60">
                <span class="text-[11px] text-gray-400">
                  <strong>Dept:</strong> ${{escapeHtml(r.department)}} &nbsp;|&nbsp;
                  <strong>Class:</strong> ${{escapeHtml(r.class_name)}} &nbsp;|&nbsp;
                  <strong>Age:</strong> ${{r.age}} &nbsp;|&nbsp;
                  👍 <strong>Helpful:</strong> ${{r.helpful}}
                </span>
                <div class="flex flex-wrap gap-1.5">${{badgesHtml}}</div>
              </div>
            </div>
          `;
        }}).join('');

      }} catch (err) {{
        countEl.innerText = 'Error loading reviews.';
        listEl.innerHTML = `<div class="text-red-400 text-xs">Failed to fetch reviews: ${{err.message}}</div>`;
      }}
    }}

    function escapeHtml(str) {{
      if (!str) return '';
      return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
    }}
  </script>
</body>
</html>
"""
    return HTMLResponse(content=html_content)
