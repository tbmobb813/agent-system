"""
FastAPI application for personal AI agent system.
Handles agent execution, streaming, history, and settings.
"""

from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from contextlib import asynccontextmanager
import logging
import os
from datetime import datetime

from app.config import settings, CostTracker
from app.agent.orchestrator import AgentOrchestrator
from app.database import init_db
from app.models import CostStatus
from app.utils.auth import verify_api_key
from app.routes.agent import router as agent_router
from app.routes.history import router as history_router
from app.routes.settings import router as settings_router
from app.routes.memory import router as memory_router
from app.routes.conversations import router as conversations_router
from app.routes.documents import router as documents_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Rate limiter — 60 req/min per IP by default
limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown logic."""
    logger.info("Starting AI Agent System...")
    await init_db()
    cost_tracker = CostTracker()
    try:
        await cost_tracker.initialize(settings.DATABASE_URL)
        logger.info("✓ Cost tracker connected to database")
    except Exception as e:
        logger.warning(f"Cost tracker running without database: {e}")
    app.state.cost_tracker = cost_tracker
    app.state.agent_orchestrator = AgentOrchestrator(cost_tracker=app.state.cost_tracker)

    # Playwright check
    try:
        from playwright.async_api import async_playwright
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            await browser.close()
        logger.info("✓ Playwright chromium ready")
    except ImportError:
        logger.warning("Playwright not installed — browser_automation unavailable (pip install playwright && playwright install chromium)")
    except Exception as e:
        logger.warning(f"Playwright chromium not found — browser_automation unavailable: {e} (run: playwright install chromium)")

    logger.info("✓ Agent system ready")

    yield

    logger.info("Shutting down...")
    if hasattr(app.state, "cost_tracker"):
        await app.state.cost_tracker.close()
    logger.info("✓ Clean shutdown")


# Initialize FastAPI app
app = FastAPI(
    title="Personal AI Agent",
    description="Your personal AI co-worker for research, analysis, coding, and automation",
    version="0.1.0",
    lifespan=lifespan,
)

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security middleware
if settings.ENVIRONMENT == "production":
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=settings.ALLOWED_HOSTS,
    )

# ============================================================================
# Modular routers
# ============================================================================

app.include_router(agent_router)
app.include_router(history_router)
app.include_router(settings_router)
app.include_router(memory_router)
app.include_router(conversations_router)
app.include_router(documents_router)


# ============================================================================
# Health & Status Endpoints
# ============================================================================

@app.get("/health")
async def health_check(request: Request):
    """Health check endpoint."""
    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
        "agent_ready": getattr(request.app.state, "agent_orchestrator", None) is not None,
        "cost_tracking": getattr(request.app.state, "cost_tracker", None) is not None,
    }


@app.get("/status/costs")
async def get_cost_status(request: Request, api_key: str = Depends(verify_api_key)):
    """Get current spending and budget status."""
    ct = getattr(request.app.state, "cost_tracker", None)
    if not ct:
        raise HTTPException(status_code=503, detail="Cost tracker not initialized")
    status = await ct.get_status()
    return CostStatus(**status)


@app.get("/status/costs/breakdown")
async def get_cost_breakdown(request: Request, api_key: str = Depends(verify_api_key)):
    """Get spending breakdown by model for the current month."""
    ct = getattr(request.app.state, "cost_tracker", None)
    if not ct:
        raise HTTPException(status_code=503, detail="Cost tracker not initialized")
    breakdown = await ct.get_spent_by_model()
    return {"breakdown": breakdown}


# ============================================================================
# Tools & Models (convenience endpoints at root level)
# ============================================================================

@app.get("/tools")
async def list_tools(request: Request, api_key: str = Depends(verify_api_key)):
    """List available tools."""
    orch = getattr(request.app.state, "agent_orchestrator", None)
    if not orch:
        raise HTTPException(status_code=503, detail="Agent not ready")
    tools = orch.get_available_tools()
    return {"tools": tools, "total": len(tools)}


@app.get("/models")
async def list_models(api_key: str = Depends(verify_api_key)):
    """List available models and their pricing."""
    from app.agent.router import ModelRouter
    router_instance = ModelRouter()
    return {
        "models": router_instance.get_available_models(),
        "routing_strategy": "complexity_based",
    }


# ============================================================================
# API Documentation
# ============================================================================

@app.get("/docs-info")
async def docs_info():
    """Links to API documentation."""
    return {"docs": "/redoc", "openapi": "/openapi.json"}


# ============================================================================
# Error handler
# ============================================================================

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "detail": str(exc)},
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000)),
        reload=settings.ENVIRONMENT == "development",
    )
