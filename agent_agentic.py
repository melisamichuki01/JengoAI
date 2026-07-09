"""
agent.py
--------
The JengoAI agentic loop.

The LLM receives the foreman's message and a list of tools.
It decides which tools to call, in what order, based on what
it receives back from each tool call. It stops when it decides
the task is complete.

Human-in-the-loop: after the LLM calls extract_site_update,
the agent pauses and asks the human to confirm the extraction
before allowing the loop to continue.
"""

import os
import json
from groq import Groq
from dotenv import load_dotenv
from tools import TOOL_SCHEMAS, TOOL_FUNCTIONS

load_dotenv()

MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")

RESET  = "\033[0m"
CYAN   = "\033[96m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
MUTED  = "\033[90m"
WHITE  = "\033[97m"
BOLD   = "\033[1m"


def print_tool_call(tool_name: str, args: dict):
    print(f"\n  {CYAN}-> Agent calling:{RESET} {WHITE}{tool_name}{RESET}")
    for k, v in args.items():
        if isinstance(v, list):
            v = ", ".join(str(i) for i in v) or "None"
        if k != "report_text":
            print(f"    {MUTED}{k}:{RESET} {v}")


def print_tool_result(tool_name: str, result: dict):
    print(f"  {GREEN}checkmark {tool_name} completed{RESET}")
    for k, v in result.items():
        if k != "report_text":
            print(f"    {MUTED}{k}:{RESET} {v}")


def print_extracted(extracted: dict):
    """Print extracted data in a readable format."""
    print(f"\n  {MUTED}{'Site':<22}{RESET}{extracted.get('site_name', 'Unknown')}")
    print(f"  {MUTED}{'Foreman':<22}{RESET}{extracted.get('foreman_name', 'Unknown')}")
    print(f"  {MUTED}{'Progress':<22}{RESET}{extracted.get('progress_percentage', 'N/A')}%")

    confidence = extracted.get("confidence", "unknown")
    conf_color = GREEN if confidence == "high" else (YELLOW if confidence == "medium" else RED)
    print(f"  {MUTED}{'Confidence':<22}{RESET}{conf_color}{confidence.upper()}{RESET}")

    blockers = extracted.get("blockers", [])
    print(f"  {MUTED}{'Blockers':<22}{RESET}{RED if blockers else GREEN}{', '.join(blockers) or 'None'}{RESET}")

    materials = extracted.get("materials_used", [])
    if materials:
        print(f"\n  {MUTED}Materials Used:{RESET}")
        for m in materials:
            print(f"    {YELLOW}* {m.get('name')}: {m.get('quantity','?')}) {m.get('unit','units')}{RESET}")
    else:
        print(f"  {MUTED}{'Materials Used':<22}{RESET}None reported")

    print(f"  {MUTED}{'Materials Needed':<22}{RESET}{extracted.get('materials_needed','None')}")
    print(f"  {MUTED}{'Labor Needed':<22}{RESET}{extracted.get('labor_needed','None')}")
    print(f"  {MUTED}{'Safety':<22}{RESET}{extracted.get('safety_incidents','None')}")


def human_confirm_extraction(extracted: dict) -> tuple:
    """
    Show extracted data and ask user to confirm.
    Returns (confirmed: bool, correction: str)
    - If confirmed: (True, "")
    - If rejected: (False, correction_text) where correction_text
      describes what was wrong so the agent can re-extract.
    """
    print(f"\n{YELLOW}{BOLD}-- Human Checkpoint ------------------------------------{RESET}")
    print(f"  {WHITE}The agent extracted the following. Please confirm.{RESET}")
    print_extracted(extracted)
    print()

    while True:
        reply = input(f"  {YELLOW}Is this correct? (y/n): {RESET}").strip().lower()
        if reply in ["y", "yes", "ndio", "sawa"]:
            return True, ""
        if reply in ["n", "no", "hapana"]:
            print(f"\n  {WHITE}What is wrong? Describe the correction:{RESET}")
            print(f"  {MUTED}Examples:{RESET}")
            print(f"  {MUTED}  - Site is Eastleigh, foreman is Grace{RESET}")
            print(f"  {MUTED}  - Progress is 45% not 60%{RESET}")
            print(f"  {MUTED}  - Missing blocker: crane is broken{RESET}")
            print()
            correction = input(f"  {YELLOW}Your correction: {RESET}").strip()
            if not correction:
                print(f"  {RED}Please describe what is wrong so the agent can fix it.{RESET}")
                continue
            return False, correction
        print(f"  {RED}Please enter y or n.{RESET}")


def run_agent(raw_message: str) -> dict:
    """
    Run the agentic loop for a single foreman message.

    Loop:
    1. Send message + tools to Groq
    2. If Groq returns tool_calls: execute each tool
       - extract_site_update: pause for human confirmation
       - human rejects: stop loop
    3. Add tool results to message history
    4. Send updated history back to Groq
    5. Repeat until Groq returns finish_reason = stop
    """
    client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

    system_prompt = """You are JengoAI, an intelligent construction site reporting agent.

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

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": f"Process this site update: {raw_message}"},
    ]

    summary = {
        "extraction":        None,
        "inventory_updates": [],
        "report_text":       None,
        "notion_url":        None,
        "confirmed":         False,
        "stopped_reason":    None,
    }

    print(f"\n{CYAN}{BOLD}-- Agent Starting --------------------------------------{RESET}")
    print(f"  {MUTED}Model: {MODEL}{RESET}")
    print(f"  {MUTED}Tools available: {len(TOOL_FUNCTIONS)}{RESET}")

    max_iterations = 20
    iteration = 0

    while iteration < max_iterations:
        iteration += 1

        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=TOOL_SCHEMAS,
            tool_choice="auto",
            temperature=0.1,
        )

        message     = response.choices[0].message
        stop_reason = response.choices[0].finish_reason

        # Agent decided it is done
        if stop_reason == "stop" or not message.tool_calls:
            print(f"\n{GREEN}{BOLD}-- Agent Complete --------------------------------------{RESET}")
            if message.content:
                print(f"  {message.content}")
            summary["stopped_reason"] = "complete"
            break

        # Add assistant message to history
        messages.append(message)

        for tool_call in message.tool_calls:
            tool_name = tool_call.function.name
            tool_args = json.loads(tool_call.function.arguments)
            tool_id   = tool_call.id

            print_tool_call(tool_name, tool_args)

            # Human in the loop after extraction
            if tool_name == "extract_site_update":
                result = TOOL_FUNCTIONS[tool_name](**tool_args)
                summary["extraction"] = result

                if result.get("confidence") == "low":
                    print(f"\n  {RED}Low confidence extraction. Message was unclear.{RESET}")
                    print(f"  {YELLOW}Please resubmit with a clearer message.{RESET}")
                    summary["stopped_reason"] = "low_confidence"
                    return summary

                max_retries = 3
                retry = 0
                while retry < max_retries:
                    confirmed, correction = human_confirm_extraction(result)
                    if confirmed:
                        summary["confirmed"] = True
                        print(f"\n  {GREEN}Confirmed. Agent continuing...{RESET}")
                        break
                    else:
                        retry += 1
                        if retry >= max_retries:
                            print(f"\n  {RED}Too many retries. Please resubmit the update.{RESET}")
                            summary["stopped_reason"] = "rejected_by_human"
                            return summary
                        print(f"\n  {CYAN}Re-extracting with your correction...{RESET}")
                        corrected_message = (
                            tool_args["raw_message"] +
                            f"\n\nCorrection from supervisor: {correction}"
                        )
                        result = TOOL_FUNCTIONS["extract_site_update"](raw_message=corrected_message)
                        summary["extraction"] = result
                        print(f"\n  {YELLOW}Updated extraction:{RESET}")

                if not summary["confirmed"]:
                    return summary

            else:
                result = TOOL_FUNCTIONS[tool_name](**tool_args)

                if tool_name == "update_inventory_for_material":
                    summary["inventory_updates"].append(result)
                    if result.get("reorder_alert_created"):
                        print(f"  {RED}! Reorder alert created for {result['material']}{RESET}")

                elif tool_name == "fetch_site_history":
                    summary["site_history"] = result.get("summary", "")
                    found = result.get("found", 0)
                    print(f"  {MUTED}Found {found} previous report(s) for {result.get('site_name')}{RESET}")

                elif tool_name == "generate_site_report":
                    summary["report_text"] = result.get("report_text")

                elif tool_name == "save_report_to_notion":
                    summary["notion_url"] = result.get("notion_url")

            print_tool_result(tool_name, result)

            messages.append({
                "role":         "tool",
                "tool_call_id": tool_id,
                "content":      json.dumps(result),
            })

    if iteration >= max_iterations:
        summary["stopped_reason"] = "max_iterations_reached"

    return summary