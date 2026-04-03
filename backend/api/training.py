from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field, validator
from typing import Optional
import re

from tinlyllmWeb.backend.models.database import get_db, User, TrainingTask, Dataset, TaskStatus
from tinlyllmWeb.backend.services.training_service import TrainingService
from tinlyllmWeb.backend.services.user_service import UserService
from tinlyllmWeb.backend.services.dataset_service import DatasetService
from tinlyllmWeb.backend.services.model_config_service import model_config_service
from tinlyllmWeb.backend.utils.jwt import get_current_user, get_current_admin
from tinlyllmWeb.backend.utils.response import success_response, error_response
from tinlyllmWeb.backend.models.database import PointsLogType

router = APIRouter(prefix="/api/training", tags=["训练任务"])


class CreateTrainingTask(BaseModel):
    dataset_id: int = Field(..., description="数据集ID")
    model_name: str = Field(..., min_length=1, max_length=100, description="模型名称")
    base_model: str = Field(..., description="基础模型")
    num_epochs: int = Field(5, description="训练轮数")
    
    @validator('model_name')
    def validate_model_name(cls, v):
        if not re.match(r'^[a-zA-Z_\u4e00-\u9fa5][a-zA-Z0-9_\u4e00-\u9fa5]*$', v):
            raise ValueError('模型名称只能包含中文、英文字母、数字和下划线，且不能以数字开头')
        return v


class TrainingTaskInfo(BaseModel):
    id: int
    model_name: str
    base_model: str
    status: str
    error_message: Optional[str]
    created_at: str
    started_at: Optional[str]
    completed_at: Optional[str]


@router.get("/base-models", summary="获取支持的基础模型列表")
async def get_base_models():
    models = model_config_service.get_enabled_models()
    return success_response(
        message="获取成功",
        data=models
    )


@router.post("/create", summary="创建训练任务")
async def create_training_task(
    task_data: CreateTrainingTask,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    print(f"[DEBUG] Received task data: {task_data}")
    
    model_config = model_config_service.get_model_by_name(task_data.base_model)
    if not model_config:
        return error_response(message="不支持的基础模型", code=400)
    
    if not model_config.get("enable", True):
        return error_response(message="该模型暂不可用", code=400)
    
    dataset = DatasetService.get_dataset_by_id(db, task_data.dataset_id)
    if not dataset or dataset.user_id != current_user.id:
        return error_response(message="数据集不存在", code=404)
    
    training_cost = model_config.get("training_cost", {}).get("min", 30.0)
    
    if current_user.points < training_cost:
        return error_response(message=f"积分不足，需要{training_cost}积分", code=400)
    
    existing_model = db.query(TrainingTask).join(
        TrainingTask.model
    ).filter(
        TrainingTask.user_id == current_user.id,
        TrainingTask.status.in_(["pending", "running"])
    ).first()
    
    if existing_model:
        return error_response(message="已有训练任务正在进行中", code=400)
    
    training_params = {
        "num_epochs": task_data.num_epochs,
        "batch_size": 2,
        "learning_rate": 5e-4,
        "lora_r": 128,
        "lora_alpha": 32,
        "max_length": 512
    }
    
    task = TrainingService.create_training_task(
        db=db,
        user_id=current_user.id,
        dataset_id=task_data.dataset_id,
        model_name=task_data.model_name,
        base_model=task_data.base_model,
        training_params=training_params
    )
    
    success = UserService.deduct_points(
        db=db,
        user_id=current_user.id,
        amount=training_cost,
        log_type=PointsLogType.TRAINING,
        description=f"训练模型：{task_data.model_name}"
    )
    
    if not success:
        return error_response(message="扣除积分失败", code=400)
    
    return success_response(
        message="训练任务创建成功",
        data={
            "task_id": task.id,
            "model_id": task.model_id,
            "status": task.status.value
        }
    )


@router.get("/tasks", summary="获取用户训练任务列表")
async def get_training_tasks(
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    tasks = TrainingService.get_user_training_tasks(db, current_user.id, skip, limit)
    
    result = []
    for task in tasks:
        result.append({
            "id": task.id,
            "model_id": task.model_id,
            "model_name": task.model.model_name if task.model else "",
            "base_model": task.model.base_model if task.model else "",
            "status": task.status.value,
            "error_message": task.error_message,
            "created_at": task.created_at.isoformat(),
            "started_at": task.started_at.isoformat() if task.started_at else None,
            "completed_at": task.completed_at.isoformat() if task.completed_at else None
        })
    
    return success_response(message="获取成功", data=result)


@router.delete("/tasks/{task_id}", summary="删除训练任务")
async def delete_training_task(
    task_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    task = TrainingService.get_training_task_by_id(db, task_id)
    
    if not task or task.user_id != current_user.id:
        return error_response(message="任务不存在", code=404)
    
    if task.status in [TaskStatus.PENDING, TaskStatus.RUNNING]:
        return error_response(message="进行中的任务不能删除，请先取消", code=400)
    
    success = TrainingService.delete_task(db, task_id, current_user.id)
    
    if not success:
        return error_response(message="删除失败", code=400)
    
    return success_response(message="删除成功")


@router.get("/tasks/{task_id}", summary="获取训练任务详情")
async def get_training_task(
    task_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    task = TrainingService.get_training_task_by_id(db, task_id)
    
    if not task or task.user_id != current_user.id:
        return error_response(message="任务不存在", code=404)
    
    return success_response(
        message="获取成功",
        data={
            "id": task.id,
            "model_id": task.model_id,
            "model_name": task.model.model_name if task.model else "",
            "base_model": task.model.base_model if task.model else "",
            "dataset_id": task.dataset_id,
            "status": task.status.value,
            "progress": task.progress,
            "logs": task.logs or "",
            "error_message": task.error_message,
            "created_at": task.created_at.isoformat(),
            "started_at": task.started_at.isoformat() if task.started_at else None,
            "completed_at": task.completed_at.isoformat() if task.completed_at else None
        }
    )


@router.post("/tasks/{task_id}/cancel", summary="取消训练任务")
async def cancel_training_task(
    task_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    task = TrainingService.get_training_task_by_id(db, task_id)
    if not task or task.user_id != current_user.id:
        return error_response(message="任务不存在", code=404)
    
    success = TrainingService.cancel_task(db, task_id, current_user.id)
    
    if not success:
        return error_response(message="取消失败", code=400)
    
    model = db.query(Model).filter(Model.id == task.model_id).first()
    if model:
        model_config = model_config_service.get_model_by_name(model.base_model)
        if model_config:
            training_cost = model_config.get("training_cost", {}).get("min", 30.0)
            UserService.add_points(
                db=db,
                user_id=current_user.id,
                amount=training_cost,
                log_type=PointsLogType.REFUND,
                description=f"取消训练任务退款：{model.model_name}"
            )
    
    return success_response(message="取消成功")


@router.post("/tasks/{task_id}/restart", summary="重新开始训练任务")
async def restart_training_task(
    task_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    task = TrainingService.get_training_task_by_id(db, task_id)
    if not task or task.user_id != current_user.id:
        return error_response(message="任务不存在", code=404)
    
    model = db.query(Model).filter(Model.id == task.model_id).first()
    if not model:
        return error_response(message="模型不存在", code=404)
    
    model_config = model_config_service.get_model_by_name(model.base_model)
    training_cost = model_config.get("training_cost", {}).get("min", 30.0) if model_config else 30.0
    
    if current_user.points < training_cost:
        return error_response(message=f"积分不足，需要{training_cost}积分", code=400)
    
    success = TrainingService.restart_task(db, task_id, current_user.id)
    
    if not success:
        return error_response(message="重启失败，任务状态不允许", code=400)
    
    UserService.deduct_points(
        db=db,
        user_id=current_user.id,
        amount=training_cost,
        log_type=PointsLogType.TRAINING,
        description=f"重新训练模型：{model.model_name}"
    )
    
    return success_response(message="重启成功")


@router.get("/all", summary="获取所有训练任务（管理员）")
async def get_all_training_tasks(
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    tasks = TrainingService.get_all_training_tasks(db, skip, limit)
    
    result = []
    for task in tasks:
        result.append({
            "id": task.id,
            "user_id": task.user_id,
            "username": task.user.username if task.user else "",
            "model_id": task.model_id,
            "model_name": task.model.model_name if task.model else "",
            "base_model": task.model.base_model if task.model else "",
            "status": task.status.value,
            "progress": task.progress,
            "logs": task.logs or "",
            "error_message": task.error_message,
            "created_at": task.created_at.isoformat(),
            "started_at": task.started_at.isoformat() if task.started_at else None,
            "completed_at": task.completed_at.isoformat() if task.completed_at else None
        })
    
    return success_response(message="获取成功", data=result)
