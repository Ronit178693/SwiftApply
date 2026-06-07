"""
LinkedIn Scraper — Fetches internship listings from LinkedIn.

Strategy (SaaS-ready, dual-mode):
1. **Production Mode (SERPAPI_KEY set)**: Uses SerpAPI's Google Jobs API which legally
   indexes LinkedIn job listings. This is the recommended approach for a SaaS product —
   no risk of IP blocks or ToS violations.
   
2. **Dev/Free Mode (no SERPAPI_KEY)**: Falls back to LinkedIn's public Guest Jobs API
   endpoint which returns HTML fragments without requiring login. Works for low-volume
   testing but will get blocked at scale.
"""

import os
import re
import json
import logging
from typing import List, Dict, Optional
from urllib.parse import quote_plus
from bs4 import BeautifulSoup

from app.services.scrapers.base_scraper import BaseScraper

logger = logging.getLogger(__name__)


class LinkedInScraper(BaseScraper):
    """
    Scrapes internship listings from LinkedIn.
    
    Automatically uses SerpAPI when SERPAPI_KEY is configured (recommended for SaaS),
    otherwise falls back to LinkedIn's public guest jobs endpoint.
    """

    PORTAL_NAME = "linkedin"
    
    # SerpAPI endpoint (production mode)
    SERPAPI_URL = "https://serpapi.com/search.json"
    
    # LinkedIn's guest jobs search API (free/dev mode)
    GUEST_API_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
    
    # Fallback: standard search page
    SEARCH_PAGE_URL = "https://www.linkedin.com/jobs/search"

    # LinkedIn-specific headers to mimic a real browser
    LINKEDIN_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
    }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.serpapi_key = os.environ.get("SERPAPI_KEY", "")
        self._mode = "serpapi" if self.serpapi_key else "guest"
        logger.info(f"[linkedin] Initialized in {self._mode} mode")

    # ──────────────────────────────────────────────────────────────
    # SerpAPI Mode (Production / SaaS)
    # ──────────────────────────────────────────────────────────────

    def _scrape_via_serpapi(self, query: str) -> List[Dict]:
        """
        Use SerpAPI's Google Jobs API to fetch LinkedIn-indexed job listings.
        This is the legally safe, scalable approach for SaaS.
        """
        params = {
            "engine": "google_jobs",
            "q": f"{query} internship",
            "location": "India",
            "gl": "in",
            "hl": "en",
            "chips": "date_posted:week",  # Posted in last week
            "api_key": self.serpapi_key,
        }

        logger.info(f"[linkedin/serpapi] Querying Google Jobs for: '{query} internship'")
        response = self._safe_get(self.SERPAPI_URL, params=params)
        
        if not response:
            return []

        jobs = []
        try:
            data = response.json()
            job_results = data.get("jobs_results", [])

            for result in job_results[:self.MAX_RESULTS_PER_QUERY]:
                title = result.get("title", "")
                company = result.get("company_name", "")
                location = result.get("location", "India")
                description = result.get("description", "")
                
                # Get the apply link — prefer LinkedIn if available
                apply_options = result.get("apply_options", [])
                source_url = ""
                for option in apply_options:
                    link = option.get("link", "")
                    if "linkedin.com" in link:
                        source_url = link
                        break
                if not source_url and apply_options:
                    source_url = apply_options[0].get("link", "")
                if not source_url:
                    source_url = result.get("share_link", result.get("job_id", ""))

                # Extract detected extensions (salary, schedule, etc.)
                extensions = result.get("detected_extensions", {})
                stipend = extensions.get("salary", "Not disclosed")
                schedule = extensions.get("schedule_type", "")
                
                if schedule:
                    description = f"[{schedule}] {description}"

                # Extract skills from highlights
                highlights = result.get("job_highlights", [])
                skills = []
                for highlight in highlights:
                    if highlight.get("title", "").lower() in ("qualifications", "requirements"):
                        skills.extend(highlight.get("items", []))

                job = self.normalize_job(
                    title=title,
                    company=company,
                    jd_text=description[:2000],  # Cap length
                    source_url=source_url,
                    source_portal=self.PORTAL_NAME,
                    stipend=stipend if stipend != "Not disclosed" else "Not disclosed",
                    location=location,
                    skills_required=skills[:10] if skills else query.split(),
                )
                jobs.append(job)

        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.error(f"[linkedin/serpapi] Error parsing response: {e}")

        return jobs

    # ──────────────────────────────────────────────────────────────
    # Guest API Mode (Free / Dev)
    # ──────────────────────────────────────────────────────────────

    def _build_guest_params(self, query: str, start: int = 0) -> dict:
        """Build the query parameters for LinkedIn's guest API."""
        return {
            "keywords": f"{query} internship",
            "location": "India",
            "f_TPR": "r604800",        # Posted in last 7 days
            "f_E": "1",                # Entry level
            "f_JT": "I",               # Job type: Internship
            "start": str(start),
            "sortBy": "R",             # Sort by relevance
        }

    def _parse_guest_api_response(self, html_content: str, query: str) -> List[Dict]:
        """Parse the HTML fragment returned by LinkedIn's guest jobs API."""
        jobs = []
        
        try:
            soup = BeautifulSoup(html_content, "lxml")
        except Exception:
            soup = BeautifulSoup(html_content, "html.parser")

        # The guest API returns <li> elements with job cards
        cards = soup.select("li")
        if not cards:
            # Fallback: try finding div-based cards
            cards = soup.select("div.base-card, div.job-search-card")

        for card in cards:
            if len(jobs) >= self.MAX_RESULTS_PER_QUERY:
                break

            # Extract title
            title_el = card.select_one(
                ".base-search-card__title, "
                ".base-card__full-link span, "
                "h3.base-search-card__title, "
                "a.base-card__full-link"
            )
            title = title_el.text.strip() if title_el else None

            # Extract company
            company_el = card.select_one(
                ".base-search-card__subtitle, "
                "h4.base-search-card__subtitle, "
                "a.hidden-nested-link"
            )
            company = company_el.text.strip() if company_el else None

            # Extract location
            location_el = card.select_one(
                ".job-search-card__location, "
                "span.job-search-card__location"
            )
            location = location_el.text.strip() if location_el else "India"

            # Extract link
            link_el = card.select_one(
                "a.base-card__full-link, "
                "a[href*='/jobs/view/']"
            )
            link = None
            if link_el:
                href = link_el.get("href", "")
                if href:
                    # Clean tracking params
                    link = href.split("?")[0] if "?" in href else href
                    if not link.startswith("http"):
                        link = f"https://www.linkedin.com{link}"

            # Extract date posted
            date_el = card.select_one(
                "time, "
                ".job-search-card__listdate, "
                ".job-search-card__listdate--new"
            )
            date_posted = date_el.get("datetime", "") if date_el else ""

            if title and link:
                jd_text = (
                    f"{title} at {company or 'company'}. "
                    f"Location: {location}. "
                    f"Posted: {date_posted or 'Recently'}. "
                    f"Search keyword: {query}. "
                    f"Apply on LinkedIn."
                )

                job = self.normalize_job(
                    title=title,
                    company=company or "Unknown Company",
                    jd_text=jd_text,
                    source_url=link,
                    source_portal=self.PORTAL_NAME,
                    stipend="Not disclosed",
                    location=location,
                    skills_required=query.split(),
                )
                jobs.append(job)

        return jobs

    def _scrape_via_guest_api(self, query: str) -> List[Dict]:
        """
        Scrape using LinkedIn's public Guest Jobs API.
        Free but unreliable at scale — use for dev/testing only.
        """
        params = self._build_guest_params(query)
        logger.info(f"[linkedin/guest] Searching: '{query} internship' via Guest API")

        response = self._safe_get(
            self.GUEST_API_URL,
            params=params,
            headers=self.LINKEDIN_HEADERS,
        )

        jobs = []
        if response:
            jobs = self._parse_guest_api_response(response.text, query)
            logger.info(f"[linkedin/guest] Guest API returned {len(jobs)} listings for '{query}'")
        
        # Fallback to standard search page
        if not jobs:
            logger.info(f"[linkedin/guest] Guest API empty for '{query}', trying search page fallback")
            params = {
                "keywords": f"{query} internship",
                "location": "India",
                "f_TPR": "r604800",
                "f_E": "1",
            }
            response = self._safe_get(
                self.SEARCH_PAGE_URL,
                params=params,
                headers=self.LINKEDIN_HEADERS,
            )
            if response:
                jobs = self._parse_guest_api_response(response.text, query)
                logger.info(f"[linkedin/guest] Search page fallback returned {len(jobs)} listings")

        return jobs

    # ──────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────

    def scrape(self, queries: List[str]) -> List[Dict]:
        """
        Scrape LinkedIn for internship listings matching the given queries.
        
        Automatically selects the best strategy:
        - SerpAPI (if SERPAPI_KEY is set) — production/SaaS mode
        - Guest API (if no key) — dev/testing mode
        
        Args:
            queries: Search terms derived from the student's resume
            
        Returns:
            List of normalized job dicts.
        """
        results = []
        seen_urls = set()

        for query in queries:
            if self._mode == "serpapi":
                jobs = self._scrape_via_serpapi(query)
            else:
                jobs = self._scrape_via_guest_api(query)

            # Deduplicate
            for job in jobs:
                if job["source_url"] not in seen_urls:
                    seen_urls.add(job["source_url"])
                    results.append(job)

        logger.info(f"[linkedin] Total scraped: {len(results)} listings (mode: {self._mode})")
        return results
