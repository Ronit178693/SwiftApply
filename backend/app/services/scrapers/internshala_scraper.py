"""
Internshala Scraper — Scrapes internship listings from internshala.com

Strategy:
- Direct HTTP GET to Internshala's internship listing pages
- URL pattern: https://internshala.com/internships/{keyword}-internship
- Uses adaptive CSS selectors with multiple fallbacks since Internshala
  periodically changes their DOM structure
- Captures top N listings per query keyword with full JD extraction
"""

import re
import logging
from typing import List, Dict, Optional
from bs4 import BeautifulSoup

from app.services.scrapers.base_scraper import BaseScraper

logger = logging.getLogger(__name__)


class InternshalaScrapser(BaseScraper):
    """Scrapes internship listings from Internshala."""

    PORTAL_NAME = "internshala"
    BASE_URL = "https://internshala.com"

    # Multiple selector sets to handle DOM changes over time
    # Internshala has changed their layout several times — we try each in order
    SELECTOR_STRATEGIES = [
        {
            # Strategy 1: Modern layout (2025+)
            "card": "div.individual_internship, div.internship_meta",
            "title": [".heading_4_5 a", ".profile a", "h3.heading_4_5 a"],
            "company": [".heading_6.company_name a", ".company_name a", "p.company_name"],
            "stipend": [".desktop-wrap .stipend", ".stipend", "span.stipend"],
            "location": [".individual_internship_details .locations a", ".location_link a", "a.location_link", "#location_names a"],
            "link_attr": "href",
        },
        {
            # Strategy 2: Alternate DOM structure
            "card": ".internship_meta, .individual_internship_header",
            "title": [".company a", "a.view_detail_button", ".heading_4_5"],
            "company": [".company_name", ".heading_6"],
            "stipend": [".stipend", ".ic-16-money + span"],
            "location": [".locations a", ".location_link"],
            "link_attr": "href",
        },
    ]

    def _try_selectors(self, element, selectors: List[str]) -> Optional[str]:
        """Try multiple CSS selectors and return the first match's text."""
        for selector in selectors:
            found = element.select_one(selector)
            if found and found.text.strip():
                return found.text.strip()
        return None

    def _try_link(self, element, selectors: List[str]) -> Optional[str]:
        """Try multiple CSS selectors and return the first match's href."""
        for selector in selectors:
            found = element.select_one(selector)
            if found:
                href = found.get("href", "")
                if href:
                    if href.startswith("/"):
                        return f"{self.BASE_URL}{href}"
                    elif href.startswith("http"):
                        return href
        return None

    def _build_search_url(self, query: str) -> str:
        """Build the Internshala search URL from a query string."""
        # Format: "Python Backend Intern" -> "python-backend-intern"
        formatted = re.sub(r'[^a-zA-Z0-9\s]', '', query.lower())
        formatted = formatted.strip().replace(" ", "-")
        
        # Remove trailing "intern" or "internship" since the URL already adds it
        formatted = re.sub(r'-?intern(ship)?$', '', formatted)
        formatted = formatted.strip("-")
        
        if not formatted:
            formatted = "software-development"
        
        return f"{self.BASE_URL}/internships/{formatted}-internship"

    def _extract_jd_from_listing(self, listing_url: str) -> str:
        """Fetch the full JD text from an individual listing page."""
        response = self._safe_get(listing_url)
        if not response:
            return ""
        
        try:
            soup = BeautifulSoup(response.content, "lxml")
            
            # Try multiple selectors for the JD content
            jd_selectors = [
                ".internship_details .text-container",
                "#about_company_section",
                ".detail_view .internship_details",
                ".about_company_text_container",
                ".internship_other_details_container",
            ]
            
            jd_parts = []
            for selector in jd_selectors:
                el = soup.select_one(selector)
                if el:
                    text = el.get_text(separator=" ", strip=True)
                    if text and len(text) > 30:
                        jd_parts.append(text)
            
            return " | ".join(jd_parts) if jd_parts else ""
        except Exception as e:
            logger.debug(f"[internshala] Error extracting JD from {listing_url}: {e}")
            return ""

    def _extract_skills_from_page(self, soup: BeautifulSoup) -> List[str]:
        """Extract skill tags from the listing page."""
        skills = []
        skill_elements = soup.select(".round_tabs, .skill_tag, .training_heading ~ .round_tabs_container .round_tabs")
        for el in skill_elements:
            skill = el.text.strip()
            if skill and len(skill) < 50:
                skills.append(skill)
        return skills

    def scrape(self, queries: List[str]) -> List[Dict]:
        """
        Scrape Internshala for internship listings matching the given queries.
        
        Args:
            queries: Search terms derived from the student's resume (e.g. ["Python Backend Intern"])
            
        Returns:
            List of normalized job dicts.
        """
        results = []
        seen_urls = set()

        for query in queries:
            url = self._build_search_url(query)
            logger.info(f"[internshala] Scraping: {url}")

            response = self._safe_get(url)
            if not response:
                logger.warning(f"[internshala] Failed to fetch listing page for query: {query}")
                continue

            try:
                soup = BeautifulSoup(response.content, "lxml")
            except Exception:
                soup = BeautifulSoup(response.content, "html.parser")

            jobs_found = 0

            # Try each selector strategy until one produces results
            for strategy in self.SELECTOR_STRATEGIES:
                cards = soup.select(strategy["card"])
                if not cards:
                    continue

                logger.info(f"[internshala] Found {len(cards)} cards for query '{query}' using strategy: {strategy['card']}")

                for card in cards:
                    if jobs_found >= self.MAX_RESULTS_PER_QUERY:
                        break

                    title = self._try_selectors(card, strategy["title"])
                    company = self._try_selectors(card, strategy["company"])
                    stipend = self._try_selectors(card, strategy["stipend"])
                    location = self._try_selectors(card, strategy["location"])
                    link = self._try_link(card, strategy["title"])

                    if not title or not link:
                        continue

                    # Deduplicate
                    if link in seen_urls:
                        continue
                    seen_urls.add(link)

                    # Fetch full JD from the listing page (extra request with throttling)
                    jd_text = self._extract_jd_from_listing(link)
                    if not jd_text:
                        jd_text = (
                            f"{title} internship at {company or 'company'}. "
                            f"Location: {location or 'India'}. Stipend: {stipend or 'Not disclosed'}. "
                            f"Search keyword: {query}. Apply on Internshala."
                        )

                    job = self.normalize_job(
                        title=title,
                        company=company or "Unknown Company",
                        jd_text=jd_text,
                        source_url=link,
                        source_portal=self.PORTAL_NAME,
                        stipend=stipend or "Not disclosed",
                        location=location or "Remote (India)",
                        skills_required=query.split(),
                    )
                    results.append(job)
                    jobs_found += 1

                # If we got results from this strategy, don't try the next one
                if jobs_found > 0:
                    break

            if jobs_found == 0:
                logger.warning(f"[internshala] No listings parsed for query '{query}'. Selectors may need updating.")

        logger.info(f"[internshala] Total scraped: {len(results)} listings")
        return results
