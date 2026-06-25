import asyncio
import os
import sys
from agents.planner import PlannerAgent
from agents.browser_agent import BrowserAgent
from agents.extractor import ExtractorAgent
from agents.summarizer import SummarizerAgent

async def main():
    print("--------------------------------------------------")
    print("Testing Agent Imports and Mock Execution Pipeline")
    print("--------------------------------------------------")
    
    # Ensure screenshot test folder exists
    screenshot_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_screenshots")
    if not os.path.exists(screenshot_dir):
        os.makedirs(screenshot_dir)
        
    print("1. Initializing agents in Mock Mode...")
    planner = PlannerAgent(use_mock=True)
    extractor = ExtractorAgent(use_mock=True)
    summarizer = SummarizerAgent(use_mock=True)
    browser = BrowserAgent(headless=True, use_mock=True)
    
    task = "Search Hacker News for GPT-5 and summarize the top stories"
    print(f"2. Input task: '{task}'")
    
    print("3. Planner Agent generating execution plan...")
    plan = planner.plan(task)
    print(f"   Generated Plan Steps: {plan}")
    
    print("4. Starting Playwright Browser...")
    await browser.start()
    
    accumulated_extraction = ""
    try:
        for idx, step in enumerate(plan):
            step_num = idx + 1
            print(f"\n[Step {step_num}] Executing {step.get('action').upper()} action...")
            res = await browser.execute_action(step, step_num, screenshot_dir)
            print(f"   Status: {res['status']}")
            print(f"   Details: {res['details']}")
            print(f"   Screenshot saved at: {res.get('screenshot_path', 'N/A')}")
            
            if step.get("action") == "extract":
                print("   Invoking Extractor Agent on page content...")
                target = step.get("target", "content")
                url = browser.page.url if browser.page else ""
                ext_text = extractor.extract(res["html"], target, url)
                print(f"   Extracted Info (truncated): {ext_text[:120]}...")
                accumulated_extraction += f"\n{ext_text}"
                
        print("\n5. Summarizer Agent synthesizing final report...")
        final_summary = summarizer.summarize(task, accumulated_extraction)
        print("--------------------------------------------------")
        print("Final Markdown Answer Summary:")
        print("--------------------------------------------------")
        print(final_summary)
        print("--------------------------------------------------")
        print("Verification Successful!")
        
    except Exception as e:
        print(f"Error encountered during verification: {e}")
        sys.exit(1)
    finally:
        await browser.stop()

if __name__ == "__main__":
    asyncio.run(main())
