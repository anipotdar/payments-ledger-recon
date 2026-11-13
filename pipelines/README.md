# Pipelines

Databricks notebooks (Python and SQL source files, synced by the bundle).

| Layer | Notebook | Status |
|---|---|---|
| setup | `00_setup.sql` | done |
| bronze | `bronze/processor_events.py` | stub, weekend 1 |
| bronze | `bronze/bank_statements.py` | weekend 1 |
| bronze | `bronze/merchant_snapshots.py` | weekend 1 |
| bronze | `bronze/fx_rates.py` | weekend 1 |
| silver | `silver/events.py`: dedup, event-time order | weekend 2 |
| silver | `silver/merchants_scd2.py` | weekend 2 |
| ledger | `ledger/post_entries.py`: double entry, append only | weekend 2 |
| recon | `recon/match.py`: exact, tolerance, many-to-one | weekend 3 |
| recon | `recon/breaks.py`: reason codes, ageing | weekend 3 |
| gold | `gold/trial_balance.sql`, dashboard | weekend 4 |

Free Edition limits that shape this: serverless only, max 5 concurrent job
tasks, one active declarative pipeline per type. A single daily job with
sequential tasks fits comfortably.
