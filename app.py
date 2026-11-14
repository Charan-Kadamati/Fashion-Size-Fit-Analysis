import os
import sqlite3
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# -----------------------------------------------------------------------------
# Configuration & Page Setup
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Size & Fit Pain-Point Intelligence | Product Analytics",
    page_icon="👗",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Styling (Theme-Adaptive for Light & Dark Modes)
st.markdown("""
<style>
    /* Theme-adaptive header typography */
    .main-header {
        font-size: 2.2rem;
        font-weight: 800;
        letter-spacing: -0.02em;
        color: var(--text-color, #FAFAFA) !important;
        margin-top: 0;
        margin-bottom: 0.25rem;
        line-height: 1.2;
    }
    .sub-header {
        font-size: 1.05rem;
        color: var(--text-color, #94A3B8) !important;
        opacity: 0.85;
        margin-bottom: 1.5rem;
        line-height: 1.45;
    }

    /* Executive KPI Cards */
    .kpi-card {
        background-color: var(--secondary-background-color, rgba(255, 255, 255, 0.05));
        border: 1px solid rgba(128, 128, 128, 0.22);
        border-radius: 12px;
        padding: 18px 20px;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
        transition: transform 0.15s ease-in-out, box-shadow 0.15s ease-in-out;
        min-height: 120px;
    }
    .kpi-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 14px rgba(0, 0, 0, 0.08);
    }
    .kpi-title {
        font-size: 0.8rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: var(--text-color, #94A3B8);
        opacity: 0.8;
        margin-bottom: 4px;
    }
    .kpi-value {
        font-size: 2.1rem;
        font-weight: 700;
        color: var(--text-color, #F8FAFC);
        line-height: 1.15;
    }
    .kpi-caption {
        font-size: 0.8rem;
        color: var(--text-color, #94A3B8);
        opacity: 0.7;
        margin-top: 6px;
    }

    /* Status Badges with High-Contrast Translucency */
    .badge-danger {
        background-color: rgba(239, 68, 68, 0.18);
        color: #F87171 !important;
        border: 1px solid rgba(239, 68, 68, 0.35);
        padding: 3px 9px;
        border-radius: 9999px;
        font-size: 0.75rem;
        font-weight: 600;
        display: inline-block;
        margin: 2px 3px;
    }
    .badge-info {
        background-color: rgba(59, 130, 246, 0.18);
        color: #60A5FA !important;
        border: 1px solid rgba(59, 130, 246, 0.35);
        padding: 3px 9px;
        border-radius: 9999px;
        font-size: 0.75rem;
        font-weight: 600;
        display: inline-block;
        margin: 2px 3px;
    }
    .badge-warning {
        background-color: rgba(245, 158, 11, 0.18);
        color: #FBBF24 !important;
        border: 1px solid rgba(245, 158, 11, 0.35);
        padding: 3px 9px;
        border-radius: 9999px;
        font-size: 0.75rem;
        font-weight: 600;
        display: inline-block;
        margin: 2px 3px;
    }
    .badge-return {
        background-color: rgba(220, 38, 38, 0.22);
        color: #FCA5A5 !important;
        border: 1px solid rgba(220, 38, 38, 0.45);
        padding: 3px 9px;
        border-radius: 9999px;
        font-size: 0.75rem;
        font-weight: 600;
        display: inline-block;
        margin: 2px 3px;
    }
    .badge-neutral {
        background-color: rgba(148, 163, 184, 0.15);
        color: #94A3B8 !important;
        border: 1px solid rgba(148, 163, 184, 0.3);
        padding: 3px 9px;
        border-radius: 9999px;
        font-size: 0.75rem;
        font-weight: 600;
        display: inline-block;
        margin: 2px 3px;
    }
</style>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# Data Loading & Enrichment
# -----------------------------------------------------------------------------
DATA_PATH = os.path.join(os.path.dirname(__file__), "data", "reviews.csv")

@st.cache_data
def load_and_enrich_data():
    if not os.path.exists(DATA_PATH):
        return None

    df = pd.read_csv(DATA_PATH)
    df.columns = [c.strip() for c in df.columns]

    # Combine review text and title for natural language matching
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

    # Keywords for size & fit general detection
    size_fit_keywords = [
        "size", "sizing", "fit", "fits", "fitted", "tight", "loose",
        "small", "large", "run small", "runs small", "run large", "runs large",
        "length", "short", "long", "waist", "bust", "shoulder", "shoulders",
        "return", "returned"
    ]
    pattern_fit = "|".join(size_fit_keywords)
    df["Is_Size_Fit"] = df["Full_Text"].str.contains(pattern_fit, regex=True, na=False)

    # Root Cause Sub-categorization
    small_keywords = ["small", "run small", "runs small", "tight", "snug", "squeeze"]
    large_keywords = ["large", "run large", "runs large", "loose", "huge", "baggy", "swimming"]
    prop_keywords = ["length", "short", "long", "waist", "bust", "shoulder", "shoulders", "torso", "hips", "petite", "tall"]

    df["Cause_Runs_Small"] = df["Full_Text"].str.contains("|".join(small_keywords), regex=True, na=False)
    df["Cause_Runs_Large"] = df["Full_Text"].str.contains("|".join(large_keywords), regex=True, na=False)
    df["Cause_Proportion"] = df["Full_Text"].str.contains("|".join(prop_keywords), regex=True, na=False)

    df["Is_Negative"] = df["Rating"] <= 2
    df["Is_Positive"] = df["Rating"] >= 4

    return df

df_raw = load_and_enrich_data()

# -----------------------------------------------------------------------------
# Empty State / Missing Data Guardrail
# -----------------------------------------------------------------------------
if df_raw is None:
    st.error("⚠️ Dataset not found at `data/reviews.csv`.")
    st.info("Please run `python download_data.py` to auto-fetch the verified 23,486-row dataset.")
    st.stop()

# -----------------------------------------------------------------------------
# Sidebar Navigation & Global Filters
# -----------------------------------------------------------------------------
st.sidebar.title("🔍 Exploration Filters")
st.sidebar.markdown("Filter customer feedback across categories and demographics.")

all_departments = sorted([d for d in df_raw["Department Name"].dropna().unique()])
selected_depts = st.sidebar.multiselect("Department", all_departments, default=all_departments)

all_cohorts = ["18-25", "26-35", "36-45", "46-55", "56+"]
selected_cohorts = st.sidebar.multiselect("Age Cohort", all_cohorts, default=all_cohorts)

rating_options = [1, 2, 3, 4, 5]
selected_ratings = st.sidebar.multiselect("Star Rating", rating_options, default=rating_options)

# Filter dataframe
filtered_df = df_raw[
    (df_raw["Department Name"].isin(selected_depts)) &
    (df_raw["Age_Cohort"].isin(selected_cohorts)) &
    (df_raw["Rating"].isin(selected_ratings))
]

st.sidebar.divider()
st.sidebar.markdown(f"**Filtered Records:** `{len(filtered_df):,}` / `{len(df_raw):,}`")
st.sidebar.markdown("### 📌 Portfolio Artifacts")
st.sidebar.markdown("- 📄 [Product Requirements Document](file:///PRD_Size_Fit_Guidance.md)")
st.sidebar.markdown("- 💻 [SQL Analysis Script](file:///sql/analysis_queries.sql)")
st.sidebar.markdown("- 📊 [CLI Numbers Script](file:///project1_numbers.py)")

# -----------------------------------------------------------------------------
# Header (Theme-adaptive, high-contrast)
# -----------------------------------------------------------------------------
st.markdown(
    '<h1 class="main-header">👗 Women\'s Apparel Size & Fit Pain-Point Intelligence</h1>'
    '<p class="sub-header">Product Analytics & PM Strategy Portfolio | Converting Customer Complaints into PDP Guidance Solutions</p>',
    unsafe_allow_html=True
)

# -----------------------------------------------------------------------------
# Tabs Layout
# -----------------------------------------------------------------------------
tab1, tab2, tab3 = st.tabs([
    "📊 Executive KPI Overview",
    "🔬 Root-Cause Deep Dive & Review Explorer",
    "🚀 Product Solution & A/B Experiment Simulator"
])

# =============================================================================
# TAB 1: Executive KPI Overview
# =============================================================================
with tab1:
    if len(filtered_df) == 0:
        st.warning("⚠️ No customer reviews match your active filter criteria. Please re-enable one or more Departments, Age Cohorts, or Star Ratings in the sidebar.")
    else:
        # Calculations
        total_revs = len(filtered_df)
        avg_rat = filtered_df["Rating"].mean() if total_revs > 0 else 0
        rec_rate = (filtered_df["Recommended IND"].sum() / total_revs * 100) if total_revs > 0 else 0
        
        neg_reviews = filtered_df[filtered_df["Is_Negative"]]
        total_negs = len(neg_reviews)
        neg_rate = (total_negs / total_revs * 100) if total_revs > 0 else 0
        
        fit_in_negs = len(neg_reviews[neg_reviews["Is_Size_Fit"]])
        fit_neg_share = (fit_in_negs / total_negs * 100) if total_negs > 0 else 0

        # Executive KPI Metric Cards (Inline HTML without multiline indentation)
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.markdown(
                f'<div class="kpi-card">'
                f'<div class="kpi-title">Total Reviews Analyzed</div>'
                f'<div class="kpi-value">{total_revs:,}</div>'
                f'<div class="kpi-caption">Full catalog volume</div>'
                f'</div>',
                unsafe_allow_html=True
            )
        with c2:
            st.markdown(
                f'<div class="kpi-card">'
                f'<div class="kpi-title">Average Rating</div>'
                f'<div class="kpi-value">{avg_rat:.2f} <span style="font-size:1.1rem; color:#F59E0B;">★</span></div>'
                f'<div class="kpi-caption">Catalog baseline score</div>'
                f'</div>',
                unsafe_allow_html=True
            )
        with c3:
            st.markdown(
                f'<div class="kpi-card">'
                f'<div class="kpi-title">Recommendation Rate</div>'
                f'<div class="kpi-value">{rec_rate:.1f}%</div>'
                f'<div class="kpi-caption">Customers recommending item</div>'
                f'</div>',
                unsafe_allow_html=True
            )
        with c4:
            st.markdown(
                f'<div class="kpi-card" style="border-left: 4px solid #EF4444;">'
                f'<div class="kpi-title">Size/Fit Share in Negatives</div>'
                f'<div class="kpi-value" style="color: #EF4444;">{fit_neg_share:.1f}%</div>'
                f'<div class="kpi-caption">{fit_in_negs:,} of {total_negs:,} 1-2★ reviews cite fit</div>'
                f'</div>',
                unsafe_allow_html=True
            )

        st.markdown("<br>", unsafe_allow_html=True)

        # Executive Insights Banner
        st.info(f"💡 **Executive Takeaway**: While the platform maintains an overall **{rec_rate:.1f}%** recommendation rate, **{fit_neg_share:.1f}%** of all negative customer reviews (1-2★) explicitly pinpoint **sizing, proportion, and fit mismatches**. Sizing uncertainty is the primary driver of customer dissatisfaction and reverse logistics overhead.")

        # Two column charts: Department & Age Cohorts
        row1_c1, row1_c2 = st.columns(2)

        with row1_c1:
            st.subheader("Department Vulnerability & Negative Rate")
            dept_summary = filtered_df.groupby("Department Name").agg(
                total_reviews=("Clothing ID", "count"),
                avg_rating=("Rating", "mean"),
                rec_rate=("Recommended IND", lambda x: (x.sum() / len(x) * 100)),
                neg_rate=("Is_Negative", lambda x: (x.sum() / len(x) * 100))
            ).reset_index().sort_values("neg_rate", ascending=False)

            max_neg = dept_summary["neg_rate"].max()
            upper_bound = 25.0 if pd.isna(max_neg) or max_neg == 0 else max_neg * 1.25

            fig_dept = px.bar(
                dept_summary,
                x="Department Name",
                y="neg_rate",
                color="neg_rate",
                color_continuous_scale="Reds",
                text="neg_rate",
                labels={"neg_rate": "Negative Review Rate (%)", "Department Name": "Department"},
                title="Negative Review Rate (%) by Department"
            )
            fig_dept.update_traces(texttemplate='%{text:.1f}%', textposition='outside')
            fig_dept.update_layout(yaxis_range=[0, upper_bound], coloraxis_showscale=False)
            st.plotly_chart(fig_dept, width="stretch", key="fig_dept")

        with row1_c2:
            st.subheader("Customer Age Cohort Sentiment & Fit Impact")
            cohort_summary = filtered_df.groupby("Age_Cohort").agg(
                total_reviews=("Clothing ID", "count"),
                avg_rating=("Rating", "mean"),
                rec_rate=("Recommended IND", lambda x: (x.sum() / len(x) * 100)),
                neg_rate=("Is_Negative", lambda x: (x.sum() / len(x) * 100))
            ).reindex(all_cohorts).dropna().reset_index()

            fig_cohort = go.Figure()
            fig_cohort.add_trace(go.Bar(
                x=cohort_summary["Age_Cohort"],
                y=cohort_summary["rec_rate"],
                name="Recommendation Rate (%)",
                marker_color="#3B82F6",
                text=cohort_summary["rec_rate"].apply(lambda v: f"{v:.1f}%"),
                textposition="inside"
            ))
            fig_cohort.add_trace(go.Scatter(
                x=cohort_summary["Age_Cohort"],
                y=cohort_summary["neg_rate"],
                name="Negative Review Rate (%)",
                yaxis="y2",
                mode="lines+markers+text",
                line=dict(color="#EF4444", width=3),
                marker=dict(size=8, color="#DC2626"),
                text=cohort_summary["neg_rate"].apply(lambda v: f"{v:.1f}%"),
                textposition="top center"
            ))
            fig_cohort.update_layout(
                title="Recommendation vs Negative Rate Across Age Cohorts",
                yaxis=dict(title="Recommendation Rate (%)", range=[60, 100]),
                yaxis2=dict(title="Negative Review Rate (%)", overlaying="y", side="right", range=[0, 25]),
                legend=dict(orientation="h", yanchor="bottom", y=-0.25, xanchor="center", x=0.5)
            )
            st.plotly_chart(fig_cohort, width="stretch", key="fig_cohort")

        # Star Rating Distribution
        st.subheader("Star Rating Volume & Sentiment Distribution")
        rating_counts = filtered_df["Rating"].value_counts().sort_index().reset_index()
        rating_counts.columns = ["Rating", "Count"]
        rating_counts["Pct"] = (rating_counts["Count"] / rating_counts["Count"].sum()) * 100

        fig_ratings = px.bar(
            rating_counts,
            x="Rating",
            y="Count",
            color="Rating",
            color_continuous_scale="Viridis",
            text=rating_counts.apply(lambda r: f"{r['Count']:,} ({r['Pct']:.1f}%)", axis=1),
            title="Review Count by Star Rating (1 to 5 Stars)"
        )
        fig_ratings.update_traces(textposition='outside')
        fig_ratings.update_layout(xaxis=dict(tickmode="linear", tick0=1, dtick=1), coloraxis_showscale=False)
        st.plotly_chart(fig_ratings, width="stretch", key="fig_ratings")

# =============================================================================
# TAB 2: Root-Cause Deep Dive & Review Explorer
# =============================================================================
with tab2:
    st.subheader("🔬 Size & Fit Root-Cause Classification (Negative Reviews)")
    st.markdown(r"We isolated all dissatisfied reviews (Rating $\le$ 2) and classified them into granular failure modes: **Runs Small / Tight**, **Runs Large / Baggy**, and **Proportion / Length Mismatch**.")

    neg_df = filtered_df[filtered_df["Is_Negative"]]

    if len(neg_df) == 0:
        st.warning("⚠️ No negative reviews match your current filter selection.")
    else:
        small_cnt = int(neg_df["Cause_Runs_Small"].sum())
        large_cnt = int(neg_df["Cause_Runs_Large"].sum())
        prop_cnt = int(neg_df["Cause_Proportion"].sum())
        total_neg_cnt = len(neg_df)

        rc1, rc2 = st.columns([1, 1])

        with rc1:
            causes_df = pd.DataFrame({
                "Root Cause": ["Runs Small / Tight", "Runs Large / Loose", "Proportion / Length Mismatch"],
                "Count": [small_cnt, large_cnt, prop_cnt],
                "Share_of_Negatives": [
                    (small_cnt / total_neg_cnt * 100) if total_neg_cnt > 0 else 0,
                    (large_cnt / total_neg_cnt * 100) if total_neg_cnt > 0 else 0,
                    (prop_cnt / total_neg_cnt * 100) if total_neg_cnt > 0 else 0
                ]
            })

            fig_donut = px.pie(
                causes_df,
                names="Root Cause",
                values="Count",
                hole=0.45,
                color="Root Cause",
                color_discrete_map={
                    "Runs Small / Tight": "#EF4444",
                    "Runs Large / Loose": "#3B82F6",
                    "Proportion / Length Mismatch": "#F59E0B"
                },
                title="Root Cause Distribution in Negative Reviews"
            )
            fig_donut.update_traces(textposition='inside', textinfo='percent+label')
            st.plotly_chart(fig_donut, width="stretch", key="fig_donut")

        with rc2:
            st.markdown("### 📋 Root Cause Summary")
            st.markdown(f"""
            - **'Runs Small' / Tight Mismatch**: **{small_cnt:,} reviews** ({(small_cnt/total_neg_cnt*100) if total_neg_cnt > 0 else 0:.1f}% of negative reviews)
              *Customers report unwearable constriction in chest, waist, and armpits.*
            - **'Runs Large' / Loose Fit**: **{large_cnt:,} reviews** ({(large_cnt/total_neg_cnt*100) if total_neg_cnt > 0 else 0:.1f}% of negative reviews)
              *Shoppers note shapeless, oversized cuts requiring sizing down.*
            - **'Proportion / Length' Mismatch**: **{prop_cnt:,} reviews** ({(prop_cnt/total_neg_cnt*100) if total_neg_cnt > 0 else 0:.1f}% of negative reviews)
              *Issues with dress hems, torso length, and petite/tall adjustments.*
            """)

            st.markdown("---")
            st.markdown("### Top Product Classes Vulnerable to Fit")
            class_fit_breakdown = neg_df.groupby("Class Name").agg(
                neg_count=("Clothing ID", "count"),
                small_count=("Cause_Runs_Small", "sum"),
                large_count=("Cause_Runs_Large", "sum"),
                prop_count=("Cause_Proportion", "sum")
            ).reset_index()
            class_fit_breakdown["fit_total"] = class_fit_breakdown["small_count"] + class_fit_breakdown["large_count"] + class_fit_breakdown["prop_count"]
            class_fit_breakdown = class_fit_breakdown.sort_values("neg_count", ascending=False).head(8)

            fig_class_breakdown = px.bar(
                class_fit_breakdown,
                x="Class Name",
                y=["small_count", "large_count", "prop_count"],
                title="Root Cause Breakdown by Product Class",
                labels={"value": "Complaint Count", "Class Name": "Product Class", "variable": "Root Cause"},
                color_discrete_map={
                    "small_count": "#EF4444",
                    "large_count": "#3B82F6",
                    "prop_count": "#F59E0B"
                }
            )
            st.plotly_chart(fig_class_breakdown, width="stretch", key="fig_class_breakdown")

        # Interactive Negative Review Search Explorer
        st.markdown("---")
        st.subheader("🔎 Searchable Negative Customer Review Explorer")
        st.markdown("Inspect real customer feedback to understand exact phrasing, emotional friction, and return triggers.")

        search_query = st.text_input("Filter reviews by keyword (e.g., 'tight', 'shoulders', 'petite', 'return', 'zipper'):", "")

        explorer_df = neg_df.copy()
        if search_query.strip():
            explorer_df = explorer_df[explorer_df["Full_Text"].str.contains(search_query.strip().lower(), na=False)]

        col_filter1, col_filter2 = st.columns(2)
        with col_filter1:
            cause_filter = st.selectbox("Filter by Specific Fit Mode:", ["All Negative Reviews", "Runs Small", "Runs Large", "Proportion/Length"])
        with col_filter2:
            sort_by = st.selectbox("Sort Reviews By:", ["Rating (Lowest First)", "Positive Feedback Count (Most Helpful)"])

        if cause_filter == "Runs Small":
            explorer_df = explorer_df[explorer_df["Cause_Runs_Small"]]
        elif cause_filter == "Runs Large":
            explorer_df = explorer_df[explorer_df["Cause_Runs_Large"]]
        elif cause_filter == "Proportion/Length":
            explorer_df = explorer_df[explorer_df["Cause_Proportion"]]

        if sort_by == "Rating (Lowest First)":
            explorer_df = explorer_df.sort_values("Rating", ascending=True)
        else:
            explorer_df = explorer_df.sort_values("Positive Feedback Count", ascending=False)

        if len(explorer_df) == 0:
            st.info(f"No reviews match your keyword search '{search_query}'. Try a broader keyword like 'fit' or 'small'.")
        else:
            st.caption(f"Showing **{min(len(explorer_df), 15)}** of **{len(explorer_df):,}** matching reviews:")

            # Native Streamlit container rendering to prevent any rogue markdown code blocks or </div> glitches
            for _, row in explorer_df.head(15).iterrows():
                title = row["Title"] if pd.notna(row["Title"]) and str(row["Title"]).strip() != "" else "Customer Review"
                body = row["Review Text"] if pd.notna(row["Review Text"]) else "No review text provided."
                rating = int(row["Rating"])
                stars = "★" * rating + "☆" * (5 - rating)
                dept = row["Department Name"] if pd.notna(row["Department Name"]) else "Unspecified"
                cls = row["Class Name"] if pd.notna(row["Class Name"]) else "Unspecified"
                age = int(row["Age"]) if pd.notna(row["Age"]) else "N/A"
                helpful = int(row["Positive Feedback Count"]) if pd.notna(row["Positive Feedback Count"]) else 0

                badge_elements = []
                if row["Cause_Runs_Small"]:
                    badge_elements.append('<span class="badge-danger">Runs Small / Tight</span>')
                if row["Cause_Runs_Large"]:
                    badge_elements.append('<span class="badge-info">Runs Large / Baggy</span>')
                if row["Cause_Proportion"]:
                    badge_elements.append('<span class="badge-warning">Proportion / Length</span>')
                if "return" in str(row["Full_Text"]):
                    badge_elements.append('<span class="badge-return">Return Triggered</span>')

                badges_html = " ".join(badge_elements) if badge_elements else '<span class="badge-neutral">General Fit Mismatch</span>'

                with st.container(border=True):
                    r_c1, r_c2 = st.columns([3, 1])
                    with r_c1:
                        st.markdown(f"**{title}**")
                    with r_c2:
                        st.markdown(f"<div style='text-align: right; color: #EF4444; font-weight: 700; font-size: 1rem;'>{stars} ({rating}/5)</div>", unsafe_allow_html=True)

                    st.markdown(f'<div style="color: var(--text-color); opacity: 0.92; margin: 6px 0; font-size: 0.93rem; line-height: 1.5;">"{body}"</div>', unsafe_allow_html=True)

                    m_c1, m_c2 = st.columns([2, 1])
                    with m_c1:
                        st.caption(f"**Dept:** {dept} &nbsp;|&nbsp; **Class:** {cls} &nbsp;|&nbsp; **Age:** {age} &nbsp;|&nbsp; 👍 **Helpful:** {helpful}")
                    with m_c2:
                        st.markdown(f"<div style='text-align: right;'>{badges_html}</div>", unsafe_allow_html=True)

# =============================================================================
# TAB 3: Product Proposal & A/B Experiment Simulator
# =============================================================================
with tab3:
    st.subheader("🚀 Feature Proposal: Smart Size & Fit Guidance (PDP Widget)")
    st.markdown("""
    Based on empirical review data showing that **over 76% of negative reviews relate to sizing and fit uncertainty**, 
    we propose integrating an AI-assisted **Smart Size & Fit Recommender** directly on the Product Detail Page (PDP).
    """)

    st.markdown("### 🧮 Interactive Return Reduction & Business ROI Simulator")
    st.markdown("Adjust business parameters below to forecast net savings from addressing size & fit pain points:")

    sim_c1, sim_c2, sim_c3 = st.columns(3)
    with sim_c1:
        annual_gmv = st.number_input("Annual Apparel GMV ($)", min_value=1_000_000, max_value=500_000_000, value=25_000_000, step=1_000_000, format="%d")
        aov = st.number_input("Average Order Value (AOV) ($)", min_value=20, max_value=500, value=115, step=5)
    with sim_c2:
        baseline_return_rate = st.slider("Baseline Return Rate (%)", min_value=10.0, max_value=50.0, value=28.0, step=0.5)
        fit_return_share = st.slider("Share of Returns Due to Size/Fit (%)", min_value=30.0, max_value=90.0, value=76.4, step=0.5)
    with sim_c3:
        target_reduction = st.slider("Target Size-Return Reduction (%)", min_value=5.0, max_value=40.0, value=20.0, step=1.0)
        reverse_logistics_cost = st.number_input("Cost Per Return (Shipping/Restock) ($)", min_value=5.0, max_value=50.0, value=15.0, step=1.0)

    # Simulator Math
    annual_orders = annual_gmv / aov
    total_returns_baseline = annual_orders * (baseline_return_rate / 100.0)
    fit_returns_baseline = total_returns_baseline * (fit_return_share / 100.0)
    
    avoided_returns = fit_returns_baseline * (target_reduction / 100.0)
    avoided_shipping_costs = avoided_returns * reverse_logistics_cost
    retained_sales_value = avoided_returns * aov
    new_return_rate = ((total_returns_baseline - avoided_returns) / annual_orders) * 100.0

    st.markdown("<br>", unsafe_allow_html=True)
    res_c1, res_c2, res_c3, res_c4 = st.columns(4)
    with res_c1:
        st.markdown(
            f'<div class="kpi-card" style="border-left: 4px solid #10B981;">'
            f'<div class="kpi-title">Avoided Customer Returns</div>'
            f'<div class="kpi-value" style="color: #10B981;">{int(avoided_returns):,}</div>'
            f'<div class="kpi-caption">Fewer return packages processed</div>'
            f'</div>',
            unsafe_allow_html=True
        )
    with res_c2:
        st.markdown(
            f'<div class="kpi-card" style="border-left: 4px solid #10B981;">'
            f'<div class="kpi-title">Reverse Logistics Savings</div>'
            f'<div class="kpi-value" style="color: #10B981;">${avoided_shipping_costs:,.0f}</div>'
            f'<div class="kpi-caption">Saved handling & shipping</div>'
            f'</div>',
            unsafe_allow_html=True
        )
    with res_c3:
        st.markdown(
            f'<div class="kpi-card" style="border-left: 4px solid #3B82F6;">'
            f'<div class="kpi-title">Retained Merchandise Value</div>'
            f'<div class="kpi-value" style="color: #3B82F6;">${retained_sales_value:,.0f}</div>'
            f'<div class="kpi-caption">Kept revenue vs refunded</div>'
            f'</div>',
            unsafe_allow_html=True
        )
    with res_c4:
        st.markdown(
            f'<div class="kpi-card">'
            f'<div class="kpi-title">New Projected Return Rate</div>'
            f'<div class="kpi-value">{new_return_rate:.2f}%</div>'
            f'<div class="kpi-caption">Down from {baseline_return_rate:.1f}% baseline</div>'
            f'</div>',
            unsafe_allow_html=True
        )

    st.markdown("<br>", unsafe_allow_html=True)

    # Detailed PRD View
    st.markdown("---")
    st.subheader("📄 Product Requirements Document (PRD) Summary")

    with st.expander("1. Executive Summary & Problem Validation", expanded=True):
        st.markdown(r"""
        - **Problem**: Analysis of 23,486 e-commerce clothing reviews reveals that **76.4%** of dissatisfied customers cite sizing or fit failure as the primary reason for rating a garment 1 or 2 stars.
        - **Business Consequence**: Size mismatch drives high customer return rates (typically 25-30% in apparel), erodes margins through double-leg freight & markdown depreciation, and damages customer lifetime value (LTV).
        - **Solution**: A low-friction, data-backed PDP guidance module ("Smart Size & Fit Assistant") that leverages machine-learned fit profiles, cohort consensus ("Runs Small / Runs Large"), and garment dimensions.
        """)

    with st.expander("2. Target User Personas", expanded=False):
        st.markdown("""
        1. **The Hesitant First-Time Shopper (Maya, 29)**: Loves a dress but hesitates to buy because sizing varies across brands. Likely to abandon cart without fit confidence.
        2. **The Multi-Size 'Bracket' Buyer (Claire, 42)**: Frequently purchases both Medium and Large with the intention of returning one, incurring high reverse logistics friction.
        3. **The Proportion-Sensitive Shopper (Elena, 54)**: Highly conscious of waistlines, hem lengths, and bust coverage. Needs specific guidance beyond standard S/M/L charts.
        """)

    with st.expander("3. Functional Requirements (P0 / P1)", expanded=False):
        st.markdown("""
        | Priority | Feature Component | Functional Specification |
        |---|---|---|
        | **P0** | **Aggregated Fit Gauge** | Real-time sentiment slider on PDP showing *"Runs True to Size (72%)"*, *"Runs Small (21%)"*, *"Runs Large (7%)"*. |
        | **P0** | **Size Recommendation Engine** | Modal accepting customer height, weight, and fit preference to output recommended size with confidence score. |
        | **P1** | **Customer Review Filter by Body Type** | Allows filtering reviews by customer age, height, and cup/waist measurements. |
        | **P1** | **Model & Garment Measure Overlay** | Interactive diagram showing exact garment measurements (bust, waist, total length) alongside model stats. |
        """)

    with st.expander("4. A/B Testing & Experimentation Roadmap", expanded=False):
        st.markdown(r"""
        - **Experiment Design**: Randomized Controlled Trial (50/50 split) across all web & mobile PDPs.
          - **Control (A)**: Standard PDP with static alphanumeric size guide table.
          - **Treatment (B)**: PDP with Smart Size & Fit Guidance Widget and Dynamic Consensus Meter.
        - **Primary Success Metric**: 
          - **Size-Related Return Rate**: Target **-15% to -20% reduction** ($p < 0.01$).
        - **Secondary & Guardrail Metrics**:
          - **PDP Conversion Rate**: Guardrail $\ge 0.0\%$ (must not reduce checkout completion).
          - **Add-to-Bag (ATB) Rate**: Target $+3.5\%$ uplift due to reduced hesitation.
          - **Bracketing Rate**: Target $-30\%$ reduction in multi-size duplicate basket orders.
        - **Sample Size & Duration**: 4 weeks minimum run to capture full order $\rightarrow$ delivery $\rightarrow$ return lifecycle.
        """)

# Footer
st.markdown("---")
st.caption("End-to-End Product Analytics Portfolio | Built with Streamlit, Plotly, SQLite & Python | Dataset: Women's E-Commerce Clothing Reviews")
