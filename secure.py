import asyncio
import time
import requests
import os

from playwright.async_api import async_playwright
from playwright_stealth import Stealth

# ----------------------------------------------------------------------
# Environment variable: RAW_URL_API must be set (e.g., a plain text URL
# that returns one raw URL per line).
# ----------------------------------------------------------------------
URL_API = os.environ.get("RAW_URL_API")
if not URL_API:
    raise EnvironmentError("Missing environment variable: RAW_URL_API")

def get_raw_urls():
    """Fetch the list of raw URLs from the API endpoint."""
    resp = requests.get(URL_API, timeout=10)
    resp.raise_for_status()
    return resp.text.splitlines()

async def get_direct_url(page, url):
    """
    Navigate to a raw URL, click/trigger the download button via HTMX,
    and extract the final redirect URL.
    """
    try:
        await page.goto(url, wait_until="domcontentloaded")
        await page.wait_for_selector('a[hx-get*="/download"]', timeout=10000)

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
    """
    Download a binary file, limiting to 50 MiB to avoid huge files.
    """
    max_bytes = 50 * 1024 * 1024  # 50 MB
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
    """Process one full cycle: fetch URLs, resolve each, download."""
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
    """Run the given number of cycles, each in a fresh Playwright instance."""
    for cycle in range(1, n + 1):
        print(f"\n========== Cycle {cycle} ==========")
        asyncio.run(run_cycle(cycle))   # works because no existing loop
        print(f"✓ Cycle {cycle} complete")

if __name__ == "__main__":
    ncycle(2)
