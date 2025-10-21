from linkwalker.spider.dynamic import BrowserWalker
from linkwalker.spider._types import BrowserWalkOptions
import asyncio
from playwright.async_api import Page

# Global counter to track how many pages we've visited
visited_n = 0

# This callback gets called for every page the walker visits
async def on_page(page: Page, html):
    global visited_n
    visited_n += 1
    print(f"Visited {visited_n} pages.", f"({page.url})")
    # You could also parse the HTML here, save screenshots, etc.

async def main():
    # Create a new BrowserWalker instance
    walker = BrowserWalker(headless=True, max_pages=4)
    await walker.start()  # launch the browser and context

    # Starting URL
    origin_url = "https://www.youtube.com"

    # Options for the walker
    options: BrowserWalkOptions = {
        "https_only": False,         # allow both http and https links
        "exclude_head": False,       # include <head> in the HTML
        "clean_url": True,           # remove query params from URLs
        "wait_until": "load",        # wait until page fully loads
        "max_depth": 2,              # how deep to follow links
        "on_page": on_page,          # callback for each page
        "domain_whitelist": ["google.com", "youtube.com"],  # restrict crawling to origin domain
    }
        
    # Start crawling
    urls = list(await walker.walk(origin_url=origin_url, options=options))
    
    # Print total unique URLs discovered
    print(urls[len(urls)//3:len(urls)//2])
    print(len(urls))
    
    # Close browser and cleanup
    await walker.close()


if __name__ == "__main__":
    # Run the main async function
    asyncio.run(main())