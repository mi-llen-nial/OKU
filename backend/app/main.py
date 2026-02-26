import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth import router as auth_router
from app.api.profile import router as profile_router
from app.api.students import router as students_router
from app.api.subjects import router as subjects_router
from app.api.teacher import router as teacher_router
from app.api.tests import router as tests_router
from app.core.config import settings
from app.db.init_db import init_db
from app.services.tts import tts_service

logging.basicConfig(level=settings.log_level.upper())
logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="OKU prototype: AI-personalized exam and learning assistant",
    debug=settings.debug,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup_event() -> None:
    init_db()
    logger.info("TTS provider: %s", type(tts_service._provider).__name__)


@app.get("/")
def root() -> dict[str, str]:
    return {"status": "ok", "docs": "/docs"}


app.include_router(auth_router, prefix=settings.api_prefix)
app.include_router(subjects_router, prefix=settings.api_prefix)
app.include_router(tests_router, prefix=settings.api_prefix)
app.include_router(students_router, prefix=settings.api_prefix)
app.include_router(teacher_router, prefix=settings.api_prefix)
app.include_router(profile_router, prefix=settings.api_prefix)
