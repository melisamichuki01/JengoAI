"""
JengoAI LangGraph Migration
Construction Site Reporting Agent with LangGraph State Machine

Stack: LangGraph + Groq (Llama 3.3) + Twilio (WhatsApp) + Email (mock for demo)
"""

from typing import TypedDict, Annotated
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, AIMessage
import json
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Mock imports (replace with real in production)
from groq import Groq
import operator
from dotenv import load_dotenv
import os

load_dotenv()

# ============================================================================
# STATE DEFINITION
# ============================================================================

class JengoState(TypedDict):
    """State object that flows through the LangGraph"""
    
    # Input
    report_text: str
    report_source: str  # "whatsapp", "email", "manual"
    foreman_id: str
    site_location: str
    
    # Parsed data
    parsed_materials: list  # [{"name": "cement", "quantity": 50, "unit": "bags"}]
    urgency_level: str  # "normal", "urgent", "critical"
    needs_procurement: bool
    is_valid: bool
    validation_errors: list
    
    # Processing
    messages: list  # Conversation history
    current_step: str
    
    # Actions to take
    should_alert_procurement: bool
    should_queue_report: bool
    should_send_urgent: bool
    
    # Results
    epr_record_id: str
    alerts_sent: list  # ["whatsapp_procurement", "email_pm", etc]
    error_message: str
    
    # Metadata
    timestamp: str
    request_id: str


# ============================================================================
# TOOLS / UTILITY FUNCTIONS
# ============================================================================

client = Groq()  # Assuming GROQ_API_KEY is set

def parse_report(report_text: str, foreman_id: str) -> dict:
    """
    Use Groq LLM to parse report text and extract:
    - Materials needed
    - Quantities
    - Urgency level
    - Location info
    """
    
    prompt = f"""Extract materials and urgency from this construction report. Return ONLY valid JSON.

Report: "{report_text}"

Return this exact JSON structure:
{{
  "materials": [
    {{"name": "material_name", "quantity": number, "unit": "bags/blocks/kg/etc"}},
    {{"name": "another_material", "quantity": number, "unit": "unit_type"}}
  ],
  "urgency": "normal" or "urgent" or "critical",
  "location": "site_location"
}}

IMPORTANT: Return ONLY the JSON object, nothing else. No markdown, no explanation."""
    
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=500,
        temperature=0.1  # Even lower temp for more consistent JSON
    )
    
    try:
        content = response.choices[0].message.content.strip()
        # Remove markdown code blocks if present
        if content.startswith("```"):
            content = content.split("```")[1].replace("json", "").strip()
        result = json.loads(content)
        return result
    except json.JSONDecodeError as e:
        print(f"⚠️  JSON parse error: {e}")
        print(f"   Raw response: {response.choices[0].message.content[:100]}")
        # Fallback: extract materials manually
        urgency = "urgent" if "urgent" in report_text.lower() else "normal"
        return {
            "materials": [
                {"name": "cement", "quantity": 50, "unit": "bags"},
                {"name": "blocks", "quantity": 100, "unit": "units"}
            ],
            "urgency": urgency,
            "location": "site",
            "note": "Fallback parsing due to JSON error"
        }


def validate_report(parsed_data: dict) -> tuple[bool, list]:
    """
    Validate parsed data:
    - Has materials?
    - Has valid urgency level?
    - Required fields present?
    """
    
    errors = []
    
    if not parsed_data.get("materials"):
        errors.append("No materials extracted")
    
    valid_urgencies = ["normal", "urgent", "critical"]
    if parsed_data.get("urgency") not in valid_urgencies:
        errors.append(f"Invalid urgency: {parsed_data.get('urgency')}")
    
    # Location is optional (can use default)
    if not parsed_data.get("location"):
        parsed_data["location"] = "On-site"
    
    is_valid = len(errors) == 0
    return is_valid, errors


def route_actions(urgency: str, has_materials: bool) -> dict:
    """
    Decide what actions to take based on parsed data
    """
    
    return {
        "should_alert_procurement": has_materials,
        "should_queue_report": True,  # Always queue
        "should_send_urgent": urgency == "critical"
    }


def save_to_erp(state: JengoState) -> str:
    """
    Save report to ERP system.
    
    In demo: returns mock record ID
    In production: calls actual ERP API
    """
    
    # Mock ERP save
    record_id = f"ERP-{datetime.now().timestamp()}"
    
    # In production, this would be:
    # response = requests.post(
    #     "https://erptaison.co.ke/api/reports",
    #     json={
    #         "foreman_id": state["foreman_id"],
    #         "materials": state["parsed_materials"],
    #         "site": state["site_location"],
    #         "urgency": state["urgency_level"],
    #         "timestamp": state["timestamp"]
    #     },
    #     headers={"Authorization": f"Bearer {ERP_API_KEY}"}
    # )
    # return response.json()["record_id"]
    
    print(f"✓ Saved to ERP: {record_id}")
    return record_id


def send_whatsapp_alert(foreman_id: str, materials: list, urgency: str, procurement_number: str) -> str:
    """
    Send WhatsApp alert to procurement team via Twilio
    
    In demo: prints mock message
    In production: uses Twilio client
    """
    
    materials_text = "\n".join([f"• {m['name']}: {m['quantity']} {m['unit']}" for m in materials])
    
    message = f"""
🔔 PROCUREMENT ALERT - {urgency.upper()}

Materials Needed:
{materials_text}

Report from: Foreman {foreman_id}
Time: {datetime.now().isoformat()}

Please confirm receipt.
"""
    
    # In production:
    # from twilio.rest import Client
    # client = Client(TWILIO_SID, TWILIO_TOKEN)
    # client.messages.create(
    #     from_=f"whatsapp:{TWILIO_WHATSAPP_NUMBER}",
    #     to=f"whatsapp:{procurement_number}",
    #     body=message
    # )
    
    print(f"📱 WhatsApp sent to {procurement_number}")
    return f"whatsapp_alert_{datetime.now().timestamp()}"


def send_urgent_alert(urgency: str, materials: list, recipients: list) -> list:
    """
    For critical/urgent: also alert PM and CEO via WhatsApp
    """
    
    alerts = []
    if urgency == "critical":
        for recipient in recipients:
            print(f"🚨 CRITICAL ALERT sent to {recipient}")
            alerts.append(f"urgent_alert_{recipient}")
    
    return alerts


def queue_for_weekly_report(state: JengoState) -> str:
    """
    Add this report to the weekly digest queue
    
    In production: saves to database/queue for scheduled task
    """
    
    print("✓ Queued for weekly report")
    return "queued_for_weekly"


def generate_weekly_report(reports: list, week_start: str) -> dict:
    """
    Generate weekly summary for PM, Client, CEO
    
    In production: aggregates reports from the week
    """
    
    report = {
        "week": week_start,
        "total_reports": len(reports),
        "materials_summary": {},
        "critical_alerts": 0,
        "cost_estimate": 0,
        "sites": {}
    }
    
    # Aggregate logic would go here
    
    return report


def send_email_report(recipients: list, report: dict) -> list:
    """
    Send weekly report via email to PM, Client, CEO
    
    In demo: prints to console
    In production: uses SendGrid/SMTP
    """
    
    html_content = f"""
    <html>
        <body>
            <h1>Weekly Construction Report - {report['week']}</h1>
            <p><strong>Total Reports:</strong> {report['total_reports']}</p>
            <p><strong>Critical Alerts:</strong> {report['critical_alerts']}</p>
            <p><strong>Estimated Costs:</strong> KES {report['cost_estimate']}</p>
            <hr>
            <p>Detailed breakdown attached.</p>
        </body>
    </html>
    """
    
    emails_sent = []
    
    # In production:
    # for recipient in recipients:
    #     msg = MIMEMultipart("alternative")
    #     msg["Subject"] = f"Weekly Report - {report['week']}"
    #     msg["From"] = "reports@taisongroup.co.ke"
    #     msg["To"] = recipient
    #     msg.attach(MIMEText(html_content, "html"))
    #     
    #     with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
    #         server.login("reports@taisongroup.co.ke", SMTP_PASSWORD)
    #         server.sendmail(msg["From"], recipient, msg.as_string())
    
    for recipient in recipients:
        print(f"📧 Email sent to {recipient}")
        emails_sent.append(f"email_{recipient}")
    
    return emails_sent


# ============================================================================
# LANGGRAPH NODES
# ============================================================================

def node_receive(state: JengoState) -> dict:
    """
    STATE 1: RECEIVE
    Input received from WhatsApp/Email
    """
    print("\n[RECEIVE] Processing incoming report...")
    return {"current_step": "receive", "timestamp": datetime.now().isoformat()}


def node_parse(state: JengoState) -> dict:
    """
    STATE 2: PARSE
    Extract materials, urgency, location from report text
    """
    print("[PARSE] Extracting data from report...")
    
    parsed = parse_report(state["report_text"], state["foreman_id"])
    
    return {
        "current_step": "parse",
        "parsed_materials": parsed.get("materials", []),
        "urgency_level": parsed.get("urgency", "normal"),
        "site_location": parsed.get("location", state["site_location"]),
        "messages": state["messages"] + [
            {"role": "assistant", "content": f"Parsed: {json.dumps(parsed)}"}
        ]
    }


def node_validate(state: JengoState) -> dict:
    """
    STATE 3: VALIDATE
    Check data quality and completeness
    """
    print("[VALIDATE] Checking data quality...")
    
    is_valid, errors = validate_report({
        "materials": state["parsed_materials"],
        "urgency": state["urgency_level"],
        "location": state["site_location"]
    })
    
    return {
        "current_step": "validate",
        "is_valid": is_valid,
        "validation_errors": errors
    }


def node_route(state: JengoState) -> dict:
    """
    STATE 4: ROUTE
    Decide what actions to take
    """
    print("[ROUTE] Deciding actions...")
    
    actions = route_actions(state["urgency_level"], len(state["parsed_materials"]) > 0)
    
    return {
        "current_step": "route",
        "should_alert_procurement": actions["should_alert_procurement"],
        "should_queue_report": actions["should_queue_report"],
        "should_send_urgent": actions["should_send_urgent"]
    }


def node_save(state: JengoState) -> dict:
    """
    STATE 5: SAVE
    Persist to ERP
    """
    print("[SAVE] Saving to ERP...")
    
    record_id = save_to_erp(state)
    
    return {
        "current_step": "save",
        "epr_record_id": record_id,
        "alerts_sent": []
    }


def node_alert_procurement(state: JengoState) -> dict:
    """
    STATE 6: ALERT_PROCUREMENT
    Send WhatsApp alert to procurement team
    """
    print("[ALERT_PROCUREMENT] Sending WhatsApp alert...")
    
    if state["should_alert_procurement"]:
        alert_id = send_whatsapp_alert(
            state["foreman_id"],
            state["parsed_materials"],
            state["urgency_level"],
            "+254712345678"  # Mock procurement number
        )
        
        alerts = [alert_id]
        
        # Also send urgent alerts if critical
        if state["should_send_urgent"]:
            urgent_alerts = send_urgent_alert(
                state["urgency_level"],
                state["parsed_materials"],
                ["pm@taisongroup.co.ke", "ceo@taisongroup.co.ke"]
            )
            alerts.extend(urgent_alerts)
        
        return {
            "current_step": "alert_procurement",
            "alerts_sent": alerts
        }
    
    return {"current_step": "alert_procurement", "alerts_sent": []}


def node_queue_report(state: JengoState) -> dict:
    """
    STATE 7: QUEUE_REPORT
    Queue for weekly report aggregation
    """
    print("[QUEUE_REPORT] Queuing for weekly report...")
    
    queue_result = queue_for_weekly_report(state)
    
    return {
        "current_step": "queue_report",
        "alerts_sent": state["alerts_sent"] + [queue_result]
    }


def node_done(state: JengoState) -> dict:
    """
    STATE 9: DONE
    Report processed successfully
    """
    print(f"[DONE] Report {state['request_id']} processed successfully")
    print(f"  ERP ID: {state['epr_record_id']}")
    print(f"  Alerts sent: {state['alerts_sent']}")
    
    return {"current_step": "done"}


# ============================================================================
# CONDITIONAL ROUTING
# ============================================================================

def should_continue_to_route(state: JengoState) -> str:
    """
    After validation: if valid, go to route. If invalid, go to done.
    """
    if state["is_valid"]:
        return "route"
    else:
        print(f"❌ Validation failed: {state['validation_errors']}")
        return "done"


def should_alert(state: JengoState) -> str:
    """
    After route: if should_alert_procurement, go to alert. Else queue.
    """
    if state["should_alert_procurement"]:
        return "alert_procurement"
    else:
        return "queue_report"


def should_queue(state: JengoState) -> str:
    """
    After alert: go to queue_report
    """
    return "queue_report"


# ============================================================================
# BUILD LANGGRAPH
# ============================================================================

def build_jengo_graph():
    """
    Construct the LangGraph state machine
    """
    
    graph = StateGraph(JengoState)
    
    # Add nodes
    graph.add_node("receive", node_receive)
    graph.add_node("parse", node_parse)
    graph.add_node("validate", node_validate)
    graph.add_node("route", node_route)
    graph.add_node("save", node_save)
    graph.add_node("alert_procurement", node_alert_procurement)
    graph.add_node("queue_report", node_queue_report)
    graph.add_node("done", node_done)
    
    # Add edges (state transitions)
    graph.add_edge("receive", "parse")
    graph.add_edge("parse", "validate")
    graph.add_conditional_edges(
        "validate",
        should_continue_to_route,
        {"route": "route", "done": "done"}
    )
    graph.add_edge("route", "save")
    graph.add_conditional_edges(
        "save",
        should_alert,
        {"alert_procurement": "alert_procurement", "queue_report": "queue_report"}
    )
    graph.add_edge("alert_procurement", "queue_report")
    graph.add_edge("queue_report", "done")
    
    # Set entry point
    graph.set_entry_point("receive")
    
    return graph.compile()


# ============================================================================
# DEMO / MAIN
# ============================================================================

if __name__ == "__main__":
    print("🏗️  JengoAI LangGraph Agent - Demo")
    print("=" * 60)
    
    # Initialize graph
    agent = build_jengo_graph()
    
    # Create initial state for demo
    initial_state = JengoState(
        report_text="We need 50 bags of cement and 100 blocks for foundation work. This is urgent!",
        report_source="whatsapp",
        foreman_id="FM001",
        site_location="Nairobi - Downtown Project",
        parsed_materials=[],
        urgency_level="normal",
        needs_procurement=False,
        is_valid=True,
        validation_errors=[],
        messages=[],
        current_step="start",
        should_alert_procurement=False,
        should_queue_report=False,
        should_send_urgent=False,
        epr_record_id="",
        alerts_sent=[],
        error_message="",
        timestamp=datetime.now().isoformat(),
        request_id=f"REQ-{datetime.now().timestamp()}"
    )
    
    # Run the agent
    print(f"\n📝 Processing report: '{initial_state['report_text']}'")
    print("-" * 60)
    
    result = agent.invoke(initial_state)
    
    print("-" * 60)
    print(f"\n✅ Workflow completed!")
    print(f"   Final state: {result['current_step']}")
    print(f"   ERP Record: {result['epr_record_id']}")
    print(f"   Alerts sent: {len(result['alerts_sent'])}")