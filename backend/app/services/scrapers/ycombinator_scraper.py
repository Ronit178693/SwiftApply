"""
Y Combinator Scraper — Scrapes internship listings from YC ecosystem.

Strategy:
Two data sources:
1. Work at a Startup (workatastartup.com) — YC's official job board
   - Uses the public companies/jobs JSON API
   - Filters for intern/entry-level positions
   
2. Hacker News "Who is Hiring?" threads — Monthly threads where startups post jobs
   - Uses the Algolia HN Search API (fast, structured JSON)
   - Filters for intern-relevant posts
"""

import re
import json
import logging
from typing import List, Dict, Optional
from bs4 import BeautifulSoup

from app.services.scrapers.base_scraper import BaseScraper

logger = logging.getLogger(__name__)


class YCombinatorScraper(BaseScraper):
    """Scrapes internship listings from YC's Work at a Startup and HN Who's Hiring threads."""

    PORTAL_NAME = "ycombinator"

    # Work at a Startup endpoints
    WATS_BASE = "https://www.workatastartup.com"
    WATS_COMPANIES_URL = "https://www.workatastartup.com/companies.json"
    WATS_JOBS_URL = "https://www.workatastartup.com/jobs"

    # HN Algolia Search API
    HN_ALGOLIA_URL = "https://hn.algolia.com/api/v1/search"

    def _scrape_work_at_startup(self, query: str) -> List[Dict]:
        """
        Scrape the Work at a Startup job board.
        
        Attempts to use the JSON API first, falls back to HTML scraping.
        """
        jobs = []

        # Attempt 1: JSON API
        params = {
            "query": query,
            "page": "1",
        }
        
        logger.info(f"[ycombinator] Querying Work at a Startup API for '{query}'")
        response = self._safe_get(self.WATS_COMPANIES_URL, params=params)
        
        if response:
            try:
                data = response.json()
                companies = data if isinstance(data, list) else data.get("companies", data.get("results", []))
                
                for company in companies:
                    if len(jobs) >= self.MAX_RESULTS_PER_QUERY:
                        break
                    
                    if isinstance(company, dict):
                        company_name = company.get("name", "YC Startup")
                        company_slug = company.get("slug", "")
                        
                        # Check if the company has relevant job listings
                        company_jobs = company.get("jobs", [])
                        if not company_jobs:
                            # Treat the company itself as a listing
                            description = company.get("description", company.get("one_liner", ""))
                            if not self._is_intern_relevant(f"{company_name} {description}", query):
                                continue
                            
                            source_url = f"{self.WATS_BASE}/companies/{company_slug}" if company_slug else self.WATS_BASE
                            
                            job = self.normalize_job(
                                title=f"Intern at {company_name}",
                                company=company_name,
                                jd_text=description or f"Internship opportunity at YC-backed startup {company_name}.",
                                source_url=source_url,
                                source_portal=self.PORTAL_NAME,
                                stipend="Competitive / Equity",
                                location=company.get("location", "Remote"),
                                skills_required=query.split(),
                            )
                            jobs.append(job)
                        else:
                            for cjob in company_jobs:
                                if len(jobs) >= self.MAX_RESULTS_PER_QUERY:
                                    break
                                    
                                title = cjob.get("title", "Software Engineering Intern")
                                
                                # Filter for intern-relevant titles
                                if not self._is_intern_relevant(title, query):
                                    continue
                                
                                job_slug = cjob.get("slug", "")
                                source_url = cjob.get("url", f"{self.WATS_BASE}/companies/{company_slug}/jobs/{job_slug}")
                                
                                job = self.normalize_job(
                                    title=title,
                                    company=company_name,
                                    jd_text=cjob.get("description", f"{title} at {company_name}. YC-backed startup."),
                                    source_url=source_url,
                                    source_portal=self.PORTAL_NAME,
                                    stipend=cjob.get("salary_range", cjob.get("compensation", "Competitive / Equity")),
                                    location=cjob.get("location", company.get("location", "Remote")),
                                    skills_required=query.split(),
                                )
                                jobs.append(job)
                                
            except (json.JSONDecodeError, TypeError, KeyError) as e:
                logger.error(f"[ycombinator] Error parsing WATS JSON: {e}")

        # Attempt 2: HTML scraping fallback
        if not jobs:
            logger.info(f"[ycombinator] JSON API returned nothing, trying HTML scrape")
            
            search_url = f"{self.WATS_JOBS_URL}?query={query}"
            response = self._safe_get(search_url)
            
            if response:
                try:
                    soup = BeautifulSoup(response.content, "lxml")
                except Exception:
                    soup = BeautifulSoup(response.content, "html.parser")
                
                # Try to extract from Next.js data or standard card elements
                script_el = soup.select_one("script#__NEXT_DATA__")
                if script_el and script_el.string:
                    try:
                        next_data = json.loads(script_el.string)
                        page_props = next_data.get("props", {}).get("pageProps", {})
                        
                        job_listings = page_props.get("jobs", page_props.get("jobListings", []))
                        for listing in job_listings[:self.MAX_RESULTS_PER_QUERY]:
                            if isinstance(listing, dict):
                                title = listing.get("title", "Engineering Intern")
                                company_data = listing.get("company", listing.get("startup", {}))
                                company_name = company_data.get("name", "YC Startup") if isinstance(company_data, dict) else str(company_data)
                                
                                job = self.normalize_job(
                                    title=title,
                                    company=company_name,
                                    jd_text=listing.get("description", f"{title} at {company_name}."),
                                    source_url=listing.get("url", search_url),
                                    source_portal=self.PORTAL_NAME,
                                    stipend=listing.get("salary", "Competitive"),
                                    location=listing.get("location", "Remote"),
                                    skills_required=query.split(),
                                )
                                jobs.append(job)
                    except json.JSONDecodeError:
                        pass

                # Standard HTML card extraction
                if not jobs:
                    cards = soup.select("div[class*='job'], div[class*='listing'], a[class*='job']")
                    for card in cards[:self.MAX_RESULTS_PER_QUERY]:
                        title_el = card.select_one("h2, h3, h4, [class*='title']")
                        company_el = card.select_one("[class*='company'], [class*='startup']")
                        
                        if title_el:
                            link_el = card if card.name == "a" else card.select_one("a")
                            href = link_el.get("href", "") if link_el else ""
                            source_url = f"{self.WATS_BASE}{href}" if href.startswith("/") else (href or search_url)
                            
                            job = self.normalize_job(
                                title=title_el.text.strip(),
                                company=company_el.text.strip() if company_el else "YC Startup",
                                jd_text=f"{title_el.text.strip()} at YC-backed startup. Apply on Work at a Startup.",
                                source_url=source_url,
                                source_portal=self.PORTAL_NAME,
                                stipend="Competitive",
                                location="Remote",
                                skills_required=query.split(),
                            )
                            jobs.append(job)

        return jobs

    def _scrape_hn_who_is_hiring(self, query: str) -> List[Dict]:
        """
        Scrape the monthly "Who is Hiring?" threads on Hacker News via Algolia API.
        
        These threads are a goldmine for startup internship opportunities,
        especially from YC companies.
        """
        jobs = []

        # Search for recent "Who is Hiring" threads
        params = {
            "query": f"{query} intern",
            "tags": "comment",
            "numericFilters": "created_at_i>1717200000",  # Last ~6 months
            "hitsPerPage": str(self.MAX_RESULTS_PER_QUERY * 2),  # Fetch extra since many won't be relevant
        }

        logger.info(f"[ycombinator] Searching HN 'Who is Hiring' for '{query} intern'")
        response = self._safe_get(self.HN_ALGOLIA_URL, params=params)
        
        if not response:
            return []

        try:
            data = response.json()
            hits = data.get("hits", [])
            
            for hit in hits:
                if len(jobs) >= self.MAX_RESULTS_PER_QUERY:
                    break
                
                comment_text = hit.get("comment_text", "")
                if not comment_text:
                    continue
                
                # Only process comments that look like job postings
                # (typically they mention company, role, location, etc.)
                text_lower = comment_text.lower()
                if not any(kw in text_lower for kw in ["intern", "junior", "entry", "new grad", "student"]):
                    continue

                # Extract company name (usually the first line or first bold text)
                clean_text = BeautifulSoup(comment_text, "html.parser").get_text(separator=" ", strip=True)
                lines = [line.strip() for line in clean_text.split("\n") if line.strip()]
                
                company_name = lines[0][:100] if lines else "HN Startup"
                # Clean up common patterns like "Company Name | Role | Location"
                if "|" in company_name:
                    parts = company_name.split("|")
                    company_name = parts[0].strip()
                
                # Build the HN comment link
                object_id = hit.get("objectID", "")
                source_url = f"https://news.ycombinator.com/item?id={object_id}" if object_id else ""

                # Try to extract location from the comment
                location = "Remote"
                location_patterns = [r"(?:remote|onsite|hybrid|location[:\s]+)([\w\s,]+)", r"\b(San Francisco|New York|London|Berlin|Remote|Hybrid)\b"]
                for pattern in location_patterns:
                    match = re.search(pattern, clean_text, re.IGNORECASE)
                    if match:
                        location = match.group(1).strip()[:100]
                        break

                job = self.normalize_job(
                    title=f"Intern/Junior Role at {company_name}",
                    company=company_name,
                    jd_text=clean_text[:1000],  # Cap at 1000 chars
                    source_url=source_url,
                    source_portal=self.PORTAL_NAME,
                    stipend="Competitive",
                    location=location,
                    skills_required=query.split(),
                )
                jobs.append(job)

        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.error(f"[ycombinator] Error parsing HN Algolia response: {e}")

        return jobs

    @staticmethod
    def _is_intern_relevant(text: str, query: str) -> bool:
        """Check if a text contains intern-relevant keywords or query terms."""
        text_lower = text.lower()
        query_lower = query.lower()
        
        # Check for intern-related keywords
        intern_keywords = ["intern", "internship", "junior", "entry level", "entry-level", "new grad", "student", "co-op", "trainee"]
        has_intern_keyword = any(kw in text_lower for kw in intern_keywords)
        
        # Check if any query terms appear
        query_terms = [t for t in query_lower.split() if len(t) > 2]
        has_query_match = any(term in text_lower for term in query_terms)
        
        return has_intern_keyword or has_query_match

    def scrape(self, queries: List[str]) -> List[Dict]:
        """
        Scrape YC ecosystem for internship listings matching the given queries.
        
        Combines results from:
        1. Work at a Startup (workatastartup.com)
        2. HN "Who is Hiring?" threads
        
        Args:
            queries: Search terms derived from the student's resume
            
        Returns:
            List of normalized job dicts.
        """
        results = []
        seen_urls = set()

        for query in queries:
            logger.info(f"[ycombinator] Searching: '{query}'")

            # Source 1: Work at a Startup
            wats_jobs = self._scrape_work_at_startup(query)
            logger.info(f"[ycombinator] WATS returned {len(wats_jobs)} listings for '{query}'")

            # Source 2: HN Who is Hiring
            hn_jobs = self._scrape_hn_who_is_hiring(query)
            logger.info(f"[ycombinator] HN returned {len(hn_jobs)} listings for '{query}'")

            # Merge and deduplicate
            for job in wats_jobs + hn_jobs:
                url = job["source_url"]
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    results.append(job)

        logger.info(f"[ycombinator] Total scraped: {len(results)} listings")
        return results
