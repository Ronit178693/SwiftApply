from fastapi import APIRouter, UploadFile, File, HTTPException, status, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func as sql_func
from app.core.database import get_db
from app.models.models import User, Resume
from app.services import ai_service
import logging

router = APIRouter(prefix="/resume", tags=["resume"])
logger = logging.getLogger(__name__)

def get_or_create_test_user(db: Session) -> User:
    """Helper to ensure a test student user exists in the DB so parsing runs smoothly."""
    test_email = "student.test@example.edu"
    try:
        user = db.query(User).filter(User.email == test_email).first()
        if not user:
            logger.info("Test user not found. Bootstrapping a default test user...")
            user = User(
                email=test_email,
                name="Test Student",
                college_id="TEST-101",
                plan="free"
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        return user
    except Exception as e:
        db.rollback()
        logger.error(f"Error finding or bootstrapping test user: {str(e)}")
        raise RuntimeError(
            f"Database access failed. Ensure the database is reachable "
            f"and tables exist. Error: {str(e)}"
        )

@router.post("/upload")
async def upload_and_parse_resume(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """
    Upload a PDF resume, extract its raw text, parse it into structured JSON using AI, 
    and save the raw text and parsed JSON record directly to the database.
    """
    # 1. Validate file format
    if not file.filename.endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported file format. Please upload a PDF file."
        )
    
    try:
        # 2. Read file content bytes
        contents = await file.read()
        if len(contents) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The uploaded PDF file is empty."
            )
            
        # 3. Extract text from PDF
        logger.info(f"Extracting text from uploaded file: {file.filename}")
        raw_text = ai_service.extract_text_from_pdf(contents)
        
        if not raw_text.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Could not extract any readable text from the PDF. The file might be scanned or image-only."
            )
            
        # 4. Parse raw text into structured JSON using the AI parsing pipeline
        logger.info("Parsing raw text into structured JSON schema...")
        parsed_json = ai_service.extract_structured_resume(raw_text)
        
        # 5. Fetch or bootstrap our default database student user
        user = get_or_create_test_user(db)
        
        # 6. Determine the next version number for this user's resumes
        latest_version = (
            db.query(sql_func.max(Resume.version))
            .filter(Resume.user_id == user.id)
            .scalar()
        )
        next_version = (latest_version or 0) + 1
        
        # 7. Insert Resume record into database
        logger.info(f"Saving parsed resume v{next_version} for user: {user.email}")
        db_resume = Resume(
            user_id=user.id,
            raw_text=raw_text,
            parsed_json=parsed_json,
            version=next_version
        )
        db.add(db_resume)
        db.commit()
        db.refresh(db_resume)
        
        return {
            "success": True,
            "filename": file.filename,
            "resume_id": str(db_resume.id),
            "user_email": user.email,
            "version": next_version,
            "raw_text_length": len(raw_text),
            "parsed_resume": parsed_json
        }
        
    except HTTPException as he:
        # Propagate standard HTTPExceptions
        raise he
    except ValueError as ve:
        logger.error(f"Value error during processing: {str(ve)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ve)
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Unexpected error during resume uploading/parsing/db: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while processing and saving the resume: {str(e)}"
        )


@router.get("/active")
def get_active_resume(
    email: str = Query("student.test@example.edu", description="Student email to retrieve their resume"),
    db: Session = Depends(get_db)
):
    """
    Retrieve the active (latest version) parsed resume for the user.
    """
    try:
        user = db.query(User).filter(User.email == email).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with email '{email}' not found."
            )
            
        resume = db.query(Resume).filter(Resume.user_id == user.id).order_by(Resume.version.desc()).first()
        if not resume:
            return {
                "success": False,
                "message": "No resume found for this user."
            }
            
        return {
            "success": True,
            "version": resume.version,
            "parsed_resume": resume.parsed_json
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error fetching active resume: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch active resume: {str(e)}"
        )

