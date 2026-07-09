#!/usr/bin/env python3
"""
JengoAI Setup Script
--------------------
Run this once to create your Notion workspace, all three databases,
and generate your .env file automatically.

Usage:
    python setup.py
"""

import os
import sys

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
  ╔══════════════════════════════════════════╗
  ║          JengoAI — First Time Setup      ║
  ║        Kamau Construction Agent          ║
  ╚══════════════════════════════════════════╝
{RESET}""")


def print_step(n, total, label):
    print(f"\n{CYAN}[{n}/{total}]{RESET} {WHITE}{label}{RESET}")


def print_ok(msg):
    print(f"  {GREEN}✓{RESET} {msg}")


def print_fail(msg):
    print(f"  {RED}✗{RESET} {msg}")


def print_info(msg):
    print(f"  {MUTED}{msg}{RESET}")


# ── STEP 1: CHECK DEPENDENCIES ────────────────────────────────────────────────

def check_dependencies():
    print_step(1, 5, "Checking dependencies")
    missing = []

    for pkg in ["notion_client", "groq", "dotenv"]:
        try:
            __import__(pkg)
            print_ok(f"{pkg} installed")
        except ImportError:
            print_fail(f"{pkg} not found")
            missing.append(pkg)

    if missing:
        pip_names = {"notion_client": "notion-client", "dotenv": "python-dotenv"}
        to_install = [pip_names.get(p, p) for p in missing]
        print(f"\n{YELLOW}Install missing packages then run setup.py again:{RESET}")
        print(f"  pip install {' '.join(to_install)}")
        sys.exit(1)


# ── STEP 2: COLLECT API KEYS ──────────────────────────────────────────────────

def collect_keys():
    print_step(2, 5, "Collecting API keys")

    existing = {}
    if os.path.exists(".env"):
        with open(".env", "r") as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    existing[k.strip()] = v.strip()

    # Notion key
    notion_key = existing.get("NOTION_API_KEY", "")
    if notion_key:
        print_ok("NOTION_API_KEY found in existing .env")
    else:
        print(f"""
  {WHITE}You need a Notion integration token.{RESET}

  {MUTED}Steps:{RESET}
  {MUTED}1. Go to https://www.notion.so/my-integrations{RESET}
  {MUTED}2. Click New Integration{RESET}
  {MUTED}3. Name it jengoai, select your workspace, click Submit{RESET}
  {MUTED}4. Copy the Internal Integration Token (starts with secret_){RESET}
""")
        notion_key = input(f"  {YELLOW}Paste your Notion API key: {RESET}").strip()
        if not notion_key.startswith("secret_"):
            print_fail("That does not look like a valid Notion key (should start with secret_)")
            sys.exit(1)

    # Groq key
    groq_key = existing.get("GROQ_API_KEY", "")
    if groq_key:
        print_ok("GROQ_API_KEY found in existing .env")
    else:
        print(f"\n  {MUTED}Go to https://console.groq.com, create a free account, copy your API key{RESET}\n")
        groq_key = input(f"  {YELLOW}Paste your Groq API key: {RESET}").strip()
        if not groq_key:
            print_fail("Groq key cannot be empty.")
            sys.exit(1)

    return notion_key, groq_key


# ── STEP 3: VERIFY NOTION KEY ─────────────────────────────────────────────────

def verify_and_connect(notion_key: str):
    print_step(3, 5, "Verifying Notion connection")
    from notion_client import Client
    from notion_client.errors import APIResponseError

    client = Client(auth=notion_key)
    try:
        me = client.users.me()
        name = me.get("name", "Unknown")
        print_ok(f"Connected to Notion as: {name}")
        return client
    except APIResponseError as e:
        print_fail(f"Notion API error: {e}")
        print(f"\n  {YELLOW}Make sure you copied the full token from notion.so/my-integrations{RESET}")
        sys.exit(1)
    except Exception as e:
        print_fail(f"Could not connect to Notion: {e}")
        sys.exit(1)


# ── STEP 4: CREATE PAGE + DATABASES ──────────────────────────────────────────

def create_workspace(client) -> dict:
    print_step(4, 5, "Creating Notion page and databases")

    # ── Create parent page ──
    print_info("Creating JengoAI page...")
    try:
        page = client.pages.create(
            parent={"type": "workspace", "workspace": True},
            icon={"type": "emoji", "emoji": "🏗️"},
            properties={
                "title": {
                    "title": [{"type": "text", "text": {"content": "JengoAI"}}]
                }
            },
            children=[
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [
                            {
                                "type": "text",
                                "text": {
                                    "content": "This page contains the three databases used by the JengoAI construction reporting agent."
                                }
                            }
                        ]
                    }
                }
            ]
        )
        page_id = page["id"]
        page_url = page.get("url", "")
        print_ok(f"JengoAI page created")
        print_info(f"URL: {page_url}")
    except Exception as e:
        print_fail(f"Failed to create page: {e}")
        print(f"\n  {YELLOW}Tip: Make sure your integration has 'Insert content' permission{RESET}")
        print(f"  {YELLOW}Go to notion.so/my-integrations → your integration → Capabilities{RESET}")
        sys.exit(1)

    db_ids = {}

    # ── Site Reports DB ──
    print_info("Creating Site Reports database...")
    try:
        db = client.databases.create(
            parent={"type": "page_id", "page_id": page_id},
            title=[{"type": "text", "text": {"content": "Kamau Construction - Site Reports"}}],
            properties={
                "Site Name":          {"title": {}},
                "Date":               {"date": {}},
                "Foreman":            {"rich_text": {}},
                "Progress %":         {"number": {"format": "number"}},
                "Blockers":           {"rich_text": {}},
                "Materials Needed":   {"rich_text": {}},
                "Labor Needed":       {"rich_text": {}},
                "Safety":             {"rich_text": {}},
                "Report":             {"rich_text": {}},
                "Verification Notes": {"rich_text": {}},
                "Status": {
                    "select": {
                        "options": [
                            {"name": "On Track",       "color": "green"},
                            {"name": "Has Blockers",   "color": "red"},
                            {"name": "Pending Review", "color": "yellow"},
                        ]
                    }
                },
                "Report Status": {
                    "select": {
                        "options": [
                            {"name": "Draft",            "color": "yellow"},
                            {"name": "PM Review",        "color": "blue"},
                            {"name": "Verified",         "color": "green"},
                            {"name": "Needs Correction", "color": "red"},
                            {"name": "Sent to Client",   "color": "gray"},
                        ]
                    }
                },
                "PM Verified": {"checkbox": {}},
            },
        )
        db_ids["NOTION_SITE_REPORTS_DB"] = db["id"].replace("-", "")
        print_ok(f"Site Reports DB created")
    except Exception as e:
        print_fail(f"Failed to create Site Reports DB: {e}")
        sys.exit(1)

    # ── Inventory DB ──
    print_info("Creating Inventory database...")
    try:
        db = client.databases.create(
            parent={"type": "page_id", "page_id": page_id},
            title=[{"type": "text", "text": {"content": "Kamau Construction - Inventory"}}],
            properties={
                "Material Name":     {"title": {}},
                "Site": {
                    "select": {
                        "options": [
                            {"name": "Westlands",  "color": "blue"},
                            {"name": "Kilimani",   "color": "green"},
                            {"name": "Eastleigh",  "color": "orange"},
                            {"name": "Other",      "color": "gray"},
                        ]
                    }
                },
                "Unit": {
                    "select": {
                        "options": [
                            {"name": "bags",    "color": "default"},
                            {"name": "litres",  "color": "blue"},
                            {"name": "pieces",  "color": "green"},
                            {"name": "kg",      "color": "yellow"},
                            {"name": "metres",  "color": "purple"},
                        ]
                    }
                },
                "Opening Stock":     {"number": {"format": "number"}},
                "Total Used":        {"number": {"format": "number"}},
                "Remaining":         {"number": {"format": "number"}},
                "Minimum Threshold": {"number": {"format": "number"}},
                "Needs Reorder":     {"checkbox": {}},
                "Last Updated":      {"date": {}},
                "Notes":             {"rich_text": {}},
            },
        )
        db_ids["NOTION_INVENTORY_DB"] = db["id"].replace("-", "")
        print_ok(f"Inventory DB created")
    except Exception as e:
        print_fail(f"Failed to create Inventory DB: {e}")
        sys.exit(1)

    # ── Reorder Alerts DB ──
    print_info("Creating Reorder Alerts database...")
    try:
        db = client.databases.create(
            parent={"type": "page_id", "page_id": page_id},
            title=[{"type": "text", "text": {"content": "Kamau Construction - Reorder Alerts"}}],
            properties={
                "Material":            {"title": {}},
                "Site": {
                    "select": {
                        "options": [
                            {"name": "Westlands",  "color": "blue"},
                            {"name": "Kilimani",   "color": "green"},
                            {"name": "Eastleigh",  "color": "orange"},
                            {"name": "Other",      "color": "gray"},
                        ]
                    }
                },
                "Remaining Stock":    {"number": {"format": "number"}},
                "Opening Stock":      {"number": {"format": "number"}},
                "Stock Remaining %":  {"number": {"format": "number"}},
                "Project Progress %": {"number": {"format": "number"}},
                "Reason":             {"rich_text": {}},
                "Flagged On":         {"date": {}},
                "Resolved On":        {"date": {}},
                "Resolved":           {"checkbox": {}},
                "Priority": {
                    "select": {
                        "options": [
                            {"name": "High",   "color": "red"},
                            {"name": "Medium", "color": "yellow"},
                            {"name": "Low",    "color": "green"},
                        ]
                    }
                },
            },
        )
        db_ids["NOTION_REORDER_DB"] = db["id"].replace("-", "")
        print_ok(f"Reorder Alerts DB created")
    except Exception as e:
        print_fail(f"Failed to create Reorder Alerts DB: {e}")
        sys.exit(1)

    return db_ids, page_url


# ── STEP 5: WRITE .ENV ────────────────────────────────────────────────────────

def write_env(notion_key: str, groq_key: str, db_ids: dict):
    print_step(5, 5, "Writing .env file")

    env_content = f"""# JengoAI Environment Variables
# Auto-generated by setup.py — do not commit this file to GitHub

GROQ_API_KEY={groq_key}
NOTION_API_KEY={notion_key}

NOTION_SITE_REPORTS_DB={db_ids["NOTION_SITE_REPORTS_DB"]}
NOTION_INVENTORY_DB={db_ids["NOTION_INVENTORY_DB"]}
NOTION_REORDER_DB={db_ids["NOTION_REORDER_DB"]}
"""
    with open(".env", "w") as f:
        f.write(env_content)
    print_ok(".env written with all keys and database IDs")


# ── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    print_header()

    check_dependencies()
    notion_key, groq_key = collect_keys()
    client = verify_and_connect(notion_key)
    db_ids, page_url = create_workspace(client)
    write_env(notion_key, groq_key, db_ids)

    print(f"""
{GREEN}{BOLD}
  ╔══════════════════════════════════════════╗
  ║           Setup complete!                ║
  ╚══════════════════════════════════════════╝
{RESET}
  {WHITE}Your JengoAI workspace is ready in Notion:{RESET}
  {CYAN}{page_url}{RESET}

  {WHITE}Three databases created:{RESET}
  {MUTED}· Kamau Construction - Site Reports{RESET}
  {MUTED}· Kamau Construction - Inventory{RESET}
  {MUTED}· Kamau Construction - Reorder Alerts{RESET}

  {WHITE}Your .env file has been written with all keys.{RESET}

  {CYAN}Run the CLI:{RESET}
    python cli.py

  {CYAN}Run the dashboard:{RESET}
    streamlit run app.py
""")


if __name__ == "__main__":
    main()