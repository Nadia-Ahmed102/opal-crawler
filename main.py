from fastapi import FastAPI
from fastapi.responses import FileResponse
from pydantic import BaseModel
from urllib.parse import urlparse, urldefrag
from playwright.sync_api import sync_playwright
from openpyxl import Workbook

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

    if lower.startswith(("mailto:", "tel:", "javascript:", "#")):
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

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Internal Pages"
    sheet.append(["URL", "Page Title"])

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )

        page = browser.new_page()

        while queue:
            current_url = normalize_url(queue.pop(0))

            if current_url in visited or should_ignore(current_url):
                continue

            visited.add(current_url)

            try:
                page.goto(
                    current_url,
                    wait_until="domcontentloaded",
                    timeout=30000
                )

                title = page.title()

                results.append({
                    "url": current_url,
                    "page_title": title
                })

                sheet.append([current_url, title])

                links = page.locator("a[href]").evaluate_all(
                    "elements => elements.map(a => a.href)"
                )

                for link in links:
                    link = normalize_url(link)
                    parsed = urlparse(link)

                    if parsed.netloc == domain and not should_ignore(link):
                        if link not in visited and link not in queue:
                            queue.append(link)

            except Exception:
                continue

        page.close()
        browser.close()

    workbook.save("crawl_results.xlsx")

    return {
        "total_pages": len(results),
        "excel_file": "crawl_results.xlsx",
        "download_url": "/download",
        "pages": results
    }


@app.get("/download")
def download_excel():
    return FileResponse(
        "crawl_results.xlsx",
        filename="crawl_results.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


@app.get("/discovery")
def discovery():
    return {
        "functions": [
            {
                "name": "crawl_site",
                "description": "Crawls a website like Screaming Frog and returns internal page URLs with page titles.",
                "parameters": [
                    {
                        "name": "site_url",
                        "type": "string",
                        "description": "The website URL to crawl.",
                        "required": True
                    }
                ],
                "endpoint": "/crawl",
                "http_method": "POST"
            }
        ]
    }