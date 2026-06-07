import os
import json
import logging
import io
from pypdf import PdfReader
import google.generativeai as genai
from pydantic import BaseModel, Field
from typing import List

logger = logging.getLogger(__name__)

# Try to initialize Gemini client if key is present
api_key = os.environ.get("GEMINI_API_KEY")
if api_key and not api_key.startswith("your_"):
    genai.configure(api_key=api_key)
    # Using gemini-2.5-flash which is standard, fast, and completely free
    model = genai.GenerativeModel("gemini-2.5-flash")
    logger.info("Successfully initialized Gemini model client.")
else:
    logger.warning("GEMINI_API_KEY is missing or invalid. Falling back to mock/demo mode for parsing.")
    model = None

# Define Pydantic Schema for structured resume response
class Experience(BaseModel):
    company: str
    role: str
    bullets: List[str]

class Project(BaseModel):
    title: str
    description: str
    bullets: List[str]

class ResumeSchema(BaseModel):
    name: str
    email: str
    skills: List[str]
    experience: List[Experience]
    education: List[str]
    projects: List[Project]

def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """
    Extracts raw text content from PDF binary bytes.
    """
    try:
        pdf_file = io.BytesIO(pdf_bytes)
        reader = PdfReader(pdf_file)
        text = ""
        for i, page in enumerate(reader.pages):
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
        return text.strip()
    except Exception as e:
        logger.error(f"Error extracting text from PDF: {str(e)}")
        raise ValueError(f"Failed to read PDF file: {str(e)}")

def extract_structured_resume(raw_pdf_text: str) -> dict:
    """
    Analyzes raw text from a resume and structures it into JSON format using Google Gemini.
    If no API key is present, falls back to a realistic mock output based on the input text.
    """
    if not raw_pdf_text.strip():
        raise ValueError("Resume text content is empty.")

    # FALLBACK MOCK MODE
    if not model:
        logger.info("Running resume parsing in MOCK mode...")
        # Simple heuristics to build a realistic mock from the text
        lines = [line.strip() for line in raw_pdf_text.split("\n") if line.strip()]
        name = lines[0] if lines else "Jane Doe"
        email = "jane.doe@example.edu"
        for line in lines:
            if "@" in line:
                # Basic email extraction
                parts = line.split()
                for part in parts:
                    if "@" in part:
                        email = part.strip("(),;<>")
                        break
        
        return {
            "name": name,
            "email": email,
            "skills": ["Python", "FastAPI", "React", "SQL", "Git", "Machine Learning"],
            "experience": [
                {
                    "company": "Tech Innovations Inc.",
                    "role": "Software Engineering Intern",
                    "bullets": [
                        "Developed RESTful APIs using FastAPI and PostgreSQL, improving query response time by 20%.",
                        "Collaborated with frontend developers to integrate responsive React components.",
                        "Participated in agile ceremonies and wrote unit tests covering 90% of service modules."
                    ]
                }
            ],
            "education": [
                "B.S. in Computer Science, University of Technology, 2027"
            ],
            "projects": [
                {
                    "title": "Resume Automator",
                    "description": "A web tool designed to parse and tailor student resumes.",
                    "bullets": [
                        "Parsed PDFs with Python and used LLMs to dynamically tailor content.",
                        "Designed a clean user interface with HTML and CSS."
                    ]
                }
            ],
            "note": "This is a demonstration parser result because GEMINI_API_KEY is not configured in .env."
        }

    # REAL AI MODE WITH SCHEMA
    prompt = f"""
    Analyze this raw text from a student's resume and parse it into a clean structured schema.
    Extract the contact details, skills, job history, education, and projects exactly.
    
    Raw Resume Text:
    {raw_pdf_text}
    """
    
    try:
        response = model.generate_content(
            prompt,
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json",
                response_schema=ResumeSchema,
                temperature=0.1,
            )
        )
        content_text = response.text.strip()
        return json.loads(content_text)
    except Exception as e:
        logger.error(f"Error parsing resume via Gemini: {str(e)}")
        raise RuntimeError(f"AI resume parsing failed: {str(e)}")

def generate_search_queries(resume_json: dict) -> list:
    """
    Analyzes the student's resume skills and projects using Gemini and outputs 
    3 optimized search terms for internship hunting.
    """
    if not model:
        logger.info("Gemini model not initialized. Using default search queries.")
        return ["Software Engineer Intern", "Web Developer Intern", "Backend Intern"]
        
    prompt = f"""
    Based on the following student resume profile, identify the top 3 distinct internship roles 
    this student is highly qualified for. For each, generate a search phrase that would return 
    the best results on job search engines (e.g., 'React developer intern', 'Machine learning intern').
    
    Resume Profile:
    {json.dumps(resume_json)}
    
    Return ONLY a JSON list of 3 strings. Example: ["React Developer Intern", "Python Backend Intern"]
    """
    try:
        response = model.generate_content(
            prompt,
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json",
                temperature=0.2,
            )
        )
        queries = json.loads(response.text.strip())
        if isinstance(queries, list):
            logger.info(f"Generated search queries from resume: {queries}")
            return queries[:3]
        return ["Software Engineer Intern", "Backend Intern", "Full Stack Intern"]
    except Exception as e:
        logger.error(f"Error generating search queries via Gemini: {str(e)}")
        return ["Software Engineer Intern", "Backend Intern", "Full Stack Intern"]


# ──────────────────────────────────────────────────────────────────────────────
# Match Scoring — Compare a student's resume skills against a job description
# ──────────────────────────────────────────────────────────────────────────────

def compute_keyword_match_score(student_skills: list, jd_text: str) -> dict:
    """
    Fast, free keyword-overlap match scorer. No API calls needed.
    
    Compares the student's skill list against the job description text using
    case-insensitive fuzzy matching. Returns a score from 0-100 plus a breakdown
    of matched and missing skills.
    
    Args:
        student_skills: List of skill strings from the parsed resume (e.g., ["Python", "FastAPI", "React"])
        jd_text: The full text of the job description
        
    Returns:
        Dict with keys: score (int 0-100), matched_skills (list), missing_skills (list), match_ratio (str)
    """
    if not student_skills or not jd_text:
        return {
            "score": 0,
            "matched_skills": [],
            "missing_skills": student_skills or [],
            "match_ratio": "0/0",
        }

    jd_lower = jd_text.lower()
    
    matched = []
    missing = []
    
    for skill in student_skills:
        skill_clean = skill.strip()
        if not skill_clean:
            continue
            
        skill_lower = skill_clean.lower()
        
        # Check for exact match
        if skill_lower in jd_lower:
            matched.append(skill_clean)
            continue
        
        # Check for partial/fuzzy matches
        # e.g., "React.js" matches "react", "ReactJS" matches "react"
        skill_normalized = skill_lower.replace(".", "").replace("-", "").replace(" ", "")
        jd_normalized = jd_lower.replace(".", "").replace("-", "").replace(" ", "")
        
        if skill_normalized in jd_normalized:
            matched.append(skill_clean)
            continue
        
        # Check for common abbreviation patterns
        # e.g., "JS" in "JavaScript", "ML" in "Machine Learning"
        skill_words = skill_lower.split()
        if len(skill_words) > 1:
            # Multi-word skill: check if all words appear in JD
            if all(word in jd_lower for word in skill_words):
                matched.append(skill_clean)
                continue
        
        missing.append(skill_clean)

    total = len(matched) + len(missing)
    score = int((len(matched) / total) * 100) if total > 0 else 0
    
    return {
        "score": score,
        "matched_skills": matched,
        "missing_skills": missing,
        "match_ratio": f"{len(matched)}/{total}",
    }


def compute_ai_match_score(student_skills: list, jd_text: str) -> dict:
    """
    AI-powered match scorer using Gemini for nuanced analysis.
    
    Goes beyond simple keyword matching to understand semantic relationships
    between skills and job requirements. Uses Gemini (free tier) for scoring.
    
    Args:
        student_skills: List of skill strings from the parsed resume
        jd_text: The full text of the job description
        
    Returns:
        Dict with keys: score (int 0-100), reason (str), recommendation (str)
    """
    # Fallback to keyword scoring if Gemini is not available
    if not model:
        logger.info("Gemini model not available. Falling back to keyword match scoring.")
        keyword_result = compute_keyword_match_score(student_skills, jd_text)
        return {
            "score": keyword_result["score"],
            "reason": f"Keyword match: {keyword_result['match_ratio']} skills matched.",
            "recommendation": "Upload your resume and configure GEMINI_API_KEY for AI-powered scoring.",
            "matched_skills": keyword_result["matched_skills"],
            "missing_skills": keyword_result["missing_skills"],
        }
    
    prompt = f"""
    You are an expert internship match evaluator. Compare the student's skills with the 
    job description and evaluate how strong of a match this is.
    
    Student Skills: {', '.join(student_skills)}
    
    Job Description:
    {jd_text[:1500]}
    
    Return ONLY a JSON object with exactly these fields:
    1. "score": integer from 0 to 100 (0 = no match, 100 = perfect match)
    2. "reason": a 2-sentence explanation of why this score was given
    3. "recommendation": a 1-sentence actionable tip for the student to improve their match
    4. "matched_skills": list of student skills that match the JD
    5. "missing_skills": list of student skills NOT relevant to this JD
    """
    
    try:
        response = model.generate_content(
            prompt,
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json",
                temperature=0.1,
            )
        )
        result = json.loads(response.text.strip())
        
        # Ensure all expected fields exist
        return {
            "score": int(result.get("score", 0)),
            "reason": result.get("reason", "Analysis complete."),
            "recommendation": result.get("recommendation", ""),
            "matched_skills": result.get("matched_skills", []),
            "missing_skills": result.get("missing_skills", []),
        }
    except Exception as e:
        logger.error(f"Error computing AI match score: {str(e)}")
        # Graceful fallback to keyword scoring
        keyword_result = compute_keyword_match_score(student_skills, jd_text)
        return {
            "score": keyword_result["score"],
            "reason": f"AI scoring failed, using keyword fallback: {keyword_result['match_ratio']} matched.",
            "recommendation": "AI scoring temporarily unavailable.",
            "matched_skills": keyword_result["matched_skills"],
            "missing_skills": keyword_result["missing_skills"],
        }


# ──────────────────────────────────────────────────────────────────────────────
# Resume Tailoring — Optimize resume bullets and generate cover letters using Gemini
# ──────────────────────────────────────────────────────────────────────────────

class TailoredResumeSchema(BaseModel):
    tailored_resume_text: str = Field(description="The full optimized resume text/JSON with rewritten bullet points.")
    cover_letter: str = Field(description="A professionally drafted cover letter or email outreach pitch tailored for this job description.")

def tailor_resume_for_jd(resume_json: dict, jd_text: str) -> dict:
    """
    FREE TIER: Tailors a student's resume bullets and drafts a cover letter
    using the Gemini 2.5 Pro or Flash model.
    """
    if not model:
        # Fallback if no API key is configured
        logger.warning("Gemini model not initialized. Using mock fallback for tailoring.")
        return {
            "tailored_resume_text": json.dumps(resume_json, indent=2),
            "cover_letter": "Dear Hiring Manager,\n\nI am writing to express my interest in the internship position. Given my background, I am confident in my ability to contribute value..."
        }

    # We use 'gemini-2.5-pro' for premium writing quality under the free tier (2 RPM limit),
    # with a failover to 'gemini-2.5-flash' in case of rate limit/errors.
    generation_model = genai.GenerativeModel("gemini-2.5-pro") 
    
    prompt = f"""
    You are an expert resume optimizer. Reword and enhance the experience bullet points and projects in the student's resume 
    to match the key requirements, terminology, and keywords of the target Job Description. 
    
    CRITICAL RULES:
    1. Keep all historical facts (employment dates, company names, job titles) 100% true. Do NOT invent new credentials.
    2. Emphasize matching skills and maximize relevance using strong active verbs.
    3. Draft a tailored, highly professional, and compelling cover letter or email outreach pitch.
    
    Job Description:
    {jd_text[:2000]}
    
    Student Resume Profile:
    {json.dumps(resume_json)}
    """

    try:
        response = generation_model.generate_content(
            prompt,
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json",
                response_schema=TailoredResumeSchema,
                temperature=0.3,
            )
        )
        return json.loads(response.text.strip())
    except Exception as e:
        logger.error(f"Error tailoring resume via Gemini Pro: {str(e)}")
        # Failover to flash if pro hits rate limits (2 RPM)
        logger.info("Retrying tailoring using gemini-2.5-flash...")
        try:
            flash_model = genai.GenerativeModel("gemini-2.5-flash")
            response = flash_model.generate_content(
                prompt,
                generation_config=genai.GenerationConfig(
                    response_mime_type="application/json",
                    response_schema=TailoredResumeSchema,
                    temperature=0.3,
                )
            )
            return json.loads(response.text.strip())
        except Exception as fe:
            logger.error(f"Flash failover tailoring failed: {str(fe)}")
            return {
                "tailored_resume_text": json.dumps(resume_json, indent=2),
                "cover_letter": f"AI Tailoring failed: {str(fe)}. Please try again later."
            }


