import os
import json
import logging
import smtplib
import io
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from typing import Union

# ReportLab imports
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

logger = logging.getLogger(__name__)

def compile_pdf_resume(resume_data: Union[dict, str]) -> bytes:
    """
    Compiles a structured resume JSON or raw text into a premium, clean, ATS-friendly PDF.
    Returns the compiled PDF binary bytes.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=40
    )
    
    styles = getSampleStyleSheet()
    
    # Custom premium styles
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=20,
        leading=24,
        textColor=colors.HexColor('#0f172a'),
        alignment=1, # Center
        spaceAfter=4
    )
    
    contact_style = ParagraphStyle(
        'DocContact',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=12,
        textColor=colors.HexColor('#475569'),
        alignment=1, # Center
        spaceAfter=15
    )
    
    h1_style = ParagraphStyle(
        'SectionHeading',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=11,
        leading=15,
        textColor=colors.HexColor('#4f46e5'),
        spaceBefore=10,
        spaceAfter=4,
        keepWithNext=True
    )
    
    body_style = ParagraphStyle(
        'BodyTextCustom',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9.5,
        leading=13.5,
        textColor=colors.HexColor('#1e293b'),
        spaceAfter=4
    )
    
    bullet_style = ParagraphStyle(
        'BulletCustom',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=13,
        textColor=colors.HexColor('#334155'),
        leftIndent=15,
        firstLineIndent=-10,
        spaceAfter=3
    )

    meta_style = ParagraphStyle(
        'ItemMeta',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=10,
        leading=13,
        textColor=colors.HexColor('#1e293b'),
        spaceAfter=2
    )

    story = []
    
    # Check if resume_data is a dict or string
    parsed = {}
    if isinstance(resume_data, str):
        try:
            parsed = json.loads(resume_data)
        except Exception:
            # Fallback for plain text resume format
            story.append(Paragraph("Resume Tailored Copy", title_style))
            story.append(Spacer(1, 10))
            for line in resume_data.split('\n'):
                if line.strip():
                    story.append(Paragraph(line, body_style))
            doc.build(story)
            return buffer.getvalue()
    elif isinstance(resume_data, dict):
        parsed = resume_data
        
    name = parsed.get("name", "Student Candidate")
    email = parsed.get("email", "student@example.edu")
    
    story.append(Paragraph(name, title_style))
    story.append(Paragraph(f"Email: {email} | Generated via AutoIntern", contact_style))
    
    # Draw horizontal line helper
    def add_section_divider(title):
        story.append(Paragraph(title.upper(), h1_style))
        # Add a thin line under the section header
        divider = Table([['']], colWidths=[532], rowHeights=[1])
        divider.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#e2e8f0')),
            ('BOTTOMPADDING', (0,0), (-1,-1), 0),
            ('TOPPADDING', (0,0), (-1,-1), 0),
        ]))
        story.append(divider)
        story.append(Spacer(1, 6))

    # Skills Section
    skills = parsed.get("skills", [])
    if skills:
        add_section_divider("Skills & Expertise")
        skills_text = ", ".join(skills)
        story.append(Paragraph(skills_text, body_style))
        story.append(Spacer(1, 8))

    # Experience Section
    experience = parsed.get("experience", [])
    if experience:
        add_section_divider("Professional Experience")
        for exp in experience:
            company = exp.get("company", "Company")
            role = exp.get("role", "Candidate")
            meta_text = f"<b>{role}</b> — <i>{company}</i>"
            story.append(Paragraph(meta_text, meta_style))
            
            bullets = exp.get("bullets", [])
            for b in bullets:
                story.append(Paragraph(f"&bull; {b}", bullet_style))
            story.append(Spacer(1, 6))
            
    # Projects Section
    projects = parsed.get("projects", [])
    if projects:
        add_section_divider("Key Projects")
        for proj in projects:
            title = proj.get("title", "Project")
            desc = proj.get("description", "")
            meta_text = f"<b>{title}</b>"
            if desc:
                meta_text += f" &mdash; <i>{desc}</i>"
            story.append(Paragraph(meta_text, meta_style))
            
            bullets = proj.get("bullets", [])
            for b in bullets:
                story.append(Paragraph(f"&bull; {b}", bullet_style))
            story.append(Spacer(1, 6))
            
    # Education Section
    education = parsed.get("education", [])
    if education:
        add_section_divider("Education")
        for edu in education:
            story.append(Paragraph(edu, body_style))
            story.append(Spacer(1, 4))
            
    doc.build(story)
    pdf_bytes = buffer.getvalue()
    return pdf_bytes


def dispatch_outreach_email(
    app_id: str,
    to_email: str,
    subject: str,
    body: str,
    tailored_resume: Union[dict, str],
    host_url: str = "http://localhost:8000"
) -> bool:
    """
    Sends the outreach email with:
    1. Embedded tracking pixel
    2. Compiled PDF resume attachment
    
    If SMTP credentials are not in .env, falls back to logging the outbound message to console
    so that local developer testing is seamless.
    """
    # Build tracking pixel URL
    pixel_url = f"{host_url}/api/applications/track/open/{app_id}.png"
    pixel_html = f'<br/><br/><img src="{pixel_url}" width="1" height="1" style="display:none;" />'
    
    # Get SMTP configuration
    smtp_host = os.environ.get("SMTP_HOST")
    smtp_port = os.environ.get("SMTP_PORT", "587")
    smtp_username = os.environ.get("SMTP_USERNAME")
    smtp_password = os.environ.get("SMTP_PASSWORD")
    smtp_from = os.environ.get("SMTP_FROM", "outreach@autointern.in")

    # Compile PDF resume
    try:
        pdf_bytes = compile_pdf_resume(tailored_resume)
    except Exception as e:
        logger.error(f"Failed to generate PDF resume: {str(e)}")
        # Simple plain-text fallback
        pdf_bytes = str(tailored_resume).encode('utf-8')

    # Send Email
    if smtp_host and smtp_username and smtp_password:
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = smtp_from
            msg["To"] = to_email
            
            # HTML content with embedded tracking pixel
            html_body = f"""
            <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <div style="white-space: pre-wrap;">{body}</div>
                {pixel_html}
            </body>
            </html>
            """
            
            msg.attach(MIMEText(body, "plain"))
            msg.attach(MIMEText(html_body, "html"))
            
            # PDF Attachment
            filename = f"Resume_{app_id[:8]}.pdf"
            part = MIMEApplication(pdf_bytes, _subtype="pdf")
            part.add_header("Content-Disposition", "attachment", filename=filename)
            msg.attach(part)
            
            # SMTP dispatch
            server = smtplib.SMTP(smtp_host, int(smtp_port))
            server.starttls()
            server.login(smtp_username, smtp_password)
            server.sendmail(smtp_from, [to_email], msg.as_string())
            server.quit()
            
            logger.info(f"Successfully sent SMTP email to {to_email} for app {app_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send SMTP email to {to_email}: {str(e)}")
            # Fallback to local logs anyway
            
    # Mock Log Fallback
    logger.info("=" * 60)
    logger.info("SMTP OUTBOUND OUTREACH EMAIL (MOCK/CONSOLE LOG)")
    logger.info(f"TO: {to_email}")
    logger.info(f"FROM: {smtp_from}")
    logger.info(f"SUBJECT: {subject}")
    logger.info(f"BODY:\n{body}")
    logger.info(f"TRACKING PIXEL EMBEDDED: {pixel_url}")
    logger.info(f"ATTACHMENT: Resume PDF ({len(pdf_bytes)} bytes) attached.")
    logger.info("=" * 60)
    return True
