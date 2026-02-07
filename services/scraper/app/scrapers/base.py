from __future__ import annotations

from abc import ABC, abstractmethod
import asyncio
import random
from playwright.async_api import BrowserContext, ElementHandle


class BaseScraper(ABC):
    platform: str
    start_url: str

    @abstractmethod
    async def scrape(self, context: BrowserContext, query: str, run_id: str) -> list:
        ...

    async def human_pause(self, min_s: float = 0.45, max_s: float = 1.35) -> None:
        await asyncio.sleep(random.uniform(min_s, max_s))

    async def pick_text(self, root: ElementHandle, selectors: list[str]) -> str:
        for selector in selectors:
            node = await root.query_selector(selector)
            if node:
                text = (await node.inner_text()).strip()
                if text:
                    return text
        return ""
