from fastapi import FastAPI
from pydantic import BaseModel
from urllib.parse import urlparse, urldefrag
from playwright.sync_api import sync_playwright

app = FastAPI()


class CrawlRequest(BaseModel):
    site_url: str


IGNORE_EXTENSIONS = (
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp",
    ".mp4", ".mp3", ".css", ".js", ".xml", ".zip"
)


def normalize_url(url: str) -> str:
    url, _ = urldefrag(url)
    return url.rstrip("/")


def should_ignore(url: str) -> bool:
    lower = url.lower()

    if lower.startswith(("mailto:", "tel:", "javascript:")):
        return True

    if any(lower.endswith(ext) for ext in IGNORE_EXTENSIONS):
        return True

    if "/episerver" in lower or "/optimizely" in lower or "/cms" in lower:
        return True

    return False


@app.post("/crawl")
def crawl(request: CrawlRequest):
    start_url = normalize_url(request.site_url)
    domain = urlparse(start_url).netloc

    visited = set()
    queue = [start_url]
    results = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        while queue:
            current_url = queue.pop(0)
            current_url = normalize_url(current_url)

            if current_url in visited:
                continue

            if should_ignore(current_url):
                continue

            visited.add(current_url)

            page = browser.new_page()

            try:
                response = page.goto(
                    current_url,
                    wait_until="domcontentloaded",
                    timeout=30000
                )

                status_code = response.status if response else None
                title = page.title()

                try:
                    h1 = page.locator("h1").first.inner_text(timeout=3000)
                except Exception:
                    h1 = ""

                results.append({
                    "url": current_url,
                    "page_title": title,
                    "status_code": status_code,
                    "h1": h1
                })

                links = page.locator("a[href]").evaluate_all(
                    "elements => elements.map(a => a.href)"
                )

                for link in links:
                    link = normalize_url(link)
                    parsed = urlparse(link)

                    if should_ignore(link):
                        continue

                    if parsed.netloc == domain:
                        if link not in visited and link not in queue:
                            queue.append(link)

            except Exception as e:
                results.append({
                    "url": current_url,
                    "page_title": "",
                    "status_code": "ERROR",
                    "h1": "",
                    "error": str(e)
                })

            finally:
                page.close()

        browser.close()

    return {
        "total_pages": len(results),
        "pages": results
    }


@app.get("/discovery")
def discovery():
    return {
        "tools": [
            {
                "name": "crawl_site",
                "description": "Crawls a website like Screaming Frog and returns internal page URLs with page titles.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "site_url": {
                            "type": "string",
                            "description": "The website URL to crawl."
                        }
                    },
                    "required": ["site_url"]
                }
            }
        ]
    }