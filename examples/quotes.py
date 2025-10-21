from linkwalker.spider.static import HTTPWalker
from linkwalker.spider._types import HTTPWalkOptions
import asyncio
from playwright.async_api import Page

# Global counter to keep track of visited pages
visited_n = 0

# Callback function called on each page that gets fetched
# Here, we just print a counter and the URL
async def on_page(page: Page, html):
    global visited_n
    visited_n += 1
    print(f"Visited {visited_n} pages.", f"({page.url})")
    # You could also parse or save HTML here, or do other processing

async def main():
    # Create the HTTP walker
    walker = HTTPWalker(max_pages=5)  # max_pages limits concurrent requests
    await walker.start()               # start the aiohttp session

    # The starting URL for crawling
    origin_url = "https://quotes.toscrape.com"

    # Crawl options
    options: HTTPWalkOptions = {
        "https_only": False,                   # allow both http and https URLs
        "exclude_head": True,                  # ignore the <head> section to reduce HTML size
        "blacklist_extensions": ["jpg", "png", "js", "jpeg", "svg", "css"],  # skip files we don't care about
        "clean_url": True,                      # remove query parameters
        "max_depth": 2,                         # how deep to follow links
        "on_page": on_page,                     # callback to process each page
        "allow_all_domains": False,             # restrict crawling to origin domain
        "url_must_contain": ["/tag/", "/author/"],  # only follow URLs containing these substrings
        "url_must_not_contain": ["/page/"]         # skip URLs containing these substrings
    }
        
    # Start crawling and collect all discovered URLs
    urls = list(await walker.walk(origin_url=origin_url, options=options))
    
    # Print a sample slice of the discovered URLs
    print(urls[len(urls)//3:len(urls)//2])
    # Print total number of discovered URLs
    print(len(urls))
    
    # Close the walker session cleanly
    await walker.close()


if __name__ == "__main__":
    # Run the async main function
    asyncio.run(main())
