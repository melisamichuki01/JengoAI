import os
from datetime import datetime
from notion_client import Client
from dotenv import load_dotenv

load_dotenv()

notion = Client(auth=os.environ.get("NOTION_API_KEY"))
DATABASE_ID = os.environ.get("NOTION_SITE_REPORTS_DB")

if not DATABASE_ID:
    raise EnvironmentError("NOTION_SITE_REPORTS_DB not set. Run: python setup.py")

def save_report_to_notion(report_text: str, extracted: dict, image_url: str = None) -> str:
    """
    Save a generated report and extracted fields as a new Notion database row.
    Automatically sets Report Status to Draft and Status based on blockers.
    """
    date_str = datetime.now().strftime("%Y-%m-%d")
    blocker_status = "Has Blockers" if extracted.get("blockers") else "On Track"

    properties = {
        "Site Name": {
            "title": [{"text": {"content": extracted.get("site_name", "Unknown")}}]
        },
        "Date": {
            "date": {"start": date_str}
        },
        "Foreman": {
            "rich_text": [{"text": {"content": extracted.get("foreman_name", "Unknown")}}]
        },
        "Blockers": {
            "rich_text": [{"text": {"content": ", ".join(extracted.get("blockers", [])) or "None"}}]
        },
        "Materials Needed": {
            "rich_text": [{"text": {"content": extracted.get("materials_needed", "None")}}]
        },
        "Labor Needed": {
            "rich_text": [{"text": {"content": extracted.get("labor_needed", "None")}}]
        },
        "Safety": {
            "rich_text": [{"text": {"content": extracted.get("safety_incidents", "No incidents reported")}}]
        },
        "Report": {
            "rich_text": [{"text": {"content": report_text}}]
        },
        "Status": {
            "select": {"name": blocker_status}
        },
        "Report Status": {
            "select": {"name": "Draft"}
        },
        "PM Verified": {
            "checkbox": False
        },
    }

    if extracted.get("progress_percentage") is not None:
        properties["Progress %"] = {"number": extracted["progress_percentage"]}

    if image_url:
        properties["Site Photos"] = {
            "files": [{"name": "Site Photo", "external": {"url": image_url}}]
        }

    response = notion.pages.create(
        parent={"database_id": DATABASE_ID},
        properties=properties,
    )

    page_url = response.get("url", "")
    print(f"Report saved to Notion: {page_url}")
    return page_url


def get_draft_reports() -> list:
    response = notion.databases.query(
        database_id=DATABASE_ID,
        filter={
            "or": [
                {"property": "Report Status", "select": {"equals": "Draft"}},
                {"property": "Report Status", "select": {"equals": "Needs Correction"}},
            ]
        },
        sorts=[{"property": "Date", "direction": "descending"}],
    )
    return [_parse_page(page) for page in response.get("results", [])]


def get_all_reports() -> list:
    response = notion.databases.query(
        database_id=DATABASE_ID,
        sorts=[{"property": "Date", "direction": "descending"}],
    )
    return [_parse_page(page) for page in response.get("results", [])]


def update_report_status(page_id: str, status: str, notes: str = "", verified: bool = False):
    notion.pages.update(
        page_id=page_id,
        properties={
            "Report Status": {"select": {"name": status}},
            "PM Verified": {"checkbox": verified},
            "Verification Notes": {
                "rich_text": [{"text": {"content": notes}}]
            },
        },
    )


def _parse_page(page: dict) -> dict:
    props = page.get("properties", {})

    def text(key):
        items = props.get(key, {}).get("rich_text", [])
        return items[0]["text"]["content"] if items else ""

    def title(key):
        items = props.get(key, {}).get("title", [])
        return items[0]["text"]["content"] if items else ""

    def select(key):
        val = props.get(key, {}).get("select")
        return val["name"] if val else ""

    def number(key):
        return props.get(key, {}).get("number")

    def date(key):
        val = props.get(key, {}).get("date")
        return val["start"] if val else ""

    def checkbox(key):
        return props.get(key, {}).get("checkbox", False)

    def files(key):
        items = props.get(key, {}).get("files", [])
        urls = []
        for f in items:
            if "external" in f:
                urls.append(f["external"]["url"])
            elif "file" in f:
                urls.append(f["file"]["url"])
        return urls

    return {
        "id": page["id"],
        "site_name": title("Site Name"),
        "date": date("Date"),
        "foreman": text("Foreman"),
        "progress": number("Progress %"),
        "blockers": text("Blockers"),
        "materials": text("Materials Needed"),
        "labor": text("Labor Needed"),
        "safety": text("Safety"),
        "report_text": text("Report"),
        "status": select("Status"),
        "report_status": select("Report Status"),
        "pm_verified": checkbox("PM Verified"),
        "verification_notes": text("Verification Notes"),
        "photos": files("Site Photos"),
    }