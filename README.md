# LinkWalker

LinkWalker is a Python library for **deep URL crawling and walking**. It supports both **dynamic browser-based crawling** (using Playwright) and **static HTTP crawling**, allowing you to traverse websites, extract links, and filter URLs with ease. Perfect for developers building scrapers, bots, or web analyzers.

## Features

- **Dynamic crawling** with Playwright (handles JavaScript-heavy pages)
- **Static HTTP crawling** using aiohttp for lightweight scraping
- **Deep crawling** with configurable max depth
- **URL filtering**:
  - Include or exclude URLs based on substrings
  - Clean URLs by removing query parameters
  - Blacklist certain file extensions
  - HTTPS-only option
- **Domain control**: restrict crawling to specific domains or subdomains
- **Callbacks**: execute custom logic on each page visited
- **Concurrency control** with adjustable max parallel pages

## Installation

```bash
pip install linkwalker
```

## Example Usage

### Dynamic Browser Walker

```python
import asyncio
from linkwalker.spider.dynamic import BrowserWalker
from linkwalker.spider._types import BrowserWalkOptions
from playwright.async_api import Page

async def on_page(page: Page, html):
    print("Visited:", page.url)

async def main():
    walker = BrowserWalker(headless=True, max_pages=4)
    await walker.start()

    options: BrowserWalkOptions = {
        "https_only": False,
        "clean_url": True,
        "max_depth": 2,
        "on_page": on_page,
        "allow_all_domains": False,
    }

    urls = await walker.walk(origin_url="https://example.com", options=options)
    print(f"Found {len(urls)} URLs")

    await walker.close()

asyncio.run(main())
```

### Static HTTP Walker

```python
import asyncio
from linkwalker.spider.static import HTTPWalker
from linkwalker.spider._types import HTTPWalkOptions

async def on_page(url, html):
    print("Visited:", url)

async def main():
    walker = HTTPWalker(max_pages=5)
    await walker.start()

    options: HTTPWalkOptions = {
        "https_only": False,
        "clean_url": True,
        "max_depth": 2,
        "on_page": on_page,
        "allow_all_domains": False,
        "url_must_contain": ["/tag/", "/author/"],
        "url_must_not_contain": ["/page/"]
    }

    urls = await walker.walk(origin_url="https://quotes.toscrape.com", options=options)
    print(f"Found {len(urls)} URLs")

    await walker.close()

asyncio.run(main())
```

## Contributing

Feel free to submit issues or pull requests. Contributions to improve crawling efficiency, filtering, or feature support are welcome.

## License

MIT License