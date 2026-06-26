import sys
import os

# Add both the script directory and the parent directory to Python's import search path
script_dir = os.path.dirname(os.path.abspath(__file__))

# Clean up sys.path to avoid import conflicts with other parent or current working directories
for path in list(sys.path):
    if "Browser-Operating-Agent" in path or path == "" or path == ".":
        try:
            sys.path.remove(path)
        except ValueError:
            pass

sys.path.insert(0, os.path.dirname(script_dir))
sys.path.insert(0, script_dir)

# Force reload of agents and utils to prevent cached import conflicts across Streamlit runs
for mod in list(sys.modules.keys()):
    if mod.startswith("agents") or mod.startswith("utils"):
        sys.modules.pop(mod, None)

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
from utils.browser_runner import BrowserRunner
import time
from datetime import datetime

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

# Proxy settings
with st.sidebar.expander("🌐 Proxy Settings", expanded=False):
    proxy_server = st.text_input("Server (e.g. http://ip:port)", value="")
    proxy_user = st.text_input("Username (optional)", value="")
    proxy_pass = st.text_input("Password (optional)", type="password", value="")

proxy_dict = None
if proxy_server:
    proxy_dict = {"server": proxy_server}
    if proxy_user and proxy_pass:
        proxy_dict["username"] = proxy_user
        proxy_dict["password"] = proxy_pass

# Browser Runner management
if "runner" not in st.session_state:
    st.session_state["runner"] = None

runner = st.session_state["runner"]
if runner and runner.running:
    if st.sidebar.button("🔴 Reset Browser Session", help="Stop and close the current browser process"):
        runner.stop()
        st.session_state["runner"] = None
        st.session_state["pipeline_stage"] = "input"
        st.sidebar.success("Browser session reset.")
        st.rerun()

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
            st.session_state["active_tab"] = "History & Detail Viewer"
else:
    st.sidebar.info("No past runs recorded.")

# ----------------- STATE INITIALIZATION -----------------
if "pipeline_stage" not in st.session_state:
    st.session_state["pipeline_stage"] = "input"
if "plan_steps" not in st.session_state:
    st.session_state["plan_steps"] = []
if "current_step_idx" not in st.session_state:
    st.session_state["current_step_idx"] = 0
if "execution_steps" not in st.session_state:
    st.session_state["execution_steps"] = []
if "accumulated_extraction" not in st.session_state:
    st.session_state["accumulated_extraction"] = ""
if "execution_logs" not in st.session_state:
    st.session_state["execution_logs"] = []
if "execution_mode" not in st.session_state:
    st.session_state["execution_mode"] = "auto"
if "task_prompt" not in st.session_state:
    st.session_state["task_prompt"] = ""
if "start_time" not in st.session_state:
    st.session_state["start_time"] = 0.0
if "run_duration" not in st.session_state:
    st.session_state["run_duration"] = 0.0
if "screenshot_path" not in st.session_state:
    st.session_state["screenshot_path"] = ""
if "final_summary" not in st.session_state:
    st.session_state["final_summary"] = ""

def get_runner_safe():
    r = st.session_state.get("runner")
    if r is None or not r.running:
        r = BrowserRunner()
        try:
            r.start(headless=headless, use_mock=use_mock, proxy=proxy_dict)
            st.session_state["runner"] = r
        except Exception as e:
            st.error(f"Failed to start browser session: {e}")
            return None
    return r

def stop_runner_safe():
    r = st.session_state.get("runner")
    if r:
        r.stop()
        st.session_state["runner"] = None

def handle_manual_click(runner_obj, x, y):
    res = runner_obj.send_cmd("manual_click", x, y)
    if res.get("screenshot_path"):
        st.session_state["screenshot_path"] = res["screenshot_path"]
    st.session_state["execution_logs"].append(f"🛠️ Manual click at ({x}, {y}): {res.get('details')}")

def handle_manual_type(runner_obj, selector, text):
    res = runner_obj.send_cmd("manual_type", selector, text)
    if res.get("screenshot_path"):
        st.session_state["screenshot_path"] = res["screenshot_path"]
    st.session_state["execution_logs"].append(f"🛠️ Manual type '{text}' into '{selector}': {res.get('details')}")

def handle_manual_navigate(runner_obj, url):
    res = runner_obj.send_cmd("manual_navigate", url)
    if res.get("screenshot_path"):
        st.session_state["screenshot_path"] = res["screenshot_path"]
    st.session_state["execution_logs"].append(f"🛠️ Manual navigate to '{url}': {res.get('details')}")

# ----------------- MAIN UI TABS -----------------
active_tab_label = st.session_state.get("active_tab", "Run Agent")
# Reset active tab after reading to let user click other tabs
if "active_tab" in st.session_state:
    del st.session_state["active_tab"]

tab_titles = ["Run Agent", "History & Detail Viewer", "Analytics Dashboard"]
try:
    default_tab_idx = tab_titles.index(active_tab_label)
except ValueError:
    default_tab_idx = 0

tab1, tab2, tab3 = st.tabs(tab_titles)

with tab1:
    st.write("### 🤖 Web Automation Run Studio")
    
    stage = st.session_state["pipeline_stage"]
    
    if stage == "input":
        st.session_state["task_prompt"] = st.text_area(
            "Describe the task in plain English:",
            value=st.session_state.get("task_prompt") or "Search for flight options from San Francisco to Tokyo and list the top 3 airlines and estimated prices.",
            height=100
        )
        
        if st.button("Generate Execution Plan"):
            if not use_mock and not groq_key:
                st.error("Please enter a valid Groq API Key or enable Mock Mode in the sidebar.")
            else:
                with st.spinner("🧠 **Planner Agent** is active: Generating execution steps..."):
                    planner = PlannerAgent(api_key=groq_key, model=groq_model, use_mock=use_mock)
                    try:
                        plan = planner.plan(st.session_state["task_prompt"])
                        if plan:
                            st.session_state["plan_steps"] = plan
                            st.session_state["pipeline_stage"] = "edit_plan"
                            st.session_state["current_step_idx"] = 0
                            st.session_state["execution_steps"] = []
                            st.session_state["accumulated_extraction"] = ""
                            st.session_state["execution_logs"] = []
                            st.session_state["screenshot_path"] = ""
                            st.session_state["final_summary"] = ""
                            st.rerun()
                        else:
                            st.error("Planner failed to generate any steps. Please try a different query.")
                    except Exception as e:
                        st.error(f"Planner failed: {e}")
                        
    elif stage == "edit_plan":
        st.write("### 📝 Review & Edit Execution Plan")
        st.info("The Planner Agent suggested the following steps. You can modify, add, or delete steps before starting execution.")
        
        edited_steps = []
        steps = st.session_state["plan_steps"]
        
        # Display each step
        for i, step in enumerate(steps):
            st.markdown(f"**Step {i+1}**")
            cols = st.columns([2, 5, 1])
            
            with cols[0]:
                action_opt = ["navigate", "search", "click", "type", "scroll", "wait", "extract"]
                curr_action = step.get("action", "navigate").lower()
                if curr_action not in action_opt:
                    action_opt.append(curr_action)
                action = st.selectbox(
                    f"Action",
                    options=action_opt,
                    index=action_opt.index(curr_action),
                    key=f"act_{i}"
                )
                
            with cols[1]:
                new_step = {"action": action}
                if action == "navigate":
                    new_step["url"] = st.text_input(f"URL", value=step.get("url", "https://"), key=f"url_{i}")
                elif action == "search":
                    new_step["query"] = st.text_input(f"Search Query", value=step.get("query", ""), key=f"q_{i}")
                elif action == "click":
                    new_step["selector"] = st.text_input(f"CSS Selector / Button Text", value=step.get("selector", ""), key=f"sel_c_{i}")
                elif action == "type":
                    new_step["selector"] = st.text_input(f"Input Selector", value=step.get("selector", ""), key=f"sel_t_{i}")
                    new_step["text"] = st.text_input(f"Text to Type", value=step.get("text", ""), key=f"txt_{i}")
                elif action == "scroll":
                    direction_opts = ["down", "up"]
                    curr_dir = step.get("direction", "down").lower()
                    new_step["direction"] = st.selectbox(
                        f"Direction",
                        options=direction_opts,
                        index=direction_opts.index(curr_dir) if curr_dir in direction_opts else 0,
                        key=f"dir_{i}"
                    )
                elif action == "wait":
                    new_step["seconds"] = st.number_input(
                        f"Seconds",
                        min_value=1,
                        max_value=30,
                        value=int(step.get("seconds", 2)),
                        key=f"sec_{i}"
                    )
                elif action == "extract":
                    new_step["target"] = st.text_input(f"Extraction Target Details", value=step.get("target", ""), key=f"tgt_{i}")
            
            with cols[2]:
                st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
                if st.button("❌", key=f"del_{i}", help="Delete this step"):
                    steps.pop(i)
                    st.session_state["plan_steps"] = steps
                    st.rerun()
                    
            edited_steps.append(new_step)
            st.markdown("---")
            
        st.session_state["plan_steps"] = edited_steps
        
        # Add new step control
        col_add1, col_add2 = st.columns([3, 7])
        with col_add1:
            if st.button("➕ Add Action Step"):
                st.session_state["plan_steps"].append({"action": "navigate", "url": "https://"})
                st.rerun()
                
        # Execution settings
        st.write("#### ⚡ Execution Mode Settings")
        st.session_state["execution_mode"] = st.radio(
            "Select how the execution loop should run:",
            options=["Auto Play (run all steps automatically to completion)", "Step-by-Step (pause after each step, allowing manual overrides)"],
            index=0 if st.session_state["execution_mode"].startswith("auto") or st.session_state["execution_mode"] == "auto" else 1
        )
        
        # Translate selection to simple key
        mode_key = "auto" if st.session_state["execution_mode"].startswith("Auto") else "step"
        st.session_state["execution_mode"] = mode_key
        
        col_act1, col_act2 = st.columns([3, 7])
        with col_act1:
            if st.button("🚀 Start Approved Plan"):
                st.session_state["pipeline_stage"] = "executing"
                st.session_state["current_step_idx"] = 0
                st.session_state["execution_steps"] = []
                st.session_state["execution_logs"] = []
                st.session_state["accumulated_extraction"] = ""
                st.session_state["start_time"] = time.time()
                st.rerun()
        with col_act2:
            if st.button("↩️ Re-generate Plan"):
                st.session_state["pipeline_stage"] = "input"
                st.rerun()
                
    elif stage == "executing":
        st.write(f"### ⚡ Running Agent Pipeline ({st.session_state['execution_mode'].upper()} Mode)")
        
        steps = st.session_state["plan_steps"]
        curr_idx = st.session_state["current_step_idx"]
        
        # Progress Indicator
        progress_pct = min(1.0, curr_idx / len(steps)) if steps else 1.0
        st.progress(progress_pct, text=f"Step {curr_idx}/{len(steps)} completed")
        
        # Setup page layouts
        col_left, col_right = st.columns([1, 1])
        
        with col_left:
            st.markdown("#### 📸 Live Browser Viewport")
            if st.session_state["screenshot_path"] and os.path.exists(st.session_state["screenshot_path"]):
                img = Image.open(st.session_state["screenshot_path"])
                st.image(img, use_container_width=True)
            else:
                st.info("Browser viewport is initializing...")
                
            # Manual Override Expandable Panel
            runner_ref = get_runner_safe()
            if runner_ref:
                with st.expander("🛠️ Interactive Manual Overrides", expanded=True):
                    st.markdown("<p style='font-size:12px; color:#8b949e;'>Inject commands directly into the active browser page at any time.</p>", unsafe_allow_html=True)
                    
                    ov_col1, ov_col2 = st.columns(2)
                    with ov_col1:
                        st.markdown("**Click Coordinates (1280x800)**")
                        x_coord = st.number_input("X Coordinate", min_value=0, max_value=1280, value=640)
                        y_coord = st.number_input("Y Coordinate", min_value=0, max_value=800, value=400)
                        if st.button("🖱️ Send Click"):
                            handle_manual_click(runner_ref, x_coord, y_coord)
                            st.rerun()
                            
                    with ov_col2:
                        st.markdown("**Keyboard Type (CSS Selector)**")
                        type_selector = st.text_input("Input Selector", placeholder="input[name='q']", key="ov_sel")
                        type_text = st.text_input("Text to Type", placeholder="Hello World", key="ov_txt")
                        if st.button("⌨️ Send Keystrokes"):
                            if type_selector and type_text:
                                handle_manual_type(runner_ref, type_selector, type_text)
                                st.rerun()
                            else:
                                st.error("Please fill in both selector and text fields.")
                                
                    st.markdown("**Direct Redirection**")
                    nav_url = st.text_input("Redirect URL", placeholder="https://example.com", key="ov_nav")
                    if st.button("🌐 Navigate Page"):
                        if nav_url:
                            handle_manual_navigate(runner_ref, nav_url)
                            st.rerun()
                            
        with col_right:
            st.markdown("#### 📜 Execution Logs")
            log_container = st.empty()
            
            # Print logs
            log_html = "".join([f"<div style='font-family:monospace; font-size:12px; margin-bottom:5px;'>{log}</div>" for log in st.session_state["execution_logs"]])
            log_container.markdown(f"<div style='border:1px solid #30363d; border-radius:6px; padding:10px; background-color:#0d1117; height:250px; overflow-y:auto;'>{log_html}</div>", unsafe_allow_html=True)
            
            # Print current state extraction
            if st.session_state["accumulated_extraction"]:
                st.markdown("#### 🔍 Extracted Web Data")
                st.markdown(st.session_state["accumulated_extraction"])
                
        # Main execution loop controller
        if st.session_state["execution_mode"] == "auto":
            # Auto play loop
            runner_ref = get_runner_safe()
            if runner_ref:
                while st.session_state["current_step_idx"] < len(steps):
                    idx = st.session_state["current_step_idx"]
                    step = steps[idx]
                    step_num = idx + 1
                    action = step.get("action", "")
                    
                    st.session_state["execution_logs"].append(f"🤖 Step {step_num}: Executing {action.upper()}...")
                    res = runner_ref.send_cmd("execute_action", step, step_num)
                    st.session_state["execution_steps"].append(res)
                    if res.get("screenshot_path"):
                        st.session_state["screenshot_path"] = res["screenshot_path"]
                        
                    if res["status"] == "error":
                        st.session_state["execution_logs"].append(f"🔴 Step {step_num} failed: {res['details']}")
                        st.session_state["pipeline_stage"] = "finished"
                        st.session_state["final_summary"] = f"Error occurred during step {step_num} ({action.upper()}): {res.get('details')}"
                        duration = time.time() - st.session_state["start_time"]
                        st.session_state["run_duration"] = duration
                        save_session_log(st.session_state["task_prompt"], steps, st.session_state["execution_steps"], st.session_state["final_summary"], duration=duration)
                        stop_runner_safe()
                        st.rerun()
                        
                    st.session_state["execution_logs"].append(f"🟢 Step {step_num} ({action.upper()}) completed: {res.get('details')}")
                    
                    if action.lower() == "extract":
                        extractor = ExtractorAgent(api_key=groq_key, model=groq_model, use_mock=use_mock)
                        target = step.get("target", "main text content")
                        state = runner_ref.send_cmd("get_current_state")
                        current_url = state.get("url", "")
                        html_content = state.get("html", "")
                        extracted_text = extractor.extract(html_content, target, current_url)
                        st.session_state["accumulated_extraction"] += f"\n--- EXTRACTION FROM {current_url} (Target: {target}) ---\n{extracted_text}\n"
                        
                    st.session_state["current_step_idx"] = idx + 1
                    st.rerun()
                    
                # Finished all steps
                st.session_state["execution_logs"].append("✍️ Summarizer Agent is active: Synthesizing final answer...")
                summarizer = SummarizerAgent(api_key=groq_key, model=groq_model, use_mock=use_mock)
                if not st.session_state["accumulated_extraction"]:
                    state = runner_ref.send_cmd("get_current_state")
                    current_url = state.get("url", "")
                    html_content = state.get("html", "")
                    extractor = ExtractorAgent(api_key=groq_key, model=groq_model, use_mock=use_mock)
                    st.session_state["accumulated_extraction"] = extractor.extract(html_content, "main content", current_url)
                    
                final_summary = summarizer.summarize(st.session_state["task_prompt"], st.session_state["accumulated_extraction"])
                st.session_state["final_summary"] = final_summary
                st.session_state["pipeline_stage"] = "finished"
                duration = time.time() - st.session_state["start_time"]
                st.session_state["run_duration"] = duration
                save_session_log(st.session_state["task_prompt"], steps, st.session_state["execution_steps"], final_summary, duration=duration)
                stop_runner_safe()
                st.rerun()
        else:
            # Step by Step mode controller
            runner_ref = get_runner_safe()
            if runner_ref:
                if curr_idx < len(steps):
                    next_step = steps[curr_idx]
                    st.write(f"**Upcoming Step:** `{next_step.get('action').upper()}` - {next_step}")
                    
                    col_run1, col_run2 = st.columns([3, 7])
                    with col_run1:
                        if st.button("➡️ Execute Step", key="btn_exec_step", help="Run the upcoming step and pause"):
                            step_num = curr_idx + 1
                            action = next_step.get("action", "")
                            
                            st.session_state["execution_logs"].append(f"🤖 Step {step_num}: Executing {action.upper()}...")
                            res = runner_ref.send_cmd("execute_action", next_step, step_num)
                            st.session_state["execution_steps"].append(res)
                            if res.get("screenshot_path"):
                                st.session_state["screenshot_path"] = res["screenshot_path"]
                                
                            if res["status"] == "error":
                                st.session_state["execution_logs"].append(f"🔴 Step {step_num} failed: {res['details']}")
                                st.session_state["pipeline_stage"] = "finished"
                                st.session_state["final_summary"] = f"Error occurred during step {step_num} ({action.upper()}): {res.get('details')}"
                                duration = time.time() - st.session_state["start_time"]
                                st.session_state["run_duration"] = duration
                                save_session_log(st.session_state["task_prompt"], steps, st.session_state["execution_steps"], st.session_state["final_summary"], duration=duration)
                                stop_runner_safe()
                                st.rerun()
                                
                            st.session_state["execution_logs"].append(f"🟢 Step {step_num} ({action.upper()}) completed: {res.get('details')}")
                            
                            if action.lower() == "extract":
                                extractor = ExtractorAgent(api_key=groq_key, model=groq_model, use_mock=use_mock)
                                target = next_step.get("target", "main text content")
                                state = runner_ref.send_cmd("get_current_state")
                                current_url = state.get("url", "")
                                html_content = state.get("html", "")
                                extracted_text = extractor.extract(html_content, target, current_url)
                                st.session_state["accumulated_extraction"] += f"\n--- EXTRACTION FROM {current_url} (Target: {target}) ---\n{extracted_text}\n"
                                
                            st.session_state["current_step_idx"] = curr_idx + 1
                            st.rerun()
                    with col_run2:
                        if st.button("⏹️ Terminate & Summarize", key="btn_term_step"):
                            st.session_state["execution_logs"].append("✍️ Summarizer Agent is active: Synthesizing final answer...")
                            summarizer = SummarizerAgent(api_key=groq_key, model=groq_model, use_mock=use_mock)
                            if not st.session_state["accumulated_extraction"]:
                                state = runner_ref.send_cmd("get_current_state")
                                current_url = state.get("url", "")
                                html_content = state.get("html", "")
                                extractor = ExtractorAgent(api_key=groq_key, model=groq_model, use_mock=use_mock)
                                st.session_state["accumulated_extraction"] = extractor.extract(html_content, "main content", current_url)
                                
                            final_summary = summarizer.summarize(st.session_state["task_prompt"], st.session_state["accumulated_extraction"])
                            st.session_state["final_summary"] = final_summary
                            st.session_state["pipeline_stage"] = "finished"
                            duration = time.time() - st.session_state["start_time"]
                            st.session_state["run_duration"] = duration
                            save_session_log(st.session_state["task_prompt"], steps, st.session_state["execution_steps"], final_summary, duration=duration)
                            stop_runner_safe()
                            st.rerun()
                else:
                    # We executed all steps but didn't summarize yet
                    st.session_state["execution_logs"].append("✍️ Summarizer Agent is active: Synthesizing final answer...")
                    summarizer = SummarizerAgent(api_key=groq_key, model=groq_model, use_mock=use_mock)
                    if not st.session_state["accumulated_extraction"]:
                        state = runner_ref.send_cmd("get_current_state")
                        current_url = state.get("url", "")
                        html_content = state.get("html", "")
                        extractor = ExtractorAgent(api_key=groq_key, model=groq_model, use_mock=use_mock)
                        st.session_state["accumulated_extraction"] = extractor.extract(html_content, "main content", current_url)
                        
                    final_summary = summarizer.summarize(st.session_state["task_prompt"], st.session_state["accumulated_extraction"])
                    st.session_state["final_summary"] = final_summary
                    st.session_state["pipeline_stage"] = "finished"
                    duration = time.time() - st.session_state["start_time"]
                    st.session_state["run_duration"] = duration
                    save_session_log(st.session_state["task_prompt"], steps, st.session_state["execution_steps"], final_summary, duration=duration)
                    stop_runner_safe()
                    st.rerun()
                    
    elif stage == "finished":
        st.success("✅ **Web Automation Task Complete!**")
        st.write(f"⏱️ **Execution Duration:** `{st.session_state['run_duration']:.1f}` seconds")
        
        col_res1, col_res2 = st.columns([1, 1])
        with col_res1:
            st.write("### 📸 Final Web Viewport")
            if st.session_state["screenshot_path"] and os.path.exists(st.session_state["screenshot_path"]):
                st.image(Image.open(st.session_state["screenshot_path"]), use_container_width=True)
            else:
                st.info("No screenshot captured.")
                
        with col_res2:
            st.write("### 📄 Synthesized Final Summary")
            st.markdown(st.session_state["final_summary"])
            if use_mock:
                st.warning("⚠️ **Note:** The agent is running in **Mock LLM (Offline Mode)**. All search results, flight details, and hyperlinks (e.g., `https://example.com/book`) are simulated templates designed for testing. To browse live websites and fetch real clickable links, uncheck **Use Mock LLM (Offline Mode)** in the sidebar and enter your **Groq API Key**.")
            
        if st.button("🚀 Start a New Task"):
            st.session_state["pipeline_stage"] = "input"
            st.session_state["plan_steps"] = []
            st.session_state["task_prompt"] = ""
            st.session_state["screenshot_path"] = ""
            st.session_state["final_summary"] = ""
            st.rerun()


with tab2:
    loaded_run = st.session_state.get("loaded_run")
    if loaded_run:
        st.write(f"### Historical Run details: {loaded_run.get('timestamp')}")
        st.markdown(f"**Task Prompt:** *{loaded_run.get('prompt')}*")
        st.write(f"⏱️ **Duration:** `{loaded_run.get('duration', 0.0):.1f}` seconds")
        
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

with tab3:
    st.write("## 📊 Advanced Analytics Dashboard")
    
    # Reload history log files
    history_logs = load_history()
    if not history_logs:
        st.info("No saved logs found to analyze. Run some tasks to generate execution history.")
    else:
        import pandas as pd
        
        rows = []
        for log in history_logs:
            timestamp = log.get("timestamp", "")
            try:
                date_val = datetime.fromisoformat(timestamp)
            except Exception:
                date_val = datetime.now()
            
            steps = log.get("steps", [])
            success = True
            if steps:
                if any(s.get("status") == "error" for s in steps):
                    success = False
            
            summary = log.get("final_summary", "")
            if "error" in summary.lower():
                success = False
                
            duration = log.get("duration", 0.0)
            if duration <= 0.0:
                duration = len(steps) * 8.0 + 5.0  # realistic estimate
                
            rows.append({
                "date": date_val.date(),
                "datetime": date_val,
                "prompt": log.get("prompt", ""),
                "success": success,
                "duration": duration,
                "steps_count": len(steps)
            })
            
        df = pd.DataFrame(rows)
        
        # Metrics Row
        total_runs = len(df)
        successes = df["success"].sum()
        success_rate = (successes / total_runs) * 100 if total_runs > 0 else 0.0
        avg_duration = df["duration"].mean() if total_runs > 0 else 0.0
        
        m_col1, m_col2, m_col3 = st.columns(3)
        with m_col1:
            st.metric("Total Executions", f"{total_runs}", help="Total number of tasks run")
        with m_col2:
            st.metric("Success Rate", f"{success_rate:.1f}%", help="Percentage of tasks completed successfully")
        with m_col3:
            st.metric("Avg Duration", f"{avg_duration:.1f}s", help="Average execution time per task")
            
        st.write("---")
        
        # Charts Row
        c_col1, c_col2 = st.columns(2)
        with c_col1:
            st.write("#### Executions per Day")
            runs_per_day = df.groupby("date").size().reset_index(name="runs").set_index("date")
            st.bar_chart(runs_per_day)
            
        with c_col2:
            st.write("#### Execution Durations (Seconds)")
            df_sorted = df.sort_values("datetime")
            durations_df = df_sorted[["datetime", "duration"]].set_index("datetime")
            st.line_chart(durations_df)
            
        st.write("---")
        st.write("### 🖼️ Visual Runs Gallery")
        
        # Card list of history runs
        gallery_cols = st.columns(3)
        for idx, row in df.iterrows():
            col_idx = idx % 3
            with gallery_cols[col_idx]:
                status_color = "#3fb950" if row["success"] else "#f85149"
                status_badge = "🟢 SUCCESS" if row["success"] else "🔴 FAILED"
                
                with st.container():
                    st.markdown(
                        f"""
                        <div style="border:1px solid #30363d; border-radius:8px; padding:15px; background-color:#161b22; margin-bottom:15px;">
                            <span style="font-size:11px; color:#8b949e;">{row['datetime'].strftime('%Y-%m-%d %H:%M:%S')}</span>
                            <h4 style="margin:5px 0; color:#58a6ff; font-size:14px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">{row['prompt']}</h4>
                            <div style="display:flex; justify-content:space-between; margin-top:10px;">
                                <span style="font-weight:bold; font-size:12px; color:{status_color};">{status_badge}</span>
                                <span style="font-size:12px; color:#8b949e;">⏱️ {row['duration']:.1f}s</span>
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True
                    )
                    
                    if st.button("Inspect Details", key=f"inspect_gallery_{idx}"):
                        st.session_state["loaded_run"] = history_logs[idx]
                        st.session_state["active_tab"] = "History & Detail Viewer"
                        st.rerun()
