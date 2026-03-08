from __future__ import annotations

from urllib.parse import quote_plus, urljoin

from playwright.async_api import BrowserContext

from ..models import JobRecord
from ..ranking import semantic_match_score
from .base import BaseScraper
from .stealth import apply_stealth


class GlassdoorScraper(BaseScraper):
    platform = "glassdoor"
    start_url = "https://www.glassdoor.com/Job/jobs.htm"

    async def scrape(self, context: BrowserContext, query: str, run_id: str) -> list[JobRecord]:
        page = context.pages[0] if context.pages else await context.new_page()
        await apply_stealth(page)

        target_url = f"{self.start_url}?sc.keyword={quote_plus(query)}&fromAge=3&sortBy=date"
        try:
            await page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
        except Exception:
            return []
        await self.human_pause(1.5, 3.0)

        # Dismiss login / cookie modals that Glassdoor aggressively pushes
        for close_selector in [
            "button[aria-label='Close']",
            ".CloseButton",
            "[data-test='close-button']",
            "button.modal_closeIcon",
            "#onetrust-accept-btn-handler",
        ]:
            try:
                btn = await page.wait_for_selector(close_selector, timeout=3000)
                if btn:
                    await btn.click()
                    await self.human_pause(0.5, 1.0)
            except Exception:
                pass

        for _ in range(6):
            await page.mouse.wheel(0, 1500)
            await self.human_pause(0.6, 1.3)

        cards = []
        for selector in [
            "[data-test='jobListing']",
            "li[data-test='jobsCard']",
            ".JobCard_jobCard__wrapper",
            "article",
        ]:
            cards = await page.query_selector_all(selector)
            if cards:
                break

        jobs: list[JobRecord] = []
        for card in cards[:100]:
            title = await self.pick_text(card, [
                "[data-test='job-title']", ".JobCard_jobTitle",
                "a.jobTitle", "h2", "h3",
            ])
            company = await self.pick_text(card, [
                "[data-test='emp-name']", ".EmployerProfile_compactEmployerName",
                ".employer-name", ".company",
            ])
            location = await self.pick_text(card, [
                "[data-test='emp-location']", ".JobCard_location", ".location",
            ])
            description = await self.pick_text(card, [
                ".jobDescriptionContent", ".job-desc", "p", ".description",
            ])
            posted_at = await self.pick_text(card, [
                "[data-test='job-age']", "time", ".date",
            ])
            salary_text = await self.pick_text(card, [
                "[data-test='detailSalary']", ".salary-estimate", ".SalaryEstimate",
            ])

            tag_nodes = await card.query_selector_all(".JobCard_badge, .badge, .tag")
            tags: list[str] = []
            for node in tag_nodes[:8]:
                text = (await node.inner_text()).strip()
                if text:
                    tags.append(text)

            anchor = await card.query_selector(
                "a[href*='/job-listing/'], a[data-test='job-link'], a[href]"
            )
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
                    url=urljoin("https://www.glassdoor.com", href),
                    description=description,
                    posted_at=posted_at or None,
                    salary_text=salary_text,
                    tags=tags,
                    semantic_score=score,
                )
            )
        return jobs
