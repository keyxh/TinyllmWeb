from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
import uvicorn
import os
import sys
import asyncio
from datetime import datetime, timedelta
import math

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tinlyllmWeb.backend.config import settings
from tinlyllmWeb.backend.api import auth, user, dataset, training, model, deployment, admin, device, openai, log, community, payment, android_pay
from tinlyllmWeb.backend.models.database import get_db, Deployment, DeploymentStatus, Device, User
from tinlyllmWeb.backend.services.user_service import UserService
from tinlyllmWeb.backend.models.database import PointsLogType

app = FastAPI(
    title="TinyLLM Platform",
    description="AI模型微调平台",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "frontend/static")), name="static")
app.mount("/backend/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "backend/static")), name="backend_static")

frontend_dir = os.path.join(os.path.dirname(__file__), "frontend")
uploads_dir = os.path.join(frontend_dir, "uploads")
os.makedirs(uploads_dir, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=uploads_dir), name="uploads")

app.include_router(auth.router)
app.include_router(user.router)
app.include_router(dataset.router)
app.include_router(training.router)
app.include_router(model.router)
app.include_router(deployment.router)
app.include_router(admin.router)
app.include_router(device.router)
app.include_router(openai.router)
app.include_router(log.router)
app.include_router(community.router)
app.include_router(payment.router)
app.include_router(android_pay.router)


async def check_deployment_timeouts():
    while True:
        try:
            db = next(get_db())
            timeout_minutes = 5
            timeout_threshold = datetime.utcnow() - timedelta(minutes=timeout_minutes)
            
            timeout_deployments = db.query(Deployment).filter(
                Deployment.status == DeploymentStatus.DEPLOYING,
                Deployment.created_at < timeout_threshold
            ).all()
            
            for deployment in timeout_deployments:
                print(f"[Deployment] 部署 {deployment.id} 超时，标记为FAILED并退款")
                
                deployment.status = DeploymentStatus.FAILED
                
                device = db.query(Device).filter(Device.id == deployment.device_id).first()
                if device:
                    device.vram_used = max(0, (device.vram_used or 0) - deployment.vram_used)
                    device.vram_free = (device.vram_total or 0) - device.vram_used
                    device.updated_at = datetime.utcnow()
                
                model = deployment.model
                refund_amount = 0
                if deployment.expires_at and deployment.expires_at > datetime.utcnow():
                    remaining_hours = max(0, (deployment.expires_at - datetime.utcnow()).total_seconds() / 3600)
                    refund_amount = max(1, math.ceil(remaining_hours / 24))
                
                if refund_amount > 0:
                    success = UserService.add_points(
                        db=db,
                        user_id=deployment.user_id,
                        amount=refund_amount,
                        log_type=PointsLogType.REFUND,
                        description=f"部署超时退款：{model.model_name if model else f'ID:{deployment.model_id}'}"
                    )
                    if success:
                        print(f"[Deployment] 已退款 {refund_amount} 积分给用户 {deployment.user_id}")
                
                db.commit()
            
            db.close()
        except Exception as e:
            print(f"[Deployment] 检查部署超时失败: {e}")
        
        await asyncio.sleep(60)


@app.on_event("startup")
async def startup_event():
    asyncio.create_task(check_deployment_timeouts())


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    print(f"[Validation Error] {exc.errors()}")
    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "message": "数据验证失败",
            "errors": exc.errors()
        }
    )


@app.get("/", response_class=HTMLResponse)
async def root():
    try:
        with open(os.path.join(os.path.dirname(__file__), "frontend/templates/login.html"), "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return HTMLResponse(content=f"<h1>错误</h1><p>无法加载登录页面: {str(e)}</p>", status_code=500)


@app.get("/app", response_class=HTMLResponse)
async def app_page():
    try:
        with open(os.path.join(os.path.dirname(__file__), "frontend/templates/app.html"), "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return HTMLResponse(content=f"<h1>错误</h1><p>无法加载应用页面: {str(e)}</p>", status_code=500)


@app.get("/admin", response_class=HTMLResponse)
async def admin_page():
    try:
        with open(os.path.join(os.path.dirname(__file__), "frontend/templates/admin.html"), "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return HTMLResponse(content=f"<h1>错误</h1><p>无法加载管理页面: {str(e)}</p>", status_code=500)


@app.get("/contact", response_class=HTMLResponse)
async def contact_page():
    try:
        with open(os.path.join(os.path.dirname(__file__), "frontend/templates/contact.html"), "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return HTMLResponse(content=f"<h1>错误</h1><p>无法加载联系客服页面: {str(e)}</p>", status_code=500)


@app.get("/community", response_class=HTMLResponse)
async def community_page():
    try:
        with open(os.path.join(os.path.dirname(__file__), "frontend/templates/community.html"), "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return HTMLResponse(content=f"<h1>错误</h1><p>无法加载社区页面: {str(e)}</p>", status_code=500)


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "app_name": settings.APP_NAME,
        "version": settings.APP_VERSION
    }


if __name__ == "__main__":
    print(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    print(f"Database: {settings.DATABASE_USER}@{settings.DATABASE_HOST}:{settings.DATABASE_PORT}/{settings.DATABASE_NAME}")
    print(f"Server running at http://0.0.0.0:8000")
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )
