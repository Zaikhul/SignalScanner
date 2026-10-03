from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1 import (
    associations,
    channel_health,
    collectors,
    exports,
    ingest,
    manifests,
    measurements,
    sessions,
    targets,
    web_scan_scopes,
    web_scans,
)
from app.api.ws import session_stream, web_scan_stream
from app.config import settings
from app.db.session import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize DB tables on startup
    await init_db()
    if getattr(settings, "WEB_SCANNER_ENABLED", False):
        from app.services.web_scan_scheduler import web_scan_scheduler
        await web_scan_scheduler.start()
    try:
        yield
    finally:
        if getattr(settings, "WEB_SCANNER_ENABLED", False):
            from app.services.web_scan_scheduler import web_scan_scheduler
            await web_scan_scheduler.stop()


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Checksum-SHA256", "Content-Disposition"],
)

# Include v1 REST routers
app.include_router(collectors.router, prefix=settings.API_V1_STR)
app.include_router(sessions.router, prefix=settings.API_V1_STR)
app.include_router(associations.router, prefix=settings.API_V1_STR)
app.include_router(manifests.router, prefix=settings.API_V1_STR)
app.include_router(measurements.router, prefix=settings.API_V1_STR)
app.include_router(targets.router, prefix=settings.API_V1_STR)
app.include_router(exports.router, prefix=settings.API_V1_STR)
app.include_router(ingest.router, prefix=settings.API_V1_STR)
app.include_router(channel_health.router, prefix=settings.API_V1_STR)
app.include_router(web_scans.router, prefix=settings.API_V1_STR)
app.include_router(web_scan_scopes.router, prefix=settings.API_V1_STR)

# Include WebSocket routers
app.include_router(session_stream.router)
app.include_router(web_scan_stream.router)


@app.get("/healthz", tags=["health"])
async def health_check():
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
    }
