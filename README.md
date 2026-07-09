# 🏗️ JengoAI

Agentic site reporting and inventory management for construction teams. Foremen submit daily updates via CLI or a Streamlit form. The agent extracts structured data, updates inventory, raises reorder alerts, generates a professional client report, and saves everything to Notion for PM review.

Built with Groq + Llama 3.3, Notion, and Streamlit.

---

## Two versions: Pipeline vs Agent

JengoAI ships with two versions of the core logic side by side. This is intentional. The two versions exist to show the difference between an LLM-powered automation pipeline and a true AI agent.

### Version 1: Pipeline (`cli_pipeline.py` + `agent_pipeline.py`)

```
You decide the order. Python calls each function in a fixed sequence.

input → extract → inventory → generate → save
```

The LLM is used twice: once to extract structured data, once to generate the report. But Python controls what happens, when, and in what order. The LLM is a smart function call inside a script, not the one making decisions.

```python
# agent_pipeline.py - you hardcode the sequence
extracted = extract_update(raw_text)
update_inventory(extracted)
report = generate_report(extracted)
save_report_to_notion(report, extracted)
```

### Version 2: Agentic (`cli_agent.py` + `agent_agentic.py`)

```
The LLM decides the order. It receives tools and a task and figures out the rest.

input → LLM decides → calls tools → reads results → decides again → stops when done
```

The LLM receives a list of 5 tools and a single instruction: "process this site update." It decides which tools to call, in what order, with what arguments, based on what each tool returns. Python only runs what the LLM asks it to run.

```python
# agent_agentic.py - LLM drives the loop
response = groq.chat.completions.create(
    model=MODEL,
    messages=messages,
    tools=TOOL_SCHEMAS,   # LLM sees available tools
    tool_choice="auto",   # LLM decides which to call
)
# If LLM wants a tool: execute it, add result to history, loop again
# If LLM says stop: task is complete
```

---

## What makes the agentic version a real agent

A true AI agent has 5 components. Here is how each one is implemented in Version 2:

| Component | What it means | Implementation |
|---|---|---|
| Brain | LLM that reasons and decides | Groq + Llama 3.3 70B |
| Tools | Functions the LLM can call | 5 tools with JSON schemas |
| Loop | Runs until the LLM decides the task is done | Groq function calling loop |
| In-context memory | Remembers what it did in this session | Full message history passed each iteration |
| Persistent memory | Remembers what happened in past sessions | `fetch_site_history` reads past Notion reports |

### The 5 tools

```
1. extract_site_update        Parse raw Swahili/English message into structured data
2. fetch_site_history         Read last 3 reports for this site from Notion
3. update_inventory_for_material  Update stock levels and raise reorder alerts
4. generate_site_report       Write a client report with historical trend context
5. save_report_to_notion      Save the report to Notion as a Draft
```

### The loop in plain terms

```
LLM receives: foreman message + list of 5 tools
        |
        v
LLM decides: "I should call extract_site_update first"
        |
        v
Python runs extract_site_update, returns structured dict
        |
        v
[Human checkpoint] - confirm extraction before continuing
        |
        v
LLM receives the result, decides: "Now I should call fetch_site_history"
        |
        v
Python runs fetch_site_history, returns last 3 reports and progress trend
        |
        v
LLM decides: "Now update_inventory_for_material for cement, then for tiles"
        |
        v
Python runs inventory updates, reorder alerts raised if needed
        |
        v
LLM decides: "Now generate_site_report with history included"
        |
        v
Python generates report with trend: "Progress improved from 70% to 85%"
        |
        v
LLM decides: "Now save_report_to_notion"
        |
        v
Python saves to Notion, returns URL
        |
        v
LLM decides: "Task complete" - loop ends
```

### Persistent memory in action

The key upgrade over Version 1 is that Version 2 remembers the past. Before generating the report, it fetches the last 3 reports for the same site and uses them to show trends:

**Version 1 report (no memory):**
> "The Kilimani site is currently at 85% completion."

**Version 2 report (with persistent memory):**
> "Progress has increased from 70% last week to 85% this week, an improvement of 15%. The crane blocker reported in the previous update has been resolved. The team continues to perform well."

Same data. Dramatically more useful report.

---

## How to compare the two versions

Run them back to back with the same foreman message and compare the output:

```bash
# Step 1: run the pipeline version
python cli_pipeline.py

# Step 2: run the agentic version with the same message
python cli_agent.py
```

Watch the terminal output. The pipeline version runs straight through with no visible decision-making. The agentic version prints each tool the LLM decides to call, in the order it decides to call them, with the arguments it chooses.

You will also notice the agentic version pauses at the human checkpoint after extraction, asks you to confirm, and re-extracts with your correction if something is wrong. The pipeline version has no such loop.

---

## Prerequisites

Two free accounts required:

- **Groq** - https://console.groq.com
- **Notion** - https://www.notion.so

---

## Setup

### Step 1: Clone the repo

```bash
git clone https://github.com/melisamichuki01/jengoai
cd jengoai
```

### Step 2: Install dependencies

```bash
pip install groq notion-client streamlit python-dotenv requests
```

### Step 3: Get your Groq API key

1. Go to https://console.groq.com
2. Sign up for a free account
3. Click **API Keys** in the left sidebar
4. Click **Create API Key** and copy it

### Step 4: Create a Notion integration

1. Go to https://www.notion.so/my-integrations
2. Click **New Integration**
3. Name it `jengoai`, select your workspace, click **Submit**
4. Copy the **Internal Integration Token** (starts with `secret_`)

### Step 5: Create a Notion page and connect your integration

1. Open Notion in your browser
2. Click **New Page** in the left sidebar, name it `JengoAI`
3. Click `...` top right → **Connections** → search for `jengoai` → add it
4. Copy the full URL from your browser

### Step 6: Run setup

```bash
python setup.py
```

Paste your Notion key, Groq key, and page URL when asked. The script creates all three databases and writes your `.env` automatically.

---

## Running the agent

### Pipeline version

```bash
python cli_pipeline.py
```

Fixed sequence. Fast. No visible decision-making. Good for showing the baseline.

### Agentic version

```bash
python cli_agent.py
```

LLM-driven loop. Shows each tool call as it happens. Includes human-in-the-loop confirmation and persistent memory. Good for showing what makes an agent different.

### Streamlit dashboard

```bash
streamlit run app.py
```

Five pages:

| Page | What it does |
|---|---|
| Overview | Summary metrics and recent reports |
| Foreman Input | Submit updates via free text or structured form |
| Pending Review | PM approves or flags reports |
| All Reports | Full history with filters |
| Inventory | Stock levels and reorder alerts |

---

## Project structure

```
jengoai/
├── agent_pipeline.py         # Version 1: fixed pipeline, you control the sequence
├── cli_pipeline.py           # Version 1: CLI runner for the pipeline
├── agent_agentic.py          # Version 2: agentic loop, LLM controls the sequence
├── cli_agent.py              # Version 2: CLI runner for the agentic version
├── tools.py                  # All 5 tool functions and their JSON schemas
├── notion_client_wrapper.py  # Notion: site reports read/write
├── inventory.py              # Notion: inventory and reorder alerts
├── app.py                    # Streamlit dashboard
├── setup.py                  # First-time setup script
├── .env.example
├── .gitignore
└── README.md
```

---

## Notion databases

Three databases created automatically by `setup.py`:

| Database | Purpose |
|---|---|
| Site Reports | One row per daily update with generated report |
| Inventory | Material stock levels per site |
| Reorder Alerts | Auto-raised when stock is low relative to project progress |

---

## Reorder logic

| Condition | Priority |
|---|---|
| Progress >= 75% and stock < 40% | High |
| Progress >= 50% and stock < 30% | High |
| Progress >= 40% and stock < 25% | Medium |
| Progress >= 25% and stock < 20% | Low |

---

## Sample foreman messages

**English:**
```
Westlands site. James here. We are at 60% completion.
Cement delivery has not arrived, we need 50 bags urgently.
Used 20 bags of cement and 10 litres of paint today.
Need 8 labourers on Thursday. No accidents today.
```

**Swahili/English mix:**
```
Kilimani site. Peter hapa. Tumefika 85%.
Crane imevunjika na steel rods hazijakuja.
Tunahitaji electrician. Mfanyakazi mmoja alijeruhiwa kidogo.
```

**High progress, triggers reorder alert:**
```
Thika site. Mary hapa. Tumefika 90%.
Tumitumia saruji mifuko 20 na tiles pieces 50 leo.
Stock ya saruji inakwisha kabisa, tunahitaji mifuko 100 haraka sana.
Salama, hakuna ajali leo.
```

---

## Troubleshooting

**`NOTION_SITE_REPORTS_DB not set`**
Run `python setup.py` to create databases and write `.env`.

**`API token is invalid`**
Add `from dotenv import load_dotenv` and `load_dotenv()` at the top of the file throwing the error.

**`Could not find database with ID`**
Open the database in Notion → `...` → Connections → add your `jengoai` integration.

**`model llama-3.1-70b-versatile has been decommissioned`**
Open `agent_pipeline.py` or `agent_agentic.py` and change the MODEL line to:
```python
MODEL = "llama-3.3-70b-versatile"
```

**Streamlit shows a blank screen**
Make sure `load_dotenv()` is at the top of `agent_agentic.py`, `notion_client_wrapper.py`, and `inventory.py`.

---

## Running on GitHub Codespaces

1. Fork this repo to your GitHub account
2. Open the repo → green **Code** button → **Codespaces** → **Create codespace on main**
3. In the terminal:

```bash
pip install groq notion-client streamlit python-dotenv requests
python setup.py
python cli_agent.py
streamlit run app.py
```

---

## Built by

[MLlabswithMel]teaching agents by building them.