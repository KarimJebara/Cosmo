# Plan: Reposition Budget-Tracker → "Cosmo" — Self-Hosted Multi-Currency Tracker for Expats

## Context

**Why this exists.** A deep market-research pass (Exa + 48 sources) on 2026‑04‑26 found that the personal-finance app market is largely saturated *except* for one defensible seam: **self-hosted, multi-currency-first, simple**. The dominant self-hosted incumbent (Actual Budget, 26K stars) has [open issue #3351](https://github.com/actualbudget/actual/issues/3351) requesting native multi-currency, unresolved despite years of demand. Firefly III ships multi-currency but is a Laravel/double-entry beast. Mainstream apps (YNAB, Monarch, Copilot) all explicitly punt on multi-currency — confirmed by direct Reddit/HN quotes from expats. 40M+ digital nomads globally; multiple niche review sites already segmenting this audience.

**Current repo state.** Flask 3.1 web app, ~1,600 LOC, raw SQLite, monolithic `app.py` (1151 lines), JSON-file merchant map, free FX API, SHA-256 password hashing. Inherited name "Habit Hunter" doesn't match what the code does. README/folder/subfolder use three different names. Tests exist (18 files, ~75KB) — a real foundation, not a toy.

**Outcome we want.** A v1, self-hosted, OSS budget tracker that beats Actual on multi-currency UX and beats Firefly on simplicity. Name: **Cosmo**. MIT-licensed, Docker-deployable, ~2 month effort.

---

## What's broken today (must fix regardless of repositioning)

| Issue | File:line | Severity |
|---|---|---|
| SHA-256 password hashing, no salt | `database.py:107-113` | CRITICAL — replace with `argon2-cffi` or `bcrypt` |
| FX rates cached forever in-process via `@lru_cache(maxsize=32)` | `currency_converter.py:6` | HIGH — rates never refresh; restart-only invalidation |
| Silent FX fallback returns un-converted amount | `currency_converter.py:25` | HIGH — corrupts totals when API fails |
| Merchant map is **global, not per-user** | `merchant_mapper.py:78-85` | CRITICAL — User A's "Tesco→Groceries" overwrites User B's |
| `DataManager.save()` does `DELETE FROM ... + INSERT ALL` | `models/data_manager.py:50-86` | HIGH — destroys created_at, race conditions, breaks IDs |
| Routes use composite `<date>/<amount>/<desc>` URL keys instead of IDs | `app.py:505,531,579,605` | HIGH — duplicate transactions collide, URL-encoding fragile |
| Exact-string-only merchant matching, case-sensitive | `merchant_mapper.py:87-100` | MED — "Tesco" ≠ "TESCO" ≠ "TESCO STORES" |
| No transaction ID surfaced to UI; no audit trail | schema | MED |
| `print()` everywhere, no logging | multiple | LOW |
| Dead code: empty `utils/`, empty `simple-budget-tracker/`, possibly stale `ui/*_tab.py` Tkinter remnants | various | LOW — remove during cleanup |

---

## Goals (v1, ranked)

1. **Multi-currency done right** — per-account currency, per-transaction original amount preserved, historical FX rate snapshots, budget views in any chosen display currency.
2. **Smart merchant categorization** — fuzzy matching + normalization, per-user, learns from corrections, transparent rules the user can audit/edit.
3. **Importer framework** — CSV importers for Revolut, Wise, N26, generic CSV. Pluggable so adding banks is a 50-line file.
4. **Accounts model** — multiple accounts per user, each with its own currency. Transfers between accounts (no double-counting).
5. **Security baseline** — argon2 hashing, CSRF tokens, secure cookies, rate-limited login, no secrets in repo.
6. **Self-hostable** — Dockerfile + docker-compose, env-driven config, single-command install on a homelab.
7. **Positioning** — rename project, rewrite README/landing copy, focus messaging on expats/nomads.

---

## Architecture decisions

- **Keep Flask.** Mature, lightweight, the team knows it. Add Blueprints to break up `app.py`.
- **Adopt SQLAlchemy 2.x + Alembic.** Raw SQLite worked at 5 tables; at 12+ tables with FX history and a real accounts model it won't. Alembic gives reversible migrations — required since we'll be reshaping the DB.
- **Keep SQLite as default DB.** Self-hosted users will love the single-file backup story. Allow Postgres via DSN for power users.
- **Live FX from `frankfurter.app`** (free, no API key, ECB rates, has historical endpoints). Fall back to `exchangerate.host`. Cache rates in DB, not in-process.
- **Fuzzy merchant matching with `rapidfuzz`** (MIT, fast Cython). Token-set ratio + normalization (uppercase, strip punctuation, drop trailing numbers). Pure-Python; no ML dependency required for v1.
- **Auth** — `argon2-cffi` (PHC winner, libsodium-grade, simpler than bcrypt for new code).
- **CSRF** — `Flask-WTF` (already pulls in Werkzeug we have).
- **Frontend** — keep Jinja templates; Chart.js (already used) stays. No SPA rewrite. Mobile-friendly CSS pass.
- **Logging** — stdlib `logging` with JSON formatter; replace all `print()` calls.

---

## Target schema (Alembic migration `001_v1_baseline`)

```
users(id, username, password_hash, base_currency, created_at)
accounts(id, user_id, name, currency, type, opening_balance, archived, created_at)
transactions(id, user_id, account_id, date, original_amount, original_currency,
             base_amount, fx_rate_used, description, merchant_normalized,
             category_id, type[income|expense|transfer], transfer_pair_id,
             notes, created_at, updated_at)
categories(id, user_id, name, type[income|expense], parent_id, color, archived)
budgets(id, user_id, category_id, period[monthly|weekly], amount, currency,
        starts_on, ends_on)
merchant_rules(id, user_id, pattern, match_type[exact|contains|fuzzy|regex],
               category_id, hit_count, last_used_at, source[user|auto])
fx_rates(id, base_currency, quote_currency, rate, date, source, fetched_at)
import_sources(id, user_id, kind[revolut_csv|wise_csv|n26_csv|generic_csv],
               last_imported_at)
```

Key invariants:
- `transactions.original_amount` and `original_currency` are immutable after insert.
- `base_amount` = `original_amount * fx_rate_used`, snapshotted at import time using the rate for `transactions.date`.
- All FK constraints enforced (`PRAGMA foreign_keys = ON`).

---

## 8-week phased rollout

### Phase 0 — Repo hygiene (Week 1, ~3 days)
- Decide final name (rename **Habit Hunter** → final). Delete `simple-budget-tracker/`, `ui/*_tab.py` (confirm dead first via `git log`/grep), `.vscode/` if personal.
- Standardize layout: move `app.py`, `database.py`, `currency_converter.py`, `merchant_mapper.py` into `cosmo/` package (or chosen name).
- Add `pyproject.toml`, ruff/black/isort config, `pre-commit`, `.env.example`.
- Add `requirements/{base,dev,test}.txt`. Pin versions.
- README rewrite — landing positioned for expats/nomads, screenshot section, install steps.
- Replace SHA-256 with argon2-cffi (data migration: rehash on next login).
- **Deliverable:** clean repo, green test suite, no behavior change yet.

### Phase 1 — DB foundation (Week 1–2, ~5 days)
- Introduce SQLAlchemy 2.x models matching target schema.
- Add Alembic, write `001_v1_baseline` migration that:
  - Creates new tables.
  - Backfills `accounts` (one default account per user, currency from session pref or 'EUR').
  - Migrates `expenses`+`incomes` → unified `transactions` with `type` discriminator.
  - Generates `categories` from existing distinct category strings.
  - Computes `base_amount` for old rows using today's FX (best-effort) and flags `fx_rate_used = NULL`.
- Replace `models/data_manager.py` (the wipe-and-reinsert footgun) with proper repository classes:
  `cosmo/repos/{transactions.py,accounts.py,budgets.py,categories.py,merchants.py}`.
- Update all `app.py` queries to repos. Keep route URLs identical for now.
- **Deliverable:** new schema live, all existing tests still pass after fixture updates.

### Phase 2 — Multi-currency engine (Week 2–3, ~7 days) — **THE WEDGE**
- New module `cosmo/fx/` with:
  - `providers/frankfurter.py`, `providers/exchangerate_host.py`, base `Provider` protocol.
  - `service.py` — `get_rate(date, from_ccy, to_ccy)` that hits `fx_rates` cache first, falls back to provider, persists. Falls back to nearest-prior date if exact date missing (weekends/holidays).
  - Daily refresh job: `cli.py refresh-fx` to be run via cron/docker healthcheck.
- Per-transaction storage: `original_amount` + `original_currency` always preserved; `base_amount` recomputed only on rate-correction.
- User setting: `base_currency` (default EUR). Display currency selectable per session.
- Account-level currency: budgets and reports respect `account.currency` for native view, base currency for aggregated view.
- Replace `currency_converter.py:format_amount_with_conversion` with `cosmo/fx/format.py` — drop `lru_cache`-forever bug, add proper symbol map (CHF, JPY, SEK, etc.).
- **New tests:** `tests/test_fx_service.py`, `tests/test_multi_currency_aggregation.py`. Stub providers via responses lib.
- **Deliverable:** can hold accounts in EUR, USD, GBP, CHF, JPY simultaneously; reports correct in any display currency; historical FX preserved.

### Phase 3 — Merchant intelligence (Week 3–4, ~5 days)
- New module `cosmo/categorize/`:
  - `normalize.py` — uppercase, strip `*`, drop trailing digits/dates, collapse whitespace, remove common bank prefixes (`POS `, `CARD PURCHASE`, etc.).
  - `matcher.py` — uses rapidfuzz token_set_ratio against `merchant_rules`. Order: exact → contains → fuzzy ≥ 88. Returns `(category_id, confidence, rule_id)`.
  - `learner.py` — when user re-categorizes, upsert a rule with `source='user'`. When user accepts a fuzzy suggestion, increment `hit_count`. If pattern misfires (user rejects same suggestion 3×), demote.
- Migrate existing JSON merchant files into `merchant_rules` per-user (current global file is empty-ish anyway — easy).
- Add **Rules** page (`/rules`) — user can see, edit, delete merchant rules. Transparency = trust.
- **Replace per-user-cross-leak bug** in `merchant_mapper.py` — that file deletes after migration.
- **Deliverable:** typing "TESCO STORES 1234 LONDON" auto-suggests "Groceries" because user once tagged "Tesco" as Groceries. Works per-user.

### Phase 4 — Accounts & importer framework (Week 4–5, ~7 days)
- Accounts CRUD UI: list, create, archive. Each shows balance in own currency + base currency.
- Transfers: pair-linked transactions (`transfer_pair_id`), excluded from income/expense totals.
- Importer framework `cosmo/importers/`:
  - Base class `BaseImporter` (already half-existing as `RevolutImporter`).
  - Adapters: `revolut.py` (port existing), `wise.py`, `n26.py`, `generic_csv.py` (column-mapping wizard).
  - Dedup on `(account_id, date, original_amount, description_hash)`.
  - Auto-categorization runs on import via Phase-3 categorizer.
- Move `templates/revolut_import.html` → generic `templates/import.html` with bank picker.
- **Deliverable:** import a Revolut CSV with mixed EUR/GBP/USD lines, get correctly-bucketed transactions across accounts, with auto-categories applied.

### Phase 5 — Budgets, analytics, UX polish (Week 6, ~5 days)
- Budget periods: weekly + monthly. Budget currency selectable.
- Reports page: spending by currency, by account, by country (derive from merchant patterns later).
- Day-of-week analytics (already exists in `templates/graphs_stats.html`) — port to new schema.
- Mobile-responsive CSS pass on `static/base.css` (currently 22KB, no media queries seen — confirm and add).
- Replace composite-key route URLs with `/transactions/<int:id>` everywhere.
- Add CSRF tokens everywhere via Flask-WTF.
- **Deliverable:** usable on phone; budget pages show progress in user's preferred display currency.

### Phase 6 — Self-hosting & ship (Week 7, ~5 days)
- `Dockerfile` (multi-stage, gunicorn, non-root user).
- `docker-compose.yml` with optional Postgres service and a Caddy reverse proxy example.
- `.env.example` with all knobs (SECRET_KEY, BASE_CURRENCY, FX_PROVIDER, etc.).
- `cli.py` with: `init-db`, `create-user`, `refresh-fx`, `import <bank> <csv>`.
- Health check endpoint `/healthz`.
- GitHub Actions: lint + test + docker build on PR.
- **Deliverable:** `docker compose up` on a fresh VPS gives a running, login-ready instance in <2 minutes.

### Phase 7 — Launch prep (Week 8, ~5 days)
- Polish landing/README with screenshots, gif demo, "Why this exists" section quoting the expat pain points the research surfaced.
- Comparison page: vs Actual Budget, vs Firefly III, vs YNAB — table + honest tradeoffs.
- Submit to: r/selfhosted, r/digitalnomad, r/expats, Hacker News (Show HN), `awesome-selfhosted` list PR.
- Announce on Borderless Budget / nomadwallets / digital-nomad communities (research showed these as audience aggregators).
- **Deliverable:** first 100 GitHub stars and issue tracker is open for business.

---

## Critical files & where changes land

| Today | After Phase 1+ |
|---|---|
| `app.py` (1151 lines, monolithic) | `cosmo/web/__init__.py` factory + Blueprints `auth.py`, `transactions.py`, `accounts.py`, `budgets.py`, `import.py`, `reports.py`, `rules.py` |
| `database.py` | `cosmo/db.py` (engine/session) + `cosmo/migrations/` (Alembic) |
| `models/data_manager.py` (wipe-and-reinsert anti-pattern) | **DELETED**, replaced by `cosmo/repos/*.py` |
| `merchant_mapper.py` (global JSON, exact match) | **DELETED**, replaced by `cosmo/categorize/{normalize,matcher,learner}.py` + `merchant_rules` table |
| `currency_converter.py` (lru_cache forever, EUR-only base) | `cosmo/fx/{service,format,providers/}` + `fx_rates` table |
| `api/revolut_importer.py` | `cosmo/importers/revolut.py` (subclass of `BaseImporter`) |
| `data/merchant_category_*.json` | **DELETED** (migrated to DB) |
| `simple-budget-tracker/`, `ui/*_tab.py` | **DELETED** (dead code) |
| `tests/` (18 files, mostly route/integration) | Kept; updated for new schema. Add `test_fx_service.py`, `test_categorize.py`, `test_importers.py`, `test_accounts.py`, `test_transfers.py` |

---

## Reused / new dependencies

**Add:** `SQLAlchemy>=2.0`, `alembic`, `argon2-cffi`, `Flask-WTF`, `Flask-Login` (replace home-rolled session decorator), `requests` (already needed by FX), `rapidfuzz`, `pydantic` (config + DTOs), `python-dotenv`, `gunicorn`, `responses` (test FX stubs), `freezegun` (test date-sensitive FX logic).

**Remove:** `datasets==4.4.1` (HuggingFace — appears unused; confirm via `grep -r "datasets"` before removing).

---

## Verification — how we know each phase shipped

| Phase | Verification |
|---|---|
| 0 | `pytest -q` green; `ruff check .` clean; README screenshot and install instructions render correctly. |
| 1 | `alembic upgrade head` on a copy of existing DB succeeds; row counts preserved; `pytest -q` green. |
| 2 | Manual: create EUR + USD + GBP accounts, add transactions in each, verify dashboard total in EUR matches an external calculator using same-day ECB rates. Automated: `tests/test_fx_service.py` covers cache hit, cache miss, fallback provider, weekend-date snap-back. |
| 3 | Manual: import 20 sample Revolut transactions, verify ≥80% auto-categorize after only ~5 user corrections. Automated: `tests/test_categorize.py` parameterized over 30 real-world descriptors. |
| 4 | Manual: run a Revolut + Wise import in same session; verify no duplicates; transfers between accounts net to zero in totals. Automated: `tests/test_importers.py` per-bank, `tests/test_transfers.py`. |
| 5 | Manual: open on phone (Chrome dev-tools mobile emulator); all pages usable; budgets page renders in chosen display currency. Automated: route smoke tests still green. |
| 6 | `docker compose up` on a clean Ubuntu VM; sign up, import CSV, see dashboard — all in <2 min. `gh actions` green. |
| 7 | Show HN posted; first external user opens an issue. |

**Definition of done for v1:** an expat in Lisbon with EUR salary, GBP UK rental income, and USD freelance work can self-host this in 5 minutes on a Hetzner box, import three bank CSVs, and see one unified dashboard with correct EUR-converted totals — *and* the merchant categorization gets noticeably smarter as they correct it. That's the wedge. Nothing else ships in v1.

---

## Open questions deferred (NOT in v1)

- Bank API integrations (GoCardless EU, SimpleFIN US, Plaid US) — Phase 8+, post-launch based on user demand.
- Investment/portfolio tracking — explicitly out of scope; let Maybe Finance fork own that.
- Mobile app — PWA only for v1; native later if traction.
- LLM-based categorization — fuzzy matching covers 80%; LLM is a v2 add-on, optional plugin.
- Couples/shared budgets — Phase 9; needs auth/permissions rework.
