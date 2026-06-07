"""
SQLAlchemy ORM models for AutoIntern.

Supports both PostgreSQL (Supabase) and SQLite (local fallback) by using
dialect-aware column types.
"""

import uuid
from sqlalchemy import Column, String, Integer, Text, ForeignKey, DateTime, func, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.types import TypeDecorator, CHAR

from app.core.database import Base


# ──────────────────────────────────────────────────────────────────────────────
# Dialect-aware column types (work on both PostgreSQL and SQLite)
# ──────────────────────────────────────────────────────────────────────────────

class PortableUUID(TypeDecorator):
    """
    UUID column that works on both PostgreSQL (native UUID) and SQLite (CHAR(36)).
    Stores as native UUID on PostgreSQL, as a 36-char string on SQLite.
    """
    impl = CHAR(36)
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            from sqlalchemy.dialects.postgresql import UUID as PG_UUID
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        else:
            return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        if dialect.name == "postgresql":
            return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
        else:
            return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        if not isinstance(value, uuid.UUID):
            return uuid.UUID(str(value))
        return value


class PortableJSON(TypeDecorator):
    """
    JSON column that uses JSONB on PostgreSQL (faster queries) and JSON on SQLite.
    """
    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            from sqlalchemy.dialects.postgresql import JSONB
            return dialect.type_descriptor(JSONB)
        else:
            return dialect.type_descriptor(JSON)


# ──────────────────────────────────────────────────────────────────────────────
# Models
# ──────────────────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id = Column(PortableUUID(), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    college_id = Column(String(100), nullable=True)
    plan = Column(String(50), default="free")
    monthly_ai_limit = Column(Integer, default=10)
    ai_used_this_month = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    resumes = relationship("Resume", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User id={self.id} email={self.email}>"


class Resume(Base):
    __tablename__ = "resumes"

    id = Column(PortableUUID(), primary_key=True, default=uuid.uuid4)
    user_id = Column(PortableUUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    raw_text = Column(Text, nullable=False)
    parsed_json = Column(PortableJSON(), nullable=False)
    file_url = Column(String(512), nullable=True)
    version = Column(Integer, default=1)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="resumes")

    def __repr__(self):
        return f"<Resume id={self.id} user_id={self.user_id} v={self.version}>"


class Job(Base):
    __tablename__ = "jobs"

    id = Column(PortableUUID(), primary_key=True, default=uuid.uuid4)
    title = Column(String(255), nullable=False)
    company = Column(String(255), nullable=False)
    jd_text = Column(Text, nullable=False)
    source_url = Column(String(512), unique=True, nullable=True, index=True)
    stipend = Column(String(100), nullable=True)
    location = Column(String(255), nullable=True)
    source_portal = Column(String(50), nullable=True, index=True)  # internshala, linkedin, wellfound, ycombinator
    skills_required = Column(PortableJSON(), nullable=True)  # List of skill keywords
    scraped_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<Job id={self.id} title={self.title!r} company={self.company!r}>"


class Application(Base):
    __tablename__ = "applications"

    id = Column(PortableUUID(), primary_key=True, default=uuid.uuid4)
    user_id = Column(PortableUUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    job_id = Column(PortableUUID(), ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True)
    tailored_resume_text = Column(Text, nullable=False)
    cover_letter = Column(Text, nullable=False)
    status = Column(String(50), default="draft")  # draft, applied, seen, replied, interview, offer, rejected
    sent_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User")
    job = relationship("Job")
    outreaches = relationship("EmailOutreach", back_populates="application", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Application id={self.id} user_id={self.user_id} job_id={self.job_id} status={self.status}>"


class EmailOutreach(Base):
    __tablename__ = "email_outreach"

    id = Column(PortableUUID(), primary_key=True, default=uuid.uuid4)
    application_id = Column(PortableUUID(), ForeignKey("applications.id", ondelete="CASCADE"), nullable=False)
    to_email = Column(String(255), nullable=False)
    subject = Column(String(255), nullable=False)
    body = Column(Text, nullable=False)
    opened_at = Column(DateTime(timezone=True), nullable=True)
    replied_at = Column(DateTime(timezone=True), nullable=True)
    sent_at = Column(DateTime(timezone=True), server_default=func.now())

    application = relationship("Application", back_populates="outreaches")

    def __repr__(self):
        return f"<EmailOutreach id={self.id} application_id={self.application_id} to={self.to_email}>"

