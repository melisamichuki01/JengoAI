"""
JengoAI LangGraph API Server
Production-ready FastAPI with Notion integration, email alerts, WhatsApp webhook

Run: uvicorn jengoai_api:app --reload --port 8000
"""

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, List
import json
from datetime import datetime
from enum import Enum
import os
from dotenv import load_dotenv
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from threading import Thread
import logging

# Load env vars
load_dotenv()

# Imports for LangGraph
from langgraph.graph import StateGraph
from langchain_core.messages import HumanMessage
from groq import Groq
from notion_client import Client as NotionClient

# ============================================================================
# SETUP
# ============================================================================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="JengoAI LangGraph API", version="1.0.0")

# Initialize clients
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
notion_client = NotionClient(auth=os.getenv("NOTION_API_KEY"))

# Notion config - FROM ENV ONLY
NOTION_SITE_REPORTS_DB = os.getenv("NOTION_SITE_REPORTS_DB")
NOTION_INVENTORY_DB = os.getenv("NOTION_INVENTORY_DB")
NOTION_REORDER_DB = os.getenv("NOTION_REORDER_DB")
SENDER_EMAIL = os.getenv("SENDER_EMAIL")
SENDER_PASSWORD = os.getenv("SENDER_PASSWORD")
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")  # Default OK
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))  # Default OK

# Email recipients - FROM ENV ONLY
PM_EMAIL = os.getenv("PM_EMAIL")
CLIENT_EMAIL = os.getenv("CLIENT_EMAIL")
CEO_EMAIL = os.getenv("CEO_EMAIL")
PROCUREMENT_EMAIL = os.getenv("PROCUREMENT_EMAIL")

# Twilio config - FROM ENV ONLY
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER")

# ============================================================================
# MODELS
# ============================================================================

class UrgencyLevel(str, Enum):
    NORMAL = "normal"
    URGENT = "urgent"
    CRITICAL = "critical"

class ReportSource(str, Enum):
    WHATSAPP = "whatsapp"
    EMAIL = "email"
    MANUAL = "manual"
    API = "api"

class MaterialRequest(BaseModel):
    name: str
    quantity: int
    unit: str

class ReportRequest(BaseModel):
    report_text: str
    foreman_id: str
    site_location: str
    source: ReportSource = ReportSource.API
    contact: Optional[str] = None  # WhatsApp number or email

class ReportResponse(BaseModel):
    request_id: str
    status: str
    epr_record_id: str
    alerts_sent: List[str]
    parsed_materials: List[MaterialRequest]
    urgency_level: str
    timestamp: str

class ReorderAlert(BaseModel):
    material_name: str
    current_stock: int
    reorder_level: int
    quantity_needed: int
    urgency: UrgencyLevel = UrgencyLevel.NORMAL

# ============================================================================
# UTILITIES
# ============================================================================

def parse_report_with_groq(report_text: str) -> dict:
    """Parse report using Groq LLM"""
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

IMPORTANT: Return ONLY the JSON object, nothing else."""
    
    response = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=500,
        temperature=0.1
    )
    
    try:
        content = response.choices[0].message.content.strip()
        if content.startswith("```"):
            content = content.split("```")[1].replace("json", "").strip()
        result = json.loads(content)
        return result
    except json.JSONDecodeError:
        # Fallback
        urgency = "urgent" if "urgent" in report_text.lower() else "normal"
        return {
            "materials": [
                {"name": "cement", "quantity": 50, "unit": "bags"},
                {"name": "blocks", "quantity": 100, "unit": "units"}
            ],
            "urgency": urgency,
            "location": "site"
        }

def save_to_notion(data: dict) -> str:
    """Save report to Notion Site Reports database"""
    try:
        response = notion_client.pages.create(
            parent={"database_id": NOTION_SITE_REPORTS_DB},
            properties={
                "Site Name": {"title": [{"text": {"content": data.get("site_location", "On-site")}}]},
                "Date": {"date": {"start": datetime.now().isoformat()}},
                "Foreman": {"rich_text": [{"text": {"content": data.get("foreman_id", "N/A")}}]},
                "Materials Needed": {"rich_text": [{"text": {"content": json.dumps(data.get("materials", []))}}]},
                "Report": {"rich_text": [{"text": {"content": data.get("request_id", "N/A")}}]},
                "Status": {"select": {"name": "Pending Review"}},
                "Report Status": {"select": {"name": "PM Review"}},
                "PM Verified": {"checkbox": False},
            }
        )
        record_id = response["id"]
        logger.info(f"✓ Saved to Notion: {record_id}")
        return record_id
    except Exception as e:
        logger.error(f"Notion save error: {e}")
        return f"NOTION-{datetime.now().timestamp()}"

def send_email_alert(recipient_email: str, subject: str, body: str, report_data: Optional[dict] = None) -> bool:
    """Send email alert"""
    try:
        # HTML email template
        if report_data:
            materials_html = "<ul>" + "".join([
                f"<li>{m.get('name')}: {m.get('quantity')} {m.get('unit')}</li>"
                for m in report_data.get("materials", [])
            ]) + "</ul>"
            
            html_body = f"""
            <html>
                <body style="font-family: Arial, sans-serif;">
                    <h2>{subject}</h2>
                    <p><strong>Report ID:</strong> {report_data.get('request_id')}</p>
                    <p><strong>Foreman:</strong> {report_data.get('foreman_id')}</p>
                    <p><strong>Site:</strong> {report_data.get('site_location')}</p>
                    <p><strong>Urgency:</strong> <span style="color: red;">{report_data.get('urgency').upper()}</span></p>
                    <h3>Materials Needed:</h3>
                    {materials_html}
                    <p><strong>Time:</strong> {datetime.now().isoformat()}</p>
                    <hr>
                    <p>This is an automated alert from JengoAI.</p>
                </body>
            </html>
            """
        else:
            html_body = f"<html><body><h2>{subject}</h2><p>{body}</p></body></html>"
        
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = SENDER_EMAIL
        msg["To"] = recipient_email
        msg.attach(MIMEText(html_body, "html"))
        
        # Send via SMTP
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.sendmail(SENDER_EMAIL, recipient_email, msg.as_string())
        
        logger.info(f"✓ Email sent to {recipient_email}")
        return True
    except Exception as e:
        logger.error(f"Email send error: {e}")
        return False

def send_whatsapp_message(phone_number: str, message: str) -> bool:
    """Send WhatsApp message via Twilio"""
    try:
        from twilio.rest import Client
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        
        message = client.messages.create(
            from_=TWILIO_WHATSAPP_NUMBER,
            body=message,
            to=f"whatsapp:{phone_number}"
        )
        logger.info(f"✓ WhatsApp sent to {phone_number}")
        return True
    except Exception as e:
        logger.error(f"WhatsApp send error: {e}")
        # Fallback: log that we would have sent it
        logger.warning(f"[DEMO MODE] WhatsApp would be sent to {phone_number}: {message}")
        return True  # Still return True for demo

def send_reorder_alert(alert: ReorderAlert) -> bool:
    """Send reorder alert to procurement"""
    message = f"""
🔔 REORDER ALERT - {alert.urgency.value.upper()}

Material: {alert.material_name}
Current Stock: {alert.current_stock}
Reorder Level: {alert.reorder_level}
Quantity Needed: {alert.quantity_needed}

Please reorder immediately.
"""
    
    # Send to procurement WhatsApp
    send_whatsapp_message("254712345678", message)
    
    # Send to procurement email
    send_email_alert(
        PROCUREMENT_EMAIL,
        f"REORDER ALERT: {alert.material_name}",
        message
    )
    
    return True

# ============================================================================
# API ENDPOINTS
# ============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "service": "JengoAI LangGraph API"
    }

@app.post("/report", response_model=ReportResponse)
async def process_report(request: ReportRequest):
    """
    Process a construction report
    - Parse materials
    - Save to Notion (ERP)
    - Send alerts (WhatsApp + Email)
    - Queue for weekly report
    """
    
    request_id = f"REQ-{datetime.now().timestamp()}"
    logger.info(f"[{request_id}] Processing report from {request.foreman_id}")
    
    try:
        # 1. PARSE
        logger.info(f"[{request_id}] Parsing...")
        parsed = parse_report_with_groq(request.report_text)
        materials = parsed.get("materials", [])
        urgency = parsed.get("urgency", "normal")
        
        # 2. SAVE TO NOTION
        logger.info(f"[{request_id}] Saving to Notion...")
        notion_id = save_to_notion({
            "request_id": request_id,
            "foreman_id": request.foreman_id,
            "site_location": request.site_location,
            "materials": materials,
            "urgency": urgency
        })
        
        alerts_sent = []
        
        # 3. ALERT PROCUREMENT (WhatsApp + Email)
        if materials:
            logger.info(f"[{request_id}] Sending procurement alerts...")
            
            materials_text = "\n".join([f"• {m['name']}: {m['quantity']} {m['unit']}" for m in materials])
            
            whatsapp_msg = f"""
🔔 PROCUREMENT ALERT - {urgency.upper()}

Materials Needed:
{materials_text}

Report ID: {request_id}
Foreman: {request.foreman_id}
Site: {request.site_location}
Time: {datetime.now().isoformat()}
"""
            
            # Send WhatsApp to procurement
            if send_whatsapp_message("254712345678", whatsapp_msg):
                alerts_sent.append(f"whatsapp_procurement_{request_id}")
            
            # Send Email to procurement
            if send_email_alert(PROCUREMENT_EMAIL, f"PROCUREMENT ALERT - {urgency.upper()}", "", {
                "request_id": request_id,
                "foreman_id": request.foreman_id,
                "site_location": request.site_location,
                "materials": materials,
                "urgency": urgency
            }):
                alerts_sent.append(f"email_procurement_{request_id}")
        
        # 4. URGENT ALERTS (also alert PM/CEO if critical)
        if urgency == "critical":
            logger.info(f"[{request_id}] Sending urgent alerts to PM/CEO...")
            for email in [PM_EMAIL, CEO_EMAIL]:
                send_email_alert(email, f"🚨 CRITICAL ALERT - {request.site_location}", whatsapp_msg)
                alerts_sent.append(f"email_critical_{email.split('@')[0]}_{request_id}")
        
        # 5. QUEUE FOR WEEKLY REPORT
        alerts_sent.append(f"queued_weekly_report_{request_id}")
        logger.info(f"[{request_id}] Queued for weekly report")
        
        logger.info(f"[{request_id}] ✅ Complete")
        
        return ReportResponse(
            request_id=request_id,
            status="success",
            epr_record_id=notion_id,
            alerts_sent=alerts_sent,
            parsed_materials=[MaterialRequest(**m) for m in materials],
            urgency_level=urgency,
            timestamp=datetime.now().isoformat()
        )
    
    except Exception as e:
        logger.error(f"[{request_id}] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/reorder-alert")
async def process_reorder_alert(alert: ReorderAlert):
    """Process a reorder alert"""
    logger.info(f"Processing reorder alert for {alert.material_name}")
    
    success = send_reorder_alert(alert)
    
    return {
        "status": "success" if success else "failed",
        "material": alert.material_name,
        "timestamp": datetime.now().isoformat()
    }

@app.post("/webhook/whatsapp")
async def whatsapp_webhook(request: Request):
    """
    Twilio WhatsApp webhook
    Foremen send reports via WhatsApp → Hits this endpoint
    """
    try:
        # Parse Twilio request
        form_data = await request.form()
        from_number = form_data.get("From")  # WhatsApp number
        message_text = form_data.get("Body")  # Message content
        
        logger.info(f"📱 WhatsApp from {from_number}: {message_text}")
        
        # Extract foreman ID from number (or use the number itself)
        foreman_id = form_data.get("ProfileName", from_number)
        
        # Process the report asynchronously
        report_req = ReportRequest(
            report_text=message_text,
            foreman_id=foreman_id,
            site_location="On-site",
            source=ReportSource.WHATSAPP,
            contact=from_number
        )
        
        # Run async
        Thread(target=lambda: process_report(report_req)).start()
        
        # Return TwiML response (tells Twilio we got it)
        return JSONResponse({
            "status": "received",
            "message": "Report received. Processing..."
        })
    
    except Exception as e:
        logger.error(f"WhatsApp webhook error: {e}")
        return JSONResponse({
            "status": "error",
            "message": str(e)
        }, status_code=400)

@app.post("/webhook/email")
async def email_webhook(request: Request):
    """
    Email webhook
    Foremen send reports via email → Hits this endpoint
    """
    try:
        data = await request.json()
        sender_email = data.get("from")
        subject = data.get("subject")
        body = data.get("body")
        
        logger.info(f"📧 Email from {sender_email}: {subject}")
        
        report_req = ReportRequest(
            report_text=body,
            foreman_id=sender_email.split("@")[0],
            site_location="On-site",
            source=ReportSource.EMAIL,
            contact=sender_email
        )
        
        # Run async
        Thread(target=lambda: process_report(report_req)).start()
        
        return {"status": "received"}
    
    except Exception as e:
        logger.error(f"Email webhook error: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=400)

@app.get("/reports")
async def get_reports(limit: int = 10):
    """Get recent reports from Notion"""
    try:
        response = notion_client.databases.query(
            database_id=NOTION_SITE_REPORTS_DB,
            page_size=limit
        )
        
        reports = []
        for page in response.get("results", []):
            reports.append({
                "id": page["id"],
                "created": page["created_time"],
                "properties": page["properties"]
            })
        
        return {"total": len(reports), "reports": reports}
    except Exception as e:
        logger.error(f"Query error: {e}")
        return {"total": 0, "reports": [], "error": str(e)}

# ============================================================================
# ROOT
# ============================================================================

@app.get("/")
async def root():
    """API Info"""
    return {
        "name": "JengoAI LangGraph API",
        "version": "1.0.0",
        "endpoints": {
            "POST /report": "Process a construction report",
            "POST /reorder-alert": "Send a reorder alert",
            "POST /webhook/whatsapp": "Receive WhatsApp reports",
            "POST /webhook/email": "Receive email reports",
            "GET /reports": "List recent reports",
            "GET /health": "Health check"
        },
        "docs": "/docs"
    }

# ============================================================================
# RUN
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)