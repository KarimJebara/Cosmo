"""Cosmo operator CLI.

Run from a self-host environment. All commands respect the same env vars
the web app reads (DATABASE_URL via cosmo/db.py, etc.).

Usage:
    python cli.py init-db
    python cli.py create-user <username> [--password ...]
    python cli.py refresh-fx [--base EUR] [--quotes USD,GBP,CHF,JPY]
    python cli.py import <bank> <user> <csv_path>
"""

from __future__ import annotations

import getpass
import logging
import sys
from datetime import date as Date
from pathlib import Path

import click

import database
from cosmo import legacy_adapter
from cosmo.fx.service import default_service as default_fx_service
from cosmo.importers import get_importer

logger = logging.getLogger(__name__)


@click.group()
def cli() -> None:
    """Cosmo administrative CLI."""
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )


@cli.command("init-db")
def init_db() -> None:
    """Run pending Alembic migrations to bring the DB to head.

    Safe to run on every container start; no-ops if already at head.
    """
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(Path(__file__).parent / "alembic.ini"))
    command.upgrade(cfg, "head")
    click.echo("DB migrated to head.")


@cli.command("create-user")
@click.argument("username")
@click.option(
    "--password",
    default=None,
    help="If omitted, prompts interactively (recommended — keeps it out of shell history).",
)
def create_user(username: str, password: str | None) -> None:
    """Create a new user. Idempotent: returns non-zero if username exists."""
    if password is None:
        password = getpass.getpass("Password: ")
        confirm = getpass.getpass("Confirm: ")
        if password != confirm:
            click.echo("Passwords don't match.", err=True)
            sys.exit(1)
    if len(password) < 8:
        click.echo("Password must be at least 8 characters.", err=True)
        sys.exit(1)

    user_id = database.create_user(username, password)
    if user_id is None:
        click.echo(f"User '{username}' already exists.", err=True)
        sys.exit(1)
    click.echo(f"Created user '{username}' (id={user_id}).")


@cli.command("refresh-fx")
@click.option("--base", default="EUR", show_default=True, help="Base currency.")
@click.option(
    "--quotes",
    default="USD,GBP,CHF,JPY,CAD,AUD,SEK,NOK,DKK,PLN",
    show_default=True,
    help="Comma-separated quote currencies to fetch for today.",
)
@click.option(
    "--on-date",
    default=None,
    help="ISO date (YYYY-MM-DD) to fetch. Defaults to today.",
)
def refresh_fx(base: str, quotes: str, on_date: str | None) -> None:
    """Fetch + cache FX rates from base→each quote for a given date.

    Designed to be called daily via cron / docker healthcheck.
    """
    target = Date.fromisoformat(on_date) if on_date else Date.today()
    service = default_fx_service()
    fetched, missed = 0, 0
    for quote in (q.strip().upper() for q in quotes.split(",") if q.strip()):
        rate = service.get_rate(target, base.upper(), quote)
        if rate is None:
            click.echo(f"  {base}->{quote}: no rate available", err=True)
            missed += 1
        else:
            click.echo(f"  {base}->{quote}: {rate:.6f}")
            fetched += 1
    click.echo(f"Done. {fetched} fetched, {missed} missed for {target.isoformat()}.")
    if missed:
        sys.exit(2)


@cli.command("import")
@click.argument("bank", type=click.Choice(["revolut", "wise", "n26", "generic"]))
@click.argument("username")
@click.argument("csv_path", type=click.Path(exists=True, dir_okay=False))
def import_csv(bank: str, username: str, csv_path: str) -> None:
    """Import a CSV for an existing user.

    Generic CSV is not supported via CLI yet (needs column-mapping config);
    use the web UI for those.
    """
    if bank == "generic":
        click.echo(
            "Generic CSV import requires column mapping; use the web UI.",
            err=True,
        )
        sys.exit(1)

    with database.get_db() as conn:
        row = conn.execute(
            "SELECT id FROM users_v2 WHERE username = ?", (username,)
        ).fetchone()
    if row is None:
        click.echo(f"User '{username}' not found.", err=True)
        sys.exit(1)
    user_id = row["id"]

    csv_content = Path(csv_path).read_text(encoding="utf-8")
    importer = get_importer(bank)
    records = list(importer.parse(csv_content))
    imported, skipped = legacy_adapter.import_transactions(
        user_id, source=bank, records=records
    )
    click.echo(f"Imported {imported}, skipped {skipped} duplicates.")


if __name__ == "__main__":
    cli()
