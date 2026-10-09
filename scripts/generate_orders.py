"""
generate_orders.py
Simulates 12 months of orders for every customer and plants the hidden
business patterns (see docs/data_patterns.md), then adds data-quality mess.

Run (from project root):  python scripts/generate_orders.py
Needs:  data/raw/dim_hubs.csv, dim_products.csv, stg_customers.csv
Output (data/raw/):
    stg_orders.csv        one row per order (raw, messy)
    stg_order_items.csv   one row per order line (raw, messy)
    _truth_customers.csv  answer key: who got the discount offer, who churned, why
    _mess_log_orders.csv  answer key: every row we deliberately damaged
"""

from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# 1. Settings and the PLANTED PATTERNS (our "ground truth")
# ---------------------------------------------------------------------------
SEED = 42
rng = np.random.default_rng(SEED)

OUT = Path(__file__).resolve().parent.parent / "data" / "raw"

START_DAY = datetime(2025, 10, 1)
END_DAY = datetime(2026, 9, 30)
SLA_MIN = 30                      # promise: delivered within 30 minutes

# Pattern 1: these hubs are slow between 8 and 11 PM
SLOW_NIGHT_HUB_IDS = {2, 5, 7}
SLOW_HOURS = {20, 21, 22}
SLOW_PROB = 0.35                  # not every night order is slow (noise)

# Pattern 2: this category gets heavy discounts but demand does NOT respond
HEAVY_DISCOUNT_CATEGORY = "Snacks"

# Pattern 3: two late deliveries in a row -> 25% chance of churning
# Pattern 4: welcome-offer customers lose the coupon on order 4 -> 30% churn
BASE_CHURN = 0.04
LATE_STREAK_CHURN = 0.25
OFFER_END_CHURN = 0.30
OFFER_SHARE = 0.50                # half of customers get a welcome coupon
OFFER_ORDERS = 3                  # coupon valid on their first 3 orders

# Q5: big baskets (10+ units) take longer to pack and deliver
BIG_BASKET_UNITS = 10
BIG_BASKET_EXTRA_MIN = 8

# ---------------------------------------------------------------------------
# 2. Load the dimension data and customers
# ---------------------------------------------------------------------------
hubs = pd.read_csv(OUT / "dim_hubs.csv")
products = pd.read_csv(OUT / "dim_products.csv")
cust = pd.read_csv(OUT / "stg_customers.csv")

# signup_date has two formats (that's our planted mess). Read ISO first,
# then fall back to DD/MM/YYYY. Never let pandas guess.
parsed = pd.to_datetime(cust["signup_date"], format="%Y-%m-%d", errors="coerce")
parsed = parsed.fillna(pd.to_datetime(cust["signup_date"], format="%d/%m/%Y", errors="coerce"))
assert parsed.notna().all()
cust["signup_dt"] = parsed

# Each customer is served by the hub in their city. Customers with a missing
# city really live somewhere, so we give them a random hub.
city_to_hub = dict(zip(hubs["city"], hubs["hub_id"]))
cust["hub_id"] = cust["city"].map(city_to_hub)
missing = cust["hub_id"].isna()
cust.loc[missing, "hub_id"] = rng.choice(hubs["hub_id"], size=missing.sum())
cust["hub_id"] = cust["hub_id"].astype(int)

# ---------------------------------------------------------------------------
# 3. Product / category helpers
# ---------------------------------------------------------------------------
CATS = ["Dairy & Bakery", "Snacks", "Beverages", "Staples"]
CAT_BASE_WEIGHT = {"Dairy & Bakery": 0.30, "Snacks": 0.25, "Beverages": 0.20, "Staples": 0.25}
cat_products = {c: products[products["category"] == c].reset_index(drop=True) for c in CATS}


def month_index(dt):
    """0 for Oct 2025 ... 11 for Sep 2026."""
    return (dt.year - 2025) * 12 + dt.month - 10


def item_discount(cat, m):
    """Item-level discount rate by category and month."""
    if cat == HEAVY_DISCOUNT_CATEGORY:
        return 0.03 + 0.27 * m / 11      # ramps 3% -> 30%
    return 0.03 + 0.05 * m / 11          # others ramp 3% -> 8%


def category_probs(m):
    """Chance that a line is from each category in month m.
    Normal categories sell MORE when discounted. Snacks do NOT (flat volume)."""
    w = []
    for c in CATS:
        base = CAT_BASE_WEIGHT[c]
        if c == HEAVY_DISCOUNT_CATEGORY:
            w.append(base)                              # flat: ignores discount
        else:
            w.append(base * (1 + 2 * item_discount(c, m)))
    w = np.array(w)
    return w / w.sum()


CAT_P = {m: category_probs(m) for m in range(12)}

# Order-time-of-day weights (hours 7..23): morning bump, big evening peak
HOURS = np.arange(7, 24)
HOUR_W = np.array([2, 4, 5, 4, 3, 3, 3, 2, 2, 3, 4, 6, 9, 11, 11, 7, 3], dtype=float)
HOUR_P = HOUR_W / HOUR_W.sum()

# ---------------------------------------------------------------------------
# 4. Simulate every customer, order by order
#    (we must go in order because churn depends on what happened before)
# ---------------------------------------------------------------------------
order_rows, item_rows, truth_rows = [], [], []
order_id = 0
line_id = 0

for cid, signup, hub_id in zip(cust["customer_id"], cust["signup_dt"], cust["hub_id"]):
    speed = rng.lognormal(0, 0.35)                 # some customers order more often
    is_offer = rng.random() < OFFER_SHARE          # hidden: got the welcome coupon?
    t = signup.to_pydatetime() + timedelta(days=int(rng.integers(0, 4)))
    n = 0
    late_hist = []
    churned, churn_n, churn_reason = False, None, None

    while t <= END_DAY:
        n += 1
        order_id += 1
        hour = int(rng.choice(HOURS, p=HOUR_P))
        ts = t.replace(hour=hour, minute=int(rng.integers(0, 60)))
        m = month_index(ts)
        coupon = rng.uniform(0.10, 0.15) if (is_offer and n <= OFFER_ORDERS) else 0.0

        # ---- basket: 1 to 8 distinct products --------------------------------
        n_lines = min(1 + int(rng.poisson(2.0)), 8)
        chosen = set()
        units = 0
        for cat in rng.choice(CATS, size=n_lines, p=CAT_P[m]):
            prod = cat_products[cat].iloc[int(rng.integers(0, len(cat_products[cat])))]
            if prod["product_id"] in chosen:
                continue
            chosen.add(prod["product_id"])
            qty = 1 + int(rng.random() < 0.35) + int(rng.random() < 0.10)
            units += qty

            item_rate = item_discount(cat, m) * rng.uniform(0.8, 1.2)
            total_rate = 1 - (1 - item_rate) * (1 - coupon)     # item + coupon combined
            gross = qty * prod["retail_price"]
            discount = round(gross * total_rate, 2)
            line_id += 1
            item_rows.append(
                (
                    line_id, order_id, int(prod["product_id"]), qty,
                    float(prod["retail_price"]), float(gross), discount,
                    round(gross - discount, 2),
                    # supplier prices creep up ~0.4% a month: store cost AT TIME OF SALE
                    round(float(prod["cost_price"]) * (1 + 0.004 * m), 2),
                )
            )

        # ---- delivery ---------------------------------------------------------
        cancelled = rng.random() < 0.02
        if cancelled:
            minutes, delivered_at, late = np.nan, pd.NaT, False
        else:
            mins = rng.normal(23, 5)
            if hour in (19, 20, 21, 22):
                mins += 2                                       # evening rush
            if units >= BIG_BASKET_UNITS:
                mins += BIG_BASKET_EXTRA_MIN                    # Q5 pattern
            if hub_id in SLOW_NIGHT_HUB_IDS and hour in SLOW_HOURS and rng.random() < SLOW_PROB:
                mins += rng.uniform(10, 20)                     # Pattern 1
            minutes = max(10, int(round(mins)))
            delivered_at = ts + timedelta(minutes=minutes)
            late = minutes > SLA_MIN

        delivery_cost = round(max(12.0, rng.normal(24, 4)) * (1 + 0.008 * m), 2)
        order_rows.append(
            (order_id, int(cid), int(hub_id), ts, delivered_at, minutes,
             delivery_cost, "cancelled" if cancelled else "delivered")
        )
        late_hist.append(late)

        # ---- did the customer churn after this order? -------------------------
        p, reason = BASE_CHURN, "random"
        if is_offer and n == OFFER_ORDERS + 1:
            p, reason = OFFER_END_CHURN, "discount_removed"      # Pattern 4
        if len(late_hist) >= 2 and late_hist[-1] and late_hist[-2] and LATE_STREAK_CHURN > p:
            p, reason = LATE_STREAK_CHURN, "late_streak"         # Pattern 3
        if rng.random() < p:
            churned, churn_n, churn_reason = True, n, reason
            break

        gap = max(1, int(round(rng.gamma(2.0, 4.0 * speed))))   # mean ~8 days
        t = t + timedelta(days=gap)

    truth_rows.append((int(cid), is_offer, n, churned, churn_n, churn_reason))

orders = pd.DataFrame(
    order_rows,
    columns=["order_id", "customer_id", "hub_id", "order_placed_at", "delivered_at",
             "delivery_minutes", "delivery_cost", "order_status"],
)
items = pd.DataFrame(
    item_rows,
    columns=["line_id", "order_id", "product_id", "quantity", "unit_price",
             "gross_amount", "discount_amount", "net_amount", "unit_cost_at_sale"],
)
truth = pd.DataFrame(
    truth_rows,
    columns=["customer_id", "got_welcome_offer", "n_orders", "churned",
             "churn_order_no", "churn_reason"],
)

# ---------------------------------------------------------------------------
# 5. Validate the CLEAN data, and check the patterns are really in it
# ---------------------------------------------------------------------------
assert orders["order_id"].is_unique and items["line_id"].is_unique
assert items["order_id"].isin(orders["order_id"]).all()
assert not items.duplicated(["order_id", "product_id"]).any()
assert (items["net_amount"] <= items["gross_amount"]).all()


def pattern_checks():
    d = orders[orders["order_status"] == "delivered"].copy()
    d["hour"] = d["order_placed_at"].dt.hour
    d["slow_hub"] = d["hub_id"].isin(SLOW_NIGHT_HUB_IDS)
    d["night"] = d["hour"].isin(SLOW_HOURS)
    d["on_time"] = d["delivery_minutes"] <= SLA_MIN

    print("\n[Pattern 1] On-time % by hub group and time (expect low only for slow hubs at night)")
    print((d.groupby(["slow_hub", "night"])["on_time"].mean() * 100).round(1).to_string())

    li = items.merge(orders[["order_id", "order_placed_at", "order_status", "delivery_cost"]], on="order_id")
    li = li[li["order_status"] == "delivered"]
    li["month"] = li["order_placed_at"].dt.to_period("M")
    li = li.merge(products[["product_id", "category"]], on="product_id")
    li["cogs"] = li["quantity"] * li["unit_cost_at_sale"]

    print("\n[Pattern 2] Snacks: discount % vs units sold per month (expect discount up, units flat-ish)")
    sn = li[li["category"] == HEAVY_DISCOUNT_CATEGORY].groupby("month").agg(
        gross=("gross_amount", "sum"), disc=("discount_amount", "sum"), units=("quantity", "sum"))
    allu = li.groupby("month")["quantity"].sum()
    sn["disc_pct"] = (sn["disc"] / sn["gross"] * 100).round(1)
    sn["share_of_units_%"] = (sn["units"] / allu * 100).round(1)
    print(sn[["disc_pct", "units", "share_of_units_%"]].to_string())

    print("\n[Q3] Monthly economics (expect revenue up, profit squeezed)")
    ords = orders[orders["order_status"] == "delivered"].copy()
    ords["month"] = ords["order_placed_at"].dt.to_period("M")
    eco = li.groupby("month").agg(revenue=("net_amount", "sum"), cogs=("cogs", "sum"))
    eco["delivery_cost"] = ords.groupby("month")["delivery_cost"].sum()
    eco["gross_margin_%"] = ((eco["revenue"] - eco["cogs"]) / eco["revenue"] * 100).round(1)
    eco["operating_profit"] = eco["revenue"] - eco["cogs"] - eco["delivery_cost"]
    eco["orders"] = ords.groupby("month").size()
    print(eco[["orders", "revenue", "gross_margin_%", "operating_profit"]].round(0).to_string())

    print("\n[Pattern 4] Churn right after order 4: welcome-offer vs not (customers with 4+ orders)")
    t4 = truth[truth["n_orders"] >= 4]
    print((t4.groupby("got_welcome_offer")["churn_order_no"]
           .apply(lambda s: (s == 4).mean() * 100).round(1)).to_string())

    print("\n[Pattern 3] Why customers churned:")
    print(truth["churn_reason"].value_counts(dropna=False).to_string())


# Run the checks NOW, while the data is still clean (before we add the mess)
if __name__ == "__main__":
    pattern_checks()


# ---------------------------------------------------------------------------
# 6. Plant the mess (raw staging layer) and log every damaged row
# ---------------------------------------------------------------------------
mess_log = []


def pick(n_total, share):
    return rng.choice(n_total, size=int(n_total * share), replace=False)


# Dates become text so we can mix formats
orders["order_placed_at"] = orders["order_placed_at"].dt.strftime("%Y-%m-%d %H:%M:%S")
orders["delivered_at"] = orders["delivered_at"].dt.strftime("%Y-%m-%d %H:%M:%S")
orders["customer_id"] = orders["customer_id"].astype("Int64")

# (a) 1.5% of orders: customer_id missing
for pos in pick(len(orders), 0.015):
    mess_log.append(("orders", int(orders.at[pos, "order_id"]), "missing_customer_id"))
    orders.at[pos, "customer_id"] = pd.NA

# (b) 1% of orders: customer_id points to a customer that doesn't exist (orphan)
for pos in pick(len(orders), 0.01):
    if pd.isna(orders.at[pos, "customer_id"]):
        continue
    mess_log.append(("orders", int(orders.at[pos, "order_id"]), "orphan_customer_id"))
    orders.at[pos, "customer_id"] = int(rng.integers(90000, 99999))

# (c) 3% of orders: order_placed_at as DD-MM-YYYY HH:MM
for pos in pick(len(orders), 0.03):
    ts = pd.Timestamp(orders.at[pos, "order_placed_at"])
    orders.at[pos, "order_placed_at"] = ts.strftime("%d-%m-%Y %H:%M")
    mess_log.append(("orders", int(orders.at[pos, "order_id"]), "date_format_ddmmyyyy"))

# (d) 0.3% of lines: absurd quantities (data-entry errors); totals scale with them
for pos in pick(len(items), 0.003):
    old_q = items.at[pos, "quantity"]
    new_q = int(rng.integers(100, 500))
    factor = new_q / old_q
    items.at[pos, "quantity"] = new_q
    items.at[pos, "gross_amount"] = round(items.at[pos, "gross_amount"] * factor, 2)
    items.at[pos, "discount_amount"] = round(items.at[pos, "discount_amount"] * factor, 2)
    items.at[pos, "net_amount"] = round(items.at[pos, "net_amount"] * factor, 2)
    mess_log.append(("order_items", int(items.at[pos, "line_id"]), "extreme_quantity"))

# (e) 1% of lines: discount_amount is NULL (net_amount is still right,
#     so Phase 2 can rebuild it as gross - net)
for pos in pick(len(items), 0.01):
    items.at[pos, "discount_amount"] = np.nan
    mess_log.append(("order_items", int(items.at[pos, "line_id"]), "null_discount"))

# ---------------------------------------------------------------------------
# 7. Save
# ---------------------------------------------------------------------------
orders.to_csv(OUT / "stg_orders.csv", index=False)
items.to_csv(OUT / "stg_order_items.csv", index=False)
truth.to_csv(OUT / "_truth_customers.csv", index=False)
pd.DataFrame(mess_log, columns=["table", "row_id", "issue"]).to_csv(
    OUT / "_mess_log_orders.csv", index=False
)

if __name__ == "__main__":
    print(f"Orders: {len(orders):,}   Order lines: {len(items):,}   Customers: {len(truth):,}")
    print("Planted mess:")
    print(pd.DataFrame(mess_log, columns=["t", "id", "issue"])["issue"].value_counts().to_string())
