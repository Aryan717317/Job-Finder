from __future__ import annotations

import re
from urllib.parse import quote_plus, urljoin

from playwright.async_api import BrowserContext

from ..models import JobRecord
from ..ranking import semantic_match_score
from .base import BaseScraper


class FreshersworldScraper(BaseScraper):
    platform = "freshersworld"
    start_url = "https://www.freshersworld.com/jobs"

    async def scrape(self, context: BrowserContext, query: str, run_id: str) -> list[JobRecord]:
        page = context.pages[0] if context.pages else await context.new_page()
        target_url = f"{self.start_url}/jobsearch/{quote_plus(query).replace('+', '-')}-jobs?sort_by=date"
        await page.goto(target_url, wait_until="domcontentloaded")
        await self.human_pause()

        for _ in range(5):
            await page.mouse.wheel(0, 1450)
            await self.human_pause(0.45, 1.0)

        cards = []
        for selector in [".job-container", ".job-card", ".job-item", "article", "li:has(a[href*='/job'])"]:
            cards = await page.query_selector_all(selector)
            if cards:
                break

        jobs: list[JobRecord] = []
        for card in cards[:120]:
            title = await self.pick_text(card, [".job-title", ".job-title a", "h2", "h3", "[data-testid*='title']"])
            company = await self.pick_text(card, [".company-name", ".job-company-name", ".company"])
            location = await self.pick_text(card, [".location", ".job-location", "[data-testid*='location']"])
            description = await self.pick_text(card, [".job-desc", ".description", "p"])
            posted_at = await self.pick_text(card, ["time", ".job-posted", ".date"])
            experience_text = await self.pick_text(card, [".experience", ".exp", "[class*='experience']"])
            salary_text = await self.pick_text(card, [".salary", ".ctc", "[class*='salary']"])
            card_text = (await card.inner_text()).strip()
            parsed_title = re.search(
                r"(?:FEATURED\s+JOB\s*\|\s*)?(?P<title>.+?)\s+Jobs\s+Opening\s+in\b",
                card_text,
                flags=re.IGNORECASE | re.DOTALL,
            )
            if parsed_title:
                normalized = " ".join(parsed_title.group("title").split())
                if normalized:
                    title = normalized
            if not description and card_text:
                description = " ".join(card_text.split())[:400]

            tag_nodes = await card.query_selector_all(".skills span, .tag, .badge, .job-tags span")
            tags: list[str] = []
            for node in tag_nodes[:8]:
                text = (await node.inner_text()).strip()
                if text:
                    tags.append(text)

            href: str | None = None
            anchors = await card.query_selector_all("a[href]")
            for anchor in anchors:
                link = await anchor.get_attribute("href")
                if not link:
                    continue
                anchor_text = ((await anchor.inner_text()) or "").strip().lower()
                if "view" in anchor_text and "apply" in anchor_text:
                    href = link
                    break
                if href is None and ("/jobs/" in link or "/job/" in link):
                    href = link
            if not title or not href:
                continue

            score = semantic_match_score(query=query, title=title, description=description)
            jobs.append(
                JobRecord(
                    run_id=run_id,
                    platform=self.platform,
                    title=title,
                    company=company or "Unknown",
                    location=location or "India/Unknown",
                    url=urljoin("https://www.freshersworld.com", href),
                    description=description,
                    posted_at=posted_at or None,
                    salary_text=salary_text,
                    experience_text=experience_text,
                    tags=tags,
                    semantic_score=score,
                )
            )
        return jobs
