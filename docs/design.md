# Design

## The setup

We are a payment facilitator. Customers pay our merchants through an external
card processor. The processor takes its fee, nets off refunds and chargebacks,
and pays the rest into our bank account: one credit per merchant per activity
day, T+1 or T+2 business days later, in the merchant's settlement currency.

Three systems describe that money and none of them is fully right:

| Source | Tells us | Can't be trusted on |
|---|---|---|
| Processor webhooks | each capture, refund, chargeback and fee | delivery: duplicates, late, out of order, missing |
| Bank statement | what cash actually arrived | references, timing, small deductions, FX |
| Merchant master | contract terms: fee, lag, status | when a change really took effect |

The ledger is the one place they are reconciled. If it balances and every
difference has a reason, finance can close the day.

## Money rules (what the generator implements)

- Capture fee = `amount * fee_bps / 10000`, rounded half up, using the fee the processor applied that day.
- Refunds do not return the capture fee.
- Chargebacks reverse the full amount plus a flat fee (INR 500, USD 15, AED 55, GBP 12).
- Payout for (merchant, activity date) = captures - refunds - chargebacks - all fees.
- Value date = activity date + lag business days. Weekends and listed bank holidays skipped.
- Cross-currency merchants are converted on the value date at mid rate less 35 bps.
- A negative net becomes a bank debit (DR line). A zero net produces no line.
- All amounts are integers in minor units. No floats anywhere.

## Chart of accounts (draft)

| Account | Type | Holds |
|---|---|---|
| `processor_receivable:<ccy>` | asset | what the processor owes us |
| `bank:<account_id>` | asset | cash in our accounts |
| `merchant_payable:<merchant_id>:<ccy>` | liability | what we owe each merchant |
| `fx_gain_loss` | P&L | conversion differences |
| `bank_charges` | expense | deductions the bank takes |
| `suspense:<ccy>` | asset/liability | money we can't explain yet |

## Posting rules

Every event becomes one journal entry with two or more legs that sum to zero.

| Event | Debit | Credit |
|---|---|---|
| capture, gross | `processor_receivable` | `merchant_payable` |
| capture, fee | `merchant_payable` | `processor_receivable` |
| refund | TODO | TODO |
| chargeback, amount and fee | TODO | TODO |
| payout received, same currency | TODO | TODO |
| payout received, converted | TODO (hint: three legs) | TODO |
| bank charge on a payout | TODO | TODO |
| unmatched bank credit | TODO (hint: it can't stay off the books) | TODO |

## Layers

| Layer | Rule |
|---|---|
| bronze | raw lines as delivered, plus file path and ingest time. Never cleaned. Replays change nothing. |
| silver | one row per business event, ordered by event time. Merchants as SCD2 from `updated_at`. |
| ledger | append only, effective dated. Corrections are reversing entries. |
| recon | daily three-way match. Unmatched items become breaks with a reason and an age. |
| gold | trial balance, break summary, dashboard. |

## Invariants

1. Ledger debits equal credits per currency, per day and overall.
2. Every journal entry balances on its own.
3. Replaying any landing file changes nothing.
4. Rebuilding 30 days from scratch gives the same ledger and breaks.
5. Every bank line ends up matched or in breaks. Nothing disappears.

These are tests in `tests/test_invariants.py`.

## Break reason codes (starter list)

| Code | Meaning | Clears itself? |
|---|---|---|
| `TIMING` | expected payout not in bank yet, inside a grace window | usually |
| `NOT_IN_BANK` | expected payout never arrived past the grace window | no |
| `NOT_IN_LEDGER` | bank credit with no matching expectation | no |
| `AMOUNT_BANK_CHARGE` | short by a known bank charge | no, book it |
| `AMOUNT_FEE_MISMATCH` | processor fee differs from the contract fee for that day | no, raise with processor |
| `AMOUNT_FX` | converted amount outside tolerance | no |
| `MATCHED_WITHOUT_REFERENCE` | matched on account + date + amount, flag for review | n/a |

## Decisions to make and defend

Write each one up in the README once made: the choice, the alternative, why.

1. **Dedup key.** `event_id` alone misses the retry that mints a new id. What is the business key, and what do you keep when two rows collide?
2. **Late data.** An event lands three days late. Do you restate the earlier day's recon or post a correction today? What does finance see?
3. **SCD2 source of time.** Snapshot date or `updated_at`? What happens with a backdated change you only see two days later?
4. **Matching tolerance.** How wide is the FX band, and why that number? What stops a tolerance from hiding a real error?

## Out of scope for v1

Partial captures and auths, multi-processor routing, merchant payouts out of
our bank, intraday recon, time zones other than UTC.
