import os
from datetime import datetime
from notion_client import Client
from dotenv import load_dotenv

load_dotenv()

notion = Client(auth=os.environ.get("NOTION_API_KEY"))

INVENTORY_DB = os.environ.get("NOTION_INVENTORY_DB")
REORDER_DB   = os.environ.get("NOTION_REORDER_DB")

if not INVENTORY_DB or not REORDER_DB:
    raise EnvironmentError("NOTION_INVENTORY_DB or NOTION_REORDER_DB not set. Run: python setup.py")

# ── REORDER LOGIC ─────────────────────────────────────────────────────────────

def should_reorder(remaining: float, opening: float, progress: float) -> tuple[bool, str, str]:
    """
    Decide whether to raise a reorder alert based on stock vs project progress.

    Rules:
      - If progress >= 75% and stock remaining < 40%  --> High priority
      - If progress >= 50% and stock remaining < 30%  --> High priority
      - If progress >= 40% and stock remaining < 25%  --> Medium priority
      - If progress >= 25% and stock remaining < 20%  --> Low priority

    Returns (should_alert: bool, reason: str, priority: str)
    """
    if opening == 0:
        return False, "", "Low"

    stock_pct = (remaining / opening) * 100

    if progress >= 75 and stock_pct < 40:
        reason = (
            f"Project is {progress}% complete but only {stock_pct:.1f}% of stock remains. "
            f"At current consumption rate, stock will run out before project completion."
        )
        return True, reason, "High"

    if progress >= 50 and stock_pct < 30:
        reason = (
            f"Project is past halfway ({progress}%) but stock is critically low at {stock_pct:.1f}%. "
            f"Reorder required to avoid site stoppage."
        )
        return True, reason, "High"

    if progress >= 40 and stock_pct < 25:
        reason = (
            f"Project is {progress}% complete with only {stock_pct:.1f}% stock remaining. "
            f"Order now to ensure timely delivery before stock runs out."
        )
        return True, reason, "Medium"

    if progress >= 25 and stock_pct < 20:
        reason = (
            f"Stock at {stock_pct:.1f}% with project at {progress}% completion. "
            f"Plan a reorder to avoid delays in later project phases."
        )
        return True, reason, "Low"

    return False, "", "Low"


# ── INVENTORY: READ ───────────────────────────────────────────────────────────

def get_inventory(site: str = None) -> list:
    """
    Fetch all inventory rows, optionally filtered by site.
    """
    filters = []
    if site:
        filters.append({"property": "Site", "select": {"equals": site}})

    query_args = {"database_id": INVENTORY_DB}
    if filters:
        query_args["filter"] = {"and": filters}

    response = notion.databases.query(**query_args)
    return [_parse_inventory_page(p) for p in response.get("results", [])]


def get_inventory_item(material: str, site: str) -> dict | None:
    response = notion.databases.query(
        database_id=INVENTORY_DB,
        filter={
            "property": "Material Name", "title": {"equals": material}
        },
    )
    results = response.get("results", [])
    return _parse_inventory_page(results[0]) if results else None


def get_reorder_alerts(resolved: bool = False) -> list:
    """
    Fetch reorder alerts. By default returns only unresolved alerts.
    """
    response = notion.databases.query(
        database_id=REORDER_DB,
        filter={"property": "Resolved", "checkbox": {"equals": resolved}},
        sorts=[{"property": "Flagged On", "direction": "descending"}],
    )
    return [_parse_alert_page(p) for p in response.get("results", [])]


# ── INVENTORY: WRITE ──────────────────────────────────────────────────────────

def update_inventory(material: str, site: str, qty_used: float, progress: float) -> dict:
    """
    Update an existing inventory item after a foreman reports usage.
    If the item doesn't exist yet, creates it with the used quantity as a starting record.
    Also runs reorder check and creates an alert if triggered.

    Returns the updated inventory item dict.
    """
    date_str = datetime.now().strftime("%Y-%m-%d")
    existing = get_inventory_item(material, site)

    if existing:
        new_used      = (existing["total_used"] or 0) + qty_used
        new_remaining = max((existing["opening_stock"] or 0) - new_used, 0)

        notion.pages.update(
            page_id=existing["id"],
            properties={
                "Total Used": {"number": new_used},
                "Remaining":  {"number": new_remaining},
                "Last Updated": {"date": {"start": date_str}},
                "Needs Reorder": {
                    "checkbox": new_remaining <= (existing["minimum_threshold"] or 0)
                },
            },
        )
        updated = {**existing, "total_used": new_used, "remaining": new_remaining}
    else:
        # First time this material is reported for this site
        new_remaining = 0
        response = notion.pages.create(
            parent={"database_id": INVENTORY_DB},
            properties={
                "Material Name": {"title": [{"text": {"content": material}}]},
                "Site": {
                        "rich_text": [{"text": {"content": site}}]
                    },
                "Opening Stock": {"number": 0},
                "Total Used":    {"number": qty_used},
                "Remaining":     {"number": 0},
                "Minimum Threshold": {"number": 0},
                "Needs Reorder": {"checkbox": False},
                "Last Updated":  {"date": {"start": date_str}},
                "Notes": {
                    "rich_text": [{"text": {"content": "Auto-created from foreman update."}}]
                },
            },
        )
        updated = _parse_inventory_page(response)

    # Run reorder check
    opening   = existing["opening_stock"] if existing else 0
    remaining = updated.get("remaining", new_remaining)
    alert, reason, priority = should_reorder(remaining, opening, progress)

    if alert:
        create_reorder_alert(
            material=material,
            site=site,
            remaining=remaining,
            opening=opening,
            progress=progress,
            reason=reason,
            priority=priority,
        )

    return updated


def pm_adjust_inventory(page_id: str, field: str, value) -> None:
    """
    Allow PM to manually adjust an inventory field.
    Supported fields: opening_stock, remaining, minimum_threshold, notes
    """
    field_map = {
        "opening_stock":      ("Opening Stock",      "number"),
        "remaining":          ("Remaining",           "number"),
        "minimum_threshold":  ("Minimum Threshold",   "number"),
        "notes":              ("Notes",               "text"),
    }

    if field not in field_map:
        raise ValueError(f"Unknown field: {field}. Supported: {list(field_map.keys())}")

    notion_field, field_type = field_map[field]
    date_str = datetime.now().strftime("%Y-%m-%d")

    if field_type == "number":
        prop_value = {"number": float(value)}
    else:
        prop_value = {"rich_text": [{"text": {"content": str(value)}}]}

    notion.pages.update(
        page_id=page_id,
        properties={
            notion_field:   prop_value,
            "Last Updated": {"date": {"start": date_str}},
        },
    )


def create_reorder_alert(
    material: str,
    site: str,
    remaining: float,
    opening: float,
    progress: float,
    reason: str,
    priority: str,
) -> str:
    """
    Create a new reorder alert row in the Reorder Alerts database.
    Returns the Notion page URL.
    """
    date_str   = datetime.now().strftime("%Y-%m-%d")
    stock_pct  = round((remaining / opening) * 100, 1) if opening else 0

    response = notion.pages.create(
        parent={"database_id": REORDER_DB},
        properties={
            "Material":          {"title": [{"text": {"content": material}}]},
            "Site":              {"select": {"name": site}},
            "Remaining Stock":   {"number": remaining},
            "Opening Stock":     {"number": opening},
            "Stock Remaining %": {"number": stock_pct},
            "Project Progress %": {"number": progress},
            "Reason":            {"rich_text": [{"text": {"content": reason}}]},
            "Flagged On":        {"date": {"start": date_str}},
            "Priority":          {"select": {"name": priority}},
            "Resolved":          {"checkbox": False},
        },
    )
    url = response.get("url", "")
    print(f"Reorder alert created ({priority}): {material} at {site} — {url}")
    return url


def resolve_alert(page_id: str) -> None:
    """Mark a reorder alert as resolved."""
    date_str = datetime.now().strftime("%Y-%m-%d")
    notion.pages.update(
        page_id=page_id,
        properties={
            "Resolved":    {"checkbox": True},
            "Resolved On": {"date": {"start": date_str}},
        },
    )


# ── PARSERS ───────────────────────────────────────────────────────────────────

def _parse_inventory_page(page: dict) -> dict:
    props = page.get("properties", {})

    def title(key):
        items = props.get(key, {}).get("title", [])
        return items[0]["text"]["content"] if items else ""

    def number(key):
        return props.get(key, {}).get("number")

    def select(key):
        val = props.get(key, {}).get("select")
        return val["name"] if val else ""

    def checkbox(key):
        return props.get(key, {}).get("checkbox", False)

    def text(key):
        items = props.get(key, {}).get("rich_text", [])
        return items[0]["text"]["content"] if items else ""

    def date(key):
        val = props.get(key, {}).get("date")
        return val["start"] if val else ""

    opening   = number("Opening Stock") or 0
    used      = number("Total Used") or 0
    remaining = number("Remaining") or 0
    stock_pct = round((remaining / opening) * 100, 1) if opening else 0

    return {
        "id":                page["id"],
        "material_name":     title("Material Name"),
        "site":              select("Site"),
        "unit":              select("Unit"),
        "opening_stock":     opening,
        "total_used":        used,
        "remaining":         remaining,
        "stock_pct":         stock_pct,
        "minimum_threshold": number("Minimum Threshold") or 0,
        "needs_reorder":     checkbox("Needs Reorder"),
        "last_updated":      date("Last Updated"),
        "notes":             text("Notes"),
    }


def _parse_alert_page(page: dict) -> dict:
    props = page.get("properties", {})

    def title(key):
        items = props.get(key, {}).get("title", [])
        return items[0]["text"]["content"] if items else ""

    def number(key):
        return props.get(key, {}).get("number")

    def select(key):
        val = props.get(key, {}).get("select")
        return val["name"] if val else ""

    def text(key):
        items = props.get(key, {}).get("rich_text", [])
        return items[0]["text"]["content"] if items else ""

    def checkbox(key):
        return props.get(key, {}).get("checkbox", False)

    def date(key):
        val = props.get(key, {}).get("date")
        return val["start"] if val else ""

    return {
        "id":               page["id"],
        "material":         title("Material"),
        "site":             select("Site"),
        "remaining_stock":  number("Remaining Stock"),
        "opening_stock":    number("Opening Stock"),
        "stock_pct":        number("Stock Remaining %"),
        "progress_pct":     number("Project Progress %"),
        "reason":           text("Reason"),
        "flagged_on":       date("Flagged On"),
        "priority":         select("Priority"),
        "resolved":         checkbox("Resolved"),
        "resolved_on":      date("Resolved On"),
    }