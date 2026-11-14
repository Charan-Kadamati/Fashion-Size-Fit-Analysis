import os
import sys
import urllib.request
import pandas as pd

CANDIDATE_URLS = [
    "https://raw.githubusercontent.com/AFAgarap/ecommerce-reviews-analysis/master/Womens%20Clothing%20E-Commerce%20Reviews.csv",
    "https://raw.githubusercontent.com/hanzhang0420/Women-Clothing-E-commerce/master/Womens%20Clothing%20E-Commerce%20Reviews.csv",
    "https://raw.githubusercontent.com/Mraghuvaran/-womens_clothing_e_commerce_reviews/master/Womens%20Clothing%20E-Commerce%20Reviews.csv",
    "https://raw.githubusercontent.com/tirthgala/Customer-Review-Sentiment-Analysis/master/Womens%20Clothing%20E-Commerce%20Reviews.csv"
]

DEST_DIR = os.path.join(os.path.dirname(__file__), "data")
DEST_FILE = os.path.join(DEST_DIR, "reviews.csv")

REQUIRED_COLUMNS = [
    "Clothing ID",
    "Age",
    "Title",
    "Review Text",
    "Rating",
    "Recommended IND",
    "Positive Feedback Count",
    "Division Name",
    "Department Name",
    "Class Name"
]

def download_dataset():
    os.makedirs(DEST_DIR, exist_ok=True)
    temp_file = os.path.join(DEST_DIR, "raw_download.csv")
    
    downloaded = False
    for url in CANDIDATE_URLS:
        print(f"Attempting download from: {url}")
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            )
            with urllib.request.urlopen(req, timeout=30) as response, open(temp_file, "wb") as out_file:
                out_file.write(response.read())
            print(f"Successfully downloaded raw data from {url}")
            downloaded = True
            break
        except Exception as e:
            print(f"Failed to download from {url}: {e}")
            continue

    if not downloaded:
        print("ERROR: All candidate mirror URLs failed. Please check internet connection or provide data/reviews.csv manually.")
        sys.exit(1)

    print("Verifying and formatting dataset...")
    df = pd.read_csv(temp_file)
    
    # If there is an unnamed index column, drop it
    unnamed_cols = [c for c in df.columns if "Unnamed" in c]
    if unnamed_cols:
        df = df.drop(columns=unnamed_cols)

    row_count = len(df)
    print(f"Total row count: {row_count}")
    
    # Verify standard columns
    missing_cols = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing_cols:
        print(f"ERROR: Missing expected columns: {missing_cols}")
        print(f"Actual columns: {list(df.columns)}")
        sys.exit(1)

    # Save cleanly to DEST_FILE
    df.to_csv(DEST_FILE, index=False)
    if os.path.exists(temp_file):
        os.remove(temp_file)

    print(f"SUCCESS: Saved verified dataset with {row_count} rows and {len(df.columns)} columns to {DEST_FILE}")
    print("Columns present:")
    for col in df.columns:
        print(f" - {col}")

if __name__ == "__main__":
    download_dataset()
