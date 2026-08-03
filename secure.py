import asyncio
import nest_asyncio
import time
import requests
import os

from playwright.async_api import async_playwright
from playwright_stealth import Stealth

nest_asyncio.apply()

URL_API = os.environ.get("RAW_URL_API")


def get_raw_urls():
    return requests.get(URL_API, timeout=10).text.splitlines()


async def get_direct_url(page, url):
    try:
        await page.goto(url, wait_until="domcontentloaded")

        await page.wait_for_selector(
            'a[hx-get*="/download"]',
            timeout=10000
        )

        direct = await page.evaluate("""
            async () => {
                try {
                    const btn = document.querySelector('a[hx-get*="/download"]');
                    if (!btn) return null;

                    const res = await fetch(
                        window.location.origin + btn.getAttribute("hx-get"),
                        {
                            headers: {
                                "HX-Request": "true",
                                "HX-Current-URL": window.location.href
                            }
                        }
                    );

                    return res.headers.get("HX-Redirect");
                } catch (e) {
                    return null;
                }
            }
        """)

        return direct

    except Exception as e:
        print(f"Failed: {url}")
        print(e)
        return None


def download(url, filename):
    max_bytes = 50 * 1024 * 1024  
    downloaded = 0

    with requests.get(url, stream=True, timeout=30) as r:
        r.raise_for_status()

        with open(filename, "wb") as f:
            for chunk in r.iter_content(8192):
                if not chunk:
                    continue

                remaining = max_bytes - downloaded

                if len(chunk) > remaining:
                    chunk = chunk[:remaining]

                f.write(chunk)
                downloaded += len(chunk)

                if downloaded >= max_bytes:
                    break


async def run_cycle(cycle_no):
    raw_urls = get_raw_urls()

    async with Stealth().use_async(async_playwright()) as p:
        browser = await p.chromium.launch(headless=True)

        try:
            for idx, raw_url in enumerate(raw_urls, start=1):
                context = await browser.new_context()
                page = await context.new_page()

                try:
                    direct = await get_direct_url(page, raw_url)

                    if not direct:
                        print(f"[{idx}] Failed: {raw_url}")
                        continue

                    print(f"[{idx}] Resolved: {direct}")

                    download(
                        direct,
                        f"tmp_cycle{cycle_no}_{idx}.bin"
                    )

                    print(f"[{idx}] Downloaded")

                except Exception as e:
                    print(f"[{idx}] Error: {e}")

                finally:
                    await context.close()

        finally:
            await browser.close()


def ncycle(n):
    for cycle in range(1, n + 1):
        print(f"\n========== Cycle {cycle} ==========")

        # Starts a NEW Playwright instance and NEW browser
        asyncio.run(run_cycle(cycle))

        # At this point Playwright and Chromium are fully closed.
        # The next iteration starts from a completely fresh process.
        print(f"✓ Cycle {cycle} complete")
        


if __name__ == "__main__":
    ncycle(1)
