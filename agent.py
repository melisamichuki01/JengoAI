import os
import json
from groq import Groq
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()  # add this line


client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
MODEL = "llama-3.3-70b-versatile"


def extract_update(raw_text: str) -> dict:
    """
    Extract structured data from a foreman's raw site update.
    Handles mixed Swahili/English and informal language.
    Now also extracts materials_used as a structured list.
    """
    prompt = f"""
You are a construction site data extractor working in Kenya.
The message may be in English, Swahili, or a mix of both. Interpret intent, not just keywords.

Swahili hints:
- "kazi X%" or "tumefika X%" = progress is X%
- "cement/saruji haijafika" = cement has not arrived (blocker)
- "vibarua X" = X labourers needed
- "salama" = safe / no accidents
- "haijafika" = has not arrived (blocker)
- "inahitajika" = is needed

Message: "{raw_text}"

Return ONLY a valid JSON object with these exact keys:
{{
  "site_name": "name of site or Unknown",
  "foreman_name": "foreman name or Unknown",
  "progress_percentage": number 0-100 or null,
  "blockers": ["list of blockers or empty list"],
  "materials_used": [
    {{"name": "material name", "quantity": number or null, "unit": "bags/litres/pieces/kg/metres or null"}}
  ],
  "materials_needed": "description of what needs to be ordered or None",
  "labor_needed": "labor requirements or None",
  "safety_incidents": "safety report or No incidents reported",
  "confidence": "high, medium, or low"
}}

For materials_used, extract every material the foreman mentions using or consuming.
If no materials are mentioned, return an empty list.
Return only the JSON. No explanation. No markdown.
"""
    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
    )

    raw = response.choices[0].message.content.strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
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
            "raw_message": raw_text,
        }


def generate_report(extracted: dict, inventory_summary: str = "") -> str:
    """
    Generate a professional client-facing site report from extracted data.
    Optionally includes an inventory status section if summary is provided.
    """
    date_str = datetime.now().strftime("%B %d, %Y")

    inventory_section = ""
    if inventory_summary:
        inventory_section = f"\nInventory Status:\n{inventory_summary}\n"

    prompt = f"""
You are a professional construction project manager writing a client site report.
Write a formal, clear, and concise report using the data below.
Use professional English. Do not invent information not present in the data.

Site: {extracted.get("site_name", "Unknown")}
Date: {date_str}
Foreman: {extracted.get("foreman_name", "Unknown")}
Progress: {extracted.get("progress_percentage", "Not reported")}%
Blockers: {", ".join(extracted.get("blockers", [])) or "None"}
Materials Needed: {extracted.get("materials_needed", "None")}
Labor Needed: {extracted.get("labor_needed", "None")}
Safety: {extracted.get("safety_incidents", "No incidents reported")}
{inventory_section}
Write the report with these sections:
1. Current Status
2. Issues and Blockers
3. Resource Requirements (materials and labor)
4. Inventory Status (only if inventory data is provided, otherwise omit)
5. Safety Report
6. Next Steps

Keep it professional and under 350 words. Address it to the client.
"""
    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
    )

    return response.choices[0].message.content.strip()


def build_inventory_summary(inventory_items: list) -> str:
    """
    Build a plain-text inventory summary to inject into the report prompt.
    """
    if not inventory_items:
        return ""

    lines = []
    for item in inventory_items:
        stock_pct = item.get("stock_pct", 0)
        status    = "CRITICAL" if stock_pct < 20 else ("LOW" if stock_pct < 40 else "OK")
        lines.append(
            f"- {item['material_name']}: {item['remaining']} {item.get('unit','units')} "
            f"remaining ({stock_pct}% of opening stock) [{status}]"
        )

    return "\n".join(lines)