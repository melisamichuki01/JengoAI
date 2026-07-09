"""
tools.py
--------
The four tools available to the JengoAI agent.
Each function does exactly one thing and returns a plain dict
so the agent can read the result and decide what to do next.
"""

import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()


# ── TOOL 1: EXTRACT ───────────────────────────────────────────────────────────

def extract_site_update(raw_message: str) -> dict:
    """
    Parse a foreman's raw WhatsApp-style message into structured data.
    Handles English, Swahili, and mixed messages.
    Returns a dict with site_name, foreman_name, progress_percentage,
    blockers, materials_used, materials_needed, labor_needed,
    safety_incidents, and confidence.
    """
    import json
    from groq import Groq

    client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

    prompt = f"""
You are a construction site data extractor working in Kenya.
The message may be in English, Swahili, or a mix. Interpret intent, not just keywords.

CRITICAL SWAHILI PATTERN:
Foremen often start with: "[SITE] [NAME] hapa"
This means site=[SITE], foreman=[NAME]. "hapa" means "reporting in".
Examples:
- "Westlands James hapa" = site: Westlands, foreman: James
- "Kilimani Peter hapa" = site: Kilimani, foreman: Peter
- "Eastleigh Grace hapa" = site: Eastleigh, foreman: Grace
- "Kisumu David hapa" = site: Kisumu, foreman: David
NEVER merge the site and foreman name into one string.

Other Swahili hints:
- "kazi X%" or "tumefika X%" = progress is X%
- "saruji" = cement
- "saruji/cement haijafika" = cement has not arrived (blocker)
- "tumitumia saruji mifuko 30" = we used 30 bags of cement
- "vibarua X" = X labourers needed
- "vibarua wote wako" = all labourers present, none needed
- "salama" or "hakuna ajali" = safe, no accidents
- "inakwisha" = running out (potential blocker or materials needed)
- "tunahitaji" = we need
- "haraka" = urgently
- "mifuko" = bags
- "lita" = litres

Message: "{raw_message}"

Return ONLY valid JSON with these exact keys:
{{
  "site_name": "construction site location ONLY, never include foreman name",
  "foreman_name": "foreman personal name ONLY, never include site name",
  "progress_percentage": number 0-100 or null,
  "blockers": ["list of blockers or empty list"],
  "materials_used": [
    {{"name": "material name in English", "quantity": number or null, "unit": "bags/litres/pieces/kg/metres or null"}}
  ],
  "materials_needed": "what needs to be ordered or None",
  "labor_needed": "labor requirements or None",
  "safety_incidents": "safety report or No incidents reported",
  "confidence": "high, medium, or low"
}}

Return only the JSON. No explanation. No markdown.
"""

    response = client.chat.completions.create(
        model=os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile"),
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
    )

    raw = response.choices[0].message.content.strip()

    try:
        return json.loads(raw)
    except Exception:
        return {
            "site_name": "Unknown",
            "foreman_name": "Unknown",
            "progress_percentage": None,
            "blockers": [],
            "materials_used": [],
            "materials_needed": "None",
            "labor_needed": "None",
            "safety_incidents": "No incidents reported",
            "confidence": "low",
            "raw_message": raw_message,
        }


# ── TOOL 2: UPDATE INVENTORY ──────────────────────────────────────────────────

def update_inventory_for_material(
    material_name: str,
    quantity_used: float,
    unit: str,
    site_name: str,
    progress_percentage: float,
) -> dict:
    """
    Update the Notion inventory database for a single material.
    Subtracts quantity_used from remaining stock.
    Checks if a reorder alert should be raised based on progress vs stock.
    Returns updated stock levels and whether a reorder alert was created.
    """
    from inventory import update_inventory

    result = update_inventory(
        material=material_name,
        site=site_name,
        qty_used=quantity_used,
        progress=progress_percentage or 0,
    )

    return {
        "material": material_name,
        "site": site_name,
        "quantity_used": quantity_used,
        "unit": unit,
        "remaining": result.get("remaining", 0),
        "stock_pct": result.get("stock_pct", 0),
        "reorder_alert_created": result.get("needs_reorder", False),
    }


# ── TOOL 3: GENERATE REPORT ───────────────────────────────────────────────────

def generate_site_report(
    site_name: str,
    foreman_name: str,
    progress_percentage: float,
    blockers: list,
    materials_needed: str,
    labor_needed: str,
    safety_incidents: str,
    inventory_summary: str = "",
    history_summary: str = "",
) -> dict:
    """
    Generate a professional client-facing site report from structured data.
    Includes historical context if history_summary is provided.
    Returns the report text.
    """
    from groq import Groq

    client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
    date_str = datetime.now().strftime("%B %d, %Y")

    inventory_section = f"\nInventory Status:\n{inventory_summary}" if inventory_summary else ""
    history_section   = f"\nHistorical Context (use this to show trends):\n{history_summary}" if history_summary else ""

    prompt = f"""
You are a professional construction project manager writing a client site report.
Write a formal, clear, and concise report using the data below.
Do not invent information not present in the data.
End the report with: Kamau Construction Management Team

IMPORTANT: If historical context is provided, you MUST reference it in the Current Status section.
Show how progress has changed since the last report. For example:
"Progress has increased from 70% last week to 85% this week, an improvement of 15%."
If there were recurring blockers, note whether they have been resolved or are ongoing.

Site: {site_name}
Date: {date_str}
Foreman: {foreman_name}
Progress Today: {progress_percentage}%
Blockers: {", ".join(blockers) if blockers else "None"}
Materials Needed: {materials_needed}
Labor Needed: {labor_needed}
Safety: {safety_incidents}
{inventory_section}
{history_section}

Write these sections:
1. Current Status (include progress trend if history is available)
2. Issues and Blockers (note if any are recurring from previous reports)
3. Resource Requirements
4. Inventory Status (only if inventory data provided)
5. Safety Report
6. Next Steps

Professional tone. Under 400 words.
"""

    response = client.chat.completions.create(
        model=os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile"),
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
    )

    report_text = response.choices[0].message.content.strip()
    return {"report_text": report_text}


# ── TOOL 4: SAVE TO NOTION ────────────────────────────────────────────────────

def save_report_to_notion(
    report_text: str,
    site_name: str,
    foreman_name: str,
    progress_percentage: float,
    blockers: list,
    materials_needed: str,
    labor_needed: str,
    safety_incidents: str,
) -> dict:
    """
    Save a generated report and all extracted fields to the Notion
    Site Reports database as a Draft. Returns the Notion page URL.
    """
    from notion_client_wrapper import save_report_to_notion as _save

    extracted = {
        "site_name":           site_name,
        "foreman_name":        foreman_name,
        "progress_percentage": progress_percentage,
        "blockers":            blockers,
        "materials_needed":    materials_needed,
        "labor_needed":        labor_needed,
        "safety_incidents":    safety_incidents,
    }

    url = _save(report_text, extracted)
    return {"notion_url": url, "status": "saved"}



# ── TOOL 5: FETCH SITE HISTORY ────────────────────────────────────────────────

def fetch_site_history(site_name: str, limit: int = 3) -> dict:
    """
    Fetch the last N reports for a given site from the Notion Site Reports database.
    Returns a summary of past progress, blockers, and trends so the agent can
    write reports with historical context baked in.
    """
    from notion_client_wrapper import get_all_reports

    all_reports = get_all_reports()

    # Filter to this site only, sorted most recent first
    site_reports = [
        r for r in all_reports
        if r.get("site_name", "").lower() == site_name.lower()
    ][:limit]

    if not site_reports:
        return {
            "site_name":  site_name,
            "found":      0,
            "history":    [],
            "summary":    f"No previous reports found for {site_name}. This appears to be the first report.",
        }

    history = []
    for r in site_reports:
        history.append({
            "date":     r.get("date", "Unknown"),
            "progress": r.get("progress"),
            "blockers": r.get("blockers", "None"),
            "safety":   r.get("safety", "No incidents"),
            "status":   r.get("status", "Unknown"),
        })

    # Build a plain text summary the LLM can read
    lines = [f"Previous reports for {site_name} (most recent first):"]
    for h in history:
        lines.append(
            f"- {h['date']}: {h['progress']}% complete, "
            f"status: {h['status']}, "
            f"blockers: {h['blockers'] or 'None'}"
        )

    # Calculate progress trend
    if len(history) >= 2:
        latest   = history[0].get("progress") or 0
        previous = history[1].get("progress") or 0
        delta    = latest - previous
        if delta > 0:
            trend = f"Progress increased by {delta}% since the last report."
        elif delta < 0:
            trend = f"Progress decreased by {abs(delta)}% since the last report. Investigate blockers."
        else:
            trend = "Progress has not changed since the last report."
        lines.append(trend)

    return {
        "site_name": site_name,
        "found":     len(history),
        "history":   history,
        "summary":   "\n".join(lines),
    }


# ── TOOL REGISTRY ─────────────────────────────────────────────────────────────
# Maps tool names (as the LLM knows them) to their Python functions.

TOOL_FUNCTIONS = {
    "extract_site_update":          extract_site_update,
    "update_inventory_for_material": update_inventory_for_material,
    "generate_site_report":         generate_site_report,
    "save_report_to_notion":        save_report_to_notion,
    "fetch_site_history":           fetch_site_history,
}


# ── TOOL SCHEMAS ──────────────────────────────────────────────────────────────
# JSON schemas passed to Groq so the LLM knows what tools exist and what
# parameters each one expects.

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "extract_site_update",
            "description": (
                "Parse a foreman's raw site update message into structured data. "
                "Always call this first. Returns site name, foreman, progress, "
                "blockers, materials used, materials needed, labor, safety, and confidence."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "raw_message": {
                        "type": "string",
                        "description": "The raw foreman message to extract data from.",
                    }
                },
                "required": ["raw_message"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_inventory_for_material",
            "description": (
                "Update inventory for a single material after a foreman reports using it. "
                "Call once per material in the materials_used list. "
                "Automatically raises a reorder alert if stock is critically low."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "material_name":       {"type": "string",  "description": "Name of the material e.g. cement"},
                    "quantity_used":       {"type": "number",  "description": "How much was used"},
                    "unit":                {"type": "string",  "description": "Unit e.g. bags, litres, kg"},
                    "site_name":           {"type": "string",  "description": "Name of the construction site"},
                    "progress_percentage": {"type": "number",  "description": "Current project completion percentage"},
                },
                "required": ["material_name", "quantity_used", "unit", "site_name", "progress_percentage"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_site_report",
            "description": (
                "Generate a professional client-facing site report from the extracted data. "
                "Call this after extraction and inventory updates are complete."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "site_name":           {"type": "string", "description": "Name of the construction site"},
                    "foreman_name":        {"type": "string", "description": "Name of the foreman"},
                    "progress_percentage": {"type": "number", "description": "Project completion percentage"},
                    "blockers":            {"type": "array",  "items": {"type": "string"}, "description": "List of issues or blockers"},
                    "materials_needed":    {"type": "string", "description": "Materials that need to be ordered"},
                    "labor_needed":        {"type": "string", "description": "Labor requirements"},
                    "safety_incidents":    {"type": "string", "description": "Safety report"},
                    "inventory_summary":   {"type": "string", "description": "Optional inventory status summary from update_inventory_for_material results"},
                    "history_summary":     {"type": "string", "description": "Historical context from fetch_site_history. ALWAYS include this if fetch_site_history was called. Pass the full summary string."},
                },
                "required": ["site_name", "foreman_name", "progress_percentage", "blockers", "materials_needed", "labor_needed", "safety_incidents"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_report_to_notion",
            "description": (
                "Save the generated report and all extracted fields to Notion as a Draft. "
                "Call this last, after the report has been generated. "
                "Returns the Notion page URL."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "report_text":         {"type": "string", "description": "The full generated report text"},
                    "site_name":           {"type": "string", "description": "Name of the construction site"},
                    "foreman_name":        {"type": "string", "description": "Name of the foreman"},
                    "progress_percentage": {"type": "number", "description": "Project completion percentage"},
                    "blockers":            {"type": "array",  "items": {"type": "string"}, "description": "List of blockers"},
                    "materials_needed":    {"type": "string", "description": "Materials that need to be ordered"},
                    "labor_needed":        {"type": "string", "description": "Labor requirements"},
                    "safety_incidents":    {"type": "string", "description": "Safety report"},
                },
                "required": ["report_text", "site_name", "foreman_name", "progress_percentage", "blockers", "materials_needed", "labor_needed", "safety_incidents"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_site_history",
            "description": (
                "Fetch the last 3 reports for a site to get historical context. "
                "Call this AFTER extracting the update and BEFORE generating the report. "
                "Use the returned summary to write a report that shows progress trends, "
                "recurring blockers, and improvement over time."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "site_name": {
                        "type": "string",
                        "description": "Name of the construction site to fetch history for.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Number of past reports to fetch. Default is 3.",
                    },
                },
                "required": ["site_name"],
            },
        },
    },
]