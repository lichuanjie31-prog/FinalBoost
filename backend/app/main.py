from dotenv import load_dotenv
load_dotenv()

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException
from .config import Settings
from .db import Database
from .auth import router as auth_router, current_user
from .common import new_id
from .business import router as business_router
from .modules.question_banks.router import router as question_banks_router
from .training import router as training_router

from .grading import GradingWorker
from .training_worker import TrainingWorker
from .schemas import ErrorEnvelope
from .marking.router import router as marking_router
from .marking.provider import TencentMarkingProvider
from .marking.qwen import QwenMarkingProvider
from .marking.fixture import FixtureMarkingProvider
from .marking.service import ExamMarkingTool
from .agent.router import router as agent_router
from concurrent.futures import ThreadPoolExecutor
import logging

logger = logging.getLogger(__name__)


def build_marking_providers(settings):
    """One provider instance per name, so a job is always polled by its own provider.

    In fixture mode every provider is stubbed, which keeps the whole pipeline real
    while the external boundary stays offline.
    """
    if settings.resolve_marking()[0] == "fixture":
        return {name: FixtureMarkingProvider(settings, name=name) for name in ("qwen", "tencent")}
    return {"qwen": QwenMarkingProvider(settings), "tencent": TencentMarkingProvider(settings)}


def create_app(**kwargs):
    settings = Settings(**kwargs)
    db = Database(settings.data_dir)

    # Initialize RAG service (lazy, optional)
    rag_service = None
    if settings.rag_enabled and settings.embedding_api_key:
        try:
            from .agent.rag import RagService
            rag_service = RagService(
                qdrant_url=settings.qdrant_url,
                embedding_base_url=settings.embedding_base_url,
                embedding_api_key=settings.embedding_api_key,
                embedding_model=settings.embedding_model,
                collection=settings.qdrant_collection,
            )
            logger.info("RAG service configured: qdrant=%s, collection=%s",
                       settings.qdrant_url, settings.qdrant_collection)
        except Exception:
            logger.warning("RAG service initialization failed, RAG disabled")

    @asynccontextmanager
    async def lifespan(app):
        settings.validate()
        db.migrate()
        # An in-process model call cannot survive a restart, so anything left
        # mid-flight by a previous run is failed rather than left hanging.
        ExamMarkingTool(db, app.state.marking_providers, settings).reconcile_interrupted()

        worker = GradingWorker(db)
        if settings.grading_mode == "llm":
            worker.configure_llm(settings)
        app.state.worker = worker
        worker.start()
        training_worker = TrainingWorker(db)
        app.state.training_worker = training_worker
        training_worker.start()
        try:
            yield
        finally:
            worker.close()
            training_worker.close()
            # Tests may replace the pool with None to run providers inline.
            executor = getattr(app.state, "marking_executor", None)
            if executor is not None:
                executor.shutdown(wait=False)

    app = FastAPI(
        title="FinalBoost",
        version="2.0.0",
        lifespan=lifespan,
        responses={code: {"model": ErrorEnvelope} for code in (400, 401, 403, 404, 409, 413, 415, 422, 429, 500)}
    )

    # Store services in app state
    app.state.settings = settings
    app.state.db = db
    app.state.rag_service = rag_service
    # MARKING_MODE=fixture swaps only the external provider boundary for a local
    # stub; every other layer stays real. Synchronous providers run on this pool so
    # a model call never holds the HTTP request open.
    app.state.marking_providers = build_marking_providers(settings)
    app.state.marking_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="marking")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE", "PATCH"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Requested-With"],
    )

    def error_response(status, message, code=None):
        # A module may pass its own business code (the question bank does); without
        # one the generic status-derived code is used.
        return JSONResponse(
            status_code=status,
            content={"code": code or status * 100 + 1, "message": message, "data": None, "requestId": new_id()},
            headers={"Cache-Control": "no-store"},
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: HTTPException):
        # A dict detail carries a module-specific business code. str() on it would
        # emit a Python repr and lose the code the frontend switches on.
        if isinstance(exc.detail, dict):
            return error_response(exc.status_code, exc.detail.get("message", ""), exc.detail.get("code"))
        return error_response(exc.status_code, str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        fields = ", ".join(str(e["loc"][-1]) for e in exc.errors())
        return error_response(400, f"参数不符合要求：{fields}")

    @app.exception_handler(Exception)
    async def internal_error(request: Request, exc: Exception):
        logger.exception("Unhandled exception")
        return error_response(500, "服务暂时不可用，请稍后重试")

    @app.get("/api/v1/health")
    def health():
        with db.transaction() as conn:
            conn.execute("SELECT 1").fetchone()
        mode = settings.grading_mode
        rag_status = "enabled" if rag_service else "disabled"
        readiness = settings.marking_readiness()
        return {
            "code": 0,
            "message": "success",
            "data": {
                "status": "ok",
                "gradingMode": mode,
                "chatMode": "llm" if settings.llm_api_key else "mock",
                "rag": rag_status,
                "version": "2.0.0-langchain",
                # Marks whether the real Tencent pathway is usable, so the UI never
                # presents a demo score as a real marking result.
                "markingMode": readiness["mode"],
                "markingProvider": readiness["provider"],
                "markingModel": readiness["model"],
                "markingConfigured": readiness["configured"],
                "markingMessage": readiness["message"],
            },
            "requestId": new_id(),
        }

    app.include_router(auth_router)
    app.include_router(business_router)
    app.include_router(marking_router)
    app.include_router(agent_router)
    app.include_router(question_banks_router)
    app.include_router(training_router)
    return app


app = create_app()
