# 🏗️ JengoAI

Agentic site reporting and inventory management for construction teams. Foremen submit daily updates via CLI or a Streamlit form. The agent extracts structured data, updates inventory, raises reorder alerts, generates a professional client report, and saves everything to Notion for PM review.

Built with Groq + Llama 3.1, Notion, and Streamlit. No WhatsApp required.

---

## What it does

1. Foreman types or pastes a site update (English, Swahili, or mixed)
2. Agent extracts: site name, progress, blockers, materials used, labor, safety
3. You confirm the extraction before anything is saved
4. Inventory is updated automatically
5. A professional client report is generated
6. Report is saved to Notion as a Draft
7. PM reviews and approves in the Streamlit dashboard

---

## Prerequisites

You need two accounts before you start. Both are free.

- **Groq** — the AI that powers the agent: https://console.groq.com
- **Notion** — where reports and inventory are stored: https://www.notion.so

---

## Setup (follow these steps in order)

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
4. Click **Create API Key**
5. Copy the key — you will need it in Step 6

### Step 4: Create a Notion integration

1. Go to https://www.notion.so/my-integrations
2. Click **New Integration**
3. Name it `jengoai`
4. Select your workspace
5. Click **Submit**
6. Copy the **Internal Integration Token** (starts with `secret_`)

### Step 5: Create a Notion page and connect your integration

Notion does not allow the agent to create pages automatically, so you need to create one page manually. This takes about 30 seconds.

1. Open Notion in your browser
2. Click **New Page** in the left sidebar
3. Name it anything, for example `JengoAI`
4. Click the `...` menu in the top right corner
5. Click **Connections**
6. Search for `jengoai` and click it to add it
7. Copy the full URL from your browser address bar

The URL will look something like this:
```
https://www.notion.so/JengoAI-abc123def456789012345678901234ab
```

### Step 6: Run the setup script

```bash
python setup.py
```

The script will ask for three things:

- Your Notion API key (from Step 4)
- Your Groq API key (from Step 3)
- Your Notion page URL (from Step 5)

It will then create all three databases in your Notion page and write a `.env` file with all the keys and IDs automatically. You do not need to copy any database IDs.

When setup is complete you should see this in your terminal:

```
  ╔══════════════════════════════════════════╗
  ║           Setup complete!                ║
  ╚══════════════════════════════════════════╝
```

And in Notion you should see three new databases inside your page:
- Kamau Construction - Site Reports
- Kamau Construction - Inventory
- Kamau Construction - Reorder Alerts

---

## Running the agent

### CLI mode (recommended for testing)

```bash
python cli.py
```

Paste or type the foreman's site update when prompted. Press Enter twice to submit.

**Example message:**
```
Westlands site. James here. We are at 60% completion.
Cement delivery has not arrived, we need 50 bags urgently.
Used 20 bags of cement and 10 litres of paint today.
Need 8 labourers on Thursday. No accidents today.
```

The agent will:
1. Extract the data and show it to you
2. Ask you to confirm before saving
3. Update inventory for any materials reported
4. Generate a professional report
5. Save it to Notion
6. Print the Notion URL

### Streamlit dashboard

```bash
streamlit run app.py
```

Open the URL shown in your terminal (usually `http://localhost:8501`).

The dashboard has five pages:

| Page | What it does |
|---|---|
| Overview | Summary metrics and recent reports |
| Foreman Input | Submit updates via free text or structured form |
| Pending Review | Approve or flag reports as PM |
| All Reports | Full history with filters |
| Inventory | Stock levels and reorder alerts |

---

## Project structure

```
jengoai/
├── agent.py                  # Groq: extract structured data and generate report
├── notion_client_wrapper.py  # Notion: read and write site reports
├── inventory.py              # Notion: inventory and reorder alerts
├── cli.py                    # CLI foreman input mode
├── app.py                    # Streamlit dashboard
├── setup.py                  # First-time setup script
├── .env.example              # Template for your .env file
├── .gitignore
└── README.md
```

---

## Notion databases

Three databases are created automatically by `setup.py`:

| Database | Purpose |
|---|---|
| Site Reports | One row per daily foreman update with generated report |
| Inventory | Tracks material stock levels per site |
| Reorder Alerts | Auto-raised when stock is low relative to project progress |

---

## Reorder logic

The agent raises a reorder alert when stock is low relative to how far along the project is:

| Condition | Priority |
|---|---|
| Project >= 75% done and stock < 40% remaining | High |
| Project >= 50% done and stock < 30% remaining | High |
| Project >= 40% done and stock < 25% remaining | Medium |
| Project >= 25% done and stock < 20% remaining | Low |

---

## Environment variables

Your `.env` file is created automatically by `setup.py`. It contains:

```
GROQ_API_KEY=your_groq_key
NOTION_API_KEY=your_notion_key
NOTION_SITE_REPORTS_DB=your_database_id
NOTION_INVENTORY_DB=your_database_id
NOTION_REORDER_DB=your_database_id
```

Never commit your `.env` file to GitHub. It is already in `.gitignore`.

---

## Troubleshooting

**`NOTION_SITE_REPORTS_DB not set. Run: python setup.py`**
Your `.env` file is missing the database IDs. Run `python setup.py` again.

**`API token is invalid`**
Your Notion key is not being loaded. Make sure `load_dotenv()` is at the top of the file throwing the error.

**`Could not find database with ID`**
The database exists but your integration does not have access to it. Open the database in Notion, click `...`, click Connections, and add your `jengoai` integration.

**`model llama-3.1-70b-versatile has been decommissioned`**
Open `agent.py` and change the MODEL line to:
```python
MODEL = "llama-3.3-70b-versatile"
```

---

## Running on GitHub Codespaces

1. Fork this repo to your GitHub account
2. Open the repo on GitHub
3. Click the green **Code** button → **Codespaces** → **Create codespace on main**
4. In the terminal that opens:

```bash
pip install groq notion-client streamlit python-dotenv requests
python setup.py
python cli.py
streamlit run app.py
```

Codespaces will prompt you to open the Streamlit port in your browser automatically.

---

## Built by

[MLlabswithMel]teaching agents by building them.