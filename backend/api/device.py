import base64
import os
import uuid
import asyncio
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import List, Optional, Dict
import json

from tinlyllmWeb.backend.models.database import get_db, Device, TrainingTask, Deployment, TaskLog, LogType
from tinlyllmWeb.backend.services.device_service import DeviceService
from tinlyllmWeb.backend.services.training_service import TrainingService
from tinlyllmWeb.backend.services.user_service import UserService
from tinlyllmWeb.backend.utils.response import success_response, error_response
from tinlyllmWeb.backend.models.database import PointsLogType
from tinlyllmWeb.backend.config import settings

router = APIRouter(prefix="/api/device", tags=["设备通信"])


class DeviceRegister(BaseModel):
    device_name: str = Field(..., description="设备名称")
    ip: str = Field(..., description="设备IP")
    port: int = Field(..., description="设备端口")
    gpu_info: str = Field(..., description="GPU信息")
    vram_total: int = Field(..., description="显存总量(MB)")
    mode: str = Field("normal", description="运行模式：normal或frp")
    frp_server: Optional[str] = Field(None, description="FRP服务器地址（FRP模式必需）")


class DeviceUpdate(BaseModel):
    device_id: int = Field(..., description="设备ID")
    device_name: Optional[str] = Field(None, description="设备名称")
    ip: Optional[str] = Field(None, description="设备IP")
    port: Optional[int] = Field(None, description="设备端口")
    gpu_info: Optional[str] = Field(None, description="GPU信息")
    vram_total: Optional[int] = Field(None, description="显存总量(MB)")
    mode: Optional[str] = Field(None, description="运行模式：normal或frp")
    frp_server: Optional[str] = Field(None, description="FRP服务器地址（FRP模式必需）")


class DeviceHeartbeat(BaseModel):
    device_key: str = Field(..., description="设备密钥")
    vram_used: int = Field(..., description="已用显存(MB)")
    vram_free: int = Field(..., description="可用显存(MB)")


class TaskProgress(BaseModel):
    device_key: str = Field(..., description="设备密钥")
    task_id: int = Field(..., description="任务ID")
    progress: float = Field(..., description="进度(0-100)")
    log: Optional[str] = Field(None, description="日志内容")


class TaskComplete(BaseModel):
    device_key: str = Field(..., description="设备密钥")
    task_id: int = Field(..., description="任务ID")
    lora_path: str = Field(..., description="LoRA路径")


class TaskFailed(BaseModel):
    device_key: str = Field(..., description="设备密钥")
    task_id: int = Field(..., description="任务ID")
    error_message: str = Field(..., description="错误信息")


class DeviceLog(BaseModel):
    device_key: str = Field(..., description="设备密钥")
    log_type: str = Field(..., description="日志类型")
    level: str = Field(..., description="日志级别")
    message: str = Field(..., description="日志内容")
    task_id: Optional[int] = Field(None, description="任务ID")
    deployment_id: Optional[int] = Field(None, description="部署ID")


@router.post("/register", summary="设备注册")
async def register_device(
    device_data: DeviceRegister,
    db: Session = Depends(get_db)
):
    device = DeviceService.register_device(
        db=db,
        device_name=device_data.device_name,
        ip=device_data.ip,
        port=device_data.port,
        gpu_info=device_data.gpu_info,
        vram_total=device_data.vram_total,
        mode=device_data.mode,
        frp_server=device_data.frp_server
    )
    
    return success_response(
        message="注册成功",
        data={
            "device_id": device.id,
            "device_key": device.device_key
        }
    )


@router.post("/update", summary="更新设备信息")
async def update_device(
    device_data: DeviceUpdate,
    db: Session = Depends(get_db)
):
    success = DeviceService.update_device_info(
        db=db,
        device_id=device_data.device_id,
        device_name=device_data.device_name,
        ip=device_data.ip,
        port=device_data.port,
        gpu_info=device_data.gpu_info,
        vram_total=device_data.vram_total,
        mode=device_data.mode,
        frp_server=device_data.frp_server
    )
    
    if success:
        return success_response(message="更新成功")
    else:
        return error_response(message="设备不存在", code=404)


@router.post("/heartbeat", summary="设备心跳")
async def device_heartbeat(
    heartbeat_data: DeviceHeartbeat,
    db: Session = Depends(get_db)
):
    device = DeviceService.get_device_by_key(db, heartbeat_data.device_key)
    
    if not device:
        return error_response(message="设备不存在", code=404)
    
    success = DeviceService.update_heartbeat(
        db=db,
        device_id=device.id,
        vram_used=heartbeat_data.vram_used,
        vram_free=heartbeat_data.vram_free
    )
    
    if not success:
        return error_response(message="更新失败", code=400)
    
    return success_response(message="心跳成功")


@router.get("/tasks/pending", summary="获取待处理任务")
async def get_pending_tasks(
    device_key: str,
    request: Request,
    db: Session = Depends(get_db)
):
    device = DeviceService.get_device_by_key(db, device_key)
    
    if not device:
        return error_response(message="设备不存在", code=404)
    
    pending_tasks = TrainingService.get_pending_tasks(db)
    
    result = []
    for task in pending_tasks:
        model = task.model
        dataset = task.dataset
        
        dataset_content_b64 = ""
        if dataset and os.path.exists(dataset.file_path):
            try:
                with open(dataset.file_path, 'rb') as f:
                    dataset_content_b64 = base64.b64encode(f.read()).decode('utf-8')
            except Exception as e:
                print(f"[Warning] 读取数据集文件失败: {e}")
        
        result.append({
            "task_id": task.id,
            "model_id": task.model_id,
            "model_name": model.model_name if model else "",
            "base_model": model.base_model if model else "",
            "dataset_id": task.dataset_id,
            "dataset_filename": dataset.filename if dataset else "",
            "dataset_content": dataset_content_b64,
            "training_params": model.training_params if model else "{}"
        })
    
    return success_response(
        message="获取成功",
        data=result
    )


@router.post("/tasks/accept", summary="接受任务")
async def accept_task(
    device_key: str,
    task_id: int,
    db: Session = Depends(get_db)
):
    device = DeviceService.get_device_by_key(db, device_key)
    
    if not device:
        return error_response(message="设备不存在", code=404)
    
    success = TrainingService.assign_task_to_device(db, task_id, device.id)
    
    if not success:
        return error_response(message="接受任务失败", code=400)
    
    return success_response(message="任务已接受")


@router.post("/tasks/progress", summary="更新任务进度")
async def update_task_progress(
    progress_data: TaskProgress,
    db: Session = Depends(get_db)
):
    device = DeviceService.get_device_by_key(db, progress_data.device_key)
    
    if not device:
        return error_response(message="设备不存在", code=404)
    
    task = TrainingService.get_training_task_by_id(db, progress_data.task_id)
    
    if not task or task.device_id != device.id:
        return error_response(message="任务不存在或不属于此设备", code=404)
    
    success = TrainingService.update_task_progress(
        db=db,
        task_id=progress_data.task_id,
        progress=progress_data.progress,
        log=progress_data.log
    )
    
    if not success:
        return error_response(message="更新失败", code=400)
    
    return success_response(message="进度已更新")


@router.post("/tasks/complete", summary="完成任务")
async def complete_task(
    complete_data: TaskComplete,
    db: Session = Depends(get_db)
):
    device = DeviceService.get_device_by_key(db, complete_data.device_key)
    
    if not device:
        return error_response(message="设备不存在", code=404)
    
    task = TrainingService.get_training_task_by_id(db, complete_data.task_id)
    
    if not task or task.device_id != device.id:
        return error_response(message="任务不存在或不属于此设备", code=404)
    
    success = TrainingService.complete_task(
        db=db,
        task_id=complete_data.task_id,
        lora_path=complete_data.lora_path
    )
    
    if not success:
        return error_response(message="完成任务失败", code=400)
    
    return success_response(message="任务已完成")


@router.post("/tasks/failed", summary="任务失败")
async def task_failed(
    failed_data: TaskFailed,
    db: Session = Depends(get_db)
):
    device = DeviceService.get_device_by_key(db, failed_data.device_key)
    
    if not device:
        return error_response(message="设备不存在", code=404)
    
    task = TrainingService.get_training_task_by_id(db, failed_data.task_id)
    
    if not task or task.device_id != device.id:
        return error_response(message="任务不存在或不属于此设备", code=404)
    
    success = TrainingService.fail_task(
        db=db,
        task_id=failed_data.task_id,
        error_message=failed_data.error_message
    )
    
    if not success:
        return error_response(message="标记失败失败", code=400)
    
    return success_response(message="任务已标记为失败")


@router.post("/logs", summary="设备日志")
async def device_logs(
    log_data: DeviceLog,
    db: Session = Depends(get_db)
):
    device = DeviceService.get_device_by_key(db, log_data.device_key)
    
    if not device:
        return error_response(message="设备不存在", code=404)
    
    try:
        log_type = LogType.TRAINING if log_data.log_type == "training" else LogType.DEPLOYMENT
    except:
        log_type = LogType.SYSTEM
    
    log = TaskLog(
        task_id=log_data.task_id,
        deployment_id=log_data.deployment_id,
        device_id=device.id,
        log_type=log_type,
        level=log_data.level,
        message=log_data.message
    )
    
    db.add(log)
    db.commit()
    
    return success_response(message="日志已记录")


@router.get("/deployments", summary="获取设备的部署任务")
async def get_device_deployments(
    device_key: str,
    db: Session = Depends(get_db)
):
    device = DeviceService.get_device_by_key(db, device_key)
    
    if not device:
        return error_response(message="设备不存在", code=404)
    
    from tinlyllmWeb.backend.models.database import DeploymentStatus
    deployments = db.query(Deployment).filter(
        Deployment.device_id == device.id,
        Deployment.status.in_([DeploymentStatus.ACTIVE, DeploymentStatus.DEPLOYING])
    ).all()
    
    result = []
    for deployment in deployments:
        model = deployment.model
        result.append({
            "deployment_id": deployment.id,
            "device_id": deployment.device_id,
            "model_id": deployment.model_id,
            "model_name": model.model_name if model else "",
            "base_model": model.base_model if model else "",
            "lora_path": model.lora_path if model else "",
            "port": deployment.port
        })
    
    return success_response(
        message="获取成功",
        data=result
    )


class DeploymentCrashed(BaseModel):
    device_key: str = Field(..., description="设备密钥")
    deployment_id: int = Field(..., description="部署ID")
    error_message: str = Field(..., description="错误信息")


class DeploymentStarted(BaseModel):
    device_key: str = Field(..., description="设备密钥")
    deployment_id: int = Field(..., description="部署ID")
    vram_used: int = Field(..., description="使用的显存（MB）")
    api_url: str = Field(None, description="API地址（FRP地址或本地地址）")


@router.post("/deployments/crashed", summary="通知部署崩溃")
async def deployment_crashed(
    data: DeploymentCrashed,
    db: Session = Depends(get_db)
):
    device = DeviceService.get_device_by_key(db, data.device_key)
    
    if not device:
        return error_response(message="设备不存在", code=404)
    
    deployment = db.query(Deployment).filter(
        Deployment.id == data.deployment_id,
        Deployment.device_id == device.id
    ).first()
    
    if not deployment:
        return error_response(message="部署不存在", code=404)
    
    from tinlyllmWeb.backend.models.database import DeploymentStatus
    deployment.status = DeploymentStatus.STOPPED
    
    device.vram_used = max(0, (device.vram_used or 0) - deployment.vram_used)
    device.vram_free = (device.vram_total or 0) - device.vram_used
    device.updated_at = datetime.utcnow()
    
    log = TaskLog(
        deployment_id=deployment.id,
        device_id=device.id,
        log_type=LogType.DEPLOYMENT,
        level="ERROR",
        message=f"部署崩溃: {data.error_message}"
    )
    db.add(log)
    db.commit()
    
    return success_response(message="部署已停止")


@router.post("/deployments/started", summary="通知部署启动成功")
async def deployment_started(
    data: DeploymentStarted,
    db: Session = Depends(get_db)
):
    device = DeviceService.get_device_by_key(db, data.device_key)
    
    if not device:
        return error_response(message="设备不存在", code=404)
    
    deployment = db.query(Deployment).filter(
        Deployment.id == data.deployment_id,
        Deployment.device_id == device.id
    ).first()
    
    if not deployment:
        return error_response(message="部署不存在", code=404)
    
    from tinlyllmWeb.backend.models.database import DeploymentStatus
    deployment.status = DeploymentStatus.ACTIVE
    deployment.vram_used = data.vram_used
    
    if data.api_url:
        deployment.api_url = data.api_url
        print(f"[Device] 部署 {data.deployment_id} API地址: {data.api_url}")
    else:
        if device.mode == "frp" and device.frp_server:
            frp_port = 32000 + deployment.id
            deployment.api_url = f"http://{device.frp_server.split(':')[0]}:{frp_port}/v1"
        else:
            deployment.api_url = f"http://{device.ip}:{deployment.port}/v1"
    
    device.vram_used = (device.vram_used or 0) + data.vram_used
    device.vram_free = (device.vram_total or 0) - device.vram_used
    device.updated_at = datetime.utcnow()
    
    log = TaskLog(
        deployment_id=deployment.id,
        device_id=device.id,
        log_type=LogType.DEPLOYMENT,
        level="INFO",
        message=f"部署启动成功，API: {deployment.api_url}，使用显存: {data.vram_used}MB"
    )
    db.add(log)
    db.commit()
    
    return success_response(message="部署状态已更新")


@router.post("/deployments/failed", summary="通知部署启动失败")
async def deployment_failed(
    data: DeploymentCrashed,
    db: Session = Depends(get_db)
):
    print(f"[Device] 收到部署失败通知: deployment_id={data.deployment_id}, error={data.error_message}")
    
    device = DeviceService.get_device_by_key(db, data.device_key)
    
    if not device:
        return error_response(message="设备不存在", code=404)
    
    deployment = db.query(Deployment).filter(
        Deployment.id == data.deployment_id,
        Deployment.device_id == device.id
    ).first()
    
    if not deployment:
        return error_response(message="部署不存在", code=404)
    
    user = db.query(User).filter(User.id == deployment.user_id).first()
    
    model = deployment.model
    model_name = model.model_name if model else f"ID:{deployment.model_id}"
    
    from tinlyllmWeb.backend.models.database import DeploymentStatus, TaskLog, LogType
    from tinlyllmWeb.backend.models.database import PointsLogType
    
    if deployment.status == DeploymentStatus.ACTIVE:
        deployment.status = DeploymentStatus.STOPPED
        
        if deployment.vram_used:
            device.vram_used = max(0, (device.vram_used or 0) - deployment.vram_used)
            device.vram_free = (device.vram_total or 0) - device.vram_used
            device.updated_at = datetime.utcnow()
    elif deployment.status == DeploymentStatus.DEPLOYING:
        deployment.status = DeploymentStatus.FAILED
        
        if deployment.vram_used:
            device.vram_used = max(0, (device.vram_used or 0) - deployment.vram_used)
            device.vram_free = (device.vram_total or 0) - device.vram_used
            device.updated_at = datetime.utcnow()
    
    log = TaskLog(
        deployment_id=deployment.id,
        device_id=device.id,
        log_type=LogType.DEPLOYMENT,
        level="ERROR",
        message=f"部署启动失败: {data.error_message}"
    )
    db.add(log)
    
    cost = 0
    refund_amount = 0
    
    if user:
        if deployment.expires_at and deployment.expires_at > datetime.utcnow():
            remaining_hours = max(0, (deployment.expires_at - datetime.utcnow()).total_seconds() / 3600)
            cost = max(1, math.ceil(remaining_hours / 24))
        
        if cost > 0:
            success = UserService.add_points(
                db=db,
                user_id=user.id,
                amount=cost,
                log_type=PointsLogType.REFUND,
                description=f"部署启动失败退款：{model_name}（{data.error_message}）"
            )
            if success:
                refund_amount = cost
                print(f"[Device] 已为用户 {user.username} 退款 {refund_amount} 积分")
            else:
                print(f"[Device] 退款失败，用户: {user.username}")
    
    db.commit()
    
    return success_response(
        message="部署已停止并退款",
        data={
            "refund_amount": refund_amount,
            "error": data.error_message
        }
    )


class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[str, WebSocket] = {}
    
    async def connect(self, device_key: str, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[device_key] = websocket
    
    def disconnect(self, device_key: str):
        if device_key in self.active_connections:
            del self.active_connections[device_key]
    
    async def send_message(self, device_key: str, message: dict):
        if device_key in self.active_connections:
            await self.active_connections[device_key].send_json(message)
    
    async def broadcast(self, message: dict):
        for connection in self.active_connections.values():
            await connection.send_json(message)


manager = ConnectionManager()


@router.websocket("/ws/{device_key}")
async def device_websocket(websocket: WebSocket, device_key: str, db: Session = Depends(get_db)):
    device = DeviceService.get_device_by_key(db, device_key)
    
    if not device:
        await websocket.close(code=1008, reason="设备不存在")
        return
    
    await manager.connect(device_key, websocket)
    print(f"[WebSocket] 设备 {device.device_name} (ID:{device.id}) 已连接")
    
    websocket.ping_interval = 30
    websocket.ping_timeout = 60
    
    try:
        from tinlyllmWeb.backend.models.database import DeploymentStatus
        deployments = db.query(Deployment).filter(
            Deployment.device_id == device.id,
            Deployment.status.in_([DeploymentStatus.ACTIVE, DeploymentStatus.DEPLOYING])
        ).all()
        
        if deployments:
            print(f"[WebSocket] 设备 {device.device_name} 有 {len(deployments)} 个活跃部署，正在推送...")
            for deployment in deployments:
                model = deployment.model
                deployment_data = {
                    "type": "command",
                    "command": "start_deployment",
                    "deployment_data": {
                        "deployment_id": deployment.id,
                        "model_id": deployment.model_id,
                        "model_name": model.model_name if model else "",
                        "base_model": model.base_model if model else "",
                        "lora_path": model.lora_path if model else "",
                        "port": deployment.port
                    }
                }
                await manager.send_message(device_key, deployment_data)
                print(f"[WebSocket] 已推送部署任务 {deployment.id}")
        
        while True:
            data = await websocket.receive_json()
            
            if data.get("type") == "heartbeat":
                pass
            elif data.get("type") == "task_progress":
                pass
            elif data.get("type") == "task_complete":
                pass
            elif data.get("type") == "task_failed":
                pass
    except WebSocketDisconnect:
        manager.disconnect(device_key)
        print(f"[WebSocket] 设备 {device.device_name} (ID:{device.id}) 已断开")
    except Exception as e:
        manager.disconnect(device_key)
        print(f"[WebSocket] 设备 {device.device_name} 连接错误: {e}")
