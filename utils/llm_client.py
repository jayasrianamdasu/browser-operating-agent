import json
import logging
import re
import urllib.parse
from groq import Groq
import config

logger = logging.getLogger("browser_agent.llm_client")

def call_llm(prompt: str, system_prompt: str = None, json_mode: bool = False, api_key: str = None, model: str = None, use_mock: bool = None) -> str:
    """
    Dispatches LLM calls to Groq API or to the offline Mock LLM client.
    """
    if use_mock is None:
        use_mock = config.USE_MOCK_LLM

    if use_mock:
        return call_mock_llm(prompt, system_prompt, json_mode)
    
    # Real Groq mode
    key = api_key or config.GROQ_API_KEY
    if not key or key == "your-key-here":
        raise ValueError(
            "Groq API Key is not set. Please provide a valid key in config.py, .env, or the Streamlit sidebar."
        )
    
    model_name = model or config.GROQ_MODEL
    
    client = Groq(api_key=key)
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    
    kwargs = {}
    if json_mode:
        # Groq supports response_format for JSON mode
        kwargs["response_format"] = {"type": "json_object"}
        
    try:
        completion = client.chat.completions.create(
            model=model_name,
            messages=messages,
            temperature=0.1,
            **kwargs
        )
        return completion.choices[0].message.content
    except Exception as e:
        logger.error(f"Error calling Groq API: {e}")
        raise e

def call_mock_llm(prompt: str, system_prompt: str = None, json_mode: bool = False) -> str:
    """
    Simulates LLM completions with high fidelity for standard queries.
    Allows running the entire project offline and free of cost.
    """
    prompt_lower = prompt.lower()
    system_lower = (system_prompt or "").lower()
    
    # 1. Determine if this is a Planner request
    # Use "planner" instead of "plan" to avoid matching "meta-explanations" in the Extractor's system prompt
    is_planner = "planner" in system_lower or "list of steps" in prompt_lower
    
    # 2. Determine if this is an Extractor request
    is_extractor = "extractor" in system_lower or "extract" in system_lower or "page content" in prompt_lower or "raw html" in prompt_lower
    
    # 3. Determine if this is a Summarizer request
    is_summarizer = "summarizer" in system_lower or "summarize" in system_lower or "final answer" in prompt_lower

    if is_planner:
        # Planner mock logic
        if any(w in prompt_lower for w in ["hacker news", "ycombinator", "hn"]):
            plan = {
                "plan": [
                    {"action": "navigate", "url": "https://news.ycombinator.com"},
                    {"action": "extract", "target": "top 3 story titles and links"}
                ]
            }
        elif "wikipedia" in prompt_lower:
            plan = {
                "plan": [
                    {"action": "navigate", "url": "https://en.wikipedia.org/wiki/Main_Page"},
                    {"action": "type", "selector": "input[name='search']", "text": "Artificial Intelligence"},
                    {"action": "click", "selector": "input[name='go'], button:has-text('Search'), input[type='submit']"},
                    {"action": "wait", "seconds": 2},
                    {"action": "extract", "target": "summary paragraph"}
                ]
            }
        else:
            # Dynamic query extraction
            query = prompt.replace("Task:", "").strip()
            # Clean common command prefixes
            for verb in ["search for", "search", "find me", "find the", "find", "show me", "show", "get me", "get"]:
                if query.lower().startswith(verb):
                    query = query[len(verb):].strip()
            query = query.strip('"').strip("'").strip(".").strip()
            if not query:
                query = "latest AI news"
                
            plan = {
                "plan": [
                    {"action": "search", "query": query},
                    {"action": "extract", "target": f"top 3 search results for {query}"}
                ]
            }
        return json.dumps(plan, indent=2)

    elif is_extractor:
        # Extractor mock logic
        if "news.ycombinator.com" in prompt_lower:
            return (
                "Extracted Stories from Hacker News:\n"
                "1. OpenAI Releases GPT-5 with Advanced Browser Integration (Link: https://news.ycombinator.com/item?id=45192031) - 425 points by user 'techcrunch'\n"
                "2. Show HN: Antigravity - An Autonomous Agent Framework (Link: https://news.ycombinator.com/item?id=45191540) - 180 points by user 'googledm'\n"
                "3. The Future of Web Automation and Playwright (Link: https://news.ycombinator.com/item?id=45189211) - 95 points by user 'browserdev'"
            )
        elif "wikipedia.org" in prompt_lower or "wikipedia" in prompt_lower:
            return (
                "Extracted content from Wikipedia:\n"
                "Artificial intelligence (AI) is intelligence—perceiving, synthesizing, and inferring information—demonstrated by machines, "
                "as opposed to intelligence displayed by non-human animals and humans. Example applications include advanced web search engines, "
                "recommendation systems, understanding human speech, self-driving cars, generative tools, and competing at the highest level in strategic games."
            )
        elif any(w in prompt_lower for w in ["flight", "ticket", "bangalore", "hyderabad"]):
            from utils.helpers import extract_cities_from_query, generate_random_flights
            origin, origin_code, destination, dest_code = extract_cities_from_query(url="", query=prompt)
            flights = generate_random_flights(origin_code, dest_code, query=prompt)
            f1, f2, f3 = flights[0], flights[1], flights[2]
            return (
                f"Extracted flight information from search results:\n"
                f"1. {f1['airline']} {f1['flight_num']}: {origin} ({origin_code}) to {destination} ({dest_code}) - Price: {f1['price']} (Link: https://example.com/book) - Departs {f1['dep_time']}, Duration {f1['duration']}.\n"
                f"2. {f2['airline']} {f2['flight_num']}: {origin} ({origin_code}) to {destination} ({dest_code}) - Price: {f2['price']} (Link: https://example.com/book) - Departs {f2['dep_time']}, Duration {f2['duration']}.\n"
                f"3. {f3['airline']} {f3['flight_num']}: {origin} ({origin_code}) to {destination} ({dest_code}) - Price: {f3['price']} (Link: https://example.com/book) - Departs {f3['dep_time']}, Duration {f3['duration']}."
            )
        elif "duckduckgo.com" in prompt_lower or "search" in prompt_lower:
            # Extract query from url or prompt
            query = "your search term"
            match = re.search(r"q=([^&\s\)]+)", prompt_lower)
            if match:
                query = urllib.parse.unquote_plus(match.group(1))
            else:
                match = re.search(r"results for ([^'\"]+)", prompt_lower)
                if match:
                    query = match.group(1).strip()
                    
            return (
                f"Extracted DuckDuckGo results for query: '{query}':\n"
                f"1. Top Result: Best guides and discussions for {query} (Link: https://example.com/search-result-1) - Detailed information on {query}.\n"
                f"2. News update: Latest updates and releases for {query} (Link: https://example.com/search-result-2) - Industry reports for {query}.\n"
                f"3. Community thread: Tips, tricks, and tutorials on {query} (Link: https://example.com/search-result-3) - Q&A on {query}."
            )
        else:
            return (
                "Extracted content from Example Domain:\n"
                "- Heading: Example Domain\n"
                "- Description: This domain is established to be used for illustrative examples in documents. You do not need to request prior permission.\n"
                "- Link: More information... (https://www.iana.org/domains/reserved)"
            )

    elif is_summarizer:
        # Summarizer mock logic
        if "hacker news" in prompt_lower or "ycombinator" in prompt_lower:
            return (
                "### Hacker News Top Stories Summary\n\n"
                "I have successfully navigated to **Hacker News** and retrieved the top stories:\n\n"
                "1. **OpenAI GPT-5 Release**: A major announcement on GPT-5's capability with advanced agentic systems, receiving high engagement (425 points).\n"
                "2. **Antigravity Framework**: A new autonomous multi-agent framework showcased in Show HN (180 points).\n"
                "3. **Future of Web Automation**: A discussion detailing how Playwright and async web scrapers are critical to LLM execution.\n\n"
                "Overall, the community is highly focused on **agentic architectures** and **browser automation**."
            )
        elif "wikipedia" in prompt_lower:
            return (
                "### Wikipedia: Artificial Intelligence Summary\n\n"
                "According to Wikipedia, **Artificial Intelligence (AI)** is defined as intelligence demonstrated by machines (perceiving, synthesizing, and inferring information), contrasting with natural intelligence.\n\n"
                "**Key Highlights:**\n"
                "- **Applications**: Includes search engines, recommendation engines, natural language speech understanding, autonomous vehicles, and generative tools.\n"
                "- **Scope**: Combines computer science, linguistics, mathematics, and engineering to build systems that automate cognitive tasks."
            )
        elif any(w in prompt_lower for w in ["flight", "ticket", "bangalore", "hyderabad"]):
            from utils.helpers import extract_cities_from_query, generate_random_flights
            origin, origin_code, destination, dest_code = extract_cities_from_query(url="", query=prompt)
            flights = generate_random_flights(origin_code, dest_code, query=prompt)
            f1, f2, f3 = flights[0], flights[1], flights[2]
            return (
                f"### ✈️ Cheapest Flights from {origin} to {destination}\n\n"
                f"Here are the top flight options retrieved from the search results:\n\n"
                f"1. **{f1['airline']} ({f1['flight_num']})**: **{f1['price']}** (Cheapest option) - Departs at {f1['dep_time']}, {f1['duration']} duration. [Book flight](https://example.com/book)\n"
                f"2. **{f2['airline']} ({f2['flight_num']})**: **{f2['price']}** - Departs at {f2['dep_time']}, {f2['duration']} duration. [Book flight](https://example.com/book)\n"
                f"3. **{f3['airline']} ({f3['flight_num']})**: **{f3['price']}** - Departs at {f3['dep_time']}, {f3['duration']} duration. [Book flight](https://example.com/book)\n\n"
                f"All flights are direct. Prices are subject to availability."
            )
        else:
            # Extract query
            query = "your search term"
            match = re.search(r"query: '([^']+)'", prompt_lower)
            if match:
                query = match.group(1)
            else:
                match = re.search(r"results for ([^'\"]+)", prompt_lower)
                if match:
                    query = match.group(1).strip()
            return (
                f"### 🔍 Search Summary for '{query}'\n\n"
                f"I have successfully searched DuckDuckGo for **'{query}'** and analyzed the results:\n\n"
                f"* **Top Guide**: Displays high engagement details regarding **{query}**. [View Guide](https://example.com/search-result-1)\n"
                f"* **News & Releases**: Documents recent product highlights and community discussions concerning **{query}**. [View News](https://example.com/search-result-2)\n"
                f"* **Tips & Tutorials**: Useful community troubleshooting and code references for **{query}**. [View Community](https://example.com/search-result-3)\n\n"
                f"The overall search results demonstrate active developer interest and a wide range of learning resources available for **{query}**."
            )
    
    # Generic mock response if none matched
    if json_mode:
        return '{"result": "Success", "data": "Mock data generated"}'
    return "This is a fallback mock response from the offline LLM client."
