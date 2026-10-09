"""
generate_dims.py
Builds the two small dimension tables for the Retail Intelligence Hub:
  - dim_hubs      (9 dark stores)
  - dim_products  (32 SKUs across 4 categories)

Run:  python generate_dims.py
Output: dim_hubs.csv, dim_products.csv
"""

import numpy as np
import pandas as pd
from pathlib import Path
OUT = Path(__file__).resolve().parent.parent / "data" / "raw"
OUT.mkdir(parents=True, exist_ok=True)

# A fixed seed makes the "random" numbers repeatable, so your results
# are the same every time you run the script. Always do this in pipelines.
rng = np.random.default_rng(42)

# ---------------------------------------------------------------------------
# GROUND TRUTH (the patterns we plan to plant later in the orders generator).
# Deliberately NOT written into dim_hubs: the warehouse should not "know"
# the answer. An analyst has to discover it from orders data.
# ---------------------------------------------------------------------------
SLOW_NIGHT_HUB_IDS = [2, 5, 7]   # slow between 8-11 PM (used in Phase 1b)
HEAVY_DISCOUNT_CATEGORY = "Snacks"  # heavy discount, flat volume (Phase 1b)

# ---------------------------------------------------------------------------
# dim_hubs
# ---------------------------------------------------------------------------
# (city, state, zone). Zone types: residential / commercial / mixed
hub_rows = [
    ("Delhi",   "Delhi",          "commercial"),
    ("Pune",    "Maharashtra",    "residential"),
    ("Mumbai",  "Maharashtra",    "commercial"),
    ("Kota",    "Rajasthan",      "mixed"),
    ("Ajmer",   "Rajasthan",      "residential"),
    ("Jaipur",  "Rajasthan",      "mixed"),
    ("Alwar",   "Rajasthan",      "residential"),
    ("Ujjain",  "Madhya Pradesh", "mixed"),
    ("Indore",  "Madhya Pradesh", "commercial"),
]

dim_hubs = pd.DataFrame(hub_rows, columns=["city", "state", "zone"])
dim_hubs.insert(0, "hub_id", range(1, len(dim_hubs) + 1))
dim_hubs.insert(
    1, "hub_name",
    dim_hubs["city"] + " " + dim_hubs["zone"].str.title() + " Hub",
)

# ---------------------------------------------------------------------------
# dim_products
# ---------------------------------------------------------------------------
# Margin range per category: cost_price = retail_price * (1 - margin)
MARGIN_RANGE = {
    "Dairy & Bakery": (0.10, 0.16),
    "Snacks":         (0.25, 0.35),
    "Beverages":      (0.18, 0.28),
    "Staples":        (0.10, 0.14),
}

# (category, sub_category, product_name, retail_price in INR)
products = [
    # Dairy & Bakery
    ("Dairy & Bakery", "Milk",   "Toned Milk 500ml",        29),
    ("Dairy & Bakery", "Milk",   "Full Cream Milk 1L",      68),
    ("Dairy & Bakery", "Curd",   "Curd 400g",               35),
    ("Dairy & Bakery", "Paneer", "Paneer 200g",             90),
    ("Dairy & Bakery", "Butter", "Butter 100g",             58),
    ("Dairy & Bakery", "Cheese", "Cheese Slices 200g",     140),
    ("Dairy & Bakery", "Bakery", "Brown Bread 400g",        45),
    ("Dairy & Bakery", "Eggs",   "Eggs 6 Pack",             48),
    # Snacks
    ("Snacks", "Chips",        "Potato Chips Salted 52g",   20),
    ("Snacks", "Chips",        "Masala Chips 90g",          40),
    ("Snacks", "Chips",        "Nachos Cheese 150g",        99),
    ("Snacks", "Biscuits",     "Cream Biscuits 120g",       30),
    ("Snacks", "Biscuits",     "Choco Cookies 150g",        60),
    ("Snacks", "Instant Food", "Instant Noodles 70g",       14),
    ("Snacks", "Namkeen",      "Namkeen Mixture 200g",      70),
    ("Snacks", "Popcorn",      "Butter Popcorn 90g",        50),
    # Beverages
    ("Beverages", "Soft Drinks",   "Cola 750ml",             40),
    ("Beverages", "Soft Drinks",   "Lemon Soda 600ml",       35),
    ("Beverages", "Juices",        "Orange Juice 1L",       120),
    ("Beverages", "Juices",        "Mango Drink 600ml",      45),
    ("Beverages", "Water",         "Mineral Water 1L",       20),
    ("Beverages", "Energy Drinks", "Energy Drink 250ml",    125),
    ("Beverages", "Tea & Coffee",  "Instant Coffee 50g",    150),
    ("Beverages", "Tea & Coffee",  "Tea Leaves 250g",       130),
    # Staples
    ("Staples", "Flour",     "Wheat Atta 5kg",              260),
    ("Staples", "Rice",      "Basmati Rice 1kg",            120),
    ("Staples", "Pulses",    "Toor Dal 1kg",                165),
    ("Staples", "Sugar",     "Sugar 1kg",                    48),
    ("Staples", "Salt",      "Iodised Salt 1kg",             28),
    ("Staples", "Oils",      "Sunflower Oil 1L",            140),
    ("Staples", "Oils",      "Mustard Oil 1L",              170),
    ("Staples", "Breakfast", "Poha 500g",                    45),
]

dim_products = pd.DataFrame(
    products, columns=["category", "sub_category", "product_name", "retail_price"]
)
dim_products.insert(0, "product_id", range(1, len(dim_products) + 1))

# Draw a random margin inside each category's range, then derive cost price.
low = dim_products["category"].map(lambda c: MARGIN_RANGE[c][0])
high = dim_products["category"].map(lambda c: MARGIN_RANGE[c][1])
margin = rng.uniform(low, high)
dim_products["cost_price"] = (dim_products["retail_price"] * (1 - margin)).round(2)

# ---------------------------------------------------------------------------
# Sanity checks: cheap now, expensive to debug later
# ---------------------------------------------------------------------------
assert dim_hubs["hub_id"].is_unique
assert dim_products["product_id"].is_unique
assert (dim_products["cost_price"] < dim_products["retail_price"]).all()
assert dim_products["retail_price"].gt(0).all()

dim_hubs.to_csv(OUT / "dim_hubs.csv", index=False)
dim_products.to_csv(OUT / "dim_products.csv", index=False)

if __name__ == "__main__":
    print(dim_hubs, "\n")
    print(dim_products.head(10), "\n")
    summary = (
        dim_products.assign(
            margin_pct=(1 - dim_products["cost_price"] / dim_products["retail_price"]) * 100
        )
        .groupby("category")["margin_pct"]
        .agg(["count", "min", "mean", "max"])
        .round(1)
    )
    print(summary)
