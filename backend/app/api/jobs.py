from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import func as sql_func
from sqlalchemy.exc import OperationalError
from app.core.database import get_db, get_db_mode
from app.models.models import Job, User, Resume
from app.services import scraper_service, ai_service
from typing import Optional, List
import logging

router = APIRouter(prefix="/jobs", tags=["jobs"])
logger = logging.getLogger(__name__)


@router.post("/scrape")
def trigger_job_scrape(
    email: str = "student.test@example.edu",
    force_mock: bool = False,
    portals: Optional[str] = Query(
        None,
        description="Comma-separated list of portals to scrape. Options: internshala, linkedin, wellfound, ycombinator. Default: all."
    ),
    db: Session = Depends(get_db),
):
    """
    Retrieves the user's active resume, generates tailored search queries via Gemini, 
    scrapes selected portals (LinkedIn, Wellfound, Internshala, Y Combinator), 
    and caches matches in the database.
    
    Query Params:
    - email: Student's email to retrieve their resume
    - force_mock: If true, use mock data instead of live scraping
    - portals: Comma-separated portal names (e.g., "internshala,linkedin")
    """
    try:
        logger.info(f"Retrieving active resume for user: {email}")
        user = db.query(User).filter(User.email == email).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with email '{email}' not found."
            )
            
        # Get active resume
        resume = db.query(Resume).filter(Resume.user_id == user.id).order_by(Resume.version.desc()).first()
        if not resume:
            # Fallback queries if no resume has been uploaded yet
            queries = ["Software Engineer Intern", "Web Developer Intern"]
            logger.warning(f"No resume found for {email}. Falling back to default search queries.")
        else:
            # Generate search queries using Gemini based on parsed resume skills/projects
            logger.info("Generating target search queries from parsed resume using Gemini...")
            queries = ai_service.generate_search_queries(resume.parsed_json)
            
        # Parse portal selection
        portal_list = None
        if portals:
            portal_list = [p.strip().lower() for p in portals.split(",") if p.strip()]
            valid_portals = [p for p in portal_list if p in scraper_service.ALL_PORTALS]
            if not valid_portals:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"No valid portals specified. Available: {', '.join(scraper_service.ALL_PORTALS)}"
                )
            portal_list = valid_portals
            
        logger.info(f"Triggering multi-portal scraper run for queries: {queries}")
        result = scraper_service.scrape_multi_portal(
            db, queries, force_mock=force_mock, portals=portal_list
        )
        
        return {
            "success": True,
            "message": "Resume-driven multi-portal scraping completed successfully.",
            "db_mode": get_db_mode(),
            "search_queries_generated": queries,
            "portals_scraped": portal_list or scraper_service.ALL_PORTALS,
            **result,
        }
    except HTTPException as he:
        raise he
    except OperationalError as oe:
        logger.error(f"Database connection error during scraping: {str(oe)[:200]}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database is temporarily unavailable. Jobs were scraped but could not be cached. Error: {str(oe)[:150]}"
        )
    except Exception as e:
        logger.error(f"Error during scrape trigger endpoint execution: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred during the job scraping cycle: {str(e)}"
        )


@router.get("")
def list_cached_jobs(
    limit: int = Query(20, ge=1, le=100, description="Max number of results to return"),
    portal: Optional[str] = Query(None, description="Filter by portal: internshala, linkedin, wellfound, ycombinator"),
    search: Optional[str] = Query(None, description="Search keyword to filter job titles and descriptions"),
    sort_by: str = Query("date", description="Sort by: date (newest first) or title (alphabetical)"),
    db: Session = Depends(get_db),
):
    """
    Retrieves the list of cached internship job listings from the database.
    
    Supports filtering by portal, keyword search, and sorting.
    """
    try:
        query = db.query(Job)
        
        # Filter by portal
        if portal:
            portal_clean = portal.strip().lower()
            if portal_clean not in scraper_service.ALL_PORTALS:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid portal: '{portal}'. Available: {', '.join(scraper_service.ALL_PORTALS)}"
                )
            query = query.filter(Job.source_portal == portal_clean)
        
        # Search filter
        if search:
            search_pattern = f"%{search}%"
            query = query.filter(
                (Job.title.ilike(search_pattern)) | 
                (Job.company.ilike(search_pattern)) | 
                (Job.jd_text.ilike(search_pattern))
            )
        
        # Sorting
        if sort_by == "title":
            query = query.order_by(Job.title.asc())
        else:
            query = query.order_by(Job.scraped_at.desc())
        
        jobs = query.limit(limit).all()
        
        return {
            "success": True,
            "count": len(jobs),
            "filters": {
                "portal": portal,
                "search": search,
                "sort_by": sort_by,
                "limit": limit,
            },
            "jobs": [
                {
                    "id": str(job.id),
                    "title": job.title,
                    "company": job.company,
                    "jd_text": job.jd_text,
                    "source_url": job.source_url,
                    "source_portal": job.source_portal,
                    "stipend": job.stipend,
                    "location": job.location,
                    "skills_required": job.skills_required,
                    "scraped_at": str(job.scraped_at) if job.scraped_at else None,
                }
                for job in jobs
            ]
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error retrieving cached job listings: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch job listings: {str(e)}"
        )


@router.get("/stats")
def get_scraping_stats(db: Session = Depends(get_db)):
    """
    Returns scraping statistics: total jobs, counts per portal, last scrape timestamp.
    """
    try:
        stats = scraper_service.get_scraping_stats(db)
        return {
            "success": True,
            **stats,
        }
    except Exception as e:
        logger.error(f"Error computing scraping stats: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to compute stats: {str(e)}"
        )


@router.get("/{job_id}/match")
def compute_match_for_job(
    job_id: str,
    email: str = Query("student.test@example.edu", description="Student email to retrieve their resume"),
    use_ai: bool = Query(False, description="Use AI-powered scoring (uses Gemini API). Default: fast keyword matching."),
    db: Session = Depends(get_db),
):
    """
    Compute a match score between the student's resume and a specific job.
    
    Two scoring modes:
    - **Keyword matching** (default, free): Fast fuzzy keyword overlap
    - **AI scoring** (use_ai=true): Uses Gemini for semantic understanding
    """
    try:
        # Get the job
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Job with id '{job_id}' not found."
            )
        
        # Get the student's resume
        user = db.query(User).filter(User.email == email).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with email '{email}' not found."
            )
        
        resume = db.query(Resume).filter(Resume.user_id == user.id).order_by(Resume.version.desc()).first()
        if not resume:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No resume found for user '{email}'. Please upload a resume first."
            )
        
        # Extract skills from parsed resume
        parsed = resume.parsed_json or {}
        student_skills = parsed.get("skills", [])
        
        if not student_skills:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="No skills found in the parsed resume. Please re-upload your resume."
            )
        
        # Compute the match score
        if use_ai:
            score_result = ai_service.compute_ai_match_score(student_skills, job.jd_text)
        else:
            score_result = ai_service.compute_keyword_match_score(student_skills, job.jd_text)
        
        return {
            "success": True,
            "job": {
                "id": str(job.id),
                "title": job.title,
                "company": job.company,
                "source_portal": job.source_portal,
            },
            "student": {
                "email": email,
                "skills": student_skills,
            },
            "scoring_mode": "ai" if use_ai else "keyword",
            "match": score_result,
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error computing match score: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to compute match score: {str(e)}"
        )


@router.post("/{job_id}/tailor")
def tailor_for_job(
    job_id: str,
    email: str = Query("student.test@example.edu", description="Student email to retrieve their resume"),
    db: Session = Depends(get_db),
):
    """
    Generate customized experience bullets and a tailored cover letter
    specifically optimized for this job description.
    """
    try:
        # Get the job
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Job with id '{job_id}' not found."
            )
        
        # Get the student's resume
        user = db.query(User).filter(User.email == email).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with email '{email}' not found."
            )
        
        resume = db.query(Resume).filter(Resume.user_id == user.id).order_by(Resume.version.desc()).first()
        if not resume:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No resume found for user '{email}'. Please upload a resume first."
            )
        
        # Call the tailoring service (Gemini)
        logger.info(f"Generating tailored resume assets for job '{job.title}' by '{job.company}'...")
        tailoring_result = ai_service.tailor_resume_for_jd(resume.parsed_json, job.jd_text)
        
        return {
            "success": True,
            "job_id": job_id,
            "job_title": job.title,
            "company": job.company,
            "tailored_resume": tailoring_result.get("tailored_resume_text"),
            "cover_letter": tailoring_result.get("cover_letter"),
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error tailoring resume for job {job_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to tailor resume: {str(e)}"
        )

