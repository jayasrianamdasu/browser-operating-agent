import json
import logging
import re
from utils.llm_client import call_llm

logger = logging.getLogger("browser_agent.planner")

class PlannerAgent:
    def __init__(self, api_key: str = None, model: str = None, use_mock: bool = True):
        self.api_key = api_key
        self.model = model
        self.use_mock = use_mock

    def get_system_prompt(self) -> str:
        return (
            "You are the Planner Agent of a Browser Operating Agent system. Your job is to break down a user's "
            "natural language web task into a sequence of execution steps.\n"
            "You must output a JSON object containing a single key 'plan', which is a list of step dictionaries.\n"
            "Each step must specify an 'action' and action-specific keys. Supported actions:\n"
            "1. 'navigate': Go to a URL. Requires key 'url' (e.g. 'https://news.ycombinator.com').\n"
            "2. 'search': Search using DuckDuckGo. Requires key 'query'.\n"
            "3. 'click': Click an element. Requires key 'selector' (CSS selector or button text like 'button:has-text(\"Submit\")').\n"
            "4. 'type': Type text into an input. Requires keys 'selector' and 'text'.\n"
            "5. 'scroll': Scroll the page. Requires key 'direction' ('down' or 'up').\n"
            "6. 'wait': Asynchronous wait. Requires key 'seconds' (integer, e.g. 2).\n"
            "7. 'extract': Get structured text for a target. Requires key 'target' (description of what to extract).\n\n"
            "CRITICAL DESIGN RULE: For general web search, lookup, or query tasks (such as searching for flight tickets, news, or general terms), "
            "you MUST prefer using the high-level 'search' action directly rather than a manual sequence of 'navigate' + 'type' + 'click'. "
            "This is because manual typing and clicking on major search engines triggers Captcha/bot-blocking. "
            "Use manual navigate/type/click only when visiting specific non-search sites like Wikipedia or Hacker News.\n\n"
            "Format example:\n"
            "{\n"
            "  \"plan\": [\n"
            "    {\"action\": \"navigate\", \"url\": \"https://news.ycombinator.com\"},\n"
            "    {\"action\": \"extract\", \"target\": \"top 3 stories and links\"}\n"
            "  ]\n"
            "}\n\n"
            "Keep the plans concise and efficient (usually 2 to 6 steps). Output ONLY valid JSON."
        )

    def plan(self, task: str) -> list:
        """
        Generates a sequence of steps for the task.
        """
        logger.info(f"Generating plan for task: '{task}'")
        system_prompt = self.get_system_prompt()
        
        try:
            response = call_llm(
                prompt=f"Task: {task}",
                system_prompt=system_prompt,
                json_mode=True,
                api_key=self.api_key,
                model=self.model,
                use_mock=self.use_mock
            )
            
            # Clean markdown code fences if LLM wrapped them in ```json
            cleaned_response = response.strip()
            if cleaned_response.startswith("```"):
                # strip opening tag
                cleaned_response = re.sub(r"^```(?:json)?\n", "", cleaned_response)
                # strip closing tag
                cleaned_response = re.sub(r"\n```$", "", cleaned_response)
            cleaned_response = cleaned_response.strip()
            
            parsed = json.loads(cleaned_response)
            plan = parsed.get("plan", [])
            
            if not isinstance(plan, list):
                raise ValueError("Parsed JSON does not contain a list of steps in 'plan'.")
                
            logger.info(f"Plan generated successfully with {len(plan)} steps.")
            return plan
            
        except Exception as e:
            logger.error(f"Failed to generate or parse plan: {e}. Falling back to basic default plan.")
            # Fallback simple plan based on keywords
            task_lower = task.lower()
            if "wikipedia" in task_lower:
                return [
                    {"action": "navigate", "url": "https://en.wikipedia.org/wiki/Main_Page"},
                    {"action": "type", "selector": "input[name='search']", "text": "Artificial Intelligence"},
                    {"action": "click", "selector": "button:has-text('Search'), input[type='submit']"},
                    {"action": "wait", "seconds": 2},
                    {"action": "extract", "target": "wikipedia article intro"}
                ]
            elif "hacker news" in task_lower or "ycombinator" in task_lower or "hn" in task_lower:
                return [
                    {"action": "navigate", "url": "https://news.ycombinator.com"},
                    {"action": "extract", "target": "top 3 story titles and links"}
                ]
            else:
                # Default search
                query = "latest AI news"
                return [
                    {"action": "search", "query": query},
                    {"action": "extract", "target": f"top 3 search results for {query}"}
                ]
