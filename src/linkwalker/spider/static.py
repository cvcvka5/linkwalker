import asyncio
import contextlib
from typing import Optional, Set
from urllib.parse import urlparse, urlunparse, urljoin
import aiohttp
from selectolax.parser import HTMLParser
from ._types import HTTPWalkOptions


class HTTPWalker:
    """
    A lightweight asynchronous web crawler built on aiohttp and selectolax.

    This class crawls HTML pages recursively and collects discovered URLs
    according to user-defined rules like:
    - depth limits
    - domain restrictions
    - file type blacklists
    - inclusion/exclusion keywords
    - HTTPS-only enforcement

    It’s built for reliability, simplicity, and speed — not for scraping the entire web.
    Perfect for internal tools, site structure analysis, or focused data extraction.
    """

    def __init__(self, max_pages: Optional[int] = None):
        """
        Initialize the HTTPWalker.

        Args:
            max_pages: (optional) maximum number of pages to crawl in parallel.
        """
        self.max_pages = max_pages
        self.session: aiohttp.ClientSession = None
        self.origin_url = None
        self.urls: Set[str] = set()       # every discovered URL
        self.visited: Set[str] = set()    # URLs already processed
        self.sem = asyncio.Semaphore(max_pages) if max_pages else None

    async def start(self):
        """
        Create a single aiohttp session with a simple, friendly user-agent.
        """
        headers = {"User-Agent": "Mozilla/5.0 (compatible; LinkWalker/1.0)"}
        self.session = aiohttp.ClientSession(headers=headers)

    async def _fetch(self, url: str) -> Optional[str]:
        """
        Download a URL and return its HTML content if it's an HTML document.

        Returns:
            str: HTML content if successful, None otherwise.
        """
        try:
            async with self.session.get(url, timeout=15) as resp:
                ctype = resp.headers.get("content-type", "")
                # Skip anything that isn’t HTML (e.g. images, PDFs, etc.)
                if "text/html" not in ctype:
                    return None
                return await resp.text(errors="ignore")
        except Exception:
            # Network errors, timeouts, invalid SSL, etc. — just skip.
            return None

    async def _process_url(self, url: str, options: HTTPWalkOptions, depth: int, queue: asyncio.Queue):
        """
        Process a single URL:
        - Fetch the page
        - Parse HTML
        - Extract links and filter them
        - Enqueue new URLs to visit
        """
        max_depth = options.get("max_depth", float("inf"))
        if depth > max_depth or url in self.visited:
            return

        self.visited.add(url)

        if self.sem:
            await self.sem.acquire()

        try:
            html = await self._fetch(url)
            if not html:
                return

            # Optionally strip the <head> section (e.g. for cleaner HTML)
            if options.get("exclude_head"):
                try:
                    tree = HTMLParser(html)
                    head = tree.css_first("head")
                    if head:
                        head.decompose()
                    html = tree.html
                except Exception:
                    pass  # Not a big deal if parsing fails

            # Optional callback for the user (async function)
            on_page = options.get("on_page")
            if on_page:
                try:
                    await on_page(url, html)
                except Exception:
                    pass  # Don’t let user callbacks crash the crawler

            # --- Link extraction ---
            parser = HTMLParser(html)
            hrefs = [n.attributes.get("href") for n in parser.css("*[href]") if n.attributes.get("href")]
            srcs = [n.attributes.get("src") for n in parser.css("*[src]") if n.attributes.get("src")]

            # Merge hrefs and srcs if not explicitly excluded
            combined = hrefs
            if not options.get("exclude_srcs"):
                combined += srcs

            # Make all links absolute relative to the current page
            urls = [urljoin(url, val) for val in combined]

            # --- Filtering stage ---

            # Enforce https:// if requested
            if options.get("https_only"):
                urls = [u for u in urls if u.startswith("https://")]
            else:
                urls = [u for u in urls if u.startswith(("https://", "http://"))]

            # Skip unwanted file types (default: images, media, executables, etc.)
            blacklist = (
                options.get("blacklist_extensions")
                or ["jpg", "png", "jpeg", "svg", "pdf", "zip", "mp3", "mp4", "exe"]
            )
            urls = [u for u in urls if not any(u.lower().endswith(ext.lower()) for ext in blacklist)]

            # Only keep URLs that contain certain substrings (if defined)
            must_contain = options.get("url_must_contain")
            if must_contain:
                urls = [u for u in urls if any(substr in u for substr in must_contain)]

            # Drop URLs that contain forbidden substrings
            must_not_contain = options.get("url_must_not_contain")
            if must_not_contain:
                urls = [u for u in urls if not any(substr in u for substr in must_not_contain)]

            # Optionally clean URLs by removing query strings and fragments
            if options.get("clean_url"):
                urls = [
                    urlunparse((urlparse(u).scheme, urlparse(u).netloc, urlparse(u).path, '', '', ''))
                    for u in urls
                ]

            # --- Queue management ---
            new_urls = set(urls) - self.visited
            self.urls.update(new_urls)

            # Respect domain rules (stay within the same domain by default)
            for u in new_urls:
                if not options.get("allow_all_domains"):
                    domain = urlparse(u).netloc
                    domain = domain[4:] if domain.startswith("www.") else domain

                    origin_domain = urlparse(self.origin_url).netloc
                    origin_domain = origin_domain[4:] if origin_domain.startswith("www.") else origin_domain

                    domain_whitelist = options.get("domain_whitelist")
                    if domain_whitelist is not None:
                        # If a whitelist exists, only allow those domains or their subdomains
                        if domain in domain_whitelist or any(
                            dom.endswith("." + domain) for dom in domain_whitelist
                        ):
                            await queue.put((u, depth + 1))
                    else:
                        # Default behavior: allow same domain and subdomains
                        if domain == origin_domain or domain.endswith("." + origin_domain):
                            await queue.put((u, depth + 1))
                else:
                    # Free roam mode — crawl everything reachable
                    await queue.put((u, depth + 1))

        finally:
            if self.sem:
                self.sem.release()

    async def walk(self, origin_url: str, options: HTTPWalkOptions):
        """
        Begin the crawl from the starting URL and return all discovered URLs.
        """
        self.origin_url = origin_url
        queue = asyncio.Queue()
        await queue.put((origin_url, 0))

        # Use up to `max_pages` concurrent workers (default 5)
        num_workers = self.max_pages or 5
        workers = [asyncio.create_task(self._worker(queue, options)) for _ in range(num_workers)]

        # Wait until all pages are processed
        await queue.join()

        # Cleanly stop workers
        for w in workers:
            w.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await w

        return self.urls

    async def _worker(self, queue: asyncio.Queue, options: HTTPWalkOptions):
        """
        Worker coroutine that continuously pulls URLs from the queue
        and processes them until the crawl finishes.
        """
        while True:
            got_task = False
            try:
                url, depth = await queue.get()
                got_task = True
                try:
                    await self._process_url(url, options, depth, queue)
                except Exception:
                    pass  # Don't stop everything for one bad page
            except asyncio.CancelledError:
                break
            finally:
                if got_task:
                    queue.task_done()

    async def close(self):
        """
        Gracefully close the aiohttp session after crawling is done.
        """
        await self.session.close()
