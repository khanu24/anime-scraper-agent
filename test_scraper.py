import asyncio
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

async def scrape_with_playwright(url):
    print(f"[+] Launching Browser to inspect: {url}\n")

    found_embeds = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        # Network requests listen karke embed / stream URLs filter karna
        async def handle_request(request):
            req_url = request.url
            if any(k in req_url for k in ['nekostream', 'embed', 'player', 'm3u8', 'vidsrc', 'megacloud']):
                if req_url not in found_embeds:
                    found_embeds.append(req_url)

        page.on("request", handle_request)

        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(6000)  # Wait for JS player execution

        content = await page.content()
        soup = BeautifulSoup(content, 'html.parser')

        title = soup.title.text.strip() if soup.title else "N/A"

        # DOM se directly IFrames dhoondna
        iframes = soup.find_all('iframe')
        for f in iframes:
            src = f.get('src') or f.get('data-src')
            if src and src not in found_embeds:
                found_embeds.append(src)

        og_image = soup.find('meta', property='og:image')
        image_url = og_image['content'] if og_image else "N/A"

        print("=" * 60)
        print("SCRAPING TEST RESULT:")
        print("=" * 60)
        print(f"Title:     {title}")
        print(f"Image:     {image_url}")
        print(f"\nExtracted Player / Stream Links ({len(found_embeds)}):")
        for idx, u in enumerate(found_embeds, 1):
            print(f"  [{idx}] {u}")
        print("=" * 60)

        await browser.close()

if __name__ == "__main__":
    target_url = "https://anikototv.to/watch/black-clover-season-2"
    asyncio.run(scrape_with_playwright(target_url))