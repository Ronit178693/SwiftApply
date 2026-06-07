# AutoIntern Project Roadmap, Work Division & Task Execution Guide

This document defines the **8-Week Roadmap** to build and launch the AutoIntern MVP, designates the **Work Division** for a typical lean startup team, and provides a deep-dive **"How-to Guide"** explaining the exact technical execution of every core task in the workflow.

---

## 1. 8-Week Master Roadmap

This chronological timeline is optimized to get a functional MVP in students' hands by Week 4, followed by polishing, monetization, and launch scaling.

```
[ W1: Architecture & Scaffolding ] ──> [ W2: AI Core & Parsing ] ──> [ W3: Aggregators & Scrapers ] ──> [ W4: Application Queue & MVP Send ]
                                                                                                                      │
[ W8: Launch & Referrals ] <─────────── [ W7: Analytics & A/B ] <─────── [ W6: Kanban & Pixels ] <───── [ W5: Match Scoring & Polish ]
```

*   **Week 1: Foundations & Scaffolding**
    *   Set up FastAPI monorepo directory layout.
    *   Configure Supabase project and execute database DDL scripts.
    *   Scaffold the React Vite frontend and build the vanilla CSS global styling tokens.
*   **Week 2: AI Core & Parsing Pipeline**
    *   Integrate the Anthropic Claude API SDK on the backend.
    *   Build the PDF text extractor and the AI resume JSON parser.
    *   Verify structured JSON extraction database writes.
*   **Week 3: Job Aggregation & Caching Engine**
    *   Write RSS feed parsers and local HTML scraper scripts.
    *   Integrate a 3-second rate-limiting utility.
    *   Set up background schedulers to scrape and cache listings in PostgreSQL every 12 hours.
*   **Week 4: The Outgoing Email Channel (MVP Milestone)**
    *   Integrate the Resend API or custom SMTP mailer.
    *   Build the basic single-page application dashboard interface showing available jobs.
    *   Test sending a basic tailored email with a custom PDF attachment.
*   **Week 5: Match Scoring & Feed Ranking**
    *   Build the AI Match Scoring endpoint (Haiku-based).
    *   Connect the React frontend to fetch jobs sorted dynamically by Match Score.
    *   Build search, filtering, and role-based categorization on the dashboard.
*   **Week 6: The Kanban Board & Tracking Pixel**
    *   Build the interactive frontend Kanban Board UI (`Draft` -> `Applied` -> `Seen`).
    *   Implement the `/track/open/{app_id}.png` tracking pixel endpoint in FastAPI.
    *   Configure the Inbound Reply Webhook to catch recruiter emails.
*   **Week 7: Split-Screen Copilot & Analytics**
    *   Build the split-screen double-pane editor UI for portal-based applications.
    *   Implement pre-generated Q&A answer-blocks and one-click PDF downloading.
    *   Create a simple Weekly Analytics dashboard for users (open rates, applications sent).
*   **Week 8: Razorpay Integration & Campus GTM Launch**
    *   Integrate Razorpay/Stripe checkout hooks to enforce the 10-application freemium limit.
    *   Build referral link code systems (refer a friend to get 10 extra monthly credits).
    *   Launch the Campus Ambassador Whatsapp/LinkedIn viral campaigns.

---

## 2. Work Division (Lean Team Structure)

To execute this roadmap efficiently, tasks are divided among three specialized roles:

### Role A: Full Stack Lead (Backend & AI Architect)
*   **Core Ownership:** FastAPI API routing, Supabase database sessions, Auth JWT validation, Claude API integration, and email delivery routes.
*   **Primary Tasks:** Weeks 1, 2, 4, 6, and 8.

### Role B: Frontend Developer (UI/UX & Interactions)
*   **Core Ownership:** React UI rendering, Vanilla CSS design tokens (glassmorphism, dark modes), Kanban board state updates, the split-screen Copilot view, and Razorpay client integrations.
*   **Primary Tasks:** Weeks 1, 4, 5, 6, 7, and 8.

### Role C: Scraper/Data Engineer (Pipelines & Background Jobs)
*   **Core Ownership:** Scrapy/BeautifulSoup scrapers, HTML structure parsers, background loop schedulers (Celery/Cron), and anti-bot bypass mechanisms.
*   **Primary Tasks:** Weeks 3, 5, and 7.

---

## 3. How to Accomplish Each Key Technical Task

Here is the exact blueprint, including file paths and code patterns, to accomplish every technical step in the AutoIntern workflow.

---

### Task 1: Setting up Supabase Database & Auth JWT Validation
*   **Goal:** Protect API routes so only students logged in via Supabase can query our backend.
*   **How to Accomplish:**
    1. Create a free project on Supabase.
    2. Execute your DDL SQL schema in the SQL Editor to initialize the tables (`users`, `resumes`, etc.).
    3. In `backend/app/core/security.py`, create a dependency that extracts and validates the Supabase bearer JWT token from incoming request headers using PyJWT or HTTPBearer:

```python
# backend/app/core/security.py
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt
import os

security = HTTPBearer()
SUPABASE_JWT_SECRET = os.environ.get("SUPABASE_JWT_SECRET")

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SUPABASE_JWT_SECRET, algorithms=["HS256"], audience="authenticated")
        user_id = payload.get("sub")
        return {"id": user_id, "email": payload.get("email")}
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired credentials",
        )
```

---

### Task 2: Resume Extraction and AI Structuring
*   **Goal:** Convert raw resume text into structured JSON skills and experience.
*   **How to Accomplish:**
    1. Use a library like `pypdf` or `pdfplumber` to extract raw string text from uploaded resume files.
    2. Write an AI prompt targeting `claude-3-haiku` that forces JSON formatting:

```python
# backend/app/services/ai_service.py
import json
from anthropic import Anthropic

client = Anthropic()

def extract_structured_resume(raw_pdf_text: str) -> dict:
    prompt = f"""
    Analyze this raw text from a student's resume and parse it into a clean JSON structure.
    Return ONLY valid JSON. Do not include markdown wraps or conversational prefixes.
    
    JSON Fields:
    - name: string
    - email: string
    - skills: list of strings
    - experience: list of dicts (company, role, bullets (list of strings))
    - education: list of strings

    Raw Resume Text:
    {raw_pdf_text}
    """
    
    response = client.messages.create(
        model="claude-3-haiku-20240307",
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}]
    )
    return json.loads(response.content[0].text)
```

---

### Task 3: Job Match Scoring
*   **Goal:** Compare a student’s skills with a Job Description (JD) and provide a Match Score (0–100).
*   **How to Accomplish:**
    1. On the FastAPI backend, query `Claude 3 Haiku` for cheap bulk scoring.
    2. Pass the list of user skills and the JD.

```python
# backend/app/services/ai_service.py
def calculate_match_score(user_skills: list, job_description: str) -> dict:
    prompt = f"""
    Analyze the student's skills against the requirements of the job description.
    Return ONLY a JSON response containing:
    1. 'score': integer from 0 to 100
    2. 'reason': a single clear sentence explaining what fits and what is missing.

    Student Skills: {', '.join(user_skills)}
    Job Description: {job_description}
    """
    response = client.messages.create(
        model="claude-3-haiku-20240307",
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}]
    )
    return json.loads(response.content[0].text)
```

---

### Task 4: Premium Resume Tailoring (Hhuman-in-the-loop Guard)
*   **Goal:** Rewrite resume bullet points targeting a specific job without hallucinating fake facts.
*   **How to Accomplish:**
    1. Query the premium `claude-3-5-sonnet` model.
    2. Force the model to retain factual truths (dates, original titles, original companies) while adapting action words.

```python
# backend/app/services/ai_service.py
def tailor_resume_bullets(resume_json: dict, job_description: str) -> dict:
    prompt = f"""
    You are an expert resume optimizer. Reword and enhance the bullet points in the student's experience to target the keywords in the Job Description.
    CRITICAL RULE: Keep all historical facts (company names, employment dates, core tasks) 100% true. Do NOT invent new credentials.
    Maximize keyword relevance using active verbs.

    Job Description:
    {job_description}

    Student Profile:
    {json.dumps(resume_json)}

    Return ONLY a JSON object matching the original input format but with optimized bullet points and a newly drafted 'cover_letter' field.
    """
    response = client.messages.create(
        model="claude-3-5-sonnet-20240620",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}]
    )
    return json.loads(response.content[0].text)
```

---

### Task 5: Web Scraping and DB Caching
*   **Goal:** Crawl listings and cache them to avoid portal API blocks.
*   **How to Accomplish:**
    1. Use `BeautifulSoup` to scrape standard listings.
    2. Throttle calls with a `3-second` sleep timer to mimic natural user behavior.
    3. Store crawled results in PostgreSQL with a unique URL constraint to prevent duplicate listings.

```python
# backend/app/services/scraper_service.py
import urllib.request
from bs4 import BeautifulSoup
import time

def scrape_internships():
    url = "https://example-careers-board.com/internships"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    
    with urllib.request.urlopen(req) as response:
        html = response.read()
        
    soup = BeautifulSoup(html, 'html.parser')
    listings = soup.find_all('div', class_='job-card')
    
    jobs = []
    for card in listings:
        title = card.find('h2').text.strip()
        company = card.find('div', class_='company').text.strip()
        jd_text = card.find('p', class_='description').text.strip()
        source_url = card.find('a')['href']
        
        jobs.append({
            "title": title,
            "company": company,
            "jd_text": jd_text,
            "source_url": source_url
        })
        # Respect target site: Throttling
        time.sleep(3.0)
    return jobs
```

---

### Task 6: 1x1 Tracking Pixel & Inbound Webhooks
*   **Goal:** Track when emails are opened and when recruiters reply.
*   **How to Accomplish:**
    1. Compile the outgoing email template inside `email_service.py` adding a unique image tag mapping to the `application_id`.
    2. Build a FastAPI route that catches the GET request and returns a raw transparent 1x1 PNG.

```python
# backend/app/api/applications.py
from fastapi import APIRouter, Response, Depends
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.schema import Application

router = APIRouter()

# 1x1 transparent PNG hex
TRANSPARENT_PNG_BYTES = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82'

@router.get("/track/open/{app_id}.png")
def track_email_open(app_id: str, db: Session = Depends(get_db)):
    # 1. Fetch application and update state to 'seen'
    application = db.query(Application).filter(Application.id == app_id).first()
    if application and application.status == "applied":
        application.status = "seen"
        db.commit()
    
    # 2. Return the transparent pixel immediately
    return Response(
        content=TRANSPARENT_PNG_BYTES, 
        media_type="image/png",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0"
        }
    )
```

---

### Task 7: React Vite Split-Screen Helper
*   **Goal:** Provide a side-by-side view that helps students copy tailored answers and drag-and-drop resumes into portals in seconds.
*   **How to Accomplish:**
    1. Render a split-screen dashboard view in React.
    2. Embed the external application link in an `<iframe>` (left pane) and the custom Copilot sidebar (right pane).
    3. Use standard clipboard APIs to copy text with one click.

```tsx
// frontend/src/pages/PortalCopilot.tsx
import React, { useState } from 'react';

interface CopilotProps {
  jobUrl: string;
  tailoredResumeUrl: string;
  coverLetterText: string;
  customQuestions: { question: string; answer: string }[];
}

export const PortalCopilot: React.FC<CopilotProps> = ({ jobUrl, tailoredResumeUrl, coverLetterText, customQuestions }) => {
  const [copied, setCopied] = useState<string | null>(null);

  const copyToClipboard = (text: string, label: string) => {
    navigator.clipboard.writeText(text);
    setCopied(label);
    setTimeout(() => setCopied(null), 2000);
  };

  return (
    <div className="flex h-screen w-full bg-slate-950 text-slate-100">
      {/* LEFT SIDE: Active Application Portal */}
      <div className="w-1/2 border-r border-slate-800">
        <iframe 
          src={jobUrl} 
          title="Job Application Portal" 
          className="w-full h-full bg-white" 
        />
      </div>

      {/* RIGHT SIDE: AutoIntern Copilot Helper */}
      <div className="w-1/2 p-6 flex flex-col justify-between overflow-y-auto">
        <div>
          <h2 className="text-xl font-bold bg-gradient-to-r from-violet-400 to-indigo-400 bg-clip-text text-transparent mb-4">
            AutoIntern Copilot
          </h2>
          
          {/* Action 1: Resume Download */}
          <div className="mb-6 p-4 bg-slate-900 border border-slate-800 rounded-xl">
            <h3 className="font-semibold text-slate-200 mb-2">1. Tailored Resume</h3>
            <a 
              href={tailoredResumeUrl} 
              download 
              className="inline-block px-4 py-2 bg-indigo-600 hover:bg-indigo-500 rounded-lg text-sm transition"
            >
              Download Tailored PDF
            </a>
          </div>

          {/* Action 2: Cover Letter Quick-Copy */}
          <div className="mb-6 p-4 bg-slate-900 border border-slate-800 rounded-xl">
            <div className="flex justify-between items-center mb-2">
              <h3 className="font-semibold text-slate-200">2. Tailored Cover Letter</h3>
              <button 
                onClick={() => copyToClipboard(coverLetterText, 'cover')} 
                className="text-xs px-2 py-1 bg-slate-800 hover:bg-slate-700 rounded text-slate-300"
              >
                {copied === 'cover' ? 'Copied!' : 'Copy'}
              </button>
            </div>
            <textarea 
              readOnly 
              value={coverLetterText} 
              className="w-full h-32 bg-slate-950 border border-slate-800 rounded-lg p-2 text-xs text-slate-400 resize-none outline-none" 
            />
          </div>
        </div>

        {/* Action 3: Done Confirmation */}
        <div className="pt-4 border-t border-slate-800">
          <button className="w-full py-3 bg-gradient-to-r from-violet-500 to-indigo-500 hover:from-violet-400 hover:to-indigo-400 font-semibold rounded-xl text-sm transition shadow-lg shadow-indigo-500/10">
            Confirm Application Submitted
          </button>
        </div>
      </div>
    </div>
  );
};
```
