import os
import json
import logging
import re
import urllib.parse
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

def save_session_log(prompt: str, plan: list, steps: list, final_summary: str, duration: float = 0.0, logs_dir: str = None) -> str:
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
        "final_summary": final_summary,
        "duration": duration
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


def extract_cities_from_query(url: str, query: str = "") -> tuple:
    """
    Extracts origin and destination cities and their airport codes from a query or search URL.
    Defaults to ('Bangalore', 'BLR', 'Hyderabad', 'HYD').
    """
    import urllib.parse
    
    origin = "Bangalore"
    origin_code = "BLR"
    destination = "Hyderabad"
    dest_code = "HYD"
    
    # 1. Extract query from URL if query is not provided
    if not query and url:
        try:
            parsed_url = urllib.parse.urlparse(url)
            params = urllib.parse.parse_qs(parsed_url.query)
            if "q" in params:
                query = params["q"][0]
        except Exception:
            pass
            
    if not query:
        return origin, origin_code, destination, dest_code
        
    query_lower = query.lower()
    
    # Check if there is " to " in the query, which is standard for flight routing
    if " to " in query_lower:
        # Split by " to " to find parts before and after
        parts = query_lower.split(" to ", 1)
        before_to = parts[0].strip()
        after_to = parts[1].strip()
        
        # Origin candidate is the last words of before_to
        # Let's extract origin candidate by removing common leading search noise
        origin_candidate = before_to
        noises = [
            "cheapest flight tickets from ",
            "cheapest flights from ",
            "cheapest tickets from ",
            "flight options from ",
            "cheapest flight from ",
            "flights from ",
            "flight from ",
            "tickets from ",
            "ticket from ",
            "cheapest flights ",
            "cheapest flight ",
            "search for ",
            "flights ",
            "flight ",
            "search ",
            "from ",
        ]
        for noise in noises:
            if origin_candidate.startswith(noise):
                origin_candidate = origin_candidate[len(noise):].strip()
            # If the noise term is inside, extract the part after it
            if " " + noise in origin_candidate:
                origin_candidate = origin_candidate.split(" " + noise)[-1].strip()
                
        # Destination candidate is the first words of after_to
        dest_candidate = after_to
        # Clean trailing noise using stopwords
        for stopword in [" and ", " show ", " list ", " with ", " for ", " next ", " this ", " cheapest "]:
            if stopword in f" {dest_candidate} ":
                dest_candidate = dest_candidate.split(stopword)[0].strip()
                
        if origin_candidate:
            origin = origin_candidate.title()
            origin_code = "".join([w[0] for w in origin.split() if w])[:3].upper()
            if len(origin_code) < 3:
                origin_code = origin[:3].upper()
                
        if dest_candidate:
            destination = dest_candidate.title()
            dest_code = "".join([w[0] for w in destination.split() if w])[:3].upper()
            if len(dest_code) < 3:
                dest_code = destination[:3].upper()
                
    # Specific common overrides for airport codes to make it look premium
    airport_overrides = {
        "Bangalore": "BLR",
        "Hyderabad": "HYD",
        "San Francisco": "SFO",
        "Tokyo": "NRT",
        "Delhi": "DEL",
        "New York": "JFK",
        "London": "LHR",
        "Singapore": "SIN",
        "Paris": "CDG",
        "Houston": "IAH",
        "India": "DEL",
    }
    if origin in airport_overrides:
        origin_code = airport_overrides[origin]
    if destination in airport_overrides:
        dest_code = airport_overrides[destination]
        
    return origin, origin_code, destination, dest_code


def generate_random_flights(origin_code: str, dest_code: str, query: str) -> list:
    """
    Generates a deterministic list of 3 mock flights based on the query.
    """
    import hashlib
    import random
    
    query_lower = (query or "").lower()
    seed_val = int(hashlib.md5(query_lower.encode('utf-8')).hexdigest(), 16)
    
    # Save current random state and restore it later to avoid side effects
    state = random.getstate()
    random.seed(seed_val)
    
    intl_airlines = [
        ("United Airlines", "UA"),
        ("Delta Air Lines", "DL"),
        ("Japan Airlines", "JL"),
        ("ANA Flights", "NH"),
        ("Singapore Airlines", "SQ"),
        ("Emirates", "EK"),
        ("British Airways", "BA"),
        ("Lufthansa", "LH")
    ]
    domestic_airlines = [
        ("IndiGo", "6E"),
        ("Air India", "AI"),
        ("Akasa Air", "QP"),
        ("SpiceJet", "SG"),
        ("Vistara", "UK")
    ]
    
    is_intl = any(c in ["SFO", "NRT", "JFK", "LHR", "SIN", "CDG", "IAH", "DEL"] for c in [origin_code, dest_code]) or \
              any(w in query_lower for w in ["tokyo", "london", "singapore", "paris", "francisco", "york", "international", "japan", "england", "uk", "usa", "houston", "india", "delhi", "iah", "nrt"])
              
    airline_pool = intl_airlines if is_intl else domestic_airlines
    
    flights = []
    # Make sure we don't sample more than available pool size
    sample_size = min(3, len(airline_pool))
    selected_airlines = random.sample(airline_pool, sample_size)
    
    # Pad selected airlines if not enough
    while len(selected_airlines) < 3:
        selected_airlines.append(random.choice(airline_pool))
    
    for idx, (airline, code) in enumerate(selected_airlines):
        flight_num = f"{code}-{random.randint(100, 999)}"
        
        # Departure/arrival times
        dep_hour = random.randint(5, 22)
        dep_min = random.choice([0, 15, 30, 45])
        dep_time = f"{dep_hour:02d}:{dep_min:02d}"
        
        # Duration & Arrival
        dur_hours = random.randint(8, 16) if is_intl else random.randint(1, 3)
        dur_mins = random.choice([0, 15, 30, 45])
        dur_str = f"{dur_hours}h {dur_mins}m"
        
        arr_hour = (dep_hour + dur_hours) % 24
        arr_min = (dep_min + dur_mins) % 60
        arr_time = f"{arr_hour:02d}:{arr_min:02d}"
        
        # Price
        if is_intl:
            price = f"USD {random.randint(450, 1250)}"
        else:
            price = f"INR {random.randint(3100, 7900):,}"
            
        flights.append({
            "airline": airline,
            "flight_num": flight_num,
            "dep_time": dep_time,
            "arr_time": arr_time,
            "duration": dur_str,
            "price": price
        })
        
    random.setstate(state)
    return flights


def generate_mock_screenshot(url: str, action: str, path: str):
    """
    Generates a beautiful mock browser screenshot representing the current step.
    Prevents network-block blank screenshots when running on cloud servers in Mock Mode.
    """
    from PIL import Image, ImageDraw
    
    # Check if light or dark theme based on site
    url_lower = url.lower()
    is_dark = "ycombinator" not in url_lower and "wikipedia" not in url_lower
    bg_color = "#1e1e1e" if is_dark else "#ffffff"
    text_primary = "#ffffff" if is_dark else "#000000"
    text_secondary = "#8b949e" if is_dark else "#555555"
    text_link = "#58a6ff" if is_dark else "#0066cc"
    
    img = Image.new("RGB", (1280, 800), color=bg_color)
    draw = ImageDraw.Draw(img)
    
    # Safe text drawing helper to handle slim Linux environments without fonts
    def draw_text_safe(pos, text_val, fill_color):
        try:
            draw.text(pos, text_val, fill=fill_color)
        except Exception:
            pass
            
    # Draw browser control bar
    header_color = "#2d2d2d" if is_dark else "#f0f0f0"
    draw.rectangle([0, 0, 1280, 60], fill=header_color)
    
    # Draw window dots (red, yellow, green)
    draw.ellipse([15, 22, 27, 34], fill="#ff5f56")
    draw.ellipse([35, 22, 47, 34], fill="#ffbd2e")
    draw.ellipse([55, 22, 67, 34], fill="#27c93f")
    
    # Draw address bar
    address_bg = "#1e1e1e" if is_dark else "#ffffff"
    address_border = "#444444" if is_dark else "#cccccc"
    draw.rectangle([100, 15, 1180, 45], fill=address_bg, outline=address_border)
    draw_text_safe((120, 23), url, fill_color=text_secondary)
    
    if "news.ycombinator.com" in url_lower:
        # Hacker News Layout
        draw.rectangle([0, 60, 1280, 85], fill="#ff6600")
        draw_text_safe((20, 66), "Hacker News  |  new | past | comments | ask | show | jobs | submit", fill_color="#000000")
        
        draw_text_safe((30, 110), "1. OpenAI Releases GPT-5 with Advanced Browser Integration (news.ycombinator.com)", fill_color="#000000")
        draw_text_safe((45, 130), "425 points by techcrunch 2 hours ago | 102 comments", fill_color="#828282")
        
        draw_text_safe((30, 170), "2. Show HN: Antigravity - An Autonomous Agent Framework (github.com/googledm)", fill_color="#000000")
        draw_text_safe((45, 190), "180 points by googledm 4 hours ago | 45 comments", fill_color="#828282")
        
        draw_text_safe((30, 230), "3. The Future of Web Automation and Playwright (browserdev.org)", fill_color="#000000")
        draw_text_safe((45, 250), "95 points by browserdev 5 hours ago | 20 comments", fill_color="#828282")
        
    elif "wikipedia.org" in url_lower:
        # Wikipedia Layout
        draw.rectangle([0, 60, 1280, 100], fill="#f8f9fa")
        draw_text_safe((50, 75), "WIKIPEDIA  -  The Free Encyclopedia", fill_color="#000000")
        
        draw_text_safe((50, 130), "Artificial Intelligence", fill_color="#000000")
        draw_text_safe((50, 150), "From Wikipedia, the free encyclopedia", fill_color="#555555")
        
        wiki_text = (
            "Artificial intelligence (AI) is intelligence-perceiving, synthesizing, and inferring information-\n"
            "demonstrated by machines, as opposed to intelligence displayed by non-human animals and humans.\n"
            "Example applications include advanced web search engines, recommendation systems, understanding human speech,\n"
            "self-driving cars, generative tools, and competing at the highest level in strategic games."
        )
        draw_text_safe((50, 190), wiki_text, fill_color="#000000")
        
    elif any(w in url_lower for w in ["flight", "ticket", "bangalore", "hyderabad", "houston", "india", "sfo", "tokyo"]):
        # Flight search Layout
        origin, origin_code, destination, dest_code = extract_cities_from_query(url)
        flights = generate_random_flights(origin_code, dest_code, url)
        
        draw_text_safe((50, 100), f"Cheapest Flights: {origin} ({origin_code}) to {destination} ({dest_code})", fill_color=text_primary)
        
        draw.rectangle([50, 130, 1180, 320], outline=address_border, width=1)
        f1, f2, f3 = flights[0], flights[1], flights[2]
        draw_text_safe((70, 150), f"{f1['airline']} {f1['flight_num']}  |  {f1['dep_time']} - {f1['arr_time']}  |  Direct  |  {f1['duration']}  |  Price: {f1['price']}", fill_color=text_primary)
        draw_text_safe((70, 180), f"Book {f1['airline']} flight ticket online...", fill_color=text_link)
        
        draw_text_safe((70, 210), f"{f2['airline']} {f2['flight_num']}  |  {f2['dep_time']} - {f2['arr_time']}  |  Direct  |  {f2['duration']}  |  Price: {f2['price']}", fill_color=text_primary)
        draw_text_safe((70, 240), f"Book {f2['airline']} flight ticket online...", fill_color=text_link)
        
        draw_text_safe((70, 270), f"{f3['airline']} {f3['flight_num']}  |  {f3['dep_time']} - {f3['arr_time']}  |  Direct  |  {f3['duration']}  |  Price: {f3['price']}", fill_color=text_primary)
        draw_text_safe((70, 300), f"Book {f3['airline']} flight ticket online...", fill_color=text_link)
        
    elif "duckduckgo" in url_lower or "search" in action:
        # Generic DuckDuckGo layout
        query = "your search term"
        match = re.search(r"q=([^&]+)", url_lower)
        if match:
            query = urllib.parse.unquote_plus(match.group(1))
            
        draw_text_safe((50, 100), f"DuckDuckGo search results for '{query}':", fill_color=text_primary)
        
        draw_text_safe((50, 150), f"Top guides and discussions on {query}", fill_color=text_link)
        draw_text_safe((50, 170), f"https://example.com/search?q={query}", fill_color="#3fb950")
        draw_text_safe((50, 190), f"Detailed information, community threads and installation guide for {query}...", fill_color=text_secondary)
        
        draw_text_safe((50, 240), f"Latest updates and releases of {query}", fill_color=text_link)
        draw_text_safe((50, 260), f"https://example.com/news/{query}", fill_color="#3fb950")
        draw_text_safe((50, 280), f"Industry announcements, change logs, and download links for {query}...", fill_color=text_secondary)
        
    else:
        # Default layout
        draw_text_safe((50, 100), "Example Domain", fill_color=text_primary)
        draw_text_safe((50, 140), "This domain is established to be used for illustrative examples in documents.", fill_color=text_secondary)
        draw_text_safe((50, 170), "More information...", fill_color=text_link)

    img.save(path)


def clean_search_query(query: str) -> str:
    if not query:
        return ""
    q = query.strip()
    q_lower = q.lower()
    
    prefixes = [
        "search duckduckgo for the ",
        "search duckduckgo for ",
        "search google for the ",
        "search google for ",
        "search wikipedia for the ",
        "search wikipedia for ",
        "search for the ",
        "search for ",
        "go to wikipedia.org and find the page for ",
        "go to wikipedia.org and find the page ",
        "go to wikipedia.org and find ",
        "go to wikipedia.org and ",
        "find the page for ",
        "find the page ",
        "find tickets from ",
        "search tickets from ",
        "find details of ",
        "find info on ",
        "find information on ",
        "latest news on ",
        "latest news about ",
        "news about ",
        "news on ",
        "find ",
        "search ",
        "go to ",
        "lookup ",
        "look up ",
    ]
    
    for prefix in prefixes:
        if q_lower.startswith(prefix):
            q = q[len(prefix):].strip()
            q_lower = q.lower()
            break
            
    q = q.strip('"').strip("'").strip(".").strip()
    return q


def _get_duckduckgo_html(query: str, url: str) -> str:
    """
    Helper function to generate the DuckDuckGo mock search results HTML.
    """
    url_lower = url.lower() if url else ""
    search_term = query if query else "latest AI news"
    if not query and "q=" in url_lower:
        match = re.search(r"q=([^&]+)", url_lower)
        if match:
            search_term = urllib.parse.unquote_plus(match.group(1))
            
    search_term = clean_search_query(search_term)
            
    # Generate dynamic slugs and details
    slug = re.sub(r'[^a-zA-Z0-9]+', '-', search_term.lower()).strip('-')
    search_lower = search_term.lower()
    
    # Check for specific queries to provide high-fidelity realistic answers
    if "paying skill" in search_lower or "computer science skill" in search_lower:
        res1_title = "Top 10 Highest Paying Tech Skills in 2026"
        res1_url = "https://en.wikipedia.org/wiki/Computer_science"
        res1_snippet = "Discover the top paying skills: 1. Generative AI / Large Language Models (Average salary $185,000), 2. Cloud Architecture (AWS/Azure - Average $165,000), 3. Cybersecurity & Zero Trust (Average $160,000), 4. Data Engineering & Analytics (Average $155,000), and 5. DevOps & Infrastructure as Code (Average $150,000)."
        
        res2_title = "The Most Demanded Computer Science Skills - Forbes"
        res2_url = "https://www.forbes.com/search/?q=tech+skills"
        res2_snippet = "Tech industries are paying top dollar for specialized skills. Machine Learning Engineers, Cloud Engineers, and Cybersecurity Experts remain at the top of the salary bracket, with senior roles easily clearing $200k in 2026."
        
        res3_title = "GitHub - awesome-paying-skills: Salaries & Resources"
        res3_url = "https://github.com/search?q=awesome+paying+skills"
        res3_snippet = "A curated database of salaries, interview guides, and certification courses for Generative AI, Cloud Infrastructure, Cyber Security, Data Engineering, and DevOps."
    elif "headphone" in search_lower or "audio" in search_lower:
        res1_title = "The Best Noise-Cancelling Headphones of 2026 - Reviews"
        res1_url = "https://en.wikipedia.org/wiki/Headphones"
        res1_snippet = "We review the top headphones of the year: 1. Sony WH-1000XM6 (Outstanding ANC, 42h battery, $399), 2. Bose QuietComfort Ultra (Unmatched comfort, 24h battery, $429), and 3. Sennheiser Momentum 4 (Class-leading sound quality, 60h battery, $349)."
        
        res2_title = "Bose vs Sony vs Sennheiser: Which ANC Headphone is Best?"
        res2_url = "https://www.google.com/search?q=anc+headphones"
        res2_snippet = "A direct head-to-head comparison. Sony's new WH-1000XM6 offers the best active noise cancellation and 42-hour battery life. Sennheiser leads in audiophile sound with 60-hour battery life, while Bose excels in comfort."
        
        res3_title = "Cheapest Deals on Premium ANC Headphones - TechRadar"
        res3_url = "https://www.techradar.com/news/audio/headphones"
        res3_snippet = "Find sales on the Sony XM6 ($379 at Amazon), Bose QC Ultra ($399 at Best Buy), and Sennheiser Momentum 4 ($299 at Walmart)."
    elif "purifier" in search_lower:
        res1_title = "Best Air Purifiers for Allergies & Pets in 2026"
        res1_url = "https://en.wikipedia.org/wiki/Air_purifier"
        res1_snippet = "The top air purifiers: 1. Coway Airmega 400S (Coverage 1560 sq ft, Dual HEPA, $499), 2. Blueair Blue Pure 211i Max (Coverage 600 sq ft, Whisper quiet, $349), and 3. Levoit Core 400S (Coverage 403 sq ft, Smart control, $219)."
        
        res2_title = "HEPA Air Purifiers: Ratings & Review Guide"
        res2_url = "https://en.wikipedia.org/wiki/HEPA"
        res2_snippet = "A comparison of True HEPA filters. Coway Airmega offers the best large-room coverage (1560 sq ft), while the Blueair Pure 211i Max is the most energy-efficient for medium rooms (600 sq ft)."
        
        res3_title = "Levoit vs Coway: Best Smart Air Purifiers"
        res3_url = "https://www.google.com/search?q=smart+air+purifiers"
        res3_snippet = "Comparison of app control and air quality sensors. The Levoit Core 400S ($219) is our top budget recommendation, while the Coway Airmega 400S ($499) excels in raw purification power."
    elif "apple" in search_lower or "aapl" in search_lower:
        res1_title = "Apple Inc. (AAPL) Stock Price Today & Real-Time Quote"
        res1_url = "https://finance.yahoo.com/quote/AAPL"
        res1_snippet = "Real-time Apple stock quote: AAPL is currently trading at $182.50 (+1.25%). Today's High: $183.10, Today's Low: $181.40, Opening Price: $181.90. Volume: 52.4 million shares."
        
        res2_title = "Apple (AAPL) Stock Analysis & Wall Street Forecasts"
        res2_url = "https://www.google.com/finance/quote/AAPL:NASDAQ"
        res2_snippet = "AAPL closed at $182.50 today, showing strength after opening at $181.90. Analysts set a 12-month median target of $210, citing strong services revenue and upcoming hardware announcements."
        
        res3_title = "AAPL - Apple Inc. Shareholders & Earnings Reports"
        res3_url = "https://www.sec.gov/edgar/searchedgar/companysearch"
        res3_snippet = "AAPL details: Market cap $2.85T, PE ratio 28.4, EPS $6.42. Today's trading range: $181.40 - $183.10."
    else:
        is_shopping = any(w in search_term.lower() for w in ["price", "cheap", "buy", "cost", "store", "sale", "cleanser", "cetaphil", "ticket", "hotel", "product"])
        if is_shopping:
            res1_title = f"Buy {search_term.title()} at Best Prices Online"
            res1_url = f"https://www.amazon.com/s?k={urllib.parse.quote_plus(search_term)}"
            res1_snippet = f"Compare prices for {search_term}. Find it in stock for $9.99 (8oz) and $14.50 (16oz). Free shipping on orders over $25. Read user ratings and discount coupons."
            
            res2_title = f"Cheapest {search_term.title()} Deals & Discounts"
            res2_url = f"https://www.google.com/search?q={urllib.parse.quote_plus(search_term)}+price"
            res2_snippet = f"Get the best deals on {search_term}. Lowest price found online is $8.49 at Walmart, followed by $10.20 at Target. Compare pharmacy prices and save up to 40%."
            
            res3_title = f"Top 10 Best {search_term.title()} Reviews and Store Locations"
            res3_url = f"https://www.google.com/search?q={urllib.parse.quote_plus(search_term)}+reviews"
            res3_snippet = f"Read verified buyer reviews for {search_term}. Check local pharmacy listings and stock status. Price ranges from $8.49 to $12.99 across major retailers."
        else:
            res1_title = f"Complete Guide to {search_term.title()} - Official Overview"
            res1_url = f"https://en.wikipedia.org/wiki/Special:Search?search={urllib.parse.quote_plus(search_term)}"
            res1_snippet = f"Learn everything about {search_term}. Discover official documentation, tutorials, pricing details, and implementation roadmaps for beginners."
            
            res2_title = f"Latest News, Trends & Updates on {search_term.title()}"
            res2_url = f"https://news.google.com/search?q={urllib.parse.quote_plus(search_term)}"
            res2_snippet = f"Read the most recent articles and community announcements regarding {search_term}. Expert columns, comparison guides, and user reviews updated daily."
            
            res3_title = f"GitHub - community/awesome-{slug}: Curated list of resources"
            res3_url = f"https://github.com/search?q={urllib.parse.quote_plus(search_term)}"
            res3_snippet = f"A curated list of awesome tutorials, libraries, tools, and code repositories relating to {search_term}. Contribute to the roadmap and join the developer chat."
        
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>{search_term} at DuckDuckGo</title>
<style>
  body {{
    font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
    background-color: #1e1e1e;
    color: #c9d1d9;
    margin: 0;
    padding: 0;
  }}
  .header {{
    background-color: #2d2d2d;
    padding: 15px 30px;
    display: flex;
    align-items: center;
    border-bottom: 1px solid #30363d;
  }}
  .logo {{
    color: #de5833;
    font-size: 20px;
    font-weight: bold;
    margin-right: 25px;
    text-decoration: none;
  }}
  .search-box {{
    background-color: #1e1e1e;
    border: 1px solid #444;
    border-radius: 8px;
    padding: 8px 16px;
    width: 450px;
    color: #fff;
    font-size: 15px;
  }}
  .content {{
    max-width: 800px;
    padding: 30px 40px;
  }}
  .result {{
    margin-bottom: 28px;
  }}
  .result-title {{
    font-size: 18px;
    color: #58a6ff;
    text-decoration: none;
    font-weight: 500;
  }}
  .result-title:hover {{
    text-decoration: underline;
  }}
  .result-url {{
    color: #3fb950;
    font-size: 13px;
    margin: 3px 0;
  }}
  .result-snippet {{
    color: #8b949e;
    font-size: 14px;
    line-height: 1.5;
  }}
</style>
</head>
<body>
  <div class="header">
    <a href="#" class="logo">🦆 DuckDuckGo</a>
    <input type="text" class="search-box" value="{search_term}" readonly>
  </div>
  <div class="content">
    <div style="color:#8b949e; font-size:13px; margin-bottom:20px;">Search results for: <b>{search_term}</b></div>
    
    <div class="result">
      <a class="result-title" href="{res1_url}">{res1_title}</a>
      <div class="result-url">{res1_url}</div>
      <div class="result-snippet">{res1_snippet}</div>
    </div>
    
    <div class="result">
      <a class="result-title" href="{res2_url}">{res2_title}</a>
      <div class="result-url">{res2_url}</div>
      <div class="result-snippet">{res2_snippet}</div>
    </div>
    
    <div class="result">
      <a class="result-title" href="{res3_url}">{res3_title}</a>
      <div class="result-url">{res3_url}</div>
      <div class="result-snippet">{res3_snippet}</div>
    </div>
  </div>
</body>
</html>"""


def get_mock_html(url: str, query: str = "", action: str = "") -> str:
    """
    Returns a beautifully styled, responsive mock HTML page representing
    various search queries or websites. This allows the browser agent to load
    this content in a headless browser and capture realistic screenshots.
    """
    url_lower = url.lower() if url else ""
    query_lower = query.lower() if query else ""
    action_lower = action.lower() if action else ""
    
    # 1. Flight Tickets Template (Higher priority than search results since it's also a search)
    if any(w in query_lower or w in url_lower for w in ["flight", "ticket", "bangalore", "hyderabad"]):
        origin, origin_code, destination, dest_code = extract_cities_from_query(url, query)
        flights = generate_random_flights(origin_code, dest_code, query or url)
        f1, f2, f3 = flights[0], flights[1], flights[2]
        
        html_template = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Flights from Bangalore to Hyderabad</title>
<style>
  body {
    font-family: 'Segoe UI', Roboto, sans-serif;
    background-color: #0b0f19;
    color: #e5e7eb;
    margin: 0;
    padding: 0;
  }
  .header {
    background-color: #111827;
    padding: 20px 40px;
    border-bottom: 1px solid #1f2937;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  .title {
    font-size: 20px;
    font-weight: 600;
    color: #3b82f6;
  }
  .container {
    max-width: 1000px;
    padding: 30px 40px;
  }
  .card {
    background-color: #1f2937;
    border: 1px solid #374151;
    border-radius: 8px;
    padding: 20px;
    margin-bottom: 20px;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  .flight-info {
    display: flex;
    gap: 50px;
  }
  .airline {
    font-weight: bold;
    font-size: 16px;
    color: #fff;
  }
  .time {
    font-size: 18px;
    font-weight: 500;
  }
  .route {
    font-size: 12px;
    color: #9ca3af;
  }
  .price-section {
    text-align: right;
  }
  .price {
    font-size: 22px;
    font-weight: bold;
    color: #10b981;
  }
  .btn-book {
    background-color: #2563eb;
    color: white;
    border: none;
    padding: 8px 16px;
    border-radius: 6px;
    font-weight: 500;
    cursor: pointer;
    margin-top: 8px;
    transition: background 0.2s;
  }
  .btn-book:hover {
    background-color: #1d4ed8;
  }
</style>
</head>
<body>
  <div class="header">
    <div class="title">✈️ Flights Search: Bangalore (BLR) to Hyderabad (HYD)</div>
    <div style="font-size:14px; color:#9ca3af;">One Way | 1 Passenger</div>
  </div>
  <div class="container">
    <h3 style="color:#9ca3af; font-weight:normal; margin-bottom: 20px;">3 Direct Flights Found</h3>
    
    <div class="card">
      <div class="flight-info">
        <div>
          <div class="airline">Akasa Air</div>
          <div style="font-size:12px; color:#9ca3af;">QP-1102</div>
        </div>
        <div>
          <div class="time">21:00 - 22:10</div>
          <div class="route">BLR → HYD (Direct)</div>
        </div>
        <div>
          <div class="time">1h 10m</div>
          <div class="route">Non-stop</div>
        </div>
      </div>
      <div class="price-section">
        <div class="price">INR 3,120</div>
        <a href="https://www.google.com/travel/flights" target="_blank" style="text-decoration: none;">
          <button class="btn-book">Select Flight</button>
        </a>
      </div>
    </div>
    
    <div class="card">
      <div class="flight-info">
        <div>
          <div class="airline">IndiGo</div>
          <div style="font-size:12px; color:#9ca3af;">6E-2412</div>
        </div>
        <div>
          <div class="time">08:30 - 09:45</div>
          <div class="route">BLR → HYD (Direct)</div>
        </div>
        <div>
          <div class="time">1h 15m</div>
          <div class="route">Non-stop</div>
        </div>
      </div>
      <div class="price-section">
        <div class="price">INR 3,450</div>
        <a href="https://www.google.com/travel/flights" target="_blank" style="text-decoration: none;">
          <button class="btn-book">Select Flight</button>
        </a>
      </div>
    </div>
    
    <div class="card">
      <div class="flight-info">
        <div>
          <div class="airline">Air India</div>
          <div style="font-size:12px; color:#9ca3af;">AI-512</div>
        </div>
        <div>
          <div class="time">14:15 - 15:35</div>
          <div class="route">BLR → HYD (Direct)</div>
        </div>
        <div>
          <div class="time">1h 20m</div>
          <div class="route">Non-stop</div>
        </div>
      </div>
      <div class="price-section">
        <div class="price">INR 3,890</div>
        <a href="https://www.google.com/travel/flights" target="_blank" style="text-decoration: none;">
          <button class="btn-book">Select Flight</button>
        </a>
      </div>
    </div>
  </div>
</body>
</html>"""
        return html_template.replace(
            "Bangalore", origin
        ).replace(
            "BLR", origin_code
        ).replace(
            "Hyderabad", destination
        ).replace(
            "HYD", dest_code
        ).replace(
            "Akasa Air", f1["airline"]
        ).replace(
            "QP-1102", f1["flight_num"]
        ).replace(
            "21:00 - 22:10", f1["dep_time"] + " - " + f1["arr_time"]
        ).replace(
            "1h 10m", f1["duration"]
        ).replace(
            "INR 3,120", f1["price"]
        ).replace(
            "IndiGo", f2["airline"]
        ).replace(
            "6E-2412", f2["flight_num"]
        ).replace(
            "08:30 - 09:45", f2["dep_time"] + " - " + f2["arr_time"]
        ).replace(
            "1h 15m", f2["duration"]
        ).replace(
            "INR 3,450", f2["price"]
        ).replace(
            "Air India", f3["airline"]
        ).replace(
            "AI-512", f3["flight_num"]
        ).replace(
            "14:15 - 15:35", f3["dep_time"] + " - " + f3["arr_time"]
        ).replace(
            "1h 20m", f3["duration"]
        ).replace(
            "INR 3,890", f3["price"]
        )

    # 2. Search Results Template (DuckDuckGo style) - Priority when searching other terms
    elif "duckduckgo" in url_lower or action_lower == "search":
        return _get_duckduckgo_html(query, url)
        
    # 2. Hacker News Template
    elif "news.ycombinator.com" in url_lower or "hacker news" in query_lower:
        return """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Hacker News</title>
<style>
  body {
    font-family: Verdana, Geneva, sans-serif;
    background-color: #f6f6ef;
    color: #000000;
    margin: 0;
    padding: 0;
  }
  .hn-header {
    background-color: #ff6600;
    padding: 6px 12px;
    display: flex;
    align-items: center;
  }
  .hn-logo {
    border: 1px solid white;
    font-weight: bold;
    color: white;
    padding: 2px 6px;
    margin-right: 8px;
    font-size: 13px;
  }
  .hn-title {
    font-weight: bold;
    font-size: 14px;
    margin-right: 15px;
  }
  .hn-nav {
    font-size: 11px;
    color: #000;
  }
  .hn-content {
    padding: 15px 25px;
  }
  .story {
    margin-top: 12px;
    font-size: 13px;
  }
  .story-title {
    color: #000000;
    text-decoration: none;
  }
  .story-title:hover {
    text-decoration: underline;
  }
  .story-site {
    color: #828282;
    font-size: 10px;
  }
  .story-subtext {
    font-size: 10px;
    color: #828282;
    margin-top: 3px;
  }
</style>
</head>
<body>
  <div class="hn-header">
    <span class="hn-logo">Y</span>
    <span class="hn-title">Hacker News</span>
    <span class="hn-nav">new | past | comments | ask | show | jobs | submit</span>
  </div>
  <div class="hn-content">
    <div class="story">
      <span style="color:#828282">1.</span> 
      <a class="story-title" href="https://news.ycombinator.com/item?id=45192031">OpenAI Releases GPT-5 with Advanced Browser Integration</a>
      <span class="story-site">(news.ycombinator.com)</span>
      <div class="story-subtext">425 points by techcrunch 2 hours ago | 102 comments</div>
    </div>
    <div class="story">
      <span style="color:#828282">2.</span> 
      <a class="story-title" href="https://github.com/googledm/antigravity">Show HN: Antigravity - An Autonomous Agent Framework</a>
      <span class="story-site">(github.com/googledm)</span>
      <div class="story-subtext">180 points by googledm 4 hours ago | 45 comments</div>
    </div>
    <div class="story">
      <span style="color:#828282">3.</span> 
      <a class="story-title" href="https://browserdev.org/future-playwright">The Future of Web Automation and Playwright</a>
      <span class="story-site">(browserdev.org)</span>
      <div class="story-subtext">95 points by browserdev 5 hours ago | 20 comments</div>
    </div>
    <div style="margin-top: 25px; font-size: 12px; color: #828282; cursor: pointer;">More...</div>
  </div>
</body>
</html>"""

    # 2. Wikipedia Template
    elif "wikipedia.org" in url_lower or "wikipedia" in query_lower or "wikipedia" in url_lower:
        # Extract title from URL if possible, e.g. /wiki/Artificial_intelligence
        title = "Artificial intelligence"
        match = re.search(r"/wiki/([^/&#?]+)", url)
        if match:
            title = urllib.parse.unquote(match.group(1)).replace("_", " ")
            
        # Clean title if it contains search query parameters or refers to main/search page
        if title.lower() in ["main page", "special:search", "search"] or "q=" in title.lower() or "search=" in title.lower():
            if "javascript" in query_lower or "javascript" in url_lower:
                title = "JavaScript"
            elif "python" in query_lower or "python" in url_lower:
                title = "Python (programming language)"
            else:
                title = query.title() if query else "Artificial intelligence"
                
        # Clean up any trailing query details
        title = re.sub(r"\?.+$", "", title).strip()
            
        if "python" in title.lower():
            p1 = "<b>Python</b> is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation. Python is dynamically typed and garbage-collected. It supports multiple programming paradigms, including structured, object-oriented, and functional programming."
            p2 = "It was created by Guido van Rossum and first released in 1991. The Python Software Foundation manages and directs resources for Python development. It is widely used in data science, machine learning, web development, and scripting."
        elif "javascript" in title.lower():
            p1 = "<b>JavaScript</b>, often abbreviated as JS, is a programming language that is one of the core technologies of the World Wide Web, alongside HTML and CSS. Over 97% of websites use JavaScript on the client side for webpage behavior, often incorporating third-party libraries."
            p2 = "It is a multi-paradigm, dynamic, weakly typed, prototype-based language. It was created by Brendan Eich in 1995 while working at Netscape, and has since become the most popular programming language in the world."
        else:
            p1 = f"<b>{title}</b> is a topic of broad interest in technology and science. This page compiles verified facts, reference materials, definitions, and recent updates regarding {title}."
            p2 = f"For more detailed documentations and resources about {title}, you can browse the official community guides, repository listings, or academic references."

        return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>{title} - Wikipedia</title>
<style>
  body {{
    font-family: sans-serif;
    background-color: #ffffff;
    color: #202122;
    margin: 0;
    padding: 0;
  }}
  .wiki-header {{
    background-color: #f8f9fa;
    border-bottom: 1px solid #a2a9b1;
    padding: 12px 30px;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }}
  .wiki-logo {{
    font-size: 20px;
    font-weight: normal;
    color: #000;
    text-decoration: none;
  }}
  .wiki-search {{
    padding: 6px 12px;
    width: 250px;
    border: 1px solid #a2a9b1;
    border-radius: 2px;
  }}
  .wiki-body {{
    padding: 40px 60px;
    max-width: 900px;
  }}
  .wiki-title {{
    font-family: 'Georgia', Times, serif;
    font-size: 34px;
    border-bottom: 1px solid #a2a9b1;
    padding-bottom: 5px;
    margin-top: 0;
    font-weight: normal;
  }}
  .wiki-subtitle {{
    font-size: 13px;
    color: #54595d;
    margin-top: 5px;
    margin-bottom: 25px;
  }}
  .wiki-p {{
    font-size: 15px;
    line-height: 1.6;
    margin-bottom: 18px;
  }}
  .wiki-p b {{
    font-weight: bold;
  }}
</style>
</head>
<body>
  <div class="wiki-header">
    <a href="#" class="wiki-logo">📖 Wikipedia</a>
    <input type="text" class="wiki-search" value="{title}" readonly>
  </div>
  <div class="wiki-body">
    <h1 class="wiki-title">{title}</h1>
    <div class="wiki-subtitle">From Wikipedia, the free encyclopedia</div>
    <p class="wiki-p">
      {p1}
    </p>
    <p class="wiki-p">
      {p2}
    </p>
  </div>
</body>
</html>"""



    # 4. Search Results Template (DuckDuckGo style) - Fallback for other queries
    elif query_lower:
        return _get_duckduckgo_html(query, url)

    # 5. Default Website Template
    else:
        # Extract domain name
        domain = "example.com"
        parsed = urllib.parse.urlparse(url)
        if parsed.netloc:
            domain = parsed.netloc
            
        return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>{domain} - Preview</title>
<style>
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
    background-color: #0d1117;
    color: #c9d1d9;
    margin: 0;
    padding: 0;
  }}
  .header {{
    background-color: #161b22;
    padding: 20px 40px;
    border-bottom: 1px solid #30363d;
  }}
  .logo {{
    font-weight: bold;
    font-size: 18px;
    color: #58a6ff;
  }}
  .container {{
    max-width: 800px;
    margin: 60px auto;
    padding: 0 20px;
    text-align: center;
  }}
  h1 {{
    font-size: 32px;
    margin-bottom: 15px;
    color: #ffffff;
  }}
  p {{
    font-size: 16px;
    line-height: 1.6;
    color: #8b949e;
    margin-bottom: 30px;
  }}
  .link {{
    color: #58a6ff;
    text-decoration: none;
    font-weight: 500;
  }}
  .link:hover {{
    text-decoration: underline;
  }}
</style>
</head>
<body>
  <div class="header">
    <div class="logo">🌐 {domain}</div>
  </div>
  <div class="container">
    <h1>Welcome to {domain}</h1>
    <p>This is a simulated secure preview of <b>{domain}</b> loaded by the Browser Operating Agent. The page content has been fetched and parsed successfully.</p>
    <a class="link" href="{url}">Go to original source →</a>
  </div>
</body>
</html>"""
