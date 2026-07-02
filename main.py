from fastapi import FastAPI
from pydantic import BaseModel
from urllib.parse import urlparse, urljoin, urldefrag
from bs4 import BeautifulSoup
import requests

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

    headers = {
        "User-Agent": "Mozilla/5.0 OpalCrawler/1.0"
    }

    while queue:
        current_url = normalize_url(queue.pop(0))

        if current_url in visited or should_ignore(current_url):
            continue

        visited.add(current_url)

        try:
            response = requests.get(
                current_url,
                headers=headers,
                timeout=15,
                allow_redirects=True
            )

            content_type = response.headers.get("content-type", "")

            if "text/html" not in content_type:
                continue

            soup = BeautifulSoup(response.text, "html.parser")

            title_tag = soup.find("title")
            title = title_tag.get_text(strip=True) if title_tag else ""

            results.append({
                "url": current_url,
                "page_title": title
            })

            for a in soup.find_all("a", href=True):
                link = urljoin(current_url, a["href"])
                link = normalize_url(link)

                parsed = urlparse(link)

                if parsed.netloc == domain and not should_ignore(link):
                    if link not in visited and link not in queue:
                        queue.append(link)

        except Exception:
            continue

    return {
        "total_pages": len(results),
        "pages": results
    }


@app.get("/discovery")
def discovery():
    return {
        "functions": [
            {
                "name": "crawl_site",
                "description": "Crawls a website and returns internal page URLs with page titles.",
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