import asyncio
import logging
import queue
import threading
import os
from agents.browser_agent import BrowserAgent

logger = logging.getLogger("browser_agent.runner")

class BrowserRunner:
    def __init__(self):
        self.cmd_queue = queue.Queue()
        self.resp_queue = queue.Queue()
        self.thread = None
        self.loop = None
        self.agent = None
        self.running = False
        self.screenshot_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "screenshots")

    def start(self, headless: bool, use_mock: bool, proxy: dict = None):
        """Starts the background thread containing the async event loop and BrowserAgent."""
        if self.running:
            return
        self.running = True
        
        # Clear queues
        while not self.cmd_queue.empty():
            try:
                self.cmd_queue.get_nowait()
            except queue.Empty:
                break
        while not self.resp_queue.empty():
            try:
                self.resp_queue.get_nowait()
            except queue.Empty:
                break

        self.thread = threading.Thread(
            target=self._run_loop,
            args=(headless, use_mock, proxy),
            daemon=True
        )
        self.thread.start()
        
        # Block until thread is ready or has an error
        status, payload = self.resp_queue.get(timeout=15.0)
        if status == "error":
            self.running = False
            raise RuntimeError(payload)

    def _run_loop(self, headless: bool, use_mock: bool, proxy: dict):
        """Worker thread entry point."""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        
        self.agent = BrowserAgent(headless=headless, use_mock=use_mock)
        
        try:
            # Initialize Playwright browser
            self.loop.run_until_complete(self.agent.start(proxy=proxy))
        except Exception as e:
            logger.error(f"Failed to start BrowserAgent in background thread: {e}")
            self.resp_queue.put(("error", f"Startup failed: {e}"))
            self.running = False
            self.loop.close()
            return

        self.resp_queue.put(("ready", None))

        # Command consumer loop
        while self.running:
            try:
                # Wait for command
                cmd_item = self.cmd_queue.get(timeout=0.2)
                cmd_type, args, kwargs = cmd_item
                
                # Execute async command
                coro = self._dispatch_cmd(cmd_type, args, kwargs)
                res = self.loop.run_until_complete(coro)
                self.resp_queue.put(("success", res))
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Error in BrowserRunner event loop execution: {e}")
                self.resp_queue.put(("error", str(e)))

        # Clean up browser agent
        try:
            self.loop.run_until_complete(self.agent.stop())
        except Exception as e:
            logger.warning(f"Error stopping BrowserAgent: {e}")
        finally:
            self.loop.close()

    async def _dispatch_cmd(self, cmd_type: str, args: tuple, kwargs: dict):
        if cmd_type == "execute_action":
            # args: (step, step_num)
            return await self.agent.execute_action(args[0], args[1], self.screenshot_dir)
        elif cmd_type == "manual_click":
            # args: (x, y)
            res = await self.agent.manual_click(args[0], args[1])
            screenshot_path = os.path.join(self.screenshot_dir, "manual_click.png")
            if self.agent.page:
                try:
                    await self.agent.page.screenshot(path=screenshot_path)
                    res["screenshot_path"] = screenshot_path
                except Exception:
                    pass
            if self.agent.page:
                try:
                    res["html"] = await self.agent.page.content()
                except Exception:
                    pass
            return res
        elif cmd_type == "manual_type":
            # args: (selector, text)
            res = await self.agent.manual_type(args[0], args[1])
            screenshot_path = os.path.join(self.screenshot_dir, "manual_type.png")
            if self.agent.page:
                try:
                    await self.agent.page.screenshot(path=screenshot_path)
                    res["screenshot_path"] = screenshot_path
                except Exception:
                    pass
            if self.agent.page:
                try:
                    res["html"] = await self.agent.page.content()
                except Exception:
                    pass
            return res
        elif cmd_type == "manual_navigate":
            # args: (url,)
            res = await self.agent.manual_navigate(args[0])
            screenshot_path = os.path.join(self.screenshot_dir, "manual_navigate.png")
            if self.agent.page:
                try:
                    await self.agent.page.screenshot(path=screenshot_path)
                    res["screenshot_path"] = screenshot_path
                except Exception:
                    pass
            if self.agent.page:
                try:
                    res["html"] = await self.agent.page.content()
                except Exception:
                    pass
            return res
        elif cmd_type == "get_current_state":
            res = {"status": "success", "url": "", "html": "", "screenshot_path": ""}
            if self.agent.page:
                try:
                    res["url"] = self.agent.page.url
                    res["html"] = await self.agent.page.content()
                    screenshot_path = os.path.join(self.screenshot_dir, "current_state.png")
                    await self.agent.page.screenshot(path=screenshot_path)
                    res["screenshot_path"] = screenshot_path
                except Exception as e:
                    res["status"] = "error"
                    res["details"] = str(e)
            return res
        else:
            raise ValueError(f"Unknown command type: {cmd_type}")

    def stop(self):
        """Stops the runner and blocks until thread completes."""
        if not self.running:
            return
        logger.info("Stopping background BrowserRunner thread...")
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=3.0)
        self.thread = None
        self.loop = None
        self.agent = None

    def send_cmd(self, cmd_type: str, *args, **kwargs):
        """Sends command to runner and waits for response."""
        if not self.running:
            raise RuntimeError("BrowserRunner is not running.")
        self.cmd_queue.put((cmd_type, args, kwargs))
        status, payload = self.resp_queue.get()
        if status == "error":
            raise RuntimeError(payload)
        return payload
