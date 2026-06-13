import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Load local environment variables from .env file
# IMPORTANT: This must happen BEFORE any database imports to ensure
# DATABASE_URL is available when the engine is lazily initialized.
dotenv_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)
    logger.info(f"Loaded environment variables from: {dotenv_path}")
else:
    logger.warning("No .env file found. Using system environment variables.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup and shutdown events."""
    # ── Startup ──
    logger.info("AutoIntern API starting up...")

    from app.core.database import init_engine, create_tables, check_db_health, get_db_mode

    # Initialize database engine (lazy init with retry + fallback)
    init_engine()

    # Auto-create tables if they don't exist
    create_tables()

    health = check_db_health()
    logger.info(f"Database health: {health}")

    if get_db_mode() == "sqlite":
        logger.warning(
            "Running with local SQLite database. "
            "To use Supabase PostgreSQL, ensure DATABASE_URL in .env is correct "
            "and the Supabase project is active (not paused)."
        )

    logger.info("AutoIntern API ready to serve requests.")

    yield  # ← Application runs here

    # ── Shutdown ──
    logger.info("AutoIntern API shutting down...")


app = FastAPI(
    title="AutoIntern API",
    description="API services for AutoIntern resume processing, job scraping, and match scoring.",
    version="1.0.0",
    lifespan=lifespan,
)

# Set up CORS middleware for React frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
from app.api.resume import router as resume_router
from app.api.jobs import router as jobs_router
from app.api.applications import router as applications_router
app.include_router(resume_router, prefix="/api")
app.include_router(jobs_router, prefix="/api")
app.include_router(applications_router, prefix="/api")



from fastapi.staticfiles import StaticFiles

# Calculate paths relative to backend/app/main.py
FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "frontend")

if os.path.exists(FRONTEND_DIR):
    # Mount frontend directory at the root to serve index.html, style.css, app.js relatively.
    # Note: This MUST be mounted last so it doesn't intercept API routes.
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
else:
    @app.get("/")
    def read_root():
        return {
            "message": "Welcome to AutoIntern API gateway! Frontend folder not found.",
            "docs_url": "/docs",
            "status": "healthy"
        }



@app.get("/api/health")
def health_check():
    """Quick health check — confirms the server is running."""
    from app.core.database import get_db_mode
    return {
        "status": "ok",
        "db_mode": get_db_mode(),
    }


@app.get("/api/health/db")
def deep_health_check():
    """
    Deep health check — tests actual database connectivity and latency.
    Returns detailed DB status for monitoring dashboards.
    """
    from app.core.database import check_db_health
    health = check_db_health()
    return {
        "status": "ok" if health["status"] == "healthy" else "degraded",
        "database": health,
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    # Disable uvicorn reload in production (when PORT env var is present)
    reload_mode = os.environ.get("PORT") is None
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=reload_mode)
