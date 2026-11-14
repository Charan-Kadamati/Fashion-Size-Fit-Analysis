-- ==============================================================================
-- SQL ANALYSIS QUERIES: Size & Fit Pain-Point Analysis (SQLite)
-- Dataset: Women's E-Commerce Clothing Reviews (`reviews` table)
-- Columns:
--   "Clothing ID", "Age", "Title", "Review Text", "Rating",
--   "Recommended IND", "Positive Feedback Count", "Division Name",
--   "Department Name", "Class Name"
-- ==============================================================================

-- ------------------------------------------------------------------------------
-- QUERY 1: Overall Executive KPIs
-- Calculates total volume, average rating, recommendation rate (%),
-- negative review count & rate (% rating <= 2), and positive review rate (% rating >= 4).
-- ------------------------------------------------------------------------------
-- Q1_OVERALL_KPIS
SELECT
    COUNT(*) AS total_reviews,
    ROUND(AVG("Rating"), 2) AS avg_rating,
    ROUND(100.0 * SUM(CASE WHEN "Recommended IND" = 1 THEN 1 ELSE 0 END) / COUNT(*), 2) AS recommendation_rate_pct,
    SUM(CASE WHEN "Rating" <= 2 THEN 1 ELSE 0 END) AS negative_reviews_count,
    ROUND(100.0 * SUM(CASE WHEN "Rating" <= 2 THEN 1 ELSE 0 END) / COUNT(*), 2) AS negative_review_rate_pct,
    SUM(CASE WHEN "Rating" >= 4 THEN 1 ELSE 0 END) AS positive_reviews_count,
    ROUND(100.0 * SUM(CASE WHEN "Rating" >= 4 THEN 1 ELSE 0 END) / COUNT(*), 2) AS positive_review_rate_pct
FROM reviews;


-- ------------------------------------------------------------------------------
-- QUERY 2: Department-Level Breakdown
-- Aggregates performance metrics by Department Name to identify high-risk product lines.
-- ------------------------------------------------------------------------------
-- Q2_DEPARTMENT_PERFORMANCE
SELECT
    COALESCE("Department Name", 'Unspecified') AS department,
    COUNT(*) AS total_reviews,
    ROUND(AVG("Rating"), 2) AS avg_rating,
    ROUND(100.0 * SUM(CASE WHEN "Recommended IND" = 1 THEN 1 ELSE 0 END) / COUNT(*), 2) AS recommendation_rate_pct,
    SUM(CASE WHEN "Rating" <= 2 THEN 1 ELSE 0 END) AS negative_reviews,
    ROUND(100.0 * SUM(CASE WHEN "Rating" <= 2 THEN 1 ELSE 0 END) / COUNT(*), 2) AS negative_review_rate_pct
FROM reviews
GROUP BY "Department Name"
HAVING COUNT(*) >= 10
ORDER BY negative_review_rate_pct DESC;


-- ------------------------------------------------------------------------------
-- QUERY 3: Class-Level Category Breakdown (Granular Product Types)
-- Evaluates ratings, review volume, and negative review shares across product classes
-- (e.g., Dresses, Knits, Blouses, Pants, Swim, Jackets).
-- ------------------------------------------------------------------------------
-- Q3_CLASS_PERFORMANCE
SELECT
    COALESCE("Department Name", 'Unspecified') AS department,
    COALESCE("Class Name", 'Unspecified') AS product_class,
    COUNT(*) AS total_reviews,
    ROUND(AVG("Rating"), 2) AS avg_rating,
    ROUND(100.0 * SUM(CASE WHEN "Recommended IND" = 1 THEN 1 ELSE 0 END) / COUNT(*), 2) AS recommendation_rate_pct,
    SUM(CASE WHEN "Rating" <= 2 THEN 1 ELSE 0 END) AS negative_reviews,
    ROUND(100.0 * SUM(CASE WHEN "Rating" <= 2 THEN 1 ELSE 0 END) / COUNT(*), 2) AS negative_review_rate_pct
FROM reviews
GROUP BY "Department Name", "Class Name"
HAVING COUNT(*) >= 20
ORDER BY negative_review_rate_pct DESC, total_reviews DESC;


-- ------------------------------------------------------------------------------
-- QUERY 4: Customer Age Cohort Analysis
-- Cohorts: 18-25, 26-35, 36-45, 46-55, 56+
-- Identifies variance in sizing perception and dissatisfaction across demographic segments.
-- ------------------------------------------------------------------------------
-- Q4_AGE_COHORT_PERFORMANCE
SELECT
    CASE
        WHEN "Age" BETWEEN 18 AND 25 THEN '18-25'
        WHEN "Age" BETWEEN 26 AND 35 THEN '26-35'
        WHEN "Age" BETWEEN 36 AND 45 THEN '36-45'
        WHEN "Age" BETWEEN 46 AND 55 THEN '46-55'
        WHEN "Age" >= 56 THEN '56+'
        ELSE 'Unknown'
    END AS age_cohort,
    COUNT(*) AS total_reviews,
    ROUND(AVG("Rating"), 2) AS avg_rating,
    ROUND(100.0 * SUM(CASE WHEN "Recommended IND" = 1 THEN 1 ELSE 0 END) / COUNT(*), 2) AS recommendation_rate_pct,
    SUM(CASE WHEN "Rating" <= 2 THEN 1 ELSE 0 END) AS negative_reviews,
    ROUND(100.0 * SUM(CASE WHEN "Rating" <= 2 THEN 1 ELSE 0 END) / COUNT(*), 2) AS negative_review_rate_pct
FROM reviews
GROUP BY age_cohort
ORDER BY
    CASE age_cohort
        WHEN '18-25' THEN 1
        WHEN '26-35' THEN 2
        WHEN '36-45' THEN 3
        WHEN '46-55' THEN 4
        WHEN '56+' THEN 5
        ELSE 6
    END;


-- ------------------------------------------------------------------------------
-- QUERY 5: Quantifying Size & Fit Complaints in Negative Reviews (Rating <= 2)
-- Filters to dissatisfied customers and detects size/fit/return terminology:
-- Keywords: size, sizing, fit, fits, fitted, tight, loose, small, large,
--           run small, runs large, length, short, long, waist, bust, shoulders, return, returned.
-- ------------------------------------------------------------------------------
-- Q5_SIZE_FIT_COMPLAINT_SHARE
WITH NegativeReviews AS (
    SELECT
        "Clothing ID",
        "Age",
        "Department Name",
        "Class Name",
        "Rating",
        "Title",
        "Review Text",
        LOWER(COALESCE("Review Text", '') || ' ' || COALESCE("Title", '')) AS full_text
    FROM reviews
    WHERE "Rating" <= 2
),
FlaggedNegativeReviews AS (
    SELECT
        *,
        CASE
            WHEN full_text LIKE '%size%'
              OR full_text LIKE '%sizing%'
              OR full_text LIKE '% fit %'
              OR full_text LIKE '% fits %'
              OR full_text LIKE '%fitted%'
              OR full_text LIKE '%tight%'
              OR full_text LIKE '%loose%'
              OR full_text LIKE '%small%'
              OR full_text LIKE '%large%'
              OR full_text LIKE '%run small%'
              OR full_text LIKE '%runs small%'
              OR full_text LIKE '%run large%'
              OR full_text LIKE '%runs large%'
              OR full_text LIKE '%length%'
              OR full_text LIKE '%short%'
              OR full_text LIKE '%long%'
              OR full_text LIKE '%waist%'
              OR full_text LIKE '%bust%'
              OR full_text LIKE '%shoulder%'
              OR full_text LIKE '%shoulders%'
              OR full_text LIKE '%return%'
              OR full_text LIKE '%returned%'
            THEN 1
            ELSE 0
        END AS is_size_fit_complaint
    FROM NegativeReviews
)
SELECT
    COUNT(*) AS total_negative_reviews,
    SUM(is_size_fit_complaint) AS size_fit_complaint_count,
    ROUND(100.0 * SUM(is_size_fit_complaint) / COUNT(*), 2) AS size_fit_complaint_pct
FROM FlaggedNegativeReviews;


-- ------------------------------------------------------------------------------
-- QUERY 6: Root Cause Sub-Classification of Size & Fit Issues
-- Categorizes negative size/fit complaints into 3 distinct operational buckets:
-- 1. "Runs Small / Tight": small, run small, runs small, tight, squeeze, snug
-- 2. "Runs Large / Baggy": large, run large, runs large, loose, huge, baggy, swimming
-- 3. "Proportion / Length": length, short, long, petite, tall, torso, waist, bust, shoulders, arm, hips
-- ------------------------------------------------------------------------------
-- Q6_ROOT_CAUSE_BREAKDOWN
WITH NegativeReviews AS (
    SELECT
        "Clothing ID",
        "Department Name",
        "Class Name",
        "Rating",
        LOWER(COALESCE("Review Text", '') || ' ' || COALESCE("Title", '')) AS full_text
    FROM reviews
    WHERE "Rating" <= 2
),
RootCauseTaggers AS (
    SELECT
        *,
        CASE
            WHEN full_text LIKE '%small%'
              OR full_text LIKE '%run small%'
              OR full_text LIKE '%runs small%'
              OR full_text LIKE '%tight%'
              OR full_text LIKE '%snug%'
              OR full_text LIKE '%squeeze%'
            THEN 1 ELSE 0
        END AS runs_small,
        CASE
            WHEN full_text LIKE '%large%'
              OR full_text LIKE '%run large%'
              OR full_text LIKE '%runs large%'
              OR full_text LIKE '%loose%'
              OR full_text LIKE '%huge%'
              OR full_text LIKE '%baggy%'
              OR full_text LIKE '%swimming%'
            THEN 1 ELSE 0
        END AS runs_large,
        CASE
            WHEN full_text LIKE '%length%'
              OR full_text LIKE '%short%'
              OR full_text LIKE '%long%'
              OR full_text LIKE '%waist%'
              OR full_text LIKE '%bust%'
              OR full_text LIKE '%shoulder%'
              OR full_text LIKE '%shoulders%'
              OR full_text LIKE '%torso%'
              OR full_text LIKE '%hips%'
              OR full_text LIKE '%petite%'
            THEN 1 ELSE 0
        END AS proportion_length
    FROM NegativeReviews
)
SELECT
    COUNT(*) AS total_negative_reviews,
    SUM(runs_small) AS runs_small_count,
    ROUND(100.0 * SUM(runs_small) / COUNT(*), 2) AS runs_small_pct,
    SUM(runs_large) AS runs_large_count,
    ROUND(100.0 * SUM(runs_large) / COUNT(*), 2) AS runs_large_pct,
    SUM(proportion_length) AS proportion_length_count,
    ROUND(100.0 * SUM(proportion_length) / COUNT(*), 2) AS proportion_length_pct,
    SUM(CASE WHEN runs_small = 1 OR runs_large = 1 OR proportion_length = 1 THEN 1 ELSE 0 END) AS any_fit_issue_count,
    ROUND(100.0 * SUM(CASE WHEN runs_small = 1 OR runs_large = 1 OR proportion_length = 1 THEN 1 ELSE 0 END) / COUNT(*), 2) AS any_fit_issue_pct
FROM RootCauseTaggers;


-- ------------------------------------------------------------------------------
-- QUERY 7: Category-Level Size & Fit Vulnerability Index
-- Evaluates which product classes suffer the highest density of size/fit complaints.
-- ------------------------------------------------------------------------------
-- Q7_CATEGORY_SIZE_FIT_VULNERABILITY
WITH ClassNegativeStats AS (
    SELECT
        COALESCE("Class Name", 'Unspecified') AS product_class,
        COALESCE("Department Name", 'Unspecified') AS department,
        COUNT(*) AS total_class_reviews,
        SUM(CASE WHEN "Rating" <= 2 THEN 1 ELSE 0 END) AS negative_reviews,
        SUM(CASE
            WHEN "Rating" <= 2 AND (
                LOWER(COALESCE("Review Text", '') || ' ' || COALESCE("Title", '')) LIKE '%size%'
                OR LOWER(COALESCE("Review Text", '') || ' ' || COALESCE("Title", '')) LIKE '%sizing%'
                OR LOWER(COALESCE("Review Text", '') || ' ' || COALESCE("Title", '')) LIKE '%fit%'
                OR LOWER(COALESCE("Review Text", '') || ' ' || COALESCE("Title", '')) LIKE '%tight%'
                OR LOWER(COALESCE("Review Text", '') || ' ' || COALESCE("Title", '')) LIKE '%loose%'
                OR LOWER(COALESCE("Review Text", '') || ' ' || COALESCE("Title", '')) LIKE '%small%'
                OR LOWER(COALESCE("Review Text", '') || ' ' || COALESCE("Title", '')) LIKE '%large%'
                OR LOWER(COALESCE("Review Text", '') || ' ' || COALESCE("Title", '')) LIKE '%length%'
                OR LOWER(COALESCE("Review Text", '') || ' ' || COALESCE("Title", '')) LIKE '%waist%'
                OR LOWER(COALESCE("Review Text", '') || ' ' || COALESCE("Title", '')) LIKE '%return%'
            ) THEN 1 ELSE 0
        END) AS size_fit_complaints
    FROM reviews
    GROUP BY "Class Name", "Department Name"
    HAVING COUNT(*) >= 50
)
SELECT
    product_class,
    department,
    total_class_reviews,
    negative_reviews,
    size_fit_complaints,
    ROUND(100.0 * negative_reviews / total_class_reviews, 2) AS negative_rate_pct,
    ROUND(100.0 * size_fit_complaints / NULLIF(negative_reviews, 0), 2) AS pct_negatives_due_to_fit,
    ROUND(100.0 * size_fit_complaints / total_class_reviews, 2) AS fit_complaint_share_of_all_reviews_pct
FROM ClassNegativeStats
ORDER BY size_fit_complaints DESC;

