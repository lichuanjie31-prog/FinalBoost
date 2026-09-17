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
from .training import router as training_router
from .grading import GradingWorker
from .training_worker import TrainingWorker
from .schemas import ErrorEnvelope

def create_app(**kwargs):
    settings = Settings(**kwargs)
    db = Database(settings.data_dir)
    @asynccontextmanager
    async def lifespan(app):
        settings.validate()
        db.migrate()
        worker = GradingWorker(db)
        if settings.llm_api_key:
            worker.configure_llm(settings)
        app.state.worker = worker
        worker.start()
        training_worker = TrainingWorker(db)
        app.state.training_worker = training_worker
        training_worker.start()
        try: yield
        finally:
            worker.close()
            training_worker.close()
    app = FastAPI(title="FinalBoost", version="1.0.0", lifespan=lifespan, responses={code:{"model":ErrorEnvelope} for code in (400,401,403,404,409,413,415,422,429,500)})
    app.state.settings, app.state.db = settings, db
    app.add_middleware(CORSMiddleware, allow_origins=list(settings.origins), allow_credentials=True, allow_methods=["GET","POST"], allow_headers=["Authorization","Content-Type","Idempotency-Key","X-Requested-With"])
    def error_response(status, message):
        return JSONResponse(status_code=status, content={"code":status*100+1,"message":message,"data":None,"requestId":new_id()}, headers={"Cache-Control":"no-store"})
    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: HTTPException): return error_response(exc.status_code,str(exc.detail))
    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        fields = ", ".join(str(e["loc"][-1]) for e in exc.errors())
        return error_response(400, f"参数不符合要求：{fields}")
    @app.exception_handler(Exception)
    async def internal_error(request: Request, exc: Exception): return error_response(500,"服务暂时不可用，请稍后重试")
    @app.get("/api/v1/health")
    def health():
        with db.transaction() as conn: conn.execute("SELECT 1").fetchone()
        mode = "llm" if settings.llm_api_key else "mock"
        return {"code":0,"message":"success","data":{"status":"ok","gradingMode":mode},"requestId":new_id()}
    app.include_router(auth_router)
    app.include_router(business_router)
    app.include_router(training_router)
    return app

app = create_app()
