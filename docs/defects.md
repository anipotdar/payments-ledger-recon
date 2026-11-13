# Planted defects

The generator plants these on purpose and records each one in
`_truth/defects.jsonl`. Build the pipeline without looking at that file. At the
end, score what was caught against it.

Counts below are from the default run (`seed=42`, 30 days, 25 merchants,
about 4,100 payment activities).

| Type | Source | What happens | Where it should be caught | Default count |
|---|---|---|---|---|
| `DUPLICATE_DELIVERY` | processor | same `event_id` delivered twice | silver dedup | 83 |
| `DUPLICATE_NEW_EVENT_ID` | processor | same capture resent under a new `event_id` | silver dedup on business key | 20 |
| `LATE_ARRIVAL` | processor | delivered 2 to 5 days after it happened | silver ordering, recon restatement | 124 |
| `OUT_OF_ORDER` | processor | refund delivered before its capture | silver ordering by event time | 46 |
| `MISSING_EVENT` | processor | capture never delivered, bank still pays it | recon: bank higher than ledger | 8 |
| `FEE_DRIFT` | processor | processor keeps the old fee for 3 days after a contract change | recon: point-in-time fee check | 2 |
| `SCHEMA_CHANGE` | processor | new API version adds `data.payment_method` | bronze schema evolution | 1 |
| `SETTLEMENT_DELAYED` | bank | payout lands one business day late | recon: timing break, ageing | 35 |
| `MISSING_PAYOUT` | bank | payout never arrives | recon: `NOT_IN_BANK` | 7 |
| `MISSING_REFERENCE` | bank | line has no payout reference | recon: fallback match | 21 |
| `BANK_CHARGE` | bank | Rs 29.50 deducted from a credit | recon: explained amount break | 28 |
| `FILE_RESEND` | bank | a statement file delivered twice under another name | bronze idempotency | 1 |
| `BACKDATED_MASTER_CHANGE` | merchant master | fee change shows up 2 days late with the real `updated_at` | silver SCD2 | 2 |
| `SNAPSHOT_GAP` | merchant master | merchant missing from one day's snapshot | silver SCD2 | 3 |

Not defects, but traps anyway:

- FX rates have no weekend rows.
- Bank value dates skip 2 Oct 2026 (holiday).
- Events near midnight land in the next day's arrival partition.
- One merchant is suspended mid-period. Refunds on its earlier payments can still arrive.
- One merchant changes name only. SCD type 1 or type 2? Your call, write it down.
