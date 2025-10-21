import contextlib
from typing import Optional, Set
from playwright.async_api import async_playwright, Browser, BrowserContext, Page
import asyncio
from urllib.parse import urlparse, urlunparse, urljoin
from ._types import BrowserWalkOptions


class BrowserWalker:
    """
    A simple asynchronous browser-based web walker using Playwright.
    
    This class spins up a headless Chromium instance and recursively visits pages,
    discovering new links (and optionally image/script sources) as it goes.
    It’s meant for crawling dynamic pages where JS rendering actually matters.

    Example:
        ```python
        walker = BrowserWalker(headless=True, max_pages=10)
        await walker.start()
        urls = await walker.walk("https://example.com", {
            "max_depth": 2,
            "https_only": True,
            "exclude_head": True,
            "clean_url": True
        })
        await walker.close()
        print(urls)
        ```
    """

    def __init__(self, headless: bool = True, max_pages: Optional[int] = None):
        # Basic setup for the browser walker
        self.headless = headless
        self.max_pages = max_pages
        self.browser: Browser = None
        self.context: BrowserContext = None
        self.origin_url = None

        # Keep track of URLs we've seen and visited
        self.urls: Set[str] = set()
        self.visited: Set[str] = set()

        # Limit concurrency if max_pages is set
        self.sem = asyncio.Semaphore(max_pages) if max_pages else None

    async def start(self):
        """Start Playwright and launch a browser context."""
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=self.headless)
        self.context = await self.browser.new_context()

    async def _process_url(self, url: str, options: BrowserWalkOptions, depth: int, queue: asyncio.Queue):
        """
        Visit a given URL, extract new links, and add them to the queue.
        This is where most of the actual crawling logic happens.
        """
        max_depth = options.get("max_depth", float("inf"))
        if depth > max_depth or url in self.visited:
            return

        self.visited.add(url)

        if self.sem:
            await self.sem.acquire()
        page = await self.context.new_page()

        try:
            # Try to load the page
            try:
                resp = await page.goto(url, wait_until=options.get("wait_until", "load"))
                content_type = resp.headers.get("content-type", "")
                if not content_type.startswith("text/html"):
                    # Skip non-HTML pages (e.g. images, PDFs)
                    await page.close()
                    return
            except Exception:
                # Some URLs just fail to load, skip them quietly
                return

            # Optionally wait for a specific selector before continuing
            wait_args = options.get("wait_for_selector")
            if wait_args:
                try:
                    await page.wait_for_selector(
                        selector=wait_args.get("selector"),
                        timeout=wait_args.get("timeout", 15_000),
                        state=wait_args.get("state", "attached"),
                        strict=wait_args.get("strict", False)
                    )
                except Exception:
                    # Don’t break just because an element didn’t show up
                    pass

            # Grab the full HTML (or just body if exclude_head=True)
            html = await page.inner_html("body") if options.get("exclude_head") else await page.content()

            # Run a custom callback if one was provided
            on_page = options.get("on_page")
            if on_page:
                try:
                    await on_page(page, html)
                except Exception:
                    pass  # User-defined callback shouldn’t crash the walker

            # Collect hrefs and srcs (usually links, scripts, and images)
            try:
                hrefs = await page.eval_on_selector_all(
                    "*[href]", "els => els.map(e => e.getAttribute('href'))"
                )
                hrefs = [h for h in hrefs if h]
            except Exception:
                hrefs = []

            try:
                srcs = await page.eval_on_selector_all(
                    "*[src]", "els => els.map(e => e.getAttribute('src'))"
                )
                srcs = [src for src in srcs if src]
            except Exception:
                srcs = []
            
            combined = hrefs
            if not options.get("exclude_srcs"):
                combined += srcs

            # Convert relative URLs to absolute
            urls = [urljoin(url, val) for val in combined]

            # Apply protocol filters
            if options.get("https_only"):
                urls = [u for u in urls if u.startswith("https://")]
            else:
                urls = [u for u in urls if u.startswith("https://") or u.startswith("http://")]

            # Skip unwanted file extensions
            blacklist = (options.get("blacklist_extensions") or 
                         ["jpg", "png", "jpeg", "svg", "pdf", "zip", "mp3", "mp4", "exe"])
            urls = [u for u in urls if not any(u.lower().endswith(ext.lower()) for ext in blacklist)]

            # Filter by required substrings
            must_contain = options.get("url_must_contain")
            if must_contain:
                urls = [u for u in urls if any(substr in u for substr in must_contain)]

            # Filter out unwanted substrings
            must_not_contain = options.get("url_must_not_contain")
            if must_not_contain:
                urls = [u for u in urls if not any(substr in u for substr in must_not_contain)]

            # Optionally remove query strings for cleaner URLs
            if options.get("clean_url"):
                urls = [
                    urlunparse((urlparse(u).scheme, urlparse(u).netloc, urlparse(u).path, '', '', ''))
                    for u in urls
                ]

            # Add discovered URLs to the queue (with domain checks)
            new_urls = set(urls) - self.visited
            self.urls.update(new_urls)

            for u in new_urls:
                if not options.get("allow_all_domains"):
                    domain = urlparse(u).netloc
                    domain = domain[4:] if domain.startswith("www.") else domain

                    origin_domain = urlparse(self.origin_url).netloc
                    origin_domain = origin_domain[4:] if origin_domain.startswith("www.") else origin_domain

                    domain_whitelist = options.get("domain_whitelist")
                    if domain_whitelist is not None:
                        if domain in domain_whitelist or any(map(lambda dom: domain.endswith("." + dom), domain_whitelist)):
                            await queue.put((u, depth + 1))
                    else:
                        # Default: allow same domain and subdomains
                        if domain == origin_domain or domain.endswith("." + origin_domain):
                            await queue.put((u, depth + 1))
                else:
                    # allow_all_domains=True means go wild
                    await queue.put((u, depth + 1))

        finally:
            await page.close()
            if self.sem:
                self.sem.release()

    async def walk(self, origin_url: str, options: BrowserWalkOptions):
        """
        Start the recursive crawl from a given origin URL.
        Spawns multiple async workers to explore discovered links.
        """
        self.origin_url = origin_url
        
        queue = asyncio.Queue()
        await queue.put((origin_url, 0))

        num_workers = self.max_pages or 5
        workers = [asyncio.create_task(self._worker(queue, options)) for _ in range(num_workers)]

        await queue.join()  # Wait for all queued URLs to finish

        for w in workers:
            w.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await w

        return self.urls

    async def _worker(self, queue: asyncio.Queue, options: BrowserWalkOptions):
        """Worker coroutine — keeps pulling URLs from the queue and processing them."""
        while True:
            got_task = False
            try:
                url, depth = await queue.get()
                got_task = True
                try:
                    await self._process_url(url, options, depth, queue)
                except Exception:
                    # We don’t really care if one page fails
                    pass
            except asyncio.CancelledError:
                break
            finally:
                if got_task:
                    queue.task_done()

    async def close(self):
        """Tear down browser and Playwright context cleanly."""
        await self.context.close()
        await self.browser.close()
        await self.playwright.stop()