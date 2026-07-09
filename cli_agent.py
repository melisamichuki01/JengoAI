#!/usr/bin/env python3
"""
JengoAI CLI
-----------
Command line interface for the JengoAI agentic reporter.
Feeds the foreman's message to the agent and shows what
the agent decides to do at each step.

Usage:
    python cli.py
"""

import os
import sys
from dotenv import load_dotenv

load_dotenv()

from agent_agentic import run_agent

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
  +==========================================+
  |         JengoAI Site Reporter            |
  |       Kamau Construction Agent           |
  +==========================================+
{RESET}""")


def print_summary(summary: dict):
    """Print a clean summary of what the agent did."""
    print(f"\n{CYAN}{BOLD}-- Summary ---------------------------------------------{RESET}")

    if summary.get("notion_url"):
        print(f"  {GREEN}Report saved to Notion:{RESET}")
        print(f"  {CYAN}{summary['notion_url']}{RESET}")

    inv_updates = summary.get("inventory_updates", [])
    if inv_updates:
        print(f"\n  {WHITE}Inventory updates:{RESET}")
        for u in inv_updates:
            pct    = u.get("stock_pct", 0)
            color  = RED if pct < 20 else (YELLOW if pct < 40 else GREEN)
            alert  = f"  {RED}REORDER ALERT CREATED{RESET}" if u.get("reorder_alert_created") else ""
            print(f"    {MUTED}{u['material']:<20}{RESET}{color}{u['remaining']} remaining ({pct}%){RESET}{alert}")

    reason = summary.get("stopped_reason")
    if reason == "low_confidence":
        print(f"\n  {RED}Agent stopped: low confidence extraction.{RESET}")
        print(f"  {YELLOW}Please resubmit with a clearer message.{RESET}")
    elif reason == "rejected_by_human":
        print(f"\n  {YELLOW}Agent stopped: update rejected by user.{RESET}")
    elif reason == "complete":
        print(f"\n  {GREEN}Agent completed successfully.{RESET}")
        print(f"  {MUTED}Open Streamlit to review and approve the report.{RESET}")
    elif reason == "max_iterations_reached":
        print(f"\n  {RED}Agent stopped: reached maximum iterations.{RESET}")

    if summary.get("report_text"):
        show = input(f"\n  {YELLOW}Show generated report? (y/n): {RESET}").strip().lower()
        if show in ["y", "yes"]:
            print(f"\n{MUTED}{'─' * 50}{RESET}")
            print(summary["report_text"])
            print(f"{MUTED}{'─' * 50}{RESET}")


def main():
    print_header()

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

    # Run the agent
    summary = run_agent(raw_text)

    # Print summary
    print_summary(summary)

    print()


if __name__ == "__main__":
    main()