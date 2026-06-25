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


def extract_cities_from_query(url: str, query: str = "") -> tuple:
    """
    Extracts origin and destination cities and their airport codes from a query or search URL.
    Defaults to ('Bangalore', 'BLR', 'Hyderabad', 'HYD').
    """
    import urllib.parse
    import re
    
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
    
    # Try regex match for "from <origin> to <destination>"
    match = re.search(r"from\s+([a-zA-Z\s\-]+?)\s+to\s+([a-zA-Z\s\-]+)", query_lower)
    if match:
        origin_candidate = match.group(1).strip()
        dest_candidate = match.group(2).strip()
        
        # Clean candidates of common trailing query noise
        for stopword in [" and ", " show ", " list ", " with ", " for ", " next ", " this ", " cheapest "]:
            if stopword in f" {dest_candidate} ":
                dest_candidate = dest_candidate.split(stopword)[0].strip()
            if stopword in f" {origin_candidate} ":
                origin_candidate = origin_candidate.split(stopword)[0].strip()
                
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
    }
    if origin in airport_overrides:
        origin_code = airport_overrides[origin]
    if destination in airport_overrides:
        dest_code = airport_overrides[destination]
        
    return origin, origin_code, destination, dest_code


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
        
    elif "flight" in url_lower or "ticket" in url_lower or "bangalore" in url_lower or "hyderabad" in url_lower:
        # Flight search Layout
        origin, origin_code, destination, dest_code = extract_cities_from_query(url)
        draw_text_safe((50, 100), f"Cheapest Flights: {origin} ({origin_code}) to {destination} ({dest_code})", fill_color=text_primary)
        
        draw.rectangle([50, 130, 1180, 320], outline=address_border, width=1)
        draw_text_safe((70, 150), f"Indigo 6E-2412  |  08:30 - 09:45  |  Direct  |  1h 15m  |  Price: INR 12,450", fill_color=text_primary)
        draw_text_safe((70, 180), "Book Indigo flight ticket online...", fill_color=text_link)
        
        draw_text_safe((70, 210), f"Air India AI-512  |  14:15 - 15:35  |  Direct  |  1h 20m  |  Price: INR 15,890", fill_color=text_primary)
        draw_text_safe((70, 240), "Book Air India flight ticket online...", fill_color=text_link)
        
        draw_text_safe((70, 270), f"Akasa Air QP-1102  |  21:00 - 22:10  |  Direct  |  1h 10m  |  Price: INR 11,120", fill_color=text_primary)
        draw_text_safe((70, 300), "Book Akasa Air flight ticket online...", fill_color=text_link)
        
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


def get_mock_html(url: str, query: str = "", action: str = "") -> str:
    """
    Returns a beautifully styled, responsive mock HTML page representing
    various search queries or websites. This allows the browser agent to load
    this content in a headless browser and capture realistic screenshots.
    """
    url_lower = url.lower() if url else ""
    query_lower = query.lower() if query else ""
    action_lower = action.lower() if action else ""
    
    # 1. Hacker News Template
    if "news.ycombinator.com" in url_lower or "hacker news" in query_lower:
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
        match = re.search(r"/wiki/([^/]+)", url)
        if match:
            title = urllib.parse.unquote(match.group(1)).replace("_", " ")
        
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
      <b>{title}</b> is intelligence—perceiving, synthesizing, and inferring information—demonstrated by machines, as opposed to intelligence displayed by non-human animals and humans. Example applications include advanced web search engines, recommendation systems, understanding human speech, self-driving cars, generative tools, and competing at the highest level in strategic games.
    </p>
    <p class="wiki-p">
      As a field of study, AI combines computer science, mathematics, statistics, cognitive science, and philosophy. The field was founded on the assumption that human intelligence can be so precisely described that a machine can be made to simulate it. This raised philosophical arguments about the mind and the ethical consequences of creating artificial beings.
    </p>
  </div>
</body>
</html>"""

    # 3. Flight Tickets Template
    elif any(w in query_lower or w in url_lower for w in ["flight", "ticket", "bangalore", "hyderabad"]):
        origin, origin_code, destination, dest_code = extract_cities_from_query(url, query)
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
        <button class="btn-book">Select Flight</button>
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
        <button class="btn-book">Select Flight</button>
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
        <button class="btn-book">Select Flight</button>
      </div>
    </div>
  </div>
</body>
</html>"""
        return html_template.replace("Bangalore", origin).replace("BLR", origin_code).replace("Hyderabad", destination).replace("HYD", dest_code).replace("3,120", "11,120").replace("3,450", "12,450").replace("3,890", "15,890")

    # 4. Search Results Template (DuckDuckGo style)
    elif "duckduckgo" in url_lower or action_lower == "search" or query_lower:
        # Determine search term
        search_term = query if query else "latest AI news"
        if not query and "q=" in url_lower:
            match = re.search(r"q=([^&]+)", url_lower)
            if match:
                search_term = urllib.parse.unquote_plus(match.group(1))
                
        # Generate dynamic slugs and details
        slug = re.sub(r'[^a-zA-Z0-9]+', '-', search_term.lower()).strip('-')
        is_shopping = any(w in search_term.lower() for w in ["price", "cheap", "buy", "cost", "store", "sale", "cleanser", "cetaphil", "ticket", "hotel", "product"])
        
        if is_shopping:
            res1_title = f"Buy {search_term.title()} at Best Prices Online"
            res1_url = f"https://www.retail-deals.com/buy/{slug}"
            res1_snippet = f"Compare prices for {search_term}. Find it in stock for $9.99 (8oz) and $14.50 (16oz). Free shipping on orders over $25. Read user ratings and discount coupons."
            
            res2_title = f"Cheapest {search_term.title()} Deals & Discounts"
            res2_url = f"https://www.super-discount-hub.com/search?q={slug}"
            res2_snippet = f"Get the best deals on {search_term}. Lowest price found online is $8.49 at Walmart, followed by $10.20 at Target. Compare pharmacy prices and save up to 40%."
            
            res3_title = f"Top 10 Best {search_term.title()} Reviews and Store Locations"
            res3_url = f"https://www.consumerguide.org/reviews/{slug}"
            res3_snippet = f"Read verified buyer reviews for {search_term}. Check local pharmacy listings and stock status. Price ranges from $8.49 to $12.99 across major retailers."
        else:
            res1_title = f"Complete Guide to {search_term.title()} - Official Overview"
            res1_url = f"https://www.knowledgebase-hub.org/wiki/{slug}"
            res1_snippet = f"Learn everything about {search_term}. Discover official documentation, tutorials, pricing details, and implementation roadmaps for beginners."
            
            res2_title = f"Latest News, Trends & Updates on {search_term.title()}"
            res2_url = f"https://www.techtrends-daily.com/news/{slug}"
            res2_snippet = f"Read the most recent articles and community announcements regarding {search_term}. Expert columns, comparison guides, and user reviews updated daily."
            
            res3_title = f"GitHub - community/awesome-{slug}: Curated list of resources"
            res3_url = f"https://github.com/community/awesome-{slug}"
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
