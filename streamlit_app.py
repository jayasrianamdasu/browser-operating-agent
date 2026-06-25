import sys
import os
# Add both the script directory and the parent directory to Python's import search path
# We insert the parent directory first and the script directory second, so that the script directory takes top priority (index 0)
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(script_dir))
sys.path.insert(0, script_dir)

import asyncio
import logging
import streamlit as st
from PIL import Image

# nest_asyncio removed to avoid conflicts with AnyIO/Starlette on Python 3.14+

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("browser_agent.app")

# Import config, helpers, and agents
import config
from utils.helpers import save_session_log, load_history
from agents.planner import PlannerAgent
from agents.browser_agent import BrowserAgent
from agents.extractor import ExtractorAgent
from agents.summarizer import SummarizerAgent

# ----------------- STREAMLIT PAGE SETUP -----------------
st.set_page_config(
    page_title="Browser Operating Agent",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Premium dark theme styling overrides (custom css injection)
st.markdown(
    """
    <style>
    .main {
        background-color: #0d1117;
        color: #c9d1d9;
    }
    .stButton>button {
        background-image: linear-gradient(135deg, #1f6feb 0%, #104fa4 100%);
        color: white;
        border: none;
        padding: 0.5rem 2rem;
        border-radius: 6px;
        transition: all 0.3s ease;
    }
    .stButton>button:hover {
        opacity: 0.9;
        transform: translateY(-1px);
    }
    .agent-box {
        border: 1px solid #30363d;
        border-radius: 8px;
        padding: 15px;
        background-color: #161b22;
        margin-bottom: 10px;
    }
    .agent-title {
        font-weight: bold;
        color: #58a6ff;
        margin-bottom: 5px;
    }
    .success-text {
        color: #3fb950;
    }
    .error-text {
        color: #f85149;
    }
    </style>
    """,
    unsafe_allow_html=True
)

st.title("🤖 Browser Operating Agent")
st.markdown("An autonomous multi-agent assistant that browses, extracts, and summarizes information from the web.")

# ----------------- SIDEBAR SETTINGS -----------------
st.sidebar.header("Configuration")

# Model configuration override options
use_mock = st.sidebar.checkbox(
    "Use Mock LLM (Offline Mode)",
    value=config.USE_MOCK_LLM,
    help="Toggle offline mode to use simulated LLM outputs instead of the real Groq API."
)

groq_key = st.sidebar.text_input(
    "Groq API Key",
    type="password",
    value=config.GROQ_API_KEY if config.GROQ_API_KEY != "your-key-here" else "",
    placeholder="gsk_...",
    disabled=use_mock,
    help="Required when Mock Mode is disabled."
)

groq_model = st.sidebar.selectbox(
    "Groq Model",
    options=["llama-3.3-70b-versatile", "mixtral-8x7b-32768", "llama-3.1-8b-instant"],
    index=0 if config.GROQ_MODEL == "llama-3.3-70b-versatile" else 1,
    disabled=use_mock
)

headless = st.sidebar.checkbox(
    "Headless Browser",
    value=config.HEADLESS_BROWSER,
    help="Run browser in background. Uncheck to visually watch the agent operate."
)

st.sidebar.markdown("---")

# ----------------- HISTORY PANEL -----------------
st.sidebar.header("Execution History")
history_logs = load_history()

if history_logs:
    history_options = {
        f"{h.get('timestamp')[:19]} - {h.get('prompt')[:25]}...": h
        for h in history_logs
    }
    selected_hist_key = st.sidebar.selectbox("Select a past run", options=list(history_options.keys()))
    
    if selected_hist_key:
        selected_run = history_options[selected_hist_key]
        if st.sidebar.button("Load Past Run"):
            st.session_state["loaded_run"] = selected_run
            st.session_state["active_tab"] = "History"
else:
    st.sidebar.info("No past runs recorded.")

# ----------------- ORCHESTRATOR PIPELINE -----------------
async def run_pipeline(task_prompt: str, api_key: str, model_name: str, use_mock_mode: bool, is_headless: bool):
    """
    Executes the multi-agent pipeline step-by-step, updating the UI in real-time.
    """
    screenshot_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "screenshots")
    if not os.path.exists(screenshot_dir):
        os.makedirs(screenshot_dir)

    # 1. Planner Agent
    status_container.info("🧠 **Planner Agent** is active: Generating execution plan...")
    planner = PlannerAgent(api_key=api_key, model=model_name, use_mock=use_mock_mode)
    
    try:
        plan = planner.plan(task_prompt)
    except Exception as e:
        status_container.error(f"Planner failed: {e}")
        return
        
    if not plan:
        status_container.error("Planner failed to generate steps.")
        return

    # Render plan in the UI
    plan_placeholder.empty()
    with plan_expander:
        st.write("#### Steps to Execute")
        for idx, step in enumerate(plan):
            st.markdown(f"**Step {idx+1}:** {step.get('action').upper()} | {step}")
            
    # 2. Browser Agent
    status_container.info("🌐 **Browser Agent** is active: Initializing Playwright browser...")
    browser_agent = BrowserAgent(headless=is_headless, use_mock=use_mock_mode)
    await browser_agent.start()
    
    executed_steps = []
    accumulated_extraction = ""
    res = {"status": "success", "details": "No steps executed", "html": ""}
    
    try:
        for idx, step in enumerate(plan):
            step_num = idx + 1
            action = step.get("action", "")
            status_container.info(f"🌐 **Browser Agent**: Executing step {step_num}/{len(plan)} ({action.upper()})...")
            
            # Run action
            res = await browser_agent.execute_action(step, step_num, screenshot_dir)
            executed_steps.append(res)
            
            # Show live screenshots in UI
            if res.get("screenshot_path") and os.path.exists(res["screenshot_path"]):
                try:
                    img = Image.open(res["screenshot_path"])
                    with screenshot_container.container():
                        st.image(img, use_container_width=True)
                except Exception as ss_load_err:
                    logger.error(f"Could not load screenshot in UI: {ss_load_err}")

            if res["status"] == "error":
                st.error(f"Step {step_num} failed: {res['details']}")
                break
                
            # If action is extract, invoke the Extractor Agent
            if action.lower() == "extract":
                status_container.info(f"🔍 **Extractor Agent** is active: Extracting target details from the webpage...")
                extractor = ExtractorAgent(api_key=api_key, model=model_name, use_mock=use_mock_mode)
                
                target = step.get("target", "main text content")
                current_url = browser_agent.page.url if browser_agent.page else ""
                
                extracted_text = extractor.extract(res["html"], target, current_url)
                
                # Append to extraction accumulator
                accumulated_extraction += f"\n--- EXTRACTION FROM {current_url} (Target: {target}) ---\n{extracted_text}\n"
                
                extraction_placeholder.empty()
                with extraction_expander:
                    st.write(f"**Extraction from Step {step_num} ({current_url})**")
                    st.markdown(extracted_text)

        # 3. Summarizer Agent
        if res["status"] != "error":
            status_container.info("✍️ **Summarizer Agent** is active: Synthesizing final answer...")
            summarizer = SummarizerAgent(api_key=api_key, model=model_name, use_mock=use_mock_mode)
            
            # If no explicit extraction occurred, use the last page's general text contents
            if not accumulated_extraction:
                last_html = executed_steps[-1].get("html", "")
                current_url = browser_agent.page.url if browser_agent.page else ""
                extractor = ExtractorAgent(api_key=api_key, model=model_name, use_mock=use_mock_mode)
                accumulated_extraction = extractor.extract(last_html, "main content", current_url)
                
            final_summary = summarizer.summarize(task_prompt, accumulated_extraction)
            
            status_container.success("✅ **Task Finished Successfully!**")
            
            # Display final summary in UI
            with summary_container.container():
                st.write("## Final Answer Summary")
                st.markdown(final_summary)
                
            # Save session log to file
            log_path = save_session_log(task_prompt, plan, executed_steps, final_summary)
            if log_path:
                st.info(f"Session log saved successfully at: `{log_path}`")
        else:
            status_container.error(f"❌ **Task terminated prematurely due to browser step failure:** {res.get('details')}")
            save_session_log(task_prompt, plan, executed_steps, f"Error: {res.get('details')}")

    except Exception as run_err:
        logger.error(f"Error during pipeline execution: {run_err}")
        status_container.error(f"Critical execution error: {run_err}")
    finally:
        await browser_agent.stop()

# ----------------- MAIN UI CONTENT -----------------
# Tab definitions
tab1, tab2 = st.tabs(["Run Agent", "History & Saved Logs"])

# Handle view redirection via session state
active_tab_state = st.session_state.get("active_tab", "Run")
if active_tab_state == "History":
    # Emulate tab select if state points to History (handled below natively)
    pass

with tab1:
    st.write("### Input Your Web Automation Task")
    default_prompt = "Search for the latest AI news and summarize the top 3 results"
    task_input = st.text_area(
        "Describe the task in plain English:",
        value=default_prompt,
        height=100
    )
    
    # Run Agent Button logic
    if st.button("Run Agent Pipeline"):
        if not use_mock and not groq_key:
            st.error("Please enter a valid Groq API Key or enable Mock Mode in the sidebar.")
        else:
            # Layout containers for execution
            status_container = st.empty()
            
            # Pre-render columns to stabilize height and avoid UI jumping/shaking
            col1, col2 = st.columns([1, 1])
            with col1:
                st.markdown("### 📸 Live Browser Screenshot")
                screenshot_container = st.empty()
                screenshot_container.info("Waiting for browser action...")
            with col2:
                st.markdown("### 📄 Final Answer Summary")
                summary_container = st.empty()
                summary_container.info("Waiting for agent to summarize...")

            plan_expander = st.expander("📝 Show Execution Plan", expanded=True)
            plan_placeholder = plan_expander.empty()
            plan_placeholder.info("Waiting for Planner Agent to generate steps...")
            
            extraction_expander = st.expander("🔍 Show Extracted Web Content", expanded=True)
            extraction_placeholder = extraction_expander.empty()
            extraction_placeholder.info("Waiting for Extractor Agent to parse page contents...")
                
            # Run the async pipeline in a separate thread to avoid AnyIO / nest_asyncio event loop conflicts under Python 3.14+
            import threading
            from streamlit.runtime.scriptrunner import add_script_run_ctx, get_script_run_ctx
            
            def run_async_in_thread(coro):
                result = []
                exception = []
                ctx = get_script_run_ctx()
                
                def target():
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        res = loop.run_until_complete(coro)
                        result.append(res)
                    except Exception as e:
                        exception.append(e)
                    finally:
                        loop.close()
                
                thread = threading.Thread(target=target)
                add_script_run_ctx(thread, ctx)
                thread.start()
                thread.join()
                if exception:
                    raise exception[0]
                return result[0] if result else None

            run_async_in_thread(
                run_pipeline(
                    task_prompt=task_input,
                    api_key=groq_key,
                    model_name=groq_model,
                    use_mock_mode=use_mock,
                    is_headless=headless
                )
            )

with tab2:
    loaded_run = st.session_state.get("loaded_run")
    if loaded_run:
        st.write(f"### Historical Run details: {loaded_run.get('timestamp')}")
        st.markdown(f"**Task Prompt:** *{loaded_run.get('prompt')}*")
        
        st.write("---")
        st.write("### Final Summary Output")
        st.markdown(loaded_run.get("final_summary", "No final summary found."))
        
        st.write("---")
        st.write("### Detailed Execution Steps")
        
        for idx, step in enumerate(loaded_run.get("steps", [])):
            step_num = idx + 1
            action = step.get("action", "").upper()
            status = step.get("status", "success")
            details = step.get("details", "")
            
            status_symbol = "🟢" if status == "success" else "🔴"
            st.markdown(f"#### {status_symbol} Step {step_num}: {action} ({status})")
            st.write(details)
            
            ss_path = step.get("screenshot_path", "")
            if ss_path and os.path.exists(ss_path):
                st.image(Image.open(ss_path), caption=f"Screenshot after Step {step_num}", use_container_width=True)
            else:
                st.caption("No screenshot available for this step.")
            st.write("---")
    else:
        st.write("Select a past run in the sidebar and click 'Load Past Run' to inspect history details.")
