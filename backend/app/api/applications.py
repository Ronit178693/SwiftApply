from fastapi import APIRouter, Depends, HTTPException, Query, status, Response
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.models import Application, EmailOutreach, User, Job
from app.services import email_service
from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List
import logging

router = APIRouter(prefix="/applications", tags=["applications"])
logger = logging.getLogger(__name__)

# Request Schemas
class ApplicationCreate(BaseModel):
    job_id: str
    email: str = "student.test@example.edu"
    tailored_resume: str
    cover_letter: str
    status: Optional[str] = "draft"

class StatusUpdate(BaseModel):
    status: str

class EmailSendRequest(BaseModel):
    to_email: str
    subject: str = "Internship Application - AutoIntern"

class InboundWebhookRequest(BaseModel):
    sender_email: str
    subject: str
    body: str

# 1x1 Transparent PNG bytes
TRANSPARENT_PNG_BYTES = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82'


@router.get("")
def list_applications(
    email: str = Query("student.test@example.edu", description="Student email to retrieve their applications"),
    db: Session = Depends(get_db)
):
    """
    Lists all applications for the student. Used to render the Kanban board dashboard.
    """
    try:
        user = db.query(User).filter(User.email == email).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with email '{email}' not found."
            )
            
        apps = db.query(Application).filter(Application.user_id == user.id).all()
        
        return {
            "success": True,
            "count": len(apps),
            "applications": [
                {
                    "id": str(app.id),
                    "job": {
                        "id": str(app.job.id) if app.job else None,
                        "title": app.job.title if app.job else "Unknown Position",
                        "company": app.job.company if app.job else "Unknown Company",
                        "location": app.job.location if app.job else None,
                        "stipend": app.job.stipend if app.job else None,
                        "source_portal": app.job.source_portal if app.job else None,
                        "source_url": app.job.source_url if app.job else None,
                        "jd_text": app.job.jd_text if app.job else ""
                    } if app.job else None,
                    "tailored_resume_text": app.tailored_resume_text,
                    "cover_letter": app.cover_letter,
                    "status": app.status,
                    "sent_at": str(app.sent_at) if app.sent_at else None,
                    "created_at": str(app.created_at) if app.created_at else None,
                }
                for app in apps
            ]
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error listing applications: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch applications: {str(e)}"
        )


@router.post("")
def create_application_draft(
    payload: ApplicationCreate,
    db: Session = Depends(get_db)
):
    """
    Creates a new application draft for a selected job.
    """
    try:
        user = db.query(User).filter(User.email == payload.email).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with email '{payload.email}' not found."
            )
            
        # Get Job details
        job = db.query(Job).filter(Job.id == payload.job_id).first()
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Job with id '{payload.job_id}' not found."
            )

        # Check if application already exists for this job and user to avoid duplicate drafts
        existing_app = (
            db.query(Application)
            .filter(Application.user_id == user.id, Application.job_id == job.id)
            .first()
        )
        if existing_app:
            # Update the existing draft/application rather than duplicating
            existing_app.tailored_resume_text = payload.tailored_resume
            existing_app.cover_letter = payload.cover_letter
            existing_app.status = payload.status
            db.commit()
            db.refresh(existing_app)
            return {
                "success": True,
                "message": "Updated existing application draft successfully.",
                "application_id": str(existing_app.id),
                "status": existing_app.status
            }

        # Create new application record
        db_app = Application(
            user_id=user.id,
            job_id=job.id,
            tailored_resume_text=payload.tailored_resume,
            cover_letter=payload.cover_letter,
            status=payload.status
        )
        db.add(db_app)
        db.commit()
        db.refresh(db_app)
        
        return {
            "success": True,
            "message": "Application draft created successfully.",
            "application_id": str(db_app.id),
            "status": db_app.status
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating application draft: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create application draft: {str(e)}"
        )


@router.put("/{id}/status")
def update_application_status(
    id: str,
    payload: StatusUpdate,
    db: Session = Depends(get_db)
):
    """
    Updates the status of an application manually (e.g. dragging cards on Kanban board).
    """
    try:
        app = db.query(Application).filter(Application.id == id).first()
        if not app:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Application with id '{id}' not found."
            )
            
        valid_statuses = ["draft", "applied", "seen", "replied", "interview", "offer", "rejected"]
        if payload.status not in valid_statuses:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status: '{payload.status}'. Valid: {', '.join(valid_statuses)}"
            )
            
        app.status = payload.status
        if payload.status == "applied" and not app.sent_at:
            app.sent_at = datetime.utcnow()
            
        db.commit()
        
        return {
            "success": True,
            "application_id": id,
            "updated_status": app.status
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating application status: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update application status: {str(e)}"
        )


@router.post("/{id}/send")
def send_outreach_email(
    id: str,
    payload: EmailSendRequest,
    db: Session = Depends(get_db)
):
    """
    Sends the outreach email containing cover letter body, tracking pixel, and tailored resume PDF.
    Updates application status to 'applied' and logs record in email_outreach.
    """
    try:
        app = db.query(Application).filter(Application.id == id).first()
        if not app:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Application with id '{id}' not found."
            )

        # Trigger email dispatch service
        success = email_service.dispatch_outreach_email(
            app_id=str(app.id),
            to_email=payload.to_email,
            subject=payload.subject,
            body=app.cover_letter,
            tailored_resume=app.tailored_resume_text
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Outreach email dispatch failed."
            )

        # Update application state
        app.status = "applied"
        app.sent_at = datetime.utcnow()

        # Save email outreach log
        db_log = EmailOutreach(
            application_id=app.id,
            to_email=payload.to_email,
            subject=payload.subject,
            body=app.cover_letter
        )
        db.add(db_log)
        db.commit()

        # Increment User AI Limit count
        user = db.query(User).filter(User.id == app.user_id).first()
        if user:
            user.ai_used_this_month = (user.ai_used_this_month or 0) + 1
            db.commit()
            
        return {
            "success": True,
            "message": "Outreach email dispatched successfully and tracked.",
            "application_id": id,
            "email_log_id": str(db_log.id)
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        db.rollback()
        logger.error(f"Error sending outreach email: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to dispatch email: {str(e)}"
        )


@router.get("/track/open/{app_id}.png")
def track_email_open(
    app_id: str,
    db: Session = Depends(get_db)
):
    """
    1x1 transparent PNG open tracking pixel.
    When loaded in recruiter's mail client, updates application status to 'seen' and opened_at logs.
    """
    try:
        app = db.query(Application).filter(Application.id == app_id).first()
        if app and app.status == "applied":
            app.status = "seen"
            db.commit()
            
            # Find and update corresponding EmailOutreach record
            log = db.query(EmailOutreach).filter(EmailOutreach.application_id == app.id).first()
            if log and not log.opened_at:
                log.opened_at = datetime.utcnow()
                db.commit()
                
            logger.info(f"Open tracking pixel triggered: application {app_id} is marked as seen.")
    except Exception as e:
        db.rollback()
        logger.error(f"Error handling tracking pixel for app {app_id}: {str(e)}")
        
    return Response(
        content=TRANSPARENT_PNG_BYTES, 
        media_type="image/png",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0"
        }
    )


@router.post("/inbound-webhook")
def inbound_webhook_handler(
    payload: InboundWebhookRequest,
    db: Session = Depends(get_db)
):
    """
    Simulated Inbound Reply Webhook to catch recruiter email replies.
    Match incoming sender email to outstanding application outreaches, updating statuses to 'replied'.
    """
    try:
        # Find outstanding email outreach logs for the sender's email
        outreach = (
            db.query(EmailOutreach)
            .filter(EmailOutreach.to_email == payload.sender_email)
            .order_by(EmailOutreach.sent_at.desc())
            .first()
        )
        if not outreach:
            # Check if matching sender email is linked anywhere else
            # Safe ignore if it doesn't match an active application
            return {
                "success": False,
                "message": f"Sender '{payload.sender_email}' does not correspond to an outstanding outreach log."
            }

        # Update logs
        outreach.replied_at = datetime.utcnow()
        
        # Update parent application
        app = db.query(Application).filter(Application.id == outreach.application_id).first()
        if app and app.status in ["applied", "seen"]:
            app.status = "replied"
            db.commit()
            logger.info(f"Recruiter reply received from {payload.sender_email} for app {app.id}. Status updated to 'replied'.")
            
        return {
            "success": True,
            "message": "Reply registered successfully.",
            "application_id": str(app.id) if app else None
        }
    except Exception as e:
        db.rollback()
        logger.error(f"Error executing webhook handler: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Inbound webhook processing failed: {str(e)}"
        )
