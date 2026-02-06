from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes.auth import router as auth_router
from app.api.routes.resumes import router as resumes_router
from app.api.routes.ats import router as ats_router
from app.api.routes.interviews import router as interviews_router
from app.api.routes.interviews_live import router as interviews_live_router
from app.api.routes.answers import router as answers_router
from app.api.routes.reports import router as reports_router
from app.api.routes.analytics import router as analytics_router
from app.core.config import settings
from app.core.errors import (
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from app.db.base import init_db


def create_application() -> FastAPI:
    """
    Application factory for the FastAPI backend.
    """
    app = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.VERSION,
        debug=settings.ENVIRONMENT == "local",
    )

    # CORS configuration
    if settings.ENVIRONMENT == "local":
        allow_origins = settings.BACKEND_CORS_ORIGINS or ["http://127.0.0.1:5173", "http://localhost:5173"]
    else:
        allow_origins = settings.BACKEND_CORS_ORIGINS

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Error handlers
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)

    # Include routers
    app.include_router(auth_router)
    app.include_router(resumes_router)
    app.include_router(ats_router)
    app.include_router(interviews_router)
    app.include_router(interviews_live_router)
    app.include_router(answers_router)
    app.include_router(reports_router)
    app.include_router(analytics_router)

    # Health endpoint
    @app.get("/health", tags=["health"])
    def health_check() -> dict[str, str]:
        """
        Basic health check endpoint to verify the API is running.
        """
        return {"status": "ok"}

    # Initialize database schema at startup (idempotent)
    @app.on_event("startup")
    def on_startup() -> None:
        init_db()

    return app


app = create_application()

