import os
import asyncio
import logging
import urllib.parse
from playwright.async_api import async_playwright
import config

logger = logging.getLogger("browser_agent.browser_agent")

class BrowserAgent:
    def __init__(self, headless: bool = None):
        self.headless = config.HEADLESS_BROWSER if headless is None else headless
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
        self.browser = await self.playwright.chromium.launch(
            headless=self.headless,
            args=["--disable-web-security", "--no-sandbox", "--disable-setuid-sandbox"]
        )
        self.context = await self.browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        self.page = await self.context.new_page()
        logger.info("Browser started successfully.")

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
        
        if not self.page:
            await self.start()

        try:
            if action == "navigate":
                url = step.get("url", "")
                if not url.startswith("http://") and not url.startswith("https://"):
                    url = f"https://{url}"
                logger.info(f"Navigating to {url}...")
                await self.page.goto(url, timeout=20000, wait_until="load")
                result["details"] = f"Navigated to {url}"
                
            elif action == "search":
                query = step.get("query", "")
                encoded_query = urllib.parse.quote_plus(query)
                # DuckDuckGo HTML mode is fast, static, and captcha-free
                url = f"https://html.duckduckgo.com/html/?q={encoded_query}"
                logger.info(f"Searching DuckDuckGo for: '{query}'...")
                await self.page.goto(url, timeout=20000, wait_until="load")
                result["details"] = f"Searched DuckDuckGo for '{query}'"
                
            elif action == "type":
                selector = step.get("selector", "")
                text = step.get("text", "")
                logger.info(f"Typing '{text}' into selector '{selector}'...")
                try:
                    await self.page.fill(selector, text, timeout=5000)
                except Exception as fill_err:
                    # Fallback selectors/methods
                    logger.warning(f"Failed standard fill, trying fallbacks: {fill_err}")
                    try:
                        # Try by placeholder
                        await self.page.get_by_placeholder(selector).fill(text, timeout=3000)
                    except Exception:
                        try:
                            # Try general inputs
                            await self.page.locator("input").first.fill(text, timeout=3000)
                        except Exception:
                            raise ValueError(f"Could not type into selector '{selector}'")
                result["details"] = f"Typed '{text}' into '{selector}'"
                
            elif action == "click":
                selector = step.get("selector", "")
                logger.info(f"Clicking selector '{selector}'...")
                try:
                    await self.page.click(selector, timeout=5000)
                except Exception as click_err:
                    logger.warning(f"Failed standard click, trying text/role fallbacks: {click_err}")
                    try:
                        # Only try text locator fallback if the selector is a simple string (no tags/brackets/commas)
                        if "," not in selector and "[" not in selector and ":" not in selector:
                            await self.page.locator(f"text={selector}").first.click(timeout=3000)
                        else:
                            raise ValueError()
                    except Exception:
                        try:
                            # Try finding by role button
                            if "," not in selector and "[" not in selector and ":" not in selector:
                                await self.page.get_by_role("button", name=selector).first.click(timeout=3000)
                            else:
                                raise ValueError()
                        except Exception:
                            # If all fallbacks fail, check if there is a generic submit/search button
                            try:
                                if "search" in selector.lower() or "submit" in selector.lower() or "go" in selector.lower():
                                    await self.page.locator("button, input[type='submit'], input[name='go']").first.click(timeout=3000)
                                else:
                                    raise ValueError()
                            except Exception:
                                raise ValueError(f"Could not click selector/element '{selector}'")
                result["details"] = f"Clicked '{selector}'"
                
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

            # Always capture screenshot after action for progress visualization
            if not os.path.exists(screenshot_dir):
                os.makedirs(screenshot_dir)
                
            screenshot_path = os.path.join(screenshot_dir, f"step_{step_num}_{action}.png")
            try:
                await self.page.screenshot(path=screenshot_path)
                result["screenshot_path"] = screenshot_path
            except Exception as ss_err:
                logger.error(f"Failed to capture screenshot: {ss_err}")

            # Capture current page content (HTML)
            result["html"] = await self.page.content()

        except Exception as e:
            logger.error(f"Error executing step {step_num} ({action}): {e}")
            result["status"] = "error"
            result["details"] = f"Error: {str(e)}"
            # Capture error screenshot if possible
            if self.page:
                screenshot_path = os.path.join(screenshot_dir, f"step_{step_num}_error.png")
                try:
                    await self.page.screenshot(path=screenshot_path)
                    result["screenshot_path"] = screenshot_path
                except Exception:
                    pass

        return result
