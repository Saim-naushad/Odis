"""Capture populated dashboard screenshots for documentation assets."""

from __future__ import annotations

import asyncio
from pathlib import Path

from playwright.async_api import async_playwright

ASSETS_DIR = Path(__file__).resolve().parents[1] / "docs" / "assets"
BASE_URL = "http://localhost:8080"


async def wait_for_populated_dashboard(page) -> None:
    await page.goto(BASE_URL, wait_until="load", timeout=60_000)

    await page.get_by_role("button", name="fuel-cell-stack-01").wait_for(
        state="visible", timeout=60_000
    )
    await page.get_by_role("button", name="fuel-cell-stack-01").click()

    await page.get_by_text("CRITICAL", exact=False).first.wait_for(
        state="visible", timeout=60_000
    )
    await page.get_by_text("Immediate mitigation", exact=False).first.wait_for(
        state="visible", timeout=60_000
    )

    await page.locator("svg").first.wait_for(state="visible", timeout=60_000)
    await page.wait_for_timeout(3000)


async def main() -> None:
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1440, "height": 900},
            device_scale_factor=2,
            color_scheme="dark",
        )
        page = await context.new_page()

        try:
            await wait_for_populated_dashboard(page)

            await page.screenshot(
                path=str(ASSETS_DIR / "dashboard-overview.png"),
                full_page=False,
            )

            investigation = page.locator('aside[aria-label="Investigation"]')
            await investigation.wait_for(state="visible")
            await investigation.screenshot(
                path=str(ASSETS_DIR / "dashboard-investigation.png"),
            )

            await page.screenshot(
                path=str(ASSETS_DIR / "dashboard-telemetry.png"),
                full_page=False,
            )
        finally:
            await browser.close()

    print(f"Captured screenshots in {ASSETS_DIR}")


if __name__ == "__main__":
    asyncio.run(main())
