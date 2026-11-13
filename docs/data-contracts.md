# Data contracts

What each source looks like on arrival. All timestamps are UTC ISO-8601 with a
`Z` suffix. All amounts are integers in minor units (paise, cents, fils, pence).

## processor_events

`landing/processor_events/arrival_date=YYYY-MM-DD/events_HH.jsonl`

One JSON object per line. Files are cut by delivery time in 6-hour windows
(`HH` = 00, 06, 12, 18), so a file holds whatever arrived in that window,
whatever day it happened.

| Field | Type | Notes |
|---|---|---|
| `event_id` | string | unique per delivery attempt, usually |
| `event_type` | string | `payment.captured`, `refund.succeeded`, `chargeback.debited` |
| `api_version` | string | changes mid-period |
| `created_at` | timestamp | when it happened (event time) |
| `delivered_at` | timestamp | when we received it (arrival time) |
| `data.payment_id` | string | the payment the event belongs to |
| `data.merchant_id` | string | |
| `data.amount_minor` | int | always positive; `event_type` gives direction |
| `data.currency` | string | presentment currency |
| `data.order_id` | string | captures only |
| `data.fee_minor` | int | captures and chargebacks |
| `data.refund_id` | string | refunds only |
| `data.chargeback_id` | string | chargebacks only |
| `data.payment_method` | string | captures, newer `api_version` only |

## bank_statements

`landing/bank_statements/statement_date=YYYY-MM-DD/statement_YYYYMMDD.csv`

Business days only. One line per payout.

| Field | Type | Notes |
|---|---|---|
| `account_id` | string | `ACC-INR-0001` or `ACC-USD-0001` |
| `statement_date` | date | |
| `line_no` | int | position in the statement file; (`statement_date`, `line_no`) identifies a line |
| `value_date` | date | |
| `direction` | string | `CR` or `DR` |
| `amount_minor` | int | always positive; `direction` gives sign |
| `currency` | string | settlement currency |
| `reference` | string | `PO-<merchant_id>-<activity yyyymmdd>`, sometimes blank |
| `narrative` | string | free text from the bank |

## merchant_master

`landing/merchant_master/snapshot_date=YYYY-MM-DD/merchants.csv`

A full snapshot every calendar day.

| Field | Type | Notes |
|---|---|---|
| `merchant_id` | string | |
| `legal_name` | string | |
| `country` | string | ISO-2 |
| `presentment_currency` | string | what customers pay in |
| `settlement_currency` | string | what lands in our bank |
| `fee_bps` | int | contract fee |
| `settlement_lag_days` | int | 1 or 2 business days |
| `status` | string | `ACTIVE` or `SUSPENDED` |
| `updated_at` | timestamp | when this version took effect in the source system |

## fx_rates

`landing/fx_rates/rate_date=YYYY-MM-DD/fx_rates.csv`

Business days only. No row on weekends or holidays.

| Field | Type | Notes |
|---|---|---|
| `rate_date` | date | |
| `base_currency` | string | USD, AED, GBP |
| `quote_currency` | string | INR |
| `mid_rate` | decimal(18,6) | stored as text; read as decimal, never float |

## _truth (scoring only)

| File | Holds |
|---|---|
| `defects.jsonl` | every planted defect: type, source, keys, expected place it gets caught |
| `merchant_changes.csv` | every contract change with its real effective date |
| `manifest.json` | config, row counts, defect counts |

The pipeline never reads `_truth`. Only the final scoring test does.
