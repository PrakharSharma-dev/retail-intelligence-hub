# Planted Data Patterns (ground truth)

The data in this project is **simulated**. To check that the analysis pipeline
actually works, the generator (`scripts/generate_orders.py`) plants known
patterns. Later, the SQL analysis should *rediscover* them. If it does, the
pipeline is trustworthy; if it doesn't, something upstream is broken.

| # | Business question | Planted pattern | Measured in the clean data |
|---|-------------------|-----------------|----------------------------|
| 1 | Which hubs miss the 30-min SLA, and when? | Hubs 2, 5, 7 (Pune, Ajmer, Alwar) are slow 8-11 PM: 35% of those orders get +10-20 min | On-time: 56% (slow hubs, night) vs 85-92% elsewhere |
| 2 | Where does discounting leak margin? | Snacks discount ramps 3% -> 30% over 12 months; demand does not respond. Other categories ramp 3% -> 8% and demand rises slightly | Snack share of units stays ~21-25% while discount rate goes from ~12% to ~33% |
| 3 | Why is revenue up but profit down? | Result of pattern 2 plus rising delivery cost (+0.8%/month) | Monthly revenue grows ~40x (Oct -> Sep); gross margin 12% -> 3%; operating profit peaks Jan and turns negative from Apr |
| 4a | Who is leaving? (service) | Two consecutive late deliveries -> 25% chance of churning (base 4%) | Churn after 2 late orders in a row: ~21% vs ~3% |
| 4b | Who is leaving? (offers) | ~50% of customers get a 10-15% welcome coupon on orders 1-3. On order 4 the coupon disappears -> 30% churn | Churn right after order 4: ~31% (offer) vs ~4% (no offer) |
| 5 | Where are we slow? | Baskets of 10+ units take +8 min | (check in Phase 3) |

## Other design choices to remember
- Order volume grows because signups grow (about 46 signups in Oct 2025 vs ~240/month by Aug 2026).
- Supplier cost creeps up 0.4%/month, and each line stores the **unit cost at time of sale**.
- Slow hubs 2, 5 and 7 are exactly the three `residential` hubs, so the data cannot separate "residential zone" from "these specific hubs". Mention this limitation in the README.
- 2% of orders are cancelled (no delivery time). Exclude them from SLA and revenue.

## Planted data-quality issues (fixed in Phase 2)
| Table | Issue | Share |
|-------|-------|-------|
| stg_customers | missing city / missing phone | 2% each |
| stg_customers | signup_date as DD/MM/YYYY | 3% |
| stg_customers | names in CAPS with extra spaces | 1.5% |
| stg_orders | missing customer_id | 1.5% |
| stg_orders | orphan customer_id (no such customer) | 1% |
| stg_orders | order_placed_at as DD-MM-YYYY HH:MM | 3% |
| stg_order_items | extreme quantity (100-500) | 0.3% |
| stg_order_items | NULL discount_amount (recoverable as gross - net) | 1% |

The generator also writes `_mess_log.csv` / `_mess_log_orders.csv` and
`_truth_customers.csv` (who got an offer, who churned and why) into
`data/raw/`. These are answer keys for validating the cleaning and analysis.
