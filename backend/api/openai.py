from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import List, Optional, AsyncGenerator
import json
import asyncio

from tinlyllmWeb.backend.models.database import get_db, User, Deployment, DeploymentStatus
from tinlyllmWeb.backend.services.deployment_service import DeploymentService
from tinlyllmWeb.backend.services.user_service import UserService
from tinlyllmWeb.backend.utils.jwt import get_current_user
from tinlyllmWeb.backend.models.database import PointsLogType
from tinlyllmWeb.backend.config import settings

router = APIRouter(prefix="/v1", tags=["OpenAI API"])

class ChatMessage(BaseModel):
    role: str = Field(..., description="消息角色")
    content: str = Field(..., description="消息内容")


class ChatCompletionRequest(BaseModel):
    model: str = Field(..., description="模型名称")
    messages: List[ChatMessage] = Field(..., description="对话消息列表")
    max_tokens: Optional[int] = Field(512, description="最大生成token数")
    temperature: Optional[float] = Field(0.7, description="生成温度")
    top_p: Optional[float] = Field(0.9, description="Top-p采样参数")
    top_k: Optional[int] = Field(50, description="Top-k采样参数")
    stream: Optional[bool] = Field(False, description="是否流式返回")
    stop: Optional[List[str]] = Field(None, description="停止词列表")


class ModelInfo(BaseModel):
    id: str
    object: str = "model"
    created: int
    owned_by: str


class ModelList(BaseModel):
    object: str = "list"
    data: List[ModelInfo]


def get_deployment_by_model(db: Session, model_name: str) -> Optional[Deployment]:
    deployment = db.query(Deployment).join(
        Deployment.model
    ).filter(
        Deployment.model.has(model_name=model_name),
        Deployment.status == DeploymentStatus.ACTIVE
    ).first()
    
    return deployment


@router.get("/models", response_model=ModelList)
async def list_models(
    db: Session = Depends(get_db)
):
    from tinlyllmWeb.backend.models.database import Model, ModelStatus
    
    models = db.query(Model).filter(
        Model.status == ModelStatus.TRAINED
    ).all()
    
    model_infos = []
    for model in models:
        deployment = db.query(Deployment).filter(
            Deployment.model_id == model.id,
            Deployment.status == DeploymentStatus.ACTIVE
        ).first()
        
        if deployment:
            model_infos.append(ModelInfo(
                id=model.model_name,
                created=int(model.created_at.timestamp()),
                owned_by="tinyllm"
            ))
    
    return ModelList(object="list", data=model_infos)


@router.post("/chat/completions")
async def create_chat_completion(
    request: ChatCompletionRequest,
    http_request: Request,
    db: Session = Depends(get_db)
):
    deployment = get_deployment_by_model(db, request.model)
    
    if not deployment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"模型 {request.model} 未部署或不存在"
        )
    
    device = deployment.device
    if not device or device.status != "online":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"设备不可用，请联系客服：{settings.CUSTOMER_EMAIL}"
        )
    
    DeploymentService.update_last_used(db, deployment.id)
    
    request_data = {
        "model": request.model,
        "messages": [{"role": msg.role, "content": msg.content} for msg in request.messages],
        "max_tokens": request.max_tokens,
        "temperature": request.temperature,
        "top_p": request.top_p,
        "top_k": request.top_k,
        "stream": request.stream
    }
    
    if request.stop:
        request_data["stop"] = request.stop
    
    try:
        import httpx
        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.post(
                f"http://{device.ip}:{deployment.port}/v1/chat/completions",
                json=request_data,
                timeout=300.0
            )
            response.raise_for_status()
            result = response.json()
            return result
    except Exception as e:
        print(f"[OpenAI] 推理请求失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"设备连接失败：{str(e)}"
        )
