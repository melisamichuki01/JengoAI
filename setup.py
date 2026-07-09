#!/usr/bin/env python3
"""
JengoAI Setup Script
--------------------
Run this once to create all three Notion databases and generate your .env file.

Usage:
    python setup.py
"""

import os
import re
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


def print_ok(msg):    print(f"  {GREEN}✓{RESET} {msg}")
def print_fail(msg):  print(f"  {RED}✗{RESET} {msg}")
def print_info(msg):  print(f"  {MUTED}{msg}{RESET}")


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
        print(f"\n{YELLOW}Run this then try again:{RESET}")
        print(f"  pip install {' '.join(to_install)}")
        sys.exit(1)


# ── STEP 2: COLLECT KEYS ─────────────────────────────────────────────────────

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

    notion_key = existing.get("NOTION_API_KEY", "")
    if notion_key:
        print_ok("NOTION_API_KEY found in .env")
    else:
        print(f"""
  {WHITE}Get your Notion integration token:{RESET}
  {MUTED}1. Go to https://www.notion.so/my-integrations{RESET}
  {MUTED}2. Click New Integration{RESET}
  {MUTED}3. Name it jengoai, select your workspace, click Submit{RESET}
  {MUTED}4. Copy the Internal Integration Token (starts with secret_){RESET}
""")
        notion_key = input(f"  {YELLOW}Paste your Notion API key: {RESET}").strip()
        if not notion_key.startswith("secret_"):
            print_fail("Key should start with secret_")
            sys.exit(1)

    groq_key = existing.get("GROQ_API_KEY", "")
    if groq_key:
        print_ok("GROQ_API_KEY found in .env")
    else:
        print(f"\n  {MUTED}Go to https://console.groq.com, sign up free, copy your API key{RESET}\n")
        groq_key = input(f"  {YELLOW}Paste your Groq API key: {RESET}").strip()
        if not groq_key:
            print_fail("Groq key cannot be empty.")
            sys.exit(1)

    return notion_key, groq_key


# ── STEP 3: VERIFY + GET PARENT PAGE ─────────────────────────────────────────

def verify_and_get_parent(notion_key: str):
    print_step(3, 5, "Connecting to Notion")
    from notion_client import Client
    from notion_client.errors import APIResponseError

    client = Client(auth=notion_key)

    try:
        me = client.users.me()
        print_ok(f"Connected as: {me.get('name', 'Unknown')}")
    except Exception as e:
        print_fail(f"Invalid Notion key: {e}")
        sys.exit(1)

    print(f"""
  {WHITE}You need to give the agent a Notion page to work in.{RESET}

  {MUTED}Quick steps:{RESET}
  {MUTED}1. Open Notion in your browser{RESET}
  {MUTED}2. Click New Page in the left sidebar{RESET}
  {MUTED}3. Name it anything e.g. JengoAI{RESET}
  {MUTED}4. Click the ... menu top right → Connections → add jengoai{RESET}
  {MUTED}5. Copy the full URL from your browser and paste it below{RESET}
""")

    while True:
        raw = input(f"  {YELLOW}Paste your Notion page URL: {RESET}").strip()
        if not raw:
            print_fail("URL cannot be empty. Try again.")
            continue

        # Extract 32-char hex ID from any Notion URL format
        clean = raw.replace("-", "").lower()
        clean = clean.split("?")[0].split("#")[0]
        matches = re.findall(r"[0-9a-f]{32}", clean)

        if matches:
            page_id = matches[-1]
            # Verify the page is accessible
            try:
                page = client.pages.retrieve(page_id)
                title_items = page.get("properties", {}).get("title", {}).get("title", [])
                title = title_items[0]["text"]["content"] if title_items else "Untitled"
                print_ok(f"Page found: {title}")
                return client, page_id
            except APIResponseError:
                print_fail("Page not accessible. Make sure you connected your jengoai integration to it (step 4 above).")
            except Exception as e:
                print_fail(f"Could not access page: {e}")
        else:
            print_fail("Could not find a page ID in that URL. Make sure you copied the full browser URL.")


# ── STEP 4: CREATE DATABASES ──────────────────────────────────────────────────

def create_databases(client, page_id: str) -> dict:
    print_step(4, 5, "Creating databases")
    db_ids = {}

    # Site Reports
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
                "Status": {"select": {"options": [
                    {"name": "On Track",       "color": "green"},
                    {"name": "Has Blockers",   "color": "red"},
                    {"name": "Pending Review", "color": "yellow"},
                ]}},
                "Report Status": {"select": {"options": [
                    {"name": "Draft",            "color": "yellow"},
                    {"name": "PM Review",        "color": "blue"},
                    {"name": "Verified",         "color": "green"},
                    {"name": "Needs Correction", "color": "red"},
                    {"name": "Sent to Client",   "color": "gray"},
                ]}},
                "PM Verified": {"checkbox": {}},
            },
        )
        db_ids["NOTION_SITE_REPORTS_DB"] = db["id"].replace("-", "")
        print_ok("Site Reports DB created")
    except Exception as e:
        print_fail(f"Failed: {e}")
        sys.exit(1)

    # Inventory
    print_info("Creating Inventory database...")
    try:
        db = client.databases.create(
            parent={"type": "page_id", "page_id": page_id},
            title=[{"type": "text", "text": {"content": "Kamau Construction - Inventory"}}],
            properties={
                "Material Name":     {"title": {}},
                "Site": {"select": {"options": [
                    {"name": "Westlands", "color": "blue"},
                    {"name": "Kilimani",  "color": "green"},
                    {"name": "Eastleigh", "color": "orange"},
                    {"name": "Other",     "color": "gray"},
                ]}},
                "Unit": {"select": {"options": [
                    {"name": "bags",   "color": "default"},
                    {"name": "litres", "color": "blue"},
                    {"name": "pieces", "color": "green"},
                    {"name": "kg",     "color": "yellow"},
                    {"name": "metres", "color": "purple"},
                ]}},
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
        print_ok("Inventory DB created")
    except Exception as e:
        print_fail(f"Failed: {e}")
        sys.exit(1)

    # Reorder Alerts
    print_info("Creating Reorder Alerts database...")
    try:
        db = client.databases.create(
            parent={"type": "page_id", "page_id": page_id},
            title=[{"type": "text", "text": {"content": "Kamau Construction - Reorder Alerts"}}],
            properties={
                "Material":            {"title": {}},
                "Site": {"select": {"options": [
                    {"name": "Westlands", "color": "blue"},
                    {"name": "Kilimani",  "color": "green"},
                    {"name": "Eastleigh", "color": "orange"},
                    {"name": "Other",     "color": "gray"},
                ]}},
                "Remaining Stock":    {"number": {"format": "number"}},
                "Opening Stock":      {"number": {"format": "number"}},
                "Stock Remaining %":  {"number": {"format": "number"}},
                "Project Progress %": {"number": {"format": "number"}},
                "Reason":             {"rich_text": {}},
                "Flagged On":         {"date": {}},
                "Resolved On":        {"date": {}},
                "Resolved":           {"checkbox": {}},
                "Priority": {"select": {"options": [
                    {"name": "High",   "color": "red"},
                    {"name": "Medium", "color": "yellow"},
                    {"name": "Low",    "color": "green"},
                ]}},
            },
        )
        db_ids["NOTION_REORDER_DB"] = db["id"].replace("-", "")
        print_ok("Reorder Alerts DB created")
    except Exception as e:
        print_fail(f"Failed: {e}")
        sys.exit(1)

    return db_ids


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
    client, page_id = verify_and_get_parent(notion_key)
    db_ids = create_databases(client, page_id)
    write_env(notion_key, groq_key, db_ids)

    print(f"""
{GREEN}{BOLD}
  ╔══════════════════════════════════════════╗
  ║           Setup complete!                ║
  ╚══════════════════════════════════════════╝
{RESET}
  {WHITE}Three databases created in your Notion page.{RESET}
  {WHITE}.env written with all keys and IDs.{RESET}

  {CYAN}Run the CLI:{RESET}
    python cli.py

  {CYAN}Run the dashboard:{RESET}
    streamlit run app.py
""")


if __name__ == "__main__":
    main()