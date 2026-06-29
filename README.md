# Browser Operating Agent

An autonomous web-automation agent system that takes a natural language request, plans execution steps, runs them using Playwright in a real chromium browser, extracts key page elements, and outputs a structured summary.

Built with Python, Streamlit, and Groq API. Features a fully offline **Mock LLM Mode** for cost-free testing and development.

---

## 🛠️ Multi-Agent Architecture

The system coordinates 4 dedicated agents in a pipeline:

1. **Planner Agent**: Parses natural language requests to output a structured JSON plan of actions (navigate, search, type, click, scroll, wait, extract).
2. **Browser Agent**: Controls a Playwright instance to execute the navigation and inputs, taking live screenshots at each step.
3. **Extractor Agent**: Strips HTML tags and uses the LLM to extract key target info from raw page contents.
4. **Summarizer Agent**: Synthesizes the extracted content into a comprehensive final report.

---

## 📂 Project Structure

```text
browser_agent/
├── agents/
│   ├── __init__.py         # Package entry (named exactly __init__.py)
│   ├── planner.py          # Plan compiler and JSON output parser
│   ├── browser_agent.py    # Playwright wrapper (async browser interactions)
│   ├── extractor.py        # Text & link extraction agent
│   └── summarizer.py       # Final summary and formatting agent
├── utils/
│   ├── __init__.py         # Package entry (named exactly __init__.py)
│   ├── llm_client.py       # Groq API caller & Mock LLM fallback simulation
│   └── helpers.py          # HTML stripping & JSON logging utilities
├── app.py                  # Streamlit UI (Live view & history dashboard)
├── config.py               # Global constants & dotenv parser
├── requirements.txt        # Package dependencies
└── README.md               # User guide (Windows PowerShell focus)
```

---

## 🚀 Setup & Execution Instructions (Windows PowerShell)

Follow these steps to set up the environment and run the application locally on Windows:

### 1. Clone or Open the Workspace
Ensure your shell directory is at the root of the project:
```powershell
cd "C:\Users\DELL\.gemini\antigravity\scratch\browser_agent"
```

### 2. Create and Activate a Virtual Environment
Creating a virtual environment ensures dependencies do not conflict with system packages:
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```
*(If you encounter execution policy errors in PowerShell, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` first).*

### 3. Install Dependencies
Install all package requirements listed in `requirements.txt`:
```powershell
pip install -r requirements.txt
```

### 4. Install Playwright Browser Binaries
Playwright requires browser binaries to operate. Run the install script:
```powershell
python -m playwright install chromium
```
*(This installs the chromium browser binary, which is used by default).*

### 5. Configure API Settings (Optional for Real Mode)
If you want to use the real Groq LLM API, create a `.env` file in the root folder:
```text
GROQ_API_KEY=your_actual_groq_api_key_here
USE_MOCK_LLM=False
```
If no `.env` is created or `USE_MOCK_LLM` remains `True`, the system automatically falls back to **Mock LLM mode** which requires no internet and runs completely free. You can also configure keys and toggle modes directly inside the Streamlit sidebar.

### 6. Run the App
Launch the Streamlit web dashboard:
```powershell
streamlit run app.py
```
A browser tab will open automatically at `http://localhost:8501`.

---

## 🌟 Key Features Built-in

- **Mock LLM Fallback**: Works out-of-the-box offline. Includes realistic mock schedules for Hacker News, Wikipedia, and Google/DuckDuckGo searches.
- **Selector Fallbacks**: The Browser Agent dynamically retries selector interactions by looking up button text, placeholders, and general input types if standard CSS selectors fail.
- **Event-Loop Conflict Resolution**: Employs `nest_asyncio` to prevent event loop collision issues commonly seen when running async Playwright scripts inside Streamlit's web threads.
- **Log Archiver & History Viewer**: Automatically saves runs into a `logs/` directory. Use the "History" tab in the UI to load past sessions and inspect old execution steps alongside captured screenshots.

---

## 🔍 How to Test the Deployed Cloud App (For Colleagues & Presentations)

If you are sharing the live **[Streamlit Cloud Link](https://browser-operating-agent.streamlit.app)** with managers, officials, or colleagues, guide them to test it using these guidelines:

### 1. No API Key Needed
The cloud app is pre-configured to securely run live searches using our backend API key. Visitors do **not** need to register or paste any key. The **"Use Mock LLM (Offline Mode)"** box will be unchecked by default, allowing them to perform real live searches out-of-the-box.

### 2. Recommended Presentation Queries
Because the app is hosted on shared cloud servers, commercial websites with aggressive anti-bot firewalls (such as airlines, booking portals, or ticketing sites) will block the server's cloud IP and cause a timeout. 

For the best demonstration, recommend they test with the following queries:

* **Dynamic Web Search (Google News/GitHub links):**
  > `Search DuckDuckGo for the best AI tools`
* **Wikipedia Subject Extraction (Custom JS Layout):**
  > `Go to wikipedia.org and find the page for JavaScript`
* **Product Search & Deals (Amazon/Best Buy active links):**
  > `Find the best noise-cancelling headphones`

*Note: If you need to demonstrate the agent performing real booking actions on airline websites (e.g. Akasa Air or IndiGo), follow the **Setup & Execution Instructions** above to run the app locally on your computer. Running it locally uses your home IP, which will bypass airline firewalls successfully!*
