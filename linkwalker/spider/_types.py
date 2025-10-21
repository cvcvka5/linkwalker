from typing import TypedDict, Optional, Literal, Callable, Awaitable
from playwright.async_api import Page

class WaitForSelectorArgs(TypedDict):
    selector: str
    timeout: Optional[float]
    state: Optional[Literal["attached", "detached", "hidden", "visible"]]
    strict: Optional[bool]

class BrowserWalkOptions(TypedDict):
    https_only: Optional[bool]
    exclude_head: Optional[bool]
    blacklist_extensions: Optional[list] # defaults to ["jpg", "png", "jpeg", "svg", "pdf", "zip", "mp3", "mp4", "exe"]
    wait_for_selector: Optional[WaitForSelectorArgs]
    clean_url: Optional[bool]
    max_depth: Optional[int]  # maximum recursion depth
    on_page: Optional[Callable[[Page], Awaitable[None]]]  # async callback
    exclude_srcs: Optional[bool] # defaults to False
    domain_whitelist: Optional[list] # defaults to only self
    allow_all_domains: Optional[bool] # defaults to False
    wait_until: Optional[Literal["domcontentloaded", "networkidle", "load", "commit"]] # defaults to load
    url_must_contain: Optional[list[str]] # defaults to None
    url_must_not_contain: Optional[list[str]] # defaults to None
    
    
class HTTPWalkOptions(TypedDict):
    https_only: Optional[bool]
    exclude_head: Optional[bool]
    blacklist_extensions: Optional[list] # defaults to ["jpg", "png", "jpeg", "svg", "pdf", "zip", "mp3", "mp4", "exe"]
    clean_url: Optional[bool]
    max_depth: Optional[int]  # maximum recursion depth
    on_page: Optional[Callable[[Page], Awaitable[None]]]  # async callback
    exclude_srcs: Optional[bool] # defaults to False
    domain_whitelist: Optional[list] # defaults to only self
    allow_all_domains: Optional[bool] # defaults to False
    url_must_contain: Optional[list[str]] # defaults to None
    url_must_not_contain: Optional[list[str]] # defaults to None