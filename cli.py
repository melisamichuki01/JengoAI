#!/usr/bin/env python3
"""
JengoAI CLI — command line foreman update input.

Usage:
    python cli.py

The agent will prompt for a site update, extract structured data,
ask for confirmation, generate a report, update inventory, and save
everything to Notion.
"""

import os
import sys
from dotenv import load_dotenv

load_dotenv()

from agent import extract_update, generate_report, build_inventory_summary
from notion_client_wrapper import save_report_to_notion
from inventory import update_inventory, get_inventory


# ── COLOURS ───────────────────────────────────────────────────────────────────

RESET  = "\033[0m"
BOLD   = "\033[1m"
CYAN   = "\033[96m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
MUTED  = "\033[90m"
WHITE  = "\033[97m"


def print_header():
    print(f"""
{CYAN}{BOLD}
  ╔═══════════════════════════════════════╗
  ║         JengoAI Site Reporter         ║
  ║       Kamau Construction Agent        ║
  ╚═══════════════════════════════════════╝
{RESET}""")


def print_section(title: str):
    print(f"\n{CYAN}{BOLD}── {title} {'─' * (40 - len(title))}{RESET}")


def print_field(label: str, value, color=WHITE):
    print(f"  {MUTED}{label:<22}{RESET}{color}{value}{RESET}")


def print_extracted(extracted: dict):
    print_section("Extracted Data")

    confidence = extracted.get("confidence", "unknown")
    conf_color = GREEN if confidence == "high" else (YELLOW if confidence == "medium" else RED)

    print_field("Site", extracted.get("site_name", "Unknown"))
    print_field("Foreman", extracted.get("foreman_name", "Unknown"))
    print_field("Progress", f"{extracted.get('progress_percentage', 'N/A')}%")
    print_field("Confidence", confidence.upper(), color=conf_color)

    blockers = extracted.get("blockers", [])
    print_field("Blockers", ", ".join(blockers) if blockers else "None",
                color=RED if blockers else GREEN)

    materials_used = extracted.get("materials_used", [])
    if materials_used:
        print(f"\n  {MUTED}Materials Used:{RESET}")
        for m in materials_used:
            qty  = m.get("quantity", "?")
            unit = m.get("unit", "units")
            print(f"    {YELLOW}• {m['name']}: {qty} {unit}{RESET}")
    else:
        print_field("Materials Used", "None reported")

    print_field("Materials Needed", extracted.get("materials_needed", "None"))
    print_field("Labor Needed",     extracted.get("labor_needed", "None"))
    print_field("Safety",           extracted.get("safety_incidents", "No incidents"))


def confirm(prompt: str) -> bool:
    while True:
        reply = input(f"\n{YELLOW}{prompt} (y/n): {RESET}").strip().lower()
        if reply in ["y", "yes"]:
            return True
        if reply in ["n", "no"]:
            return False
        print(f"{RED}Please enter y or n.{RESET}")


def run():
    print_header()

    # ── INPUT ─────────────────────────────────────────────────────────────────
    print(f"{MUTED}Paste or type the foreman's site update below.")
    print(f"Press Enter twice when done.{RESET}\n")

    lines = []
    while True:
        try:
            line = input()
            if line == "" and lines and lines[-1] == "":
                break
            lines.append(line)
        except EOFError:
            break

    raw_text = "\n".join(lines).strip()

    if not raw_text:
        print(f"{RED}No input provided. Exiting.{RESET}")
        sys.exit(1)

    # ── EXTRACT ───────────────────────────────────────────────────────────────
    print(f"\n{MUTED}Extracting structured data...{RESET}", end="", flush=True)
    extracted = extract_update(raw_text)
    print(f" {GREEN}done{RESET}")

    if extracted.get("confidence") == "low":
        print(f"\n{RED}{BOLD}Low confidence extraction.{RESET}")
        print(f"{YELLOW}The message was unclear. Please try again with more detail:{RESET}")
        print(f"  • Site name")
        print(f"  • Progress percentage")
        print(f"  • Any blockers or issues")
        print(f"  • Materials used or needed")
        sys.exit(1)

    print_extracted(extracted)

    # ── CONFIRMATION ──────────────────────────────────────────────────────────
    if not confirm("Is this extraction correct?"):
        print(f"\n{YELLOW}Update discarded. Please resubmit with a clearer message.{RESET}")
        sys.exit(0)

    # ── INVENTORY UPDATE ──────────────────────────────────────────────────────
    materials_used = extracted.get("materials_used", [])
    progress       = extracted.get("progress_percentage") or 0
    site           = extracted.get("site_name", "Other")
    alerts_created = []

    if materials_used:
        print_section("Updating Inventory")
        for m in materials_used:
            name = m.get("name", "")
            qty  = m.get("quantity") or 0
            if not name or qty == 0:
                continue

            print(f"  {MUTED}Updating {name}...{RESET}", end="", flush=True)
            updated = update_inventory(
                material=name,
                site=site,
                qty_used=qty,
                progress=progress,
            )

            remaining = updated.get("remaining", 0)
            stock_pct = updated.get("stock_pct", 0)
            status_color = RED if stock_pct < 20 else (YELLOW if stock_pct < 40 else GREEN)
            print(f" {status_color}{remaining} remaining ({stock_pct}%){RESET}")

            if updated.get("needs_reorder"):
                alerts_created.append(name)

    if alerts_created:
        print(f"\n  {RED}{BOLD}Reorder alerts created:{RESET}")
        for a in alerts_created:
            print(f"  {RED}• {a}{RESET}")

    # ── GENERATE REPORT ───────────────────────────────────────────────────────
    print_section("Generating Report")
    print(f"  {MUTED}Calling Groq...{RESET}", end="", flush=True)

    inventory_items   = get_inventory(site=site)
    inventory_summary = build_inventory_summary(inventory_items)
    report            = generate_report(extracted, inventory_summary)

    print(f" {GREEN}done{RESET}")
    print(f"\n{MUTED}{'─' * 50}{RESET}")
    print(report)
    print(f"{MUTED}{'─' * 50}{RESET}")

    # ── SAVE TO NOTION ────────────────────────────────────────────────────────
    if not confirm("Save this report to Notion?"):
        print(f"\n{YELLOW}Report not saved.{RESET}")
        sys.exit(0)

    print(f"\n  {MUTED}Saving to Notion...{RESET}", end="", flush=True)
    notion_url = save_report_to_notion(report, extracted)
    print(f" {GREEN}done{RESET}")

    print(f"\n{GREEN}{BOLD}Report saved successfully.{RESET}")
    print(f"  {MUTED}Notion URL:{RESET} {CYAN}{notion_url}{RESET}")

    if alerts_created:
        print(f"\n{YELLOW}{BOLD}Action required:{RESET}")
        print(f"{YELLOW}Reorder alerts were raised for: {', '.join(alerts_created)}{RESET}")
        print(f"{YELLOW}Review them in the Reorder Alerts database in Notion.{RESET}")

    print(f"\n{MUTED}Done. Open Streamlit to review and approve this report.{RESET}\n")


if __name__ == "__main__":
    run()