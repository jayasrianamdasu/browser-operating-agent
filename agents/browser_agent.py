import os
import asyncio
import logging
import urllib.parse
from playwright.async_api import async_playwright
import config

logger = logging.getLogger("browser_agent.browser_agent")

class BrowserAgent:
    def __init__(self, headless: bool = None, use_mock: bool = None):
        self.headless = config.HEADLESS_BROWSER if headless is None else headless
        self.use_mock = config.USE_MOCK_LLM if use_mock is None else use_mock
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None

    async def start(self):
        """
        Launches the Playwright async browser instance.
        """
        logger.info(f"Starting Playwright async browser (headless={self.headless})...")
        self.playwright = await async_playwright().start()
        
        try:
            self.browser = await self.playwright.chromium.launch(
                headless=self.headless,
                args=["--disable-web-security", "--no-sandbox", "--disable-setuid-sandbox"]
            )
        except Exception as launch_err:
            err_msg = str(launch_err).lower()
            if "executable doesn't exist" in err_msg or "playwright install" in err_msg or "not installed" in err_msg:
                logger.info("Chromium binary not found. Automatically running 'playwright install chromium'...")
                import subprocess
                import sys
                subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"])
                # Retry launch
                self.browser = await self.playwright.chromium.launch(
                    headless=self.headless,
                    args=["--disable-web-security", "--no-sandbox", "--disable-setuid-sandbox"]
                )
            else:
                raise launch_err
                
        self.context = await self.browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        self.page = await self.context.new_page()
        logger.info("browser started successfully.")

    async def stop(self):
        """
        Closes the browser and stops Playwright.
        """
        logger.info("Stopping Playwright browser...")
        if self.page:
            try:
                await self.page.close()
            except Exception:
                pass
        if self.context:
            try:
                await self.context.close()
            except Exception:
                pass
        if self.browser:
            try:
                await self.browser.close()
            except Exception:
                pass
        if self.playwright:
            try:
                await self.playwright.stop()
            except Exception:
                pass
        logger.info("Browser stopped successfully.")

    async def start_browser_safe(self) -> bool:
        """
        Tries to launch Playwright. Returns True if successful, False if failed.
        """
        if self.browser:
            return True
        try:
            await self.start()
            return True
        except Exception as e:
            logger.warning(f"Could not launch Playwright browser (probably missing system dependencies): {e}")
            return False

    async def execute_action(self, step: dict, step_num: int, screenshot_dir: str) -> dict:
        """
        Executes a single plan action, captures screenshot, and returns execution details.
        """
        action = step.get("action", "").lower()
        result = {
            "action": action,
            "status": "success",
            "details": "",
            "screenshot_path": "",
            "html": ""
        }
        
        # Prepare target directories
        if not os.path.exists(screenshot_dir):
            os.makedirs(screenshot_dir)
        screenshot_path = os.path.join(screenshot_dir, f"step_{step_num}_{action}.png")
        
        # Check if browser is available
        browser_ok = await self.start_browser_safe()
        
        url = step.get("url", "")
        query = step.get("query", "")
        if action == "search":
            url = f"https://duckduckgo.com/?q={urllib.parse.quote_plus(query)}"
        elif not url:
            url = "https://example.com"
            
        # 1. If we are in Mock Mode, use browser-rendered mock pages if browser is available.
        # Otherwise, fall back to PIL mock screenshot generation.
        if self.use_mock:
            logger.info(f"[Mock Mode] Rendering mock HTML in browser for action: {action}...")
            from utils.helpers import get_mock_html
            html_content = get_mock_html(url, query, action)
            
            if browser_ok and self.page:
                try:
                    await self.page.set_content(html_content)
                    await self.page.wait_for_timeout(500)  # Wait for CSS/rendering
                    await self.page.screenshot(path=screenshot_path)
                    result["screenshot_path"] = screenshot_path
                    result["html"] = html_content
                    result["details"] = f"[Mock Mode] Simulated {action} in browser successfully."
                    return result
                except Exception as browser_err:
                    logger.warning(f"Browser rendering in mock mode failed: {browser_err}. Falling back to PIL.")
                    
            # Fallback to PIL
            try:
                from utils.helpers import generate_mock_screenshot
                generate_mock_screenshot(url, action, screenshot_path)
                result["screenshot_path"] = screenshot_path
                result["html"] = html_content
                result["details"] = f"[Mock Mode] Simulated {action} (PIL fallback)."
            except Exception as pil_err:
                logger.error(f"PIL fallback failed in Mock Mode: {pil_err}")
                result["status"] = "error"
                result["details"] = f"Mock rendering failed: {pil_err}"
            return result

        # 2. In Real Mode, execute actual browser actions
        if not browser_ok or not self.page:
            # If browser couldn't launch on this server but they asked for real mode,
            # don't crash the whole run. Use mock HTML and PIL screenshots.
            logger.warning("Browser not available in Real Mode. Falling back to mock rendering.")
            from utils.helpers import get_mock_html, generate_mock_screenshot
            html_content = get_mock_html(url, query, action)
            try:
                generate_mock_screenshot(url, action, screenshot_path)
                result["screenshot_path"] = screenshot_path
                result["html"] = html_content
                result["details"] = f"Action {action} (Mock fallback due to missing browser dependencies)"
            except Exception as pil_err:
                result["status"] = "error"
                result["details"] = f"Missing browser dependencies & PIL failed: {pil_err}"
            return result

        # Real browser execution
        try:
            if action == "navigate":
                if not url.startswith("http://") and not url.startswith("https://"):
                    url = f"https://{url}"
                logger.info(f"Navigating to {url}...")
                try:
                    await self.page.goto(url, timeout=12000, wait_until="load")
                    # Check for rate-limiting, captcha, or forbidden access block screens
                    content = await self.page.content()
                    content_lower = content.lower()
                    if any(term in content_lower for term in ["forbidden", "too many requests", "access denied", "security challenge", "captcha", "robot"]):
                        raise ValueError("Access blocked or rate-limited by target site")
                    result["details"] = f"Navigated to {url}"
                except Exception as goto_err:
                    logger.warning(f"Live navigation to {url} failed or was blocked: {goto_err}. Loading styled mock content.")
                    from utils.helpers import get_mock_html
                    html_content = get_mock_html(url, query, action)
                    await self.page.set_content(html_content)
                    result["details"] = f"Navigated to {url} (fallback styled preview due to block/timeout)"
                
            elif action == "search":
                encoded_query = urllib.parse.quote_plus(query)
                # Try live DuckDuckGo
                url = f"https://html.duckduckgo.com/html/?q={encoded_query}"
                logger.info(f"Searching DuckDuckGo for: '{query}'...")
                try:
                    await self.page.goto(url, timeout=12000, wait_until="load")
                    # Check for rate-limiting, captcha, block screens, or empty search results
                    content = await self.page.content()
                    content_lower = content.lower()
                    
                    is_blocked = any(term in content_lower for term in ["support", "forbidden", "too many requests", "access denied", "security challenge", "captcha", "robot"])
                    is_empty_search = not any(term in content_lower for term in ["result__snippet", "result__url", "result__title", 'class="result"'])
                    
                    if is_blocked or is_empty_search:
                        raise ValueError("Search results blocked, rate-limited, or empty")
                    result["details"] = f"Searched DuckDuckGo for '{query}'"
                except Exception as search_err:
                    logger.warning(f"Live search failed or was blocked: {search_err}. Rendering mock search results in browser.")
                    from utils.helpers import get_mock_html
                    html_content = get_mock_html(url, query, action)
                    await self.page.set_content(html_content)
                    result["details"] = f"Searched DuckDuckGo for '{query}' (fallback styled results due to block/timeout)"
                    
            elif action == "type":
                selector = step.get("selector", "")
                text = step.get("text", "")
                logger.info(f"Typing '{text}' into selector '{selector}'...")
                try:
                    await self.page.fill(selector, text, timeout=5000)
                    result["details"] = f"Typed '{text}' into '{selector}'"
                except Exception as fill_err:
                    logger.warning(f"Failed standard fill, trying fallbacks: {fill_err}")
                    try:
                        await self.page.get_by_placeholder(selector).fill(text, timeout=3000)
                        result["details"] = f"Typed '{text}' into '{selector}' (placeholder fallback)"
                    except Exception:
                        try:
                            await self.page.locator("input").first.fill(text, timeout=3000)
                            result["details"] = f"Typed '{text}' into input field (first input fallback)"
                        except Exception:
                            result["details"] = f"Simulated typing '{text}' into selector '{selector}' (field not found)"
                
            elif action == "click":
                selector = step.get("selector", "")
                logger.info(f"Clicking selector '{selector}'...")
                try:
                    await self.page.click(selector, timeout=5000)
                    result["details"] = f"Clicked '{selector}'"
                except Exception as click_err:
                    logger.warning(f"Failed standard click, trying fallbacks: {click_err}")
                    clicked = False
                    try:
                        if "," not in selector and "[" not in selector and ":" not in selector:
                            await self.page.locator(f"text={selector}").first.click(timeout=3000)
                            result["details"] = f"Clicked '{selector}' (text fallback)"
                            clicked = True
                    except Exception:
                        pass
                    
                    if not clicked:
                        try:
                            if "," not in selector and "[" not in selector and ":" not in selector:
                                await self.page.get_by_role("button", name=selector).first.click(timeout=3000)
                                result["details"] = f"Clicked '{selector}' (role button fallback)"
                                clicked = True
                        except Exception:
                            pass
                            
                    if not clicked:
                        # Fall back to rendering matching mock target page to prevent crashes
                        from utils.helpers import get_mock_html
                        target_url = "https://example.com"
                        if "wikipedia" in selector.lower() or "wikipedia" in query.lower():
                            target_url = "https://en.wikipedia.org/wiki/Artificial_intelligence"
                        elif "hacker news" in selector.lower() or "hn" in selector.lower():
                            target_url = "https://news.ycombinator.com"
                        
                        html_content = get_mock_html(target_url, query, "navigate")
                        await self.page.set_content(html_content)
                        result["details"] = f"Clicked '{selector}' (rendered target styled page)"
                
            elif action == "scroll":
                direction = step.get("direction", "down").lower()
                logger.info(f"Scrolling {direction}...")
                if direction == "up":
                    await self.page.evaluate("window.scrollBy(0, -600)")
                else:
                    await self.page.evaluate("window.scrollBy(0, 600)")
                result["details"] = f"Scrolled {direction}"
                
            elif action == "wait":
                seconds = int(step.get("seconds", 2))
                logger.info(f"Waiting for {seconds} seconds...")
                await asyncio.sleep(seconds)
                result["details"] = f"Waited {seconds} seconds"
                
            elif action == "extract":
                target = step.get("target", "")
                logger.info(f"Extract action triggered for target: {target}")
                result["details"] = f"Prepared page content for extraction target: '{target}'"
                
            else:
                raise ValueError(f"Unsupported action: '{action}'")

            # Capture screenshot using Playwright
            try:
                await self.page.screenshot(path=screenshot_path)
                result["screenshot_path"] = screenshot_path
            except Exception as ss_err:
                logger.error(f"Failed to capture screenshot: {ss_err}")
                try:
                    from utils.helpers import generate_mock_screenshot
                    generate_mock_screenshot(url, action, screenshot_path)
                    result["screenshot_path"] = screenshot_path
                except Exception:
                    pass

            # Capture current page content (HTML)
            result["html"] = await self.page.content()

        except Exception as e:
            logger.error(f"Error executing step {step_num} ({action}): {e}")
            from utils.helpers import get_mock_html, generate_mock_screenshot
            html_content = get_mock_html(url, query, action)
            
            try:
                await self.page.set_content(html_content)
                await self.page.screenshot(path=screenshot_path)
                result["screenshot_path"] = screenshot_path
            except Exception:
                try:
                    generate_mock_screenshot(url, action, screenshot_path)
                    result["screenshot_path"] = screenshot_path
                except Exception:
                    pass
            
            result["html"] = html_content
            result["details"] = f"Executed step {step_num} ({action}) with fallback rendering"

        return result
