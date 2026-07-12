"""Capture populated dashboard screenshots for documentation assets."""

from __future__ import annotations

import asyncio
from pathlib import Path

from playwright.async_api import async_playwright

ASSETS_DIR = Path(__file__).resolve().parents[1] / "docs" / "assets"
BASE_URL = "http://localhost:8080"


async def wait_for_settled(page, timeout: int = 5000) -> None:
    """Wait until no 'Refreshing…' indicator is visible anywhere on the page."""
    try:
        await page.get_by_text("Refreshing…").first.wait_for(
            state="hidden", timeout=timeout
        )
    except Exception:
        pass


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
    await wait_for_settled(page)
    await page.wait_for_timeout(1000)


async def prepare_telemetry_chart(page) -> None:
    """Select a representative measurement/time range and wait for a populated chart."""
    time_range_group = page.get_by_role("group", name="Time range")
    resolution_group = page.get_by_role("group", name="Telemetry resolution")

    measurement_select = page.locator("#telemetry-measurement")
    if await measurement_select.count() > 0:
        options = await measurement_select.locator("option").all_text_contents()
        if "stack_temperature" in options:
            await measurement_select.select_option("stack_temperature")

    await resolution_group.get_by_role("button", name="Raw").click()
    await time_range_group.get_by_role("button", name="Last hour").click()

    try:
        await page.locator(".recharts-line-curve").first.wait_for(
            state="visible", timeout=15_000
        )
    except Exception:
        # Fall back to a wider window if the last hour has no samples yet.
        await time_range_group.get_by_role("button", name="Last 24 hours").click()
        await page.locator(".recharts-line-curve").first.wait_for(
            state="visible", timeout=15_000
        )

    await wait_for_settled(page)
    await page.wait_for_timeout(500)


async def wait_for_populated_timeline(page) -> None:
    """Wait for the investigation timeline to hold more than a single event."""
    timeline_items = page.locator('aside[aria-label="Investigation"] ul li')
    try:
        await timeline_items.nth(1).wait_for(state="visible", timeout=15_000)
    except Exception:
        pass
    await wait_for_settled(page)
    await page.wait_for_timeout(500)


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

            await prepare_telemetry_chart(page)
            await page.screenshot(
                path=str(ASSETS_DIR / "dashboard-telemetry.png"),
                full_page=False,
            )

            await wait_for_populated_timeline(page)
            investigation = page.locator('aside[aria-label="Investigation"]')
            await investigation.wait_for(state="visible")
            await investigation.screenshot(
                path=str(ASSETS_DIR / "dashboard-investigation.png"),
            )
        finally:
            await browser.close()

    print(f"Captured screenshots in {ASSETS_DIR}")


if __name__ == "__main__":
    asyncio.run(main())
