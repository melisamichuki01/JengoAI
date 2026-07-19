"""
webhook.py
----------
FastAPI server that receives incoming WhatsApp messages from Twilio
and drives the agent via agent_whatsapp.py.

Run:
    uvicorn webhook:app --reload --port 8000

Expose locally for Twilio to reach it (during development):
    ngrok http 8000

Then set your Twilio WhatsApp sandbox "When a message comes in" webhook to:
    https://<your-ngrok-subdomain>.ngrok.io/webhook
"""

import os
from fastapi import FastAPI, Form
from fastapi.responses import PlainTextResponse
from dotenv import load_dotenv
from twilio.twiml.messaging_response import MessagingResponse

from agent_whatsapp import process_incoming

load_dotenv()

app = FastAPI(title="JengoAI WhatsApp Webhook")


@app.get("/")
def health_check():
    return {"status": "JengoAI webhook is running"}


@app.post("/webhook")
async def whatsapp_webhook(From: str = Form(...), Body: str = Form(...)):
    """
    Twilio POSTs here for every inbound WhatsApp message.
    `From` looks like 'whatsapp:+2547XXXXXXXX', `Body` is the message text.
    """
    phone = From.replace("whatsapp:", "")
    incoming_text = Body

    try:
        reply_text = process_incoming(phone, incoming_text)
    except Exception as e:
        reply_text = f"Something went wrong processing that update: {e}"

    twiml = MessagingResponse()
    twiml.message(reply_text)
    return PlainTextResponse(content=str(twiml), media_type="application/xml")