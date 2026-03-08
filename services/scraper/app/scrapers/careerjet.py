from __future__ import annotations

from urllib.parse import quote_plus, urljoin

from playwright.async_api import BrowserContext

from ..models import JobRecord
from ..ranking import semantic_match_score
from .base import BaseScraper
from .stealth import apply_stealth


class CareerJetScraper(BaseScraper):
    platform = "careerjet"
    start_url = "https://www.careerjet.com/search/jobs"

    async def scrape(self, context: BrowserContext, query: str, run_id: str) -> list[JobRecord]:
        page = context.pages[0] if context.pages else await context.new_page()
        await apply_stealth(page)

        target_url = f"{self.start_url}?s={quote_plus(query)}&l=&sort=date&nw=7"
        try:
            await page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
        except Exception:
            return []
        await self.human_pause(1.5, 3.0)

        # CareerJet uses Cloudflare Turnstile -- may block headless browsers entirely.
        # If the page contains a CAPTCHA challenge, return empty gracefully.
        try:
            content = await page.content()
            if "challenge" in content.lower() and "turnstile" in content.lower():
                return []
        except Exception:
            pass

        for _ in range(5):
            await page.mouse.wheel(0, 1450)
            await self.human_pause(0.5, 1.1)

        cards = []
        for selector in [
            "article.job",
            ".job",
            ".jix_robotjob",
            "li:has(a[href*='jobvacancyid'])",
            "article",
        ]:
            cards = await page.query_selector_all(selector)
            if cards:
                break

        jobs: list[JobRecord] = []
        for card in cards[:100]:
            title = await self.pick_text(card, ["h2 a", ".title", ".job-title a", "h2", "h3"])
            company = await self.pick_text(card, [".company", ".job-company", "p.company"])
            location = await self.pick_text(card, [".location", ".job-location", "ul.location li"])
            description = await self.pick_text(card, [".desc", ".description", "p"])
            posted_at = await self.pick_text(card, ["time", ".date"])
            salary_text = await self.pick_text(card, [".salary", ".job-salary"])

            tag_nodes = await card.query_selector_all(".tag, .badge")
            tags: list[str] = []
            for node in tag_nodes[:8]:
                text = (await node.inner_text()).strip()
                if text:
                    tags.append(text)

            anchor = await card.query_selector("a[href*='jobvacancyid'], h2 a, a[href]")
            href = await anchor.get_attribute("href") if anchor else None
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
                    url=urljoin("https://www.careerjet.com", href),
                    description=description,
                    posted_at=posted_at or None,
                    salary_text=salary_text,
                    tags=tags,
                    semantic_score=score,
                )
            )
        return jobs
