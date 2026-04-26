# Cosmo

**A self-hosted, multi-currency budget tracker for expats and digital nomads.**

> ⚠️ **Status: pre-v1.** Active rewrite in progress on `cosmo-v1`. See [`docs/PLAN.md`](#roadmap) for the full roadmap.

---

## Why this exists

Most budgeting apps assume you live in one country, earn in one currency, and spend in that same currency. If you don't — if your salary lands in EUR, your UK rental income comes in GBP, and your freelance clients pay in USD — the mainstream tools fight you:

- **YNAB** ([explicit guidance](https://support.ynab.com/en_us/using-multiple-currencies-in-ynab-a-guide-SyBF6PHno)): run separate budgets per currency or use third-party plugins.
- **Monarch / Copilot**: USD-first; international transactions show up unconverted or in your card's settlement currency.
- **Actual Budget** (the leading self-hosted option): [open issue #3351](https://github.com/actualbudget/actual/issues/3351) requesting native multi-currency, unresolved.
- **Firefly III**: full multi-currency, but Laravel + double-entry bookkeeping = a steep climb for normal users.

Cosmo's goal is the gap in the middle: **simple like Actual, multi-currency like Firefly, self-hosted like both, designed for the 40M+ people whose money crosses borders.**

## Core features (v1, in flight)

- **Per-account currency.** Hold accounts in EUR, USD, GBP, CHF, JPY, etc. simultaneously.
- **Historical FX snapshots.** Every transaction stores its original amount, original currency, and the exchange rate used at the date it occurred. Rate changes don't rewrite history.
- **Smart merchant categorization.** Fuzzy matching with normalization — "TESCO STORES 1234 LONDON" auto-categorizes as Groceries because you tagged "Tesco" once. Per-user, transparent rules you can audit and edit.
- **Pluggable CSV importers.** Revolut, Wise, N26, generic CSV. Adding a new bank is a small adapter file.
- **Accounts & transfers.** Multiple accounts per user; transfers between accounts are pair-linked and excluded from income/expense totals.
- **Self-hostable.** Single `docker compose up` on a homelab or VPS. SQLite by default; Postgres optional.
- **Privacy-first.** No bank API needed. No data leaves your server. MIT-licensed.

## Quick start

```bash
git clone https://github.com/KarimJebara/Cosmo.git
cd Cosmo
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # edit SECRET_KEY at minimum
python app.py
```

Open `http://localhost:5002`. Sign up, then start adding income, expenses, and budgets. Reset dev data anytime with `python reset_for_testing.py`.

## Running tests

```bash
pip install -r requirements/test.txt
pytest -q
```

## Roadmap

The full plan (8 weeks, 8 phases) lives in [`docs/PLAN.md`](docs/PLAN.md):

| Phase | Focus | Status |
|---|---|---|
| 0 | Repo hygiene, security baseline (argon2), drop dead code | **In progress** |
| 1 | SQLAlchemy + Alembic, unified `transactions` schema | Next |
| 2 | Multi-currency engine (the wedge): per-account currency, historical FX | |
| 3 | Merchant intelligence: fuzzy matching, per-user rules | |
| 4 | Accounts model + transfers + importer framework | |
| 5 | Budgets/analytics polish, mobile-responsive CSS | |
| 6 | Dockerfile, docker-compose, GitHub Actions CI | |
| 7 | Launch: Show HN, r/selfhosted, awesome-selfhosted | |

## How Cosmo compares

| | Cosmo (target) | Actual Budget | Firefly III | YNAB | Monarch |
|---|---|---|---|---|---|
| Self-hosted | ✅ | ✅ | ✅ | ❌ | ❌ |
| Native multi-currency | ✅ | ❌ ([#3351](https://github.com/actualbudget/actual/issues/3351)) | ✅ | ❌ | ❌ |
| Simple to deploy | ✅ | ✅ | ⚠️ heavy | n/a | n/a |
| Learning merchant rules | ✅ | ⚠️ rule-based | ⚠️ rule-based | ⚠️ payee memory | ✅ ML |
| Open source | ✅ MIT | ✅ MIT | ✅ AGPL | ❌ | ❌ |
| Price | Free | Free / $1.40/mo hosted | Free | $14.99/mo | $14.99/mo |

## Contributing

Pre-v1, the API and schema are still moving. If you want to follow along or contribute, open an issue first — happy to chat about scope.

## License

MIT. See `LICENSE` (added in Phase 6).
