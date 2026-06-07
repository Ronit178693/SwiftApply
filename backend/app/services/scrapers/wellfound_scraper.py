"""
Wellfound (formerly AngelList) Scraper — Scrapes internship listings from wellfound.com

Strategy:
- Primary: Use Wellfound's GraphQL API to search for jobs
- Fallback: Scrape the public role listing pages via HTML
- Filters for intern/entry-level roles
- Extracts company info, compensation, and location from structured API data
"""

import re
import json
import logging
from typing import List, Dict, Optional
from bs4 import BeautifulSoup

from app.services.scrapers.base_scraper import BaseScraper

logger = logging.getLogger(__name__)


class WellfoundScraper(BaseScraper):
    """Scrapes internship listings from Wellfound (formerly AngelList Talent)."""

    PORTAL_NAME = "wellfound"
    BASE_URL = "https://wellfound.com"
    GRAPHQL_URL = "https://wellfound.com/graphql"

    # GraphQL query to search for startup jobs
    SEARCH_QUERY = """
    query StartupJobSearch($query: String!, $page: Int) {
        talent {
            seoLandingPageJobSearchResults(query: $query, page: $page) {
                results {
                    id
                    title
                    slug
                    description
                    liveStartDate
                    compensation
                    remoteOk
                    primaryRoleTitle
                    locationNames
                    startup {
                        name
                        slug
                        companyUrl
                        logoUrl
                        highConcept
                    }
                }
                totalCount
                perPage
            }
        }
    }
    """

    def _try_graphql_search(self, query: str) -> List[Dict]:
        """Attempt to search via Wellfound's GraphQL API."""
        jobs = []
        
        headers = {
            **self.DEFAULT_HEADERS,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": "https://wellfound.com/role/intern",
        }

        payload = {
            "query": self.SEARCH_QUERY,
            "variables": {
                "query": f"{query} intern",
                "page": 1,
            }
        }

        response = self._safe_post(self.GRAPHQL_URL, json_data=payload, headers=headers)
        if not response:
            return []

        try:
            data = response.json()
            search_results = (
                data.get("data", {})
                .get("talent", {})
                .get("seoLandingPageJobSearchResults", {})
                .get("results", [])
            )

            for result in search_results[:self.MAX_RESULTS_PER_QUERY]:
                startup = result.get("startup", {})
                company_name = startup.get("name", "Unknown Startup")
                company_slug = startup.get("slug", "")
                job_slug = result.get("slug", "")
                
                source_url = f"{self.BASE_URL}/company/{company_slug}/jobs/{job_slug}" if company_slug and job_slug else ""
                if not source_url:
                    source_url = startup.get("companyUrl", "")

                location_names = result.get("locationNames", [])
                location = ", ".join(location_names) if location_names else ("Remote" if result.get("remoteOk") else "Not specified")

                compensation = result.get("compensation", "")
                stipend = compensation if compensation else "Competitive / Equity"

                description = result.get("description", "")
                high_concept = startup.get("highConcept", "")
                jd_text = f"{description} | Company: {high_concept}" if high_concept else description

                job = self.normalize_job(
                    title=result.get("title", result.get("primaryRoleTitle", "Startup Intern")),
                    company=company_name,
                    jd_text=jd_text or f"Internship at {company_name}. Apply on Wellfound.",
                    source_url=source_url,
                    source_portal=self.PORTAL_NAME,
                    stipend=stipend,
                    location=location,
                    skills_required=query.split(),
                )
                jobs.append(job)

        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.error(f"[wellfound] Error parsing GraphQL response: {e}")

        return jobs

    def _try_html_scrape(self, query: str) -> List[Dict]:
        """Fallback: scrape Wellfound's role listing pages via HTML."""
        jobs = []
        
        # Build the role page URL
        formatted_role = re.sub(r'[^a-zA-Z0-9\s]', '', query.lower()).strip().replace(" ", "-")
        url = f"{self.BASE_URL}/role/{formatted_role}"
        
        logger.info(f"[wellfound] HTML fallback: {url}")
        response = self._safe_get(url)
        if not response:
            # Try alternate URL patterns
            url = f"{self.BASE_URL}/jobs?role={formatted_role}"
            response = self._safe_get(url)
            if not response:
                return []

        try:
            soup = BeautifulSoup(response.content, "lxml")
        except Exception:
            soup = BeautifulSoup(response.content, "html.parser")

        # Try to find job listing cards
        card_selectors = [
            "div[data-test='StartupResult']",
            "div.job-listing-card",
            "div.styles_component__card",
            "div[class*='JobListing']",
            "div[class*='startup-row']",
        ]

        cards = []
        for selector in card_selectors:
            cards = soup.select(selector)
            if cards:
                break

        if not cards:
            # Try parsing from embedded JSON/script data
            scripts = soup.select("script[type='application/json'], script#__NEXT_DATA__")
            for script in scripts:
                try:
                    data = json.loads(script.string or "")
                    # Navigate Next.js page props
                    if isinstance(data, dict) and "props" in data:
                        page_props = data.get("props", {}).get("pageProps", {})
                        listings = page_props.get("listings", page_props.get("jobs", []))
                        if isinstance(listings, list):
                            for listing in listings[:self.MAX_RESULTS_PER_QUERY]:
                                if isinstance(listing, dict):
                                    job = self.normalize_job(
                                        title=listing.get("title", listing.get("role", "Intern")),
                                        company=listing.get("company", {}).get("name", listing.get("companyName", "Startup")),
                                        jd_text=listing.get("description", "Apply on Wellfound."),
                                        source_url=listing.get("url", url),
                                        source_portal=self.PORTAL_NAME,
                                        stipend=listing.get("compensation", "Competitive"),
                                        location=listing.get("location", "Remote"),
                                        skills_required=query.split(),
                                    )
                                    jobs.append(job)
                except (json.JSONDecodeError, TypeError):
                    continue

        for card in cards[:self.MAX_RESULTS_PER_QUERY]:
            title_el = card.select_one("a[class*='title'], h4, h3, a[data-test='JobTitle']")
            company_el = card.select_one("a[class*='company'], h2, span[data-test='StartupName']")
            location_el = card.select_one("span[class*='location'], div[class*='location']")
            
            title = title_el.text.strip() if title_el else None
            if not title:
                continue
                
            company = company_el.text.strip() if company_el else "Startup"
            location = location_el.text.strip() if location_el else "Remote"
            
            # Extract link
            link = None
            link_el = card.select_one("a[href*='/jobs/'], a[href*='/company/']")
            if link_el:
                href = link_el.get("href", "")
                link = f"{self.BASE_URL}{href}" if href.startswith("/") else href

            job = self.normalize_job(
                title=title,
                company=company,
                jd_text=f"{title} at {company}. Location: {location}. Apply on Wellfound.",
                source_url=link or url,
                source_portal=self.PORTAL_NAME,
                stipend="Competitive / Equity",
                location=location,
                skills_required=query.split(),
            )
            jobs.append(job)

        return jobs

    def scrape(self, queries: List[str]) -> List[Dict]:
        """
        Scrape Wellfound for internship listings matching the given queries.
        
        Tries GraphQL API first, falls back to HTML scraping.
        
        Args:
            queries: Search terms derived from the student's resume
            
        Returns:
            List of normalized job dicts.
        """
        results = []
        seen_urls = set()

        for query in queries:
            logger.info(f"[wellfound] Searching: '{query}'")

            # Try GraphQL first
            jobs = self._try_graphql_search(query)
            
            if not jobs:
                logger.info(f"[wellfound] GraphQL returned nothing for '{query}', trying HTML fallback")
                jobs = self._try_html_scrape(query)

            logger.info(f"[wellfound] Found {len(jobs)} listings for '{query}'")

            # Deduplicate
            for job in jobs:
                if job["source_url"] not in seen_urls:
                    seen_urls.add(job["source_url"])
                    results.append(job)

        logger.info(f"[wellfound] Total scraped: {len(results)} listings")
        return results
