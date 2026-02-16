from __future__ import annotations

from urllib.parse import quote_plus, urljoin

from playwright.async_api import BrowserContext

from ..models import JobRecord
from ..ranking import semantic_match_score
from .base import BaseScraper
from .stealth import apply_stealth


class RemoteOkScraper(BaseScraper):
    platform = "remote_ok"
    start_url = "https://remoteok.com/remote-jobs"

    async def scrape(self, context: BrowserContext, query: str, run_id: str) -> list[JobRecord]:
        page = context.pages[0] if context.pages else await context.new_page()
        await apply_stealth(page)

        target_url = f"{self.start_url}?query={quote_plus(query)}"
        await page.goto(target_url, wait_until="domcontentloaded")
        await self.human_pause(1.0, 2.0)

        # Wait for table rows to hydrate from JS
        try:
            await page.wait_for_selector("tr.job, tr[data-slug]", timeout=10000)
        except Exception:
            pass

        for _ in range(6):
            await page.mouse.wheel(0, 1500)
            await self.human_pause(0.5, 1.1)

        # Remote OK uses a table layout with tr.job rows
        cards = []
        for selector in ["tr.job", "tr[data-slug]", "tr:has(td.company)", "article"]:
            cards = await page.query_selector_all(selector)
            if cards:
                break

        jobs: list[JobRecord] = []
        for card in cards[:100]:
            title = await self.pick_text(card, ["h2", "td.company h2", "[itemprop='title']", "h3"])
            company = await self.pick_text(card, ["h3", "td.company h3", "[itemprop='name']", ".company-name"])
            location = await self.pick_text(card, [".location", "td.location", ".location.tooltip"])
            description = await self.pick_text(card, ["p", ".description", "td.description"])
            salary_text = await self.pick_text(card, [".salary", "td.salary"])

            tag_nodes = await card.query_selector_all(".tag, td.tags .tag, .tags a")
            tags: list[str] = []
            for node in tag_nodes[:8]:
                text = (await node.inner_text()).strip()
                if text:
                    tags.append(text)

            anchor = await card.query_selector("a[href*='/remote-jobs/'], a[href]")
            href = await anchor.get_attribute("href") if anchor else None
            # Fallback: use data-slug attribute to construct URL
            if not href:
                slug = await card.get_attribute("data-slug")
                if slug:
                    href = f"/remote-jobs/{slug}"
            if not title or not href:
                continue

            score = semantic_match_score(query=query, title=title, description=description)
            jobs.append(
                JobRecord(
                    run_id=run_id,
                    platform=self.platform,
                    title=title,
                    company=company or "Unknown",
                    location=location or "Remote/Unknown",
                    url=urljoin("https://remoteok.com", href),
                    description=description,
                    salary_text=salary_text,
                    tags=tags,
                    semantic_score=score,
                )
            )
        return jobs
