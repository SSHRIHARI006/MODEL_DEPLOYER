# Marketplace notes — simplified credit system

This document describes the billing feature set that actually exists, replacing the
original marketplace/wallet pivot spec (deleted). There is no real money anywhere in
this system: credits are an internal accounting unit only.

## What is built

- **Wallet** (`billing.Wallet`) — one per user; tracks `credit_balance`,
  `lifetime_earned`, and `lifetime_spent`.
- **Ledger** (`billing.LedgerTransaction`) — immutable audit log of credit movements.
  Transaction types are `DEPOSIT` and `INFERENCE` only.
- **Starting credits** — every new account is granted `BILLING_STARTING_CREDITS`
  (default 100) automatically on signup.
- **Free top-up** — `POST /api/wallet/deposit/` increments the balance and writes a
  `DEPOSIT` ledger entry. There is no payment processor behind it. It is disabled
  unless `BILLING_DEMO_DEPOSITS=true` and the caller is staff (see `docs/security.md`).
- **Per-model charge rate** — `Model.cost_per_run` (default 1 credit/inference),
  settable at upload or update time through the model registry API. It must be a
  finite, non-negative decimal: the update endpoint validates it and the database
  carries a `cost_per_run >= 0` check constraint.
- **Monetized gateway** — `POST /api/v1/inference/@<username>/<model_name>/` checks
  the consumer's balance before running, returns `402 Payment Required` with the
  balance and cost when credits are insufficient, and on success deducts the charge
  from the consumer and credits the model owner in full, writing one `INFERENCE`
  ledger entry. Universal API keys (`md_live_...`) or JWT both authenticate this
  endpoint.

## Explicitly out of scope

- No `PAYOUT` transaction type or any cash-out/withdrawal flow.
- No payment gateway integration (Stripe or otherwise) — "add credits" just
  increments a number.
- No marketplace economics: no revenue share, platform cut, or pricing tiers. The
  creator receives the full charge amount.

## Self-hosting

Self-hosted instances almost never want billing enforced. Set `BILLING_ENABLED=false`
in `.env` to skip the balance check and all wallet/ledger writes on predict;
inference then runs unconditionally and only `PredictionLog` is written. The
`.env.example` ships with billing disabled.
