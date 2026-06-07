# Scrapers sub-package for multi-portal internship scraping
from app.services.scrapers.base_scraper import BaseScraper
from app.services.scrapers.internshala_scraper import InternshalaScrapser
from app.services.scrapers.linkedin_scraper import LinkedInScraper
from app.services.scrapers.wellfound_scraper import WellfoundScraper
from app.services.scrapers.ycombinator_scraper import YCombinatorScraper

__all__ = [
    "BaseScraper",
    "InternshalaScrapser",
    "LinkedInScraper",
    "WellfoundScraper",
    "YCombinatorScraper",
]
