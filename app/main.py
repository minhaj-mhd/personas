import os
from fastapi import FastAPI, Depends
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db

app = FastAPI(title="AI Multi-Persona Voice Agent Platform")

# Determine base paths relative to main.py
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
templates_dir = os.path.join(BASE_DIR, "templates")
static_dir = os.path.join(BASE_DIR, "static")

# Create directories if they do not exist
os.makedirs(templates_dir, exist_ok=True)
os.makedirs(static_dir, exist_ok=True)

# Mount static files router
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Initialize Jinja2 templates engine
templates = Jinja2Templates(directory=templates_dir)

@app.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)):
    """
    Health check endpoint verifying FastAPI server and Database connectivity.
    """
    try:
        # Simple test query to check DB availability
        await db.execute(text("SELECT 1"))
        return {
            "status": "ok",
            "database": "connected"
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "database": f"Error: {str(e)}"
        }

@app.get("/web/health-badge", response_class=HTMLResponse)
async def web_health_badge(db: AsyncSession = Depends(get_db)):
    """
    HTML endpoint for HTMX dynamic health check status.
    """
    try:
        await db.execute(text("SELECT 1"))
        return """
        <div class="flex items-center gap-3 bg-emerald-500/10 border border-emerald-500/20 px-4 py-3 rounded-xl text-emerald-400 transition-all duration-300">
            <i class="fa-solid fa-circle-check text-lg animate-pulse"></i>
            <div>
                <span class="font-semibold block text-sm">System Connected</span>
                <span class="text-xs text-emerald-400/80">FastAPI & PostgreSQL + pgvector are fully operational.</span>
            </div>
        </div>
        """
    except Exception:
        return """
        <div class="flex items-center gap-3 bg-rose-500/10 border border-rose-500/20 px-4 py-3 rounded-xl text-rose-400 transition-all duration-300">
            <i class="fa-solid fa-circle-exclamation text-lg"></i>
            <div>
                <span class="font-semibold block text-sm">Database Offline</span>
                <span class="text-xs text-rose-400/80">Could not reach database container. Make sure Docker is running.</span>
            </div>
        </div>
        """

# Import and include routers
from app.api.personas import router as personas_api_router  # noqa: E402
from app.api.conversations import router as conversations_api_router  # noqa: E402
from app.api.voice_ws import router as voice_ws_router  # noqa: E402
from app.web.views import router as web_views_router  # noqa: E402

app.include_router(personas_api_router)
app.include_router(conversations_api_router)
app.include_router(voice_ws_router)
app.include_router(web_views_router)
