from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List

from tinlyllmWeb.backend.models.database import get_db, User, Model, ModelStatus
from tinlyllmWeb.backend.services.model_service import ModelService
from tinlyllmWeb.backend.utils.jwt import get_current_user, get_current_admin
from tinlyllmWeb.backend.utils.response import success_response, error_response

router = APIRouter(prefix="/api/models", tags=["模型管理"])


class ModelInfo(BaseModel):
    id: int
    model_name: str
    base_model: str
    status: str
    created_at: str


@router.get("/", summary="获取用户模型列表")
async def get_models(
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    models = db.query(Model).filter(
        Model.user_id == current_user.id,
        Model.status != ModelStatus.FAILED,
        Model.status != ModelStatus.DELETED
    ).order_by(Model.created_at.desc()).offset(skip).limit(limit).all()
    
    return success_response(
        message="获取成功",
        data=[
            {
                "id": model.id,
                "model_name": model.model_name,
                "base_model": model.base_model,
                "status": model.status.value,
                "created_at": model.created_at.isoformat()
            }
            for model in models
        ]
    )


@router.get("/{model_id}", summary="获取模型详情")
async def get_model(
    model_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    model = ModelService.get_model_by_id(db, model_id)
    
    if not model or model.user_id != current_user.id:
        return error_response(message="模型不存在", code=404)
    
    return success_response(
        message="获取成功",
        data={
            "id": model.id,
            "model_name": model.model_name,
            "base_model": model.base_model,
            "status": model.status.value,
            "training_params": model.training_params,
            "created_at": model.created_at.isoformat(),
            "updated_at": model.updated_at.isoformat()
        }
    )


@router.delete("/{model_id}", summary="删除模型")
async def delete_model(
    model_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    success = ModelService.delete_model(db, model_id, current_user.id)
    
    if not success:
        return error_response(message="删除失败，模型可能正在被部署", code=400)
    
    return success_response(message="删除成功")


@router.get("/all", summary="获取所有模型（管理员）")
async def get_all_models(
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    models = ModelService.get_all_models(db, skip, limit)
    
    return success_response(
        message="获取成功",
        data=[
            {
                "id": model.id,
                "user_id": model.user_id,
                "username": model.user.username if model.user else "",
                "model_name": model.model_name,
                "base_model": model.base_model,
                "status": model.status.value,
                "created_at": model.created_at.isoformat()
            }
            for model in models
        ]
    )
