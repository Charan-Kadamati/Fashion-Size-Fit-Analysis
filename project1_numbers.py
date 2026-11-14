import os
import sqlite3
import pandas as pd

def run_analysis(csv_path="data/reviews.csv"):
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"Dataset not found at {csv_path}. Please run download_data.py first.")

    # Load dataset
    df = pd.read_csv(csv_path)

    # Clean column names (strip whitespace)
    df.columns = [c.strip() for c in df.columns]

    # In-memory SQLite database
    conn = sqlite3.connect(":memory:")
    
    # Write to SQLite
    df.to_sql("reviews", conn, index=False, if_exists="replace")

    cursor = conn.cursor()

    # 1. Overall KPIs
    cursor.execute("""
    SELECT
        COUNT(*) AS total_reviews,
        ROUND(AVG("Rating"), 2) AS avg_rating,
        ROUND(100.0 * SUM(CASE WHEN "Recommended IND" = 1 THEN 1 ELSE 0 END) / COUNT(*), 2) AS rec_rate_pct,
        SUM(CASE WHEN "Rating" <= 2 THEN 1 ELSE 0 END) AS neg_count,
        ROUND(100.0 * SUM(CASE WHEN "Rating" <= 2 THEN 1 ELSE 0 END) / COUNT(*), 2) AS neg_rate_pct
    FROM reviews;
    """)
    total_reviews, avg_rating, rec_rate_pct, neg_count, neg_rate_pct = cursor.fetchone()

    # 2. Negative reviews size & fit keyword matching
    # Keywords: size, sizing, fit, fits, fitted, tight, loose, small, large, run small, runs large, length, short, long, waist, bust, shoulders, return, returned
    keywords = [
        "size", "sizing", "fit", "fits", "fitted", "tight", "loose",
        "small", "large", "run small", "runs small", "run large", "runs large",
        "length", "short", "long", "waist", "bust", "shoulder", "shoulders",
        "return", "returned"
    ]
    
    # We construct SQL conditions
    kw_conditions = " OR ".join([f'LOWER(COALESCE("Review Text", "") || " " || COALESCE("Title", "")) LIKE "%{kw}%"' for kw in keywords])

    cursor.execute(f"""
    SELECT
        COUNT(*) AS total_neg,
        SUM(CASE WHEN {kw_conditions} THEN 1 ELSE 0 END) AS fit_neg_count,
        ROUND(100.0 * SUM(CASE WHEN {kw_conditions} THEN 1 ELSE 0 END) / COUNT(*), 2) AS fit_neg_pct
    FROM reviews
    WHERE "Rating" <= 2;
    """)
    total_neg, fit_neg_count, fit_neg_pct = cursor.fetchone()

    # 3. Root-cause categorization inside negative reviews:
    # Runs Small vs. Runs Large vs. Proportion / Length
    small_kws = ["small", "run small", "runs small", "tight", "snug", "squeeze"]
    large_kws = ["large", "run large", "runs large", "loose", "huge", "baggy", "swimming"]
    prop_kws = ["length", "short", "long", "waist", "bust", "shoulder", "shoulders", "torso", "hips", "petite", "tall"]

    small_cond = " OR ".join([f'LOWER(COALESCE("Review Text", "") || " " || COALESCE("Title", "")) LIKE "%{kw}%"' for kw in small_kws])
    large_cond = " OR ".join([f'LOWER(COALESCE("Review Text", "") || " " || COALESCE("Title", "")) LIKE "%{kw}%"' for kw in large_kws])
    prop_cond = " OR ".join([f'LOWER(COALESCE("Review Text", "") || " " || COALESCE("Title", "")) LIKE "%{kw}%"' for kw in prop_kws])

    cursor.execute(f"""
    SELECT
        COUNT(*) AS total_neg,
        SUM(CASE WHEN {small_cond} THEN 1 ELSE 0 END) AS small_count,
        ROUND(100.0 * SUM(CASE WHEN {small_cond} THEN 1 ELSE 0 END) / COUNT(*), 2) AS small_pct,
        SUM(CASE WHEN {large_cond} THEN 1 ELSE 0 END) AS large_count,
        ROUND(100.0 * SUM(CASE WHEN {large_cond} THEN 1 ELSE 0 END) / COUNT(*), 2) AS large_pct,
        SUM(CASE WHEN {prop_cond} THEN 1 ELSE 0 END) AS prop_count,
        ROUND(100.0 * SUM(CASE WHEN {prop_cond} THEN 1 ELSE 0 END) / COUNT(*), 2) AS prop_pct
    FROM reviews
    WHERE "Rating" <= 2;
    """)
    _, small_count, small_pct, large_count, large_pct, prop_count, prop_pct = cursor.fetchone()

    # 4. Department Level Performance
    cursor.execute(f"""
    SELECT
        COALESCE("Department Name", 'Unspecified') AS dept,
        COUNT(*) AS total_rev,
        ROUND(AVG("Rating"), 2) AS avg_rat,
        ROUND(100.0 * SUM(CASE WHEN "Recommended IND" = 1 THEN 1 ELSE 0 END) / COUNT(*), 2) AS rec_pct,
        SUM(CASE WHEN "Rating" <= 2 THEN 1 ELSE 0 END) AS neg_rev,
        ROUND(100.0 * SUM(CASE WHEN "Rating" <= 2 THEN 1 ELSE 0 END) / COUNT(*), 2) AS neg_pct,
        SUM(CASE WHEN "Rating" <= 2 AND ({kw_conditions}) THEN 1 ELSE 0 END) AS fit_neg,
        ROUND(100.0 * SUM(CASE WHEN "Rating" <= 2 AND ({kw_conditions}) THEN 1 ELSE 0 END) / NULLIF(SUM(CASE WHEN "Rating" <= 2 THEN 1 ELSE 0 END), 0), 2) AS fit_in_neg_pct
    FROM reviews
    GROUP BY "Department Name"
    HAVING COUNT(*) >= 10
    ORDER BY neg_pct DESC;
    """)
    dept_rows = cursor.fetchall()

    # 5. Class Level Performance (top affected category)
    cursor.execute(f"""
    SELECT
        COALESCE("Class Name", 'Unspecified') AS class_name,
        COALESCE("Department Name", 'Unspecified') AS dept_name,
        COUNT(*) AS total_rev,
        ROUND(AVG("Rating"), 2) AS avg_rat,
        ROUND(100.0 * SUM(CASE WHEN "Recommended IND" = 1 THEN 1 ELSE 0 END) / COUNT(*), 2) AS rec_pct,
        SUM(CASE WHEN "Rating" <= 2 THEN 1 ELSE 0 END) AS neg_rev,
        ROUND(100.0 * SUM(CASE WHEN "Rating" <= 2 THEN 1 ELSE 0 END) / COUNT(*), 2) AS neg_pct,
        SUM(CASE WHEN "Rating" <= 2 AND ({kw_conditions}) THEN 1 ELSE 0 END) AS fit_neg,
        ROUND(100.0 * SUM(CASE WHEN "Rating" <= 2 AND ({kw_conditions}) THEN 1 ELSE 0 END) / NULLIF(SUM(CASE WHEN "Rating" <= 2 THEN 1 ELSE 0 END), 0), 2) AS fit_in_neg_pct
    FROM reviews
    GROUP BY "Class Name", "Department Name"
    HAVING COUNT(*) >= 50
    ORDER BY fit_neg DESC;
    """)
    class_rows = cursor.fetchall()
    top_class_row = class_rows[0] if class_rows else None

    # Top class by negative review rate (min 50 reviews)
    cursor.execute(f"""
    SELECT
        COALESCE("Class Name", 'Unspecified') AS class_name,
        COALESCE("Department Name", 'Unspecified') AS dept_name,
        COUNT(*) AS total_rev,
        ROUND(AVG("Rating"), 2) AS avg_rat,
        SUM(CASE WHEN "Rating" <= 2 THEN 1 ELSE 0 END) AS neg_rev,
        ROUND(100.0 * SUM(CASE WHEN "Rating" <= 2 THEN 1 ELSE 0 END) / COUNT(*), 2) AS neg_pct,
        SUM(CASE WHEN "Rating" <= 2 AND ({kw_conditions}) THEN 1 ELSE 0 END) AS fit_neg,
        ROUND(100.0 * SUM(CASE WHEN "Rating" <= 2 AND ({kw_conditions}) THEN 1 ELSE 0 END) / NULLIF(SUM(CASE WHEN "Rating" <= 2 THEN 1 ELSE 0 END), 0), 2) AS fit_in_neg_pct
    FROM reviews
    GROUP BY "Class Name", "Department Name"
    HAVING COUNT(*) >= 50
    ORDER BY neg_pct DESC;
    """)
    highest_neg_rate_class = cursor.fetchone()

    # 6. Age Cohorts Analysis (18-25, 26-35, 36-45, 46-55, 56+)
    cursor.execute(f"""
    SELECT
        CASE
            WHEN "Age" BETWEEN 18 AND 25 THEN '18-25'
            WHEN "Age" BETWEEN 26 AND 35 THEN '26-35'
            WHEN "Age" BETWEEN 36 AND 45 THEN '36-45'
            WHEN "Age" BETWEEN 46 AND 55 THEN '46-55'
            WHEN "Age" >= 56 THEN '56+'
            ELSE 'Unknown'
        END AS age_cohort,
        COUNT(*) AS total_rev,
        ROUND(AVG("Rating"), 2) AS avg_rat,
        ROUND(100.0 * SUM(CASE WHEN "Recommended IND" = 1 THEN 1 ELSE 0 END) / COUNT(*), 2) AS rec_pct,
        SUM(CASE WHEN "Rating" <= 2 THEN 1 ELSE 0 END) AS neg_rev,
        ROUND(100.0 * SUM(CASE WHEN "Rating" <= 2 THEN 1 ELSE 0 END) / COUNT(*), 2) AS neg_pct,
        SUM(CASE WHEN "Rating" <= 2 AND ({kw_conditions}) THEN 1 ELSE 0 END) AS fit_neg,
        ROUND(100.0 * SUM(CASE WHEN "Rating" <= 2 AND ({kw_conditions}) THEN 1 ELSE 0 END) / NULLIF(SUM(CASE WHEN "Rating" <= 2 THEN 1 ELSE 0 END), 0), 2) AS fit_in_neg_pct
    FROM reviews
    GROUP BY age_cohort
    ORDER BY neg_pct DESC;
    """)
    age_rows = cursor.fetchall()
    worst_age_cohort = age_rows[0] if age_rows else None

    # Print summary
    print("=" * 70)
    print("  PRODUCT ANALYTICS & PM PORTFOLIO: SIZE & FIT ANALYSIS")
    print("=" * 70)
    print(f"\n[1] OVERALL DATASET METRICS:")
    print(f"    - Total Customer Reviews:             {total_reviews:,}")
    print(f"    - Overall Average Rating:             {avg_rating:.2f} / 5.00")
    print(f"    - Customer Recommendation Rate:       {rec_rate_pct:.2f}%")
    print(f"    - Negative Reviews (Rating <= 2):     {neg_count:,} ({neg_rate_pct:.2f}%)")

    print(f"\n[2] SIZE & FIT PAIN-POINT SHARE (AMONG NEGATIVE REVIEWS):")
    print(f"    - Negative Reviews Citing Size/Fit:   {fit_neg_count:,} of {total_neg:,}")
    print(f"    - Size & Fit Pain-Point Share:        {fit_neg_pct:.2f}%")

    print(f"\n[3] ROOT CAUSE SUB-CLASSIFICATION (AMONG NEGATIVE REVIEWS):")
    print(f"    - 'Runs Small' / Tight Issues:        {small_count:,} ({small_pct:.2f}%)")
    print(f"    - 'Runs Large' / Loose Issues:        {large_count:,} ({large_pct:.2f}%)")
    print(f"    - 'Proportion / Length' Issues:       {prop_count:,} ({prop_pct:.2f}%)")

    print(f"\n[4] TOP AFFECTED CATEGORY BY SIZE/FIT COMPLAINT VOLUME:")
    if top_class_row:
        c_name, c_dept, c_tot, c_rat, c_rec, c_neg, c_neg_pct, c_fit_neg, c_fit_in_neg_pct = top_class_row
        print(f"    - Category:                           {c_name} ({c_dept})")
        print(f"    - Total Reviews:                      {c_tot:,}")
        print(f"    - Negative Reviews:                   {c_neg:,} ({c_neg_pct:.2f}%)")
        print(f"    - Fit Complaints Volume:              {c_fit_neg:,} ({c_fit_in_neg_pct:.2f}% of negative reviews)")

    print(f"\n[5] HIGHEST NEGATIVE RATE CATEGORY (min 50 reviews):")
    if highest_neg_rate_class:
        hn_name, hn_dept, hn_tot, hn_rat, hn_neg, hn_neg_pct, hn_fit_neg, hn_fit_in_neg_pct = highest_neg_rate_class
        print(f"    - Category:                           {hn_name} ({hn_dept})")
        print(f"    - Total Reviews:                      {hn_tot:,}")
        print(f"    - Negative Rate:                      {hn_neg_pct:.2f}% ({hn_neg:,} negative reviews)")
        print(f"    - Fit Complaint Share in Negatives:   {hn_fit_in_neg_pct:.2f}%")

    print(f"\n[6] DEMOGRAPHIC / AGE COHORT BREAKDOWN:")
    for cohort, tot, rat, rec, neg, neg_p, f_neg, f_neg_p in age_rows:
        print(f"    - Age Cohort {cohort:>5}:  Total: {tot:>5} | Avg Rating: {rat:.2f} | Rec: {rec:.2f}% | Neg Rate: {neg_p:.2f}% | Fit Share: {f_neg_p:.2f}%")

    if worst_age_cohort:
        w_cohort, w_tot, w_rat, w_rec, w_neg, w_neg_p, w_f_neg, w_f_neg_p = worst_age_cohort
        print(f"\n    >> Worst Performing Age Group: Cohort {w_cohort} (Negative Review Rate: {w_neg_p:.2f}%, Avg Rating: {w_rat:.2f})")

    print("\n" + "=" * 70)

    results = {
        "total_reviews": total_reviews,
        "avg_rating": avg_rating,
        "rec_rate_pct": rec_rate_pct,
        "neg_count": neg_count,
        "neg_rate_pct": neg_rate_pct,
        "fit_neg_count": fit_neg_count,
        "fit_neg_pct": fit_neg_pct,
        "small_count": small_count,
        "small_pct": small_pct,
        "large_count": large_count,
        "large_pct": large_pct,
        "prop_count": prop_count,
        "prop_pct": prop_pct,
        "top_class_row": top_class_row,
        "highest_neg_rate_class": highest_neg_rate_class,
        "worst_age_cohort": worst_age_cohort,
        "age_rows": age_rows,
        "dept_rows": dept_rows,
        "class_rows": class_rows
    }
    conn.close()
    return results

if __name__ == "__main__":
    run_analysis()

