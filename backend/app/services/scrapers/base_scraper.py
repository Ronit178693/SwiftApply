"""
Base scraper class providing common infrastructure for all portal scrapers.
Includes rate limiting, shared HTTP headers, proxy support, error handling, and logging.

For SaaS production:
- Set PROXY_URL env var to route requests through a rotating proxy service
  (e.g., "http://user:pass@proxy.example.com:8080")
- Set SERPAPI_KEY for LinkedIn (see linkedin_scraper.py)
"""

import os
import time
import logging
import requests
from abc import ABC, abstractmethod
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


class BaseScraper(ABC):
    """
    Abstract base class for all internship portal scrapers.
    
    Every portal scraper must implement the `scrape()` method which accepts
    a list of search query strings and returns a list of normalized job dicts.
    """

    # Common browser-like headers to reduce bot detection
    DEFAULT_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
    }

    # Minimum seconds between consecutive HTTP requests to the same portal
    RATE_LIMIT_SECONDS: float = 3.0

    # Maximum number of listings to capture per search query
    MAX_RESULTS_PER_QUERY: int = 5

    # Portal identifier string (set by subclasses)
    PORTAL_NAME: str = "unknown"

    def __init__(self, rate_limit: Optional[float] = None, max_results: Optional[int] = None,
                 proxy_url: Optional[str] = None):
        if rate_limit is not None:
            self.RATE_LIMIT_SECONDS = rate_limit
        if max_results is not None:
            self.MAX_RESULTS_PER_QUERY = max_results
        
        # Persistent session for connection pooling
        self.session = requests.Session()
        self.session.headers.update(self.DEFAULT_HEADERS)
        
        # Configure proxy for SaaS scalability
        # Reads from constructor arg, then PROXY_URL env var
        self._proxy_url = proxy_url or os.environ.get("PROXY_URL", "")
        if self._proxy_url:
            self.session.proxies = {
                "http": self._proxy_url,
                "https": self._proxy_url,
            }
            # Disable SSL verification for proxies that intercept SSL handshakes (like ScraperAPI)
            self.session.verify = False
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            logger.info(f"[{self.PORTAL_NAME}] Proxy configured (SSL bypass active): {self._proxy_url.split('@')[-1] if '@' in self._proxy_url else 'configured'}")
        
        # Track last request time for rate limiting
        self._last_request_time: float = 0.0

    def _throttle(self):
        """Enforce minimum delay between consecutive requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.RATE_LIMIT_SECONDS:
            wait_time = self.RATE_LIMIT_SECONDS - elapsed
            logger.debug(f"[{self.PORTAL_NAME}] Rate limiting: sleeping {wait_time:.1f}s")
            time.sleep(wait_time)
        self._last_request_time = time.time()

    def _safe_get(self, url: str, params: Optional[dict] = None, 
                  headers: Optional[dict] = None, timeout: int = 15) -> Optional[requests.Response]:
        """
        Make a rate-limited GET request with error handling.
        Returns the Response object, or None if the request failed.
        """
        self._throttle()
        try:
            merged_headers = {**self.DEFAULT_HEADERS, **(headers or {})}
            response = self.session.get(url, params=params, headers=merged_headers, timeout=timeout)
            
            if response.status_code == 200:
                return response
            elif response.status_code == 429:
                logger.warning(f"[{self.PORTAL_NAME}] Rate limited (429) on {url}. Backing off 10s.")
                time.sleep(10)
                return None
            elif response.status_code == 403:
                logger.warning(f"[{self.PORTAL_NAME}] Forbidden (403) on {url}. Likely bot-detected.")
                return None
            else:
                logger.warning(f"[{self.PORTAL_NAME}] HTTP {response.status_code} on {url}")
                return None
        except requests.exceptions.Timeout:
            logger.error(f"[{self.PORTAL_NAME}] Timeout on {url}")
            return None
        except requests.exceptions.ConnectionError:
            logger.error(f"[{self.PORTAL_NAME}] Connection error on {url}")
            return None
        except Exception as e:
            logger.error(f"[{self.PORTAL_NAME}] Unexpected error on {url}: {str(e)}")
            return None

    def _safe_post(self, url: str, json_data: Optional[dict] = None,
                   headers: Optional[dict] = None, timeout: int = 15) -> Optional[requests.Response]:
        """
        Make a rate-limited POST request with error handling.
        Returns the Response object, or None if the request failed.
        """
        self._throttle()
        try:
            merged_headers = {**self.DEFAULT_HEADERS, **(headers or {})}
            response = self.session.post(url, json=json_data, headers=merged_headers, timeout=timeout)
            
            if response.status_code == 200:
                return response
            else:
                logger.warning(f"[{self.PORTAL_NAME}] POST HTTP {response.status_code} on {url}")
                return None
        except Exception as e:
            logger.error(f"[{self.PORTAL_NAME}] POST error on {url}: {str(e)}")
            return None

    @staticmethod
    def normalize_job(
        title: str,
        company: str,
        jd_text: str,
        source_url: str,
        source_portal: str,
        stipend: str = "Not disclosed",
        location: str = "Remote",
        skills_required: Optional[List[str]] = None,
    ) -> Dict:
        """
        Build a normalized job dictionary matching the DB schema.
        All portal scrapers must return jobs in this format.
        """
        return {
            "title": title.strip() if title else "Untitled Position",
            "company": company.strip() if company else "Unknown Company",
            "jd_text": jd_text.strip() if jd_text else "",
            "source_url": source_url.strip() if source_url else "",
            "source_portal": source_portal.lower(),
            "stipend": stipend.strip() if stipend else "Not disclosed",
            "location": location.strip() if location else "Remote",
            "skills_required": skills_required or [],
        }

    @abstractmethod
    def scrape(self, queries: List[str]) -> List[Dict]:
        """
        Scrape internship listings from the portal for the given search queries.
        
        Args:
            queries: List of search query strings (e.g., ["Python Backend Intern", "React Developer Intern"])
            
        Returns:
            List of normalized job dicts matching the schema from normalize_job().
        """
        pass

    def __repr__(self):
        return f"<{self.__class__.__name__} portal={self.PORTAL_NAME}>"
