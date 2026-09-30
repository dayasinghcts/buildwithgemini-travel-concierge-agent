import asyncio
import os
from pathlib import Path
from playwright.async_api import async_playwright

async def main():
    output_dir = Path("/config/Desktop/Session1/travel-concierge-agent/demo_output")
    output_dir.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            record_video_dir=str(output_dir),
            record_video_size={"width": 1280, "height": 800}
        )
        page = await context.new_page()

        print("1. Navigating to local chat app at http://localhost:8080...")
        await page.goto("http://localhost:8080")
        await asyncio.sleep(3)

        # 1st Prompt: Core capability of Travel Concierge (destination search / recommendations)
        prompt_1 = "Find tropical beach destinations with rich culture and history"
        print(f"2. Sending 1st prompt: '{prompt_1}'")
        await page.fill("#input", prompt_1)
        await asyncio.sleep(1)
        await page.click("button[type='submit']")

        print("3. Waiting for agent response to 1st prompt...")
        await page.wait_for_function("document.querySelectorAll('.msg.agent').length >= 1", timeout=60000)
        await asyncio.sleep(6)

        # 2nd Prompt: Richer prompt showing tool calls, live weather lookup, and image preview generation
        prompt_2 = "What is the live weather in Kyoto and generate a visual preview photo of Kyoto temple?"
        print(f"4. Sending 2nd prompt: '{prompt_2}'")
        await page.fill("#input", prompt_2)
        await asyncio.sleep(1)
        await page.click("button[type='submit']")

        print("5. Waiting for agent response to 2nd prompt...")
        await page.wait_for_function("document.querySelectorAll('.msg.agent').length >= 2", timeout=90000)
        await asyncio.sleep(8)

        video_path = await page.video.path()
        await context.close()
        await browser.close()
        print(f"✅ Demo video recording complete! Saved to: {video_path}")

if __name__ == "__main__":
    asyncio.run(main())
