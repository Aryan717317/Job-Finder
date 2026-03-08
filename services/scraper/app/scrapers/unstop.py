from __future__ import annotations

from urllib.parse import quote_plus, urljoin

from playwright.async_api import BrowserContext

from ..models import JobRecord
from ..ranking import semantic_match_score
from .base import BaseScraper
from .stealth import apply_stealth


# Fresher-focused queries for Software Dev, AI/ML, and Data Science roles.
# The scraper runs through each of these for every incoming search query,
# ensuring broad coverage of entry-level opportunities on Unstop.
_FRESHER_QUERY_VARIANTS: list[str] = [
    "{query} Fresher",
    "Software Developer Fresher",
    "Software Engineer Entry Level",
    "SDE Fresher 2024 2025 2026",
    "Machine Learning Engineer Fresher",
    "AI ML Engineer Entry Level",
    "Data Scientist Fresher",
    "Data Analyst Entry Level",
    "Data Science Fresher",
    "Python Developer Fresher",
    "Deep Learning Engineer Fresher",
    "NLP Engineer Entry Level",
    "Generative AI Fresher",
    "Prompt Engineer",
]


class UnstopScraper(BaseScraper):
    """Scraper for Unstop (formerly Dare2Compete) – fresher jobs in SDE, AI/ML & Data Science."""

    platform = "unstop"
    start_url = "https://unstop.com/jobs"

    async def scrape(self, context: BrowserContext, query: str, run_id: str) -> list[JobRecord]:
        page = context.pages[0] if context.pages else await context.new_page()
        await apply_stealth(page)

        seen_urls: set[str] = set()
        all_jobs: list[JobRecord] = []

        # Build the list of search terms: the caller's query plus fresher variants
        search_terms = [variant.replace("{query}", query) for variant in _FRESHER_QUERY_VARIANTS]

        for term in search_terms:
            target_url = f"{self.start_url}?search={quote_plus(term)}&sort=posted_new"
            await page.goto(target_url, wait_until="domcontentloaded")
            await self.human_pause(1.0, 2.5)

            # Scroll to load lazy-rendered job cards
            for _ in range(6):
                await page.mouse.wheel(0, 1600)
                await self.human_pause(0.5, 1.2)

            # Try multiple selectors (Unstop redesigns periodically)
            cards = []
            for selector in [
                ".single_profile",
                ".opp-listing",
                ".opportunity-card",
            ]:
                cards = await page.query_selector_all(selector)
                if cards:
                    break
                    
            if not cards:
                title = await page.title()
                html_snippet = (await page.content())[:800]
                raise Exception(f"UNSTOP ZERO CARDS. Title: {title} | HTML Snippet: {html_snippet}")

            for card in cards[:60]:
                jobs = await self._extract_card(card, query, run_id, seen_urls)
                all_jobs.extend(jobs)

        return all_jobs

    async def _extract_card(
        self,
        card,
        query: str,
        run_id: str,
        seen_urls: set[str],
    ) -> list[JobRecord]:
        """Extract a single job card; returns empty list if duplicate or invalid."""
        title = await self.pick_text(card, [
            "h2", "h3",
            ".opp-title", ".opportunity-title",
            "[data-testid*='title']", "a.title",
        ])
        company = await self.pick_text(card, [
            ".company-name", ".org-name", ".company",
            "[data-testid*='company']", ".opp-company",
        ])
        location = await self.pick_text(card, [
            ".location", ".loc",
            "[data-testid*='location']", ".opp-location",
        ])
        description = await self.pick_text(card, [
            ".desc", ".description", "p",
            "[data-testid*='description']",
        ])
        posted_at = await self.pick_text(card, [
            ".date", ".posted-date", "time",
            "[data-testid*='date']", ".opp-date",
        ])
        experience_text = await self.pick_text(card, [
            ".experience", ".exp",
            "[data-testid*='experience']",
        ])
        salary_text = await self.pick_text(card, [
            ".stipend", ".salary", ".ctc",
            "[data-testid*='salary']",
        ])

        # Extract the job detail link
        anchor = await card.query_selector(
            "a[href*='/job/'], a[href*='/opportunity/'], a[href*='/jobs/'], a[href]"
        )
        href = await anchor.get_attribute("href") if anchor else None
        if not title or not href:
            return []

        full_url = urljoin("https://unstop.com", href)

        # Deduplicate across multiple search terms
        if full_url in seen_urls:
            return []
        seen_urls.add(full_url)

        # Extract skill/tag labels
        tag_nodes = await card.query_selector_all(
            ".badge, .tag, .chip, .skill, span[class*='tag'], span[class*='skill']"
        )
        tags: list[str] = []
        for node in tag_nodes[:8]:
            text = (await node.inner_text()).strip()
            if text:
                tags.append(text)

        score = semantic_match_score(query=query, title=title, description=description)
        return [
            JobRecord(
                run_id=run_id,
                platform=self.platform,
                title=title,
                company=company or "Unknown",
                location=location or "India/Unknown",
                url=full_url,
                description=description,
                posted_at=posted_at or None,
                employment_type="Fresher",
                salary_text=salary_text,
                experience_text=experience_text,
                tags=tags,
                semantic_score=score,
            )
        ]
