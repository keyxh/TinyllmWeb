from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List

from tinlyllmWeb.backend.models.database import get_db, User
from tinlyllmWeb.backend.services.device_service import DeviceService
from tinlyllmWeb.backend.services.training_service import TrainingService
from tinlyllmWeb.backend.services.deployment_service import DeploymentService
from tinlyllmWeb.backend.services.user_service import UserService
from tinlyllmWeb.backend.utils.jwt import get_current_admin
from tinlyllmWeb.backend.utils.response import success_response, error_response

router = APIRouter(prefix="/api/admin", tags=["管理后台"])


class DashboardStats(BaseModel):
    total_users: int
    total_devices: int
    online_devices: int
    total_models: int
    total_deployments: int
    active_deployments: int
    pending_tasks: int
    running_tasks: int


@router.get("/dashboard", summary="获取仪表盘统计数据")
async def get_dashboard_stats(
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    from tinlyllmWeb.backend.models.database import Device, Deployment, TrainingTask, Model, DeviceStatus, DeploymentStatus, TaskStatus
    
    total_users = db.query(User).count()
    total_devices = db.query(Device).count()
    online_devices = db.query(Device).filter(Device.status == DeviceStatus.ONLINE).count()
    total_models = db.query(Model).filter(Model.status != "deleted").count()
    total_deployments = db.query(Deployment).count()
    active_deployments = db.query(Deployment).filter(Deployment.status == DeploymentStatus.ACTIVE).count()
    pending_tasks = db.query(TrainingTask).filter(TrainingTask.status == TaskStatus.PENDING).count()
    running_tasks = db.query(TrainingTask).filter(TrainingTask.status == TaskStatus.RUNNING).count()
    
    return success_response(
        message="获取成功",
        data={
            "total_users": total_users,
            "total_devices": total_devices,
            "online_devices": online_devices,
            "total_models": total_models,
            "total_deployments": total_deployments,
            "active_deployments": active_deployments,
            "pending_tasks": pending_tasks,
            "running_tasks": running_tasks
        }
    )


@router.get("/devices", summary="获取所有设备")
async def get_devices(
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    devices = DeviceService.get_all_devices(db, skip, limit)
    
    return success_response(
        message="获取成功",
        data=[
            {
                "id": device.id,
                "device_name": device.device_name,
                "device_key": device.device_key,
                "ip": device.ip,
                "port": device.port,
                "gpu_info": device.gpu_info,
                "vram_total": device.vram_total,
                "vram_used": device.vram_used,
                "vram_free": device.vram_free,
                "status": device.status.value,
                "last_heartbeat": device.last_heartbeat.isoformat() if device.last_heartbeat else None,
                "created_at": device.created_at.isoformat()
            }
            for device in devices
        ]
    )


@router.delete("/devices/{device_id}", summary="删除设备")
async def delete_device(
    device_id: int,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    success = DeviceService.delete_device(db, device_id)
    
    if not success:
        return error_response(message="删除失败，设备可能有正在运行的任务或部署", code=400)
    
    return success_response(message="删除成功")


@router.post("/tasks/{task_id}/assign", summary="手动分配任务到设备")
async def assign_task_to_device(
    task_id: int,
    device_id: int,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    success = TrainingService.assign_task_to_device(db, task_id, device_id)
    
    if not success:
        return error_response(message="分配失败", code=400)
    
    return success_response(message="分配成功")


@router.post("/deployments/check-expired", summary="检查并处理过期部署")
async def check_expired_deployments(
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    expired = DeploymentService.check_expired_deployments(db)
    
    return success_response(
        message=f"处理了{len(expired)}个过期部署",
        data={"count": len(expired)}
    )


@router.post("/devices/check-offline", summary="检查并处理离线设备")
async def check_offline_devices(
    timeout_minutes: int = 5,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    offline_devices = DeviceService.check_offline_devices(db, timeout_minutes)
    
    return success_response(
        message=f"处理了{len(offline_devices)}个离线设备",
        data={"count": len(offline_devices)}
    )
