# Cosmo

**A self-hosted, multi-currency budget tracker for expats and digital nomads.**

> **Status: v1 release candidate.** Phases 0–6 of the roadmap are shipped; Phase 7 (launch prep) is in progress. See [`docs/PLAN.md`](docs/PLAN.md) for the full plan.

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

## Quick start (self-host with Docker)

```bash
git clone https://github.com/KarimJebara/Cosmo.git
cd Cosmo
cp .env.example .env
# Edit .env and set SECRET_KEY at minimum:
#   python -c "import secrets; print(secrets.token_urlsafe(48))"
docker compose up -d
```

Open `http://localhost:5002` and sign up. The SQLite database lives in a named Docker volume (`cosmo-data`) so it survives restarts and rebuilds.

The container migrates the schema on every boot (`python cli.py init-db`), exposes a `/healthz` liveness probe, and runs on a non-root user under gunicorn.

### Operator CLI

```bash
docker compose exec cosmo python cli.py create-user alice
docker compose exec cosmo python cli.py refresh-fx
docker compose exec cosmo python cli.py import revolut alice /data/revolut.csv
```

### Local development

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements/dev.txt
cp .env.example .env
python app.py            # http://localhost:5002
pytest -q                # 254 tests, ~10s
ruff check .             # 0 findings
```

## Roadmap

The full plan (8 weeks, 8 phases) lives in [`docs/PLAN.md`](docs/PLAN.md):

| Phase | Focus | Status |
|---|---|---|
| 0 | Repo hygiene, argon2 password hashing, drop dead code | ✅ done |
| 1 | SQLAlchemy + Alembic, unified `transactions` schema | ✅ done |
| 2 | Multi-currency engine: per-account currency, historical FX | ✅ done |
| 3 | Merchant intelligence: fuzzy matching, per-user rules | ✅ done |
| 4 | Accounts model + transfers + CSV importer framework | ✅ done |
| 5 | Budgets/analytics polish, mobile-responsive CSS | deferred |
| 6 | Dockerfile, docker-compose, GitHub Actions CI | ✅ done |
| 7 | Launch: Show HN, r/selfhosted, awesome-selfhosted | in progress |

## How Cosmo compares

| | Cosmo | Actual Budget | Firefly III | YNAB | Monarch |
|---|---|---|---|---|---|
| Self-hosted | ✅ | ✅ | ✅ | ❌ | ❌ |
| Native multi-currency | ✅ | ❌ ([#3351](https://github.com/actualbudget/actual/issues/3351)) | ✅ | ❌ | ❌ |
| Simple to deploy | ✅ `docker compose up` | ✅ | ⚠️ Laravel + double-entry | n/a (SaaS) | n/a (SaaS) |
| Learning merchant rules | ✅ fuzzy + per-user | ⚠️ rule-based | ⚠️ rule-based | ⚠️ payee memory | ✅ ML |
| Open source | ✅ MIT | ✅ MIT | ✅ AGPL | ❌ | ❌ |
| Price | Free | Free / $1.40/mo hosted | Free | $14.99/mo | $14.99/mo |

### Honest tradeoffs

- **vs YNAB / Monarch / Copilot.** They have polished mobile apps, bank API integrations (Plaid/SimpleFIN), and full-time UX teams. Cosmo doesn't. If you live in one country, earn in one currency, and want a beautiful iOS app, pay them — they're great products.
- **vs Actual Budget.** Actual is more mature and has zero-knowledge sync; Cosmo's wedge is multi-currency, which Actual still doesn't ship natively after years of demand. If you're single-currency, Actual is probably the better pick today.
- **vs Firefly III.** Firefly is more powerful (proper double-entry, Postgres, full bank-API ecosystem). Cosmo is dramatically simpler — one Flask app, one SQLite file, no double-entry mental model — at the cost of features Firefly power-users rely on.

Cosmo's bet: there's a real gap between "Actual but multi-currency" and "Firefly but simpler." That's the seam.

## Contributing

Pre-v1, the API and schema are still moving. If you want to follow along or contribute, open an issue first — happy to chat about scope.

## License

MIT. See [`LICENSE`](LICENSE).
