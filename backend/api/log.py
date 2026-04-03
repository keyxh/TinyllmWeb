from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional

from tinlyllmWeb.backend.models.database import get_db, User, TaskLog, Model, Deployment
from tinlyllmWeb.backend.utils.jwt import get_current_user
from tinlyllmWeb.backend.utils.response import success_response, error_response

router = APIRouter(prefix="/api/logs", tags=["日志管理"])


class LogInfo(BaseModel):
    id: int
    task_id: Optional[int]
    deployment_id: Optional[int]
    log_type: str
    level: str
    message: str
    created_at: str


@router.get("/model/{model_id}", summary="获取模型日志")
async def get_model_logs(
    model_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    model = db.query(Model).filter(Model.id == model_id).first()
    
    if not model or model.user_id != current_user.id:
        return error_response(message="模型不存在", code=404)
    
    logs = db.query(TaskLog).filter(
        (TaskLog.task_id == model_id) | (TaskLog.deployment_id.in_(
            db.query(Deployment.id).filter(Deployment.model_id == model_id)
        ))
    ).order_by(TaskLog.created_at.desc()).offset(skip).limit(limit).all()
    
    result = []
    for log in logs:
        result.append({
            "id": log.id,
            "task_id": log.task_id,
            "deployment_id": log.deployment_id,
            "log_type": log.log_type.value,
            "level": log.level,
            "message": log.message,
            "created_at": log.created_at.isoformat()
        })
    
    return success_response(message="获取成功", data=result)


@router.get("/task/{task_id}", summary="获取任务日志")
async def get_task_logs(
    task_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    logs = db.query(TaskLog).filter(
        TaskLog.task_id == task_id
    ).order_by(TaskLog.created_at.desc()).offset(skip).limit(limit).all()
    
    result = []
    for log in logs:
        result.append({
            "id": log.id,
            "task_id": log.task_id,
            "deployment_id": log.deployment_id,
            "log_type": log.log_type.value,
            "level": log.level,
            "message": log.message,
            "created_at": log.created_at.isoformat()
        })
    
    return success_response(message="获取成功", data=result)


@router.get("/deployment/{deployment_id}", summary="获取部署日志")
async def get_deployment_logs(
    deployment_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    deployment = db.query(Deployment).filter(Deployment.id == deployment_id).first()
    
    if not deployment or deployment.user_id != current_user.id:
        return error_response(message="部署不存在", code=404)
    
    logs = db.query(TaskLog).filter(
        TaskLog.deployment_id == deployment_id
    ).order_by(TaskLog.created_at.desc()).offset(skip).limit(limit).all()
    
    result = []
    for log in logs:
        result.append({
            "id": log.id,
            "task_id": log.task_id,
            "deployment_id": log.deployment_id,
            "log_type": log.log_type.value,
            "level": log.level,
            "message": log.message,
            "created_at": log.created_at.isoformat()
        })
    
    return success_response(message="获取成功", data=result)
