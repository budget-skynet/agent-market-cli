#!/usr/bin/env python3
"""
Agent Market CLI — command-line client for market.near.ai
Usage: am <command> [options]
"""
import click
import requests
import json
import os
import sys
from pathlib import Path

BASE_URL = "https://market.near.ai/v1"
CONFIG_PATH = Path.home() / ".am_config"


def load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text())
        except Exception:
            return {}
    return {}


def save_config(cfg: dict) -> None:
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2))
    CONFIG_PATH.chmod(0o600)


def get_api_key(ctx_obj: dict) -> str:
    key = (
        (ctx_obj or {}).get("api_key")
        or os.environ.get("AM_API_KEY")
        or load_config().get("api_key")
    )
    if not key:
        click.echo(
            "Error: API key required.\n"
            "  Set env var:  export AM_API_KEY=sk_live_...\n"
            "  Or run:       am config --api-key sk_live_...",
            err=True,
        )
        sys.exit(1)
    return key


def make_headers(api_key: str) -> dict:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def fmt_output(obj, ctx_obj: dict) -> None:
    if (ctx_obj or {}).get("output") == "json":
        click.echo(json.dumps(obj, indent=2))
    else:
        yield obj  # caller handles text


# ── ROOT GROUP ──────────────────────────────────────────────────────────────

@click.group()
@click.option("--api-key", envvar="AM_API_KEY", default=None,
              help="API key (overrides AM_API_KEY env var and config file)")
@click.option("--output", default="text", type=click.Choice(["text", "json"]),
              show_default=True, help="Output format")
@click.pass_context
def cli(ctx, api_key, output):
    """Agent Market CLI — interact with market.near.ai from your terminal."""
    ctx.ensure_object(dict)
    ctx.obj["api_key"] = api_key or load_config().get("api_key")
    ctx.obj["output"] = output


@cli.command("config")
@click.option("--api-key", required=True, help="Your market.near.ai API key")
def config_cmd(api_key):
    """Save API key to ~/.am_config (permissions set to 600)."""
    save_config({"api_key": api_key})
    click.echo(f"✅ Config saved to {CONFIG_PATH}")


# ── JOBS ────────────────────────────────────────────────────────────────────

@cli.group()
def jobs():
    """Browse, inspect, and create marketplace jobs."""


@jobs.command("list")
@click.option("--status", default="open", show_default=True,
              type=click.Choice(["open", "filling", "in_progress", "completed", "expired", "closed"]),
              help="Filter by job status")
@click.option("--limit", default=20, show_default=True, help="Number of results to return")
@click.option("--tag", default=None, multiple=True, help="Filter by tag (repeatable: --tag python --tag near)")
@click.option("--offset", default=0, show_default=True, help="Pagination offset")
@click.pass_obj
def jobs_list(obj, status, limit, tag, offset):
    """List marketplace jobs."""
    key = get_api_key(obj)
    params = {"status": status, "limit": limit, "offset": offset}
    if tag:
        params["tags"] = ",".join(tag)
    r = requests.get(f"{BASE_URL}/jobs", headers=make_headers(key), params=params, timeout=15)
    r.raise_for_status()
    data = r.json()
    jobs_data = data if isinstance(data, list) else data.get("data", data)

    if obj.get("output") == "json":
        click.echo(json.dumps(jobs_data, indent=2))
    else:
        if not jobs_data:
            click.echo("No jobs found.")
            return
        click.echo(f"{'ID':<10} {'BUDGET':>8}  {'TITLE'}")
        click.echo("─" * 70)
        for j in jobs_data:
            jid = str(j.get("job_id", "?"))[:8]
            budget = f"{j.get('budget_max', '?')}N"
            title = j.get("title", "?")[:55]
            click.echo(f"{jid:<10} {budget:>8}  {title}")


@jobs.command("get")
@click.argument("job_id")
@click.pass_obj
def jobs_get(obj, job_id):
    """Get full details of a specific job."""
    key = get_api_key(obj)
    r = requests.get(f"{BASE_URL}/jobs/{job_id}", headers=make_headers(key), timeout=15)
    r.raise_for_status()
    data = r.json()

    if obj.get("output") == "json":
        click.echo(json.dumps(data, indent=2))
    else:
        click.echo(f"Title:       {data.get('title')}")
        click.echo(f"Status:      {data.get('status')}")
        click.echo(f"Budget:      {data.get('budget_max')} NEAR")
        click.echo(f"Tags:        {', '.join(data.get('tags', []))}")
        click.echo(f"Created:     {data.get('created_at', '?')[:19]}")
        click.echo(f"URL:         https://market.near.ai/jobs/{job_id}")
        desc = data.get("description", "")
        if desc:
            click.echo(f"\nDescription:\n{desc[:500]}")


@jobs.command("create")
@click.option("--title", required=True, help="Job title")
@click.option("--desc", required=True, help="Job description (requirements)")
@click.option("--budget", required=True, type=float, help="Maximum budget in NEAR")
@click.option("--tag", default=None, multiple=True, help="Tags (repeatable: --tag python --tag near)")
@click.option("--deadline", default=86400, show_default=True,
              help="Deadline in seconds (default 24h = 86400)")
@click.pass_obj
def jobs_create(obj, title, desc, budget, tag, deadline):
    """Create a new job on the marketplace."""
    key = get_api_key(obj)
    payload = {
        "title": title,
        "description": desc,
        "budget_max": str(budget),
        "tags": list(tag),
        "deadline_seconds": deadline,
    }
    r = requests.post(f"{BASE_URL}/jobs", headers=make_headers(key), json=payload, timeout=15)
    r.raise_for_status()
    data = r.json()

    if obj.get("output") == "json":
        click.echo(json.dumps(data, indent=2))
    else:
        job_id = data.get("job_id", "?")
        click.echo(f"✅ Job created: {job_id}")
        click.echo(f"   Title:  {data.get('title')}")
        click.echo(f"   Budget: {data.get('budget_max')} NEAR")
        click.echo(f"   URL:    https://market.near.ai/jobs/{job_id}")


# ── BIDS ────────────────────────────────────────────────────────────────────

@cli.group()
def bids():
    """View your bids and place new ones."""


@bids.command("list")
@click.option("--status", default=None,
              type=click.Choice(["pending", "accepted", "rejected", "withdrawn", "expired"]),
              help="Filter by bid status")
@click.option("--limit", default=20, show_default=True, help="Number of results")
@click.pass_obj
def bids_list(obj, status, limit):
    """List your bids across all jobs."""
    key = get_api_key(obj)
    params = {"limit": limit}
    if status:
        params["status"] = status
    r = requests.get(f"{BASE_URL}/agents/me/bids", headers=make_headers(key), params=params, timeout=15)
    r.raise_for_status()
    data = r.json()
    bids_data = data if isinstance(data, list) else data.get("bids", [])

    if obj.get("output") == "json":
        click.echo(json.dumps(bids_data, indent=2))
    else:
        if not bids_data:
            click.echo("No bids found.")
            return
        click.echo(f"{'BID_ID':<10} {'JOB_ID':<10} {'AMOUNT':>8}  {'STATUS':<12}  PROPOSAL")
        click.echo("─" * 80)
        for b in bids_data:
            bid_id = str(b.get("bid_id", "?"))[:8]
            job_id = str(b.get("job_id", "?"))[:8]
            amount = f"{b.get('amount', '?')}N"
            bstatus = b.get("status", "?")
            proposal = b.get("proposal", "")[:30]
            click.echo(f"{bid_id:<10} {job_id:<10} {amount:>8}  {bstatus:<12}  {proposal}")


@bids.command("place")
@click.argument("job_id")
@click.option("--amount", required=True, type=float, help="Bid amount in NEAR")
@click.option("--proposal", required=True, help="Your proposal / cover letter")
@click.pass_obj
def bids_place(obj, job_id, amount, proposal):
    """Place a bid on a job."""
    key = get_api_key(obj)
    payload = {"amount": str(amount), "proposal": proposal}
    r = requests.post(
        f"{BASE_URL}/jobs/{job_id}/bids",
        headers=make_headers(key), json=payload, timeout=15
    )
    r.raise_for_status()
    data = r.json()

    if obj.get("output") == "json":
        click.echo(json.dumps(data, indent=2))
    else:
        bid_id = data.get("bid_id", "?")
        click.echo(f"✅ Bid placed: {bid_id}")
        click.echo(f"   Job:    {job_id}")
        click.echo(f"   Amount: {amount} NEAR")


# ── WALLET ──────────────────────────────────────────────────────────────────

@cli.command("wallet")
@click.pass_obj
def wallet(obj):
    """Show your wallet balance."""
    key = get_api_key(obj)
    r = requests.get(f"{BASE_URL}/wallet/balance", headers=make_headers(key), timeout=15)
    r.raise_for_status()
    data = r.json()

    if obj.get("output") == "json":
        click.echo(json.dumps(data, indent=2))
    else:
        balance = data.get("balance") or data.get("available") or data.get("total") or str(data)
        click.echo(f"💰 Wallet balance: {balance} NEAR")


# ── SERVICES ────────────────────────────────────────────────────────────────

@cli.group()
def services():
    """Browse and invoke agent services."""


@services.command("list")
@click.option("--tag", default=None, multiple=True, help="Filter by tag")
@click.option("--limit", default=20, show_default=True, help="Number of results")
@click.option("--category", default=None, help="Filter by category")
@click.pass_obj
def services_list(obj, tag, limit, category):
    """List available services on the marketplace."""
    key = get_api_key(obj)
    params = {"limit": limit}
    if tag:
        params["tags"] = ",".join(tag)
    if category:
        params["category"] = category
    r = requests.get(f"{BASE_URL}/services", headers=make_headers(key), params=params, timeout=15)
    r.raise_for_status()
    data = r.json()
    svcs = data if isinstance(data, list) else data.get("data", data)

    if obj.get("output") == "json":
        click.echo(json.dumps(svcs, indent=2))
    else:
        if not svcs:
            click.echo("No services found.")
            return
        click.echo(f"{'ID':<10} {'PRICE':>8}  {'CATEGORY':<14}  NAME")
        click.echo("─" * 70)
        for s in svcs:
            sid = str(s.get("service_id", "?"))[:8]
            price = f"{s.get('price_amount', '?')}N"
            cat = s.get("category", "?")[:12]
            name = s.get("name", "?")[:45]
            click.echo(f"{sid:<10} {price:>8}  {cat:<14}  {name}")


# ── ENTRY POINT ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    cli()
