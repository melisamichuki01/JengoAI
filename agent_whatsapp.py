"""
agent_whatsapp.py
------------------
Same agentic loop as agent_agentic.py, adapted so the human-in-the-loop
confirmation works over WhatsApp instead of a terminal.

The problem this solves: run_agent() in agent_agentic.py pauses on
input(), which blocks the whole process waiting for a keypress. A
Twilio webhook can't do that, each WhatsApp message arrives as its
own separate HTTP request. So the confirmation step has to survive
across two requests instead of one blocking call.

How it works:
1. Foreman sends a message -> new session created, extract_site_update
   is called, result is sent back as a WhatsApp question ("Is this
   correct?"), and the loop PAUSES. The session (message history) is
   held in SESSIONS, keyed by phone number.
2. Foreman replies -> we look up their session, interpret the reply as
   a confirmation or a correction, and either continue the loop
   (fetch_site_history -> update_inventory -> generate_report -> save)
   or re-extract with the correction and ask again.

SESSIONS is in-memory, which is fine for a workshop demo and a single
web process, but will not survive a restart or work across multiple
server instances. For production, swap the dict for Redis or a small
database table keyed by phone number.
"""

import os
import json
import groq
from groq import Groq
from dotenv import load_dotenv
from tools import TOOL_SCHEMAS, TOOL_FUNCTIONS

load_dotenv()

MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
MAX_RETRIES = 3
MAX_TOOL_CALL_RETRIES = 2  # separate from confirmation retries; this is for malformed tool-call args

SYSTEM_PROMPT = """You are JengoAI, an intelligent construction site reporting agent.

Your job is to process a foreman's daily site update and:
1. Call extract_site_update to parse the raw message
2. Call fetch_site_history with the site_name to get historical context
3. Call update_inventory_for_material once per material in materials_used
4. Call generate_site_report — you MUST pass the history_summary from fetch_site_history into the history_summary parameter so the report shows progress trends
5. Call save_report_to_notion to save the final report

Always follow this exact order. After saving to Notion, your task is complete.
If extraction confidence is low, stop immediately and say why.
Call update_inventory_for_material separately for EACH material listed.
CRITICAL: Always pass history_summary to generate_site_report. Never leave it empty if fetch_site_history returned data."""

# phone_number -> session dict
SESSIONS = {}

CONFIRM_WORDS = {
    "y", "yes", "yeah", "yeap", "yep", "yup", "ya", "yea",
    "ndio", "sawa", "sahihi", "correct", "ok", "okay", "sure", "confirm", "confirmed",
}
REJECT_WORDS = {"n", "no", "nah", "nope", "hapana", "wrong", "si sahihi"}


def _client():
    return Groq(api_key=os.environ.get("GROQ_API_KEY"))


def _create_with_retry(client, messages: list):
    """
    Wraps client.chat.completions.create with a retry for Groq's
    400 tool_use_failed error, which happens when the model emits
    tool-call arguments that don't match the declared schema, most
    commonly numbers sent as strings (e.g. "60" instead of 60).

    On failure, appends a corrective system message telling the model
    exactly what went wrong and retries once. This mutates `messages`
    in place so the correction stays in history for the rest of the
    conversation, not just this one call.
    """
    last_error = None

    for attempt in range(MAX_TOOL_CALL_RETRIES + 1):
        try:
            return client.chat.completions.create(
                model=MODEL,
                messages=messages,
                tools=TOOL_SCHEMAS,
                tool_choice="auto",
                temperature=0.1,
            )
        except groq.BadRequestError as e:
            last_error = e
            body = getattr(e, "body", None) or {}
            error_info = body.get("error", {}) if isinstance(body, dict) else {}
            code = error_info.get("code")

            if code != "tool_use_failed" or attempt == MAX_TOOL_CALL_RETRIES:
                raise

            failed_generation = error_info.get("failed_generation", "")
            messages.append({
                "role": "system",
                "content": (
                    "Your previous tool call failed schema validation: "
                    f"{error_info.get('message', 'invalid arguments')}. "
                    f"You sent: {failed_generation}. "
                    "Numeric fields (quantity_used, progress_percentage, etc.) "
                    "must be JSON numbers, not strings. For example use "
                    "60 not \"60\", and 0 not \"0\". Retry the same tool call "
                    "with correctly typed arguments."
                ),
            })

    raise last_error


def _format_confirmation_question(extracted: dict) -> str:
    blockers = ", ".join(extracted.get("blockers", [])) or "None"
    materials = extracted.get("materials_used", [])
    materials_str = ", ".join(
        f"{m.get('name')} ({m.get('quantity','?')} {m.get('unit','units')})" for m in materials
    ) or "None reported"

    return (
        f"Please confirm this is correct:\n\n"
        f"Site: {extracted.get('site_name', 'Unknown')}\n"
        f"Foreman: {extracted.get('foreman_name', 'Unknown')}\n"
        f"Progress: {extracted.get('progress_percentage', 'N/A')}%\n"
        f"Blockers: {blockers}\n"
        f"Materials used: {materials_str}\n"
        f"Materials needed: {extracted.get('materials_needed', 'None')}\n"
        f"Labor needed: {extracted.get('labor_needed', 'None')}\n"
        f"Safety: {extracted.get('safety_incidents', 'None')}\n\n"
        f"Reply YES to confirm, or describe what's wrong (e.g. "
        f"\"progress is 45% not 60%\")."
    )


def _run_tool_call(tool_call) -> dict:
    name = tool_call.function.name
    args = json.loads(tool_call.function.arguments)
    result = TOOL_FUNCTIONS[name](**args)
    return result


def start_session(phone: str, raw_message: str) -> str:
    """
    Kick off a new agent session for this phone number.
    Runs until the agent calls extract_site_update, then pauses and
    returns the confirmation question to send back over WhatsApp.
    """
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Process this site update: {raw_message}"},
    ]

    client = _client()
    response = _create_with_retry(client, messages)
    message = response.choices[0].message

    if not message.tool_calls:
        # Shouldn't happen given the system prompt, but handle gracefully
        SESSIONS.pop(phone, None)
        return "Sorry, I couldn't process that update. Please resend with site, progress, and any blockers."

    tool_call = message.tool_calls[0]  # should be extract_site_update
    messages.append(message)
    result = _run_tool_call(tool_call)

    if result.get("confidence") == "low":
        SESSIONS.pop(phone, None)
        return "That message was unclear (low confidence). Please resend with more detail, e.g. site name, progress %, and blockers."

    messages.append({
        "role": "tool",
        "tool_call_id": tool_call.id,
        "content": json.dumps(result),
    })

    SESSIONS[phone] = {
        "messages": messages,
        "state": "awaiting_confirmation",
        "raw_message": raw_message,
        "retries": 0,
    }

    return _format_confirmation_question(result)


def _continue_after_confirmation(phone: str) -> str:
    """
    Confirmation received. Let the agent proceed automatically through
    fetch_site_history -> update_inventory -> generate_report -> save,
    with no further human checkpoints, until it finishes.
    """
    session = SESSIONS[phone]
    messages = session["messages"]
    client = _client()

    max_iterations = 10
    report_text = None
    notion_url = None

    for _ in range(max_iterations):
        response = _create_with_retry(client, messages)
        message = response.choices[0].message

        if not message.tool_calls:
            break

        messages.append(message)
        for tool_call in message.tool_calls:
            result = _run_tool_call(tool_call)
            if tool_call.function.name == "generate_site_report":
                report_text = result.get("report_text")
            if tool_call.function.name == "save_report_to_notion":
                notion_url = result.get("notion_url")
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": json.dumps(result),
            })

    SESSIONS.pop(phone, None)

    return "Your report has been received. Thank you."


def _retry_extraction(phone: str, correction: str) -> str:
    session = SESSIONS[phone]
    session["retries"] += 1

    if session["retries"] >= MAX_RETRIES:
        SESSIONS.pop(phone, None)
        return "Too many correction attempts. Please resend the full update as a fresh message."

    corrected_raw = f"{session['raw_message']}\n\nCorrection from supervisor: {correction}"
    result = TOOL_FUNCTIONS["extract_site_update"](raw_message=corrected_raw)

    if result.get("confidence") == "low":
        SESSIONS.pop(phone, None)
        return "Still unclear after correction. Please resend the full update as a fresh message."

    # Replace the last tool result in the message history with the corrected extraction
    session["messages"][-1] = {
        "role": "tool",
        "tool_call_id": session["messages"][-1]["tool_call_id"],
        "content": json.dumps(result),
    }
    session["raw_message"] = corrected_raw

    return _format_confirmation_question(result)


def _classify_confirmation(text: str) -> str:
    """
    Classifies a free-form WhatsApp reply to the confirmation question as
    'confirm', 'reject', or 'correction'. Uses the LLM rather than a fixed
    word list, so any phrasing (yeah, yeap, sawa, nope, "that's right",
    Swahili/English mix, etc.) is understood without maintaining a list.

    Falls back to simple keyword matching only if the classification call
    itself fails (e.g. network issue), so a reply is never silently dropped.
    """
    client = _client()
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You classify a short WhatsApp reply to a confirmation "
                        "question. The person was asked to confirm extracted "
                        "construction site report data is correct. "
                        "Reply with exactly one word:\n"
                        "CONFIRM - they are agreeing it's correct, in any "
                        "phrasing or language (e.g. yes, yeah, yeap, sawa, "
                        "ndio, correct, ok, sounds good)\n"
                        "REJECT - they are saying it's wrong without giving "
                        "specifics (e.g. no, hapana, wrong, that's not right)\n"
                        "CORRECTION - they are describing what needs to change\n"
                        "Respond with only one word: CONFIRM, REJECT, or CORRECTION."
                    ),
                },
                {"role": "user", "content": text},
            ],
            temperature=0,
            max_tokens=5,
        )
        label = response.choices[0].message.content.strip().upper()
        if "CONFIRM" in label:
            return "confirm"
        if "REJECT" in label:
            return "reject"
        return "correction"
    except Exception:
        text_clean = text.strip().lower()
        if text_clean in CONFIRM_WORDS or text_clean.startswith("yes"):
            return "confirm"
        if text_clean in REJECT_WORDS:
            return "reject"
        return "correction"


def process_incoming(phone: str, text: str) -> str:
    """
    Entry point called by the webhook for every incoming WhatsApp message.
    Returns the plain-text reply to send back.
    """
    session = SESSIONS.get(phone)

    if session is None or session.get("state") != "awaiting_confirmation":
        return start_session(phone, text.strip())

    label = _classify_confirmation(text)

    if label == "confirm":
        session["state"] = "active"
        return _continue_after_confirmation(phone)

    if label == "reject":
        return "Please describe what's wrong, e.g. \"progress is 45% not 60%\" or \"missing blocker: crane broken\"."

    return _retry_extraction(phone, text.strip())