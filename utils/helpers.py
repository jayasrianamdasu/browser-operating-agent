import os
import json
import logging
from datetime import datetime
from bs4 import BeautifulSoup
import config

logger = logging.getLogger("browser_agent.helpers")

def clean_html(html_content: str, max_chars: int = 15000) -> str:
    """
    Cleans raw HTML by removing unnecessary tags (scripts, styles, head, svgs)
    to save token usage and fits content within LLM context window limits.
    """
    if not html_content:
        return ""
    
    try:
        soup = BeautifulSoup(html_content, "html.parser")
        
        # Remove script, style, head, nav, footer, noscript, svg, iframe, meta
        for element in soup(["script", "style", "head", "noscript", "svg", "iframe", "meta", "header", "footer"]):
            element.decompose()
            
        # Extract text and links
        cleaned_lines = []
        for element in soup.find_all(text=True):
            text = element.strip()
            if text:
                parent = element.parent
                # If element is an anchor link, format as 'Text (Link: href)'
                if parent and parent.name == "a" and parent.has_attr("href"):
                    href = parent["href"]
                    # If relative link, we keep it as is
                    cleaned_lines.append(f"{text} (Link: {href})")
                else:
                    cleaned_lines.append(text)
                    
        cleaned_text = "\n".join(cleaned_lines)
        
        # Limit size to prevent LLM context overflow
        if len(cleaned_text) > max_chars:
            cleaned_text = cleaned_text[:max_chars] + "\n... [HTML Content Truncated for Token Limit] ..."
            
        return cleaned_text
    except Exception as e:
        logger.error(f"Error cleaning HTML: {e}")
        return html_content[:max_chars]

def save_session_log(prompt: str, plan: list, steps: list, final_summary: str, logs_dir: str = None) -> str:
    """
    Saves the session logs to a JSON file.
    """
    if logs_dir is None:
        logs_dir = config.LOGS_DIR
        
    if not os.path.exists(logs_dir):
        os.makedirs(logs_dir)
        
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    task_id = f"session_{timestamp_str}"
    
    log_data = {
        "task_id": task_id,
        "timestamp": datetime.now().isoformat(),
        "prompt": prompt,
        "plan": plan,
        "steps": steps,  # Each step has: action, details, screenshot_path, status, log
        "final_summary": final_summary
    }
    
    file_path = os.path.join(logs_dir, f"{task_id}.json")
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(log_data, f, indent=4, ensure_ascii=False)
        logger.info(f"Session log saved to {file_path}")
        return file_path
    except Exception as e:
        logger.error(f"Failed to save session log: {e}")
        return ""

def load_history(logs_dir: str = None) -> list:
    """
    Loads all saved session logs from the logs directory, sorted by timestamp descending.
    """
    if logs_dir is None:
        logs_dir = config.LOGS_DIR
        
    if not os.path.exists(logs_dir):
        return []
        
    history = []
    for file_name in os.listdir(logs_dir):
        if file_name.endswith(".json"):
            file_path = os.path.join(logs_dir, file_name)
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    log_data = json.load(f)
                    history.append(log_data)
            except Exception as e:
                logger.error(f"Failed to read log file {file_path}: {e}")
                
    # Sort by timestamp descending
    history.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return history
