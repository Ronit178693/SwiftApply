"""
Scraper Service — Orchestrator for multi-portal internship scraping.

Coordinates all 4 portal scrapers (Internshala, LinkedIn, Wellfound, Y Combinator),
runs them concurrently using a thread pool, merges/deduplicates results, and caches
them in the PostgreSQL database.
"""

import logging
import time
import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Optional, Set
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError, OperationalError

from app.models.models import Job
from app.services.scrapers.internshala_scraper import InternshalaScrapser
from app.services.scrapers.linkedin_scraper import LinkedInScraper
from app.services.scrapers.wellfound_scraper import WellfoundScraper
from app.services.scrapers.ycombinator_scraper import YCombinatorScraper

logger = logging.getLogger(__name__)

# Registry of available portal scrapers
SCRAPER_REGISTRY = {
    "internshala": InternshalaScrapser,
    "linkedin": LinkedInScraper,
    "wellfound": WellfoundScraper,
    "ycombinator": YCombinatorScraper,
}

# All portal names for convenience
ALL_PORTALS = list(SCRAPER_REGISTRY.keys())


def fetch_mock_internships() -> list:
    """
    Returns a list of high-quality mock internship listings for fallback
    or testing purposes.
    """
    return [
        {
            "title": "Backend Engineering Intern",
            "company": "TechScale Solutions",
            "jd_text": (
                "TechScale is looking for a backend intern to join our platform team. "
                "You will build scalable APIs, optimize queries, and integrate third-party webhooks. "
                "Skills required: Python, FastAPI, SQL, PostgreSQL, Git, REST APIs, and Docker."
            ),
            "source_url": "https://careers.techscale.io/jobs/backend-intern-101",
            "source_portal": "mock",
            "stipend": "Rs. 25,000 / month",
            "location": "Remote (India)",
            "skills_required": ["Python", "FastAPI", "SQL", "PostgreSQL", "Git", "REST APIs"]
        },
        {
            "title": "Software Development Intern (Full-Stack)",
            "company": "SportsPulse Inc.",
            "jd_text": (
                "Join our Bangalore team to build real-time sports analytics dashboards. "
                "You will work on React 19 frontends and Node.js/Express backends, deploying services on Vercel and AWS. "
                "Experience with Socket.io, state management (Zustand), and payment gateway integrations (Razorpay) is a plus. "
                "Requirements: React.js, Node.js, Express.js, MongoDB, JavaScript, Socket.io, CSS3."
            ),
            "source_url": "https://sportspulse.co/careers/fullstack-intern-bangalore",
            "source_portal": "mock",
            "stipend": "Rs. 30,000 / month",
            "location": "Bangalore, India",
            "skills_required": ["React.js", "Node.js", "Express.js", "MongoDB", "JavaScript", "Socket.io", "CSS3", "Razorpay", "Zustand"]
        },
        {
            "title": "Machine Learning Research Intern",
            "company": "Cognitive Defense Systems",
            "jd_text": (
                "Work on military and defense simulation environments. The role involves creating adversarial combat agents "
                "using reinforcement learning, PyTorch models, and custom combat simulations in Python. "
                "Required qualifications: Python, PyTorch, NumPy, SciPy, Pandas, Scikit-learn, LSTMs, and Feature Engineering."
            ),
            "source_url": "https://cogdefense.mil/careers/ml-internship-tactical",
            "source_portal": "mock",
            "stipend": "Rs. 45,000 / month",
            "location": "Delhi NCR, India",
            "skills_required": ["Python", "PyTorch", "NumPy", "SciPy", "Pandas", "Scikit-learn", "LSTMs"]
        },
        {
            "title": "Decentralized Finance (DeFi) Developer Intern",
            "company": "BlockAnchor Labs",
            "jd_text": (
                "BlockAnchor Labs builds decentralized transparency products. We are looking for an intern familiar with "
                "blockchain SDKs (like Stellar SDK, Horizon API) to build dual-ledger escrow systems, lockups, and audit pipelines. "
                "Requirements: JavaScript, Node.js, Express.js, MongoDB, Stellar SDK, Horizon, and JWT authentication."
            ),
            "source_url": "https://blockanchor.io/jobs/blockchain-intern",
            "source_portal": "mock",
            "stipend": "Rs. 35,000 / month",
            "location": "Remote",
            "skills_required": ["JavaScript", "Node.js", "Express.js", "MongoDB", "Stellar SDK", "Horizon", "JWT"]
        }
    ]


def _generate_fallback_url(job_data: dict) -> str:
    """Generate a deterministic unique URL for jobs that have no source_url."""
    content = f"{job_data.get('title', '')}-{job_data.get('company', '')}-{job_data.get('source_portal', '')}"
    url_hash = hashlib.md5(content.encode()).hexdigest()[:12]
    return f"https://autointern.local/generated/{url_hash}"


def _run_single_scraper(portal_name: str, queries: List[str]) -> Dict:
    """
    Run a single portal scraper and return its results with metadata.
    This function is called inside the thread pool.
    """
    start_time = time.time()
    try:
        scraper_class = SCRAPER_REGISTRY[portal_name]
        scraper = scraper_class()
        jobs = scraper.scrape(queries)
        elapsed = time.time() - start_time
        
        logger.info(f"[orchestrator] {portal_name} completed in {elapsed:.1f}s — {len(jobs)} jobs found")
        return {
            "portal": portal_name,
            "jobs": jobs,
            "count": len(jobs),
            "elapsed_seconds": round(elapsed, 1),
            "success": True,
            "error": None,
        }
    except Exception as e:
        elapsed = time.time() - start_time
        logger.error(f"[orchestrator] {portal_name} FAILED after {elapsed:.1f}s: {str(e)}")
        return {
            "portal": portal_name,
            "jobs": [],
            "count": 0,
            "elapsed_seconds": round(elapsed, 1),
            "success": False,
            "error": str(e),
        }


def _cache_jobs_to_db(db: Session, jobs: List[Dict]) -> tuple:
    """
    Insert jobs into the database one-by-one with proper error isolation.
    
    Each job is inserted in its own transaction savepoint so that a single
    failure doesn't roll back the entire batch.
    
    Returns:
        (inserted_count, skipped_count, error_count)
    """
    inserted = 0
    skipped = 0
    errors = 0

    for job_data in jobs:
        try:
            source_url = job_data.get("source_url", "").strip()

            # Ensure every job has a source_url (required for dedup)
            if not source_url:
                source_url = _generate_fallback_url(job_data)
                job_data["source_url"] = source_url

            # Check for existing job with this URL
            existing = db.query(Job.id).filter(Job.source_url == source_url).first()
            if existing:
                skipped += 1
                continue

            new_job = Job(
                title=(job_data.get("title") or "Untitled Position")[:255],
                company=(job_data.get("company") or "Unknown Company")[:255],
                jd_text=job_data.get("jd_text") or "No description available.",
                source_url=source_url[:512],
                stipend=(job_data.get("stipend") or "Not disclosed")[:100],
                location=(job_data.get("location") or "Remote")[:255],
                source_portal=(job_data.get("source_portal") or "unknown")[:50],
                skills_required=job_data.get("skills_required") or [],
            )
            db.add(new_job)
            db.flush()  # Flush to detect constraint violations immediately
            inserted += 1

        except IntegrityError as ie:
            # Duplicate URL hit the unique constraint — expected, just skip
            db.rollback()
            skipped += 1
            logger.debug(f"[cache] Duplicate URL skipped (constraint): {job_data.get('source_url', '?')[:80]}")
        except OperationalError as oe:
            db.rollback()
            errors += 1
            logger.error(f"[cache] DB operational error inserting job: {str(oe)[:150]}")
        except Exception as e:
            db.rollback()
            errors += 1
            logger.error(f"[cache] Unexpected error inserting job '{job_data.get('title', '?')}': {str(e)[:150]}")

    # Final commit for all successfully added jobs
    if inserted > 0:
        try:
            db.commit()
            logger.info(f"[cache] Successfully committed {inserted} new job(s) to database.")
        except Exception as commit_err:
            logger.error(f"[cache] Final commit failed: {str(commit_err)[:150]}")
            db.rollback()
            inserted = 0

    return inserted, skipped, errors


def scrape_multi_portal(
    db: Session,
    queries: List[str],
    force_mock: bool = False,
    portals: Optional[List[str]] = None,
) -> Dict:
    """
    Orchestrate scraping across multiple portals concurrently.
    
    Iterates through the search queries generated from the student's resume,
    scrapes internship positions across the selected portals, deduplicates,
    and caches them in the PostgreSQL database.
    
    Args:
        db: SQLAlchemy database session
        queries: List of search query strings derived from resume parsing
        force_mock: If True, skip real scraping and use mock data
        portals: List of portal names to scrape. Defaults to all 4 portals.
        
    Returns:
        Dict with scraping results summary including per-portal stats.
    """
    # Determine which portals to scrape
    if portals:
        active_portals = [p for p in portals if p in SCRAPER_REGISTRY]
        if not active_portals:
            logger.warning(f"No valid portals specified: {portals}. Using all portals.")
            active_portals = ALL_PORTALS
    else:
        active_portals = ALL_PORTALS

    # Handle mock mode
    if force_mock or not queries:
        logger.info("Scraper running in mock mode or queries empty. Loading mock internships.")
        scraped_jobs = fetch_mock_internships()
        portal_stats = [{"portal": "mock", "count": len(scraped_jobs), "success": True, "elapsed_seconds": 0, "error": None}]
    else:
        logger.info(f"Starting concurrent scraping across {len(active_portals)} portals: {active_portals}")
        logger.info(f"Search queries: {queries}")
        
        scraped_jobs = []
        portal_stats = []
        
        # Run all portal scrapers concurrently using a thread pool
        with ThreadPoolExecutor(max_workers=len(active_portals)) as executor:
            future_to_portal = {
                executor.submit(_run_single_scraper, portal, queries): portal
                for portal in active_portals
            }
            
            for future in as_completed(future_to_portal):
                portal_name = future_to_portal[future]
                try:
                    result = future.result(timeout=120)  # 2-minute timeout per portal
                    scraped_jobs.extend(result["jobs"])
                    portal_stats.append({
                        "portal": result["portal"],
                        "count": result["count"],
                        "success": result["success"],
                        "elapsed_seconds": result["elapsed_seconds"],
                        "error": result["error"],
                    })
                except Exception as e:
                    logger.error(f"[orchestrator] Future for {portal_name} raised: {e}")
                    portal_stats.append({
                        "portal": portal_name,
                        "count": 0,
                        "success": False,
                        "elapsed_seconds": 0,
                        "error": str(e),
                    })

    # Deduplicate by source_url before database insertion
    seen_urls: Set[str] = set()
    unique_jobs = []
    for job in scraped_jobs:
        url = (job.get("source_url") or "").strip()
        if url and url not in seen_urls:
            seen_urls.add(url)
            unique_jobs.append(job)
        elif not url:
            # Generate a fallback URL for dedup
            fallback_url = _generate_fallback_url(job)
            if fallback_url not in seen_urls:
                seen_urls.add(fallback_url)
                job["source_url"] = fallback_url
                unique_jobs.append(job)

    logger.info(f"[orchestrator] Total after dedup: {len(unique_jobs)} jobs (from {len(scraped_jobs)} raw)")

    # Cache in the database
    inserted_count, skipped_count, error_count = _cache_jobs_to_db(db, unique_jobs)

    if error_count > 0:
        logger.warning(f"[orchestrator] {error_count} job(s) failed to insert into database.")

    return {
        "total_scraped": len(unique_jobs),
        "new_jobs_cached": inserted_count,
        "duplicates_skipped": skipped_count,
        "insert_errors": error_count,
        "portal_results": portal_stats,
    }


def get_scraping_stats(db: Session) -> Dict:
    """
    Return statistics about the current job cache.
    """
    try:
        from sqlalchemy import func
        
        total_jobs = db.query(func.count(Job.id)).scalar() or 0
        
        # Per-portal counts
        portal_counts = (
            db.query(Job.source_portal, func.count(Job.id))
            .group_by(Job.source_portal)
            .all()
        )
        
        # Last scrape time
        last_scrape = db.query(func.max(Job.scraped_at)).scalar()
        
        return {
            "total_jobs": total_jobs,
            "jobs_by_portal": {portal: count for portal, count in portal_counts if portal},
            "last_scrape_at": str(last_scrape) if last_scrape else None,
        }
    except Exception as e:
        logger.error(f"Error computing scraping stats: {e}")
        return {"total_jobs": 0, "jobs_by_portal": {}, "last_scrape_at": None}
