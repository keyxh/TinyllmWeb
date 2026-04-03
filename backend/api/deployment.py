from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List
import asyncio
from datetime import datetime
import math

from tinlyllmWeb.backend.models.database import get_db, User, Deployment, TrainingTask
from tinlyllmWeb.backend.services.deployment_service import DeploymentService
from tinlyllmWeb.backend.services.model_service import ModelService
from tinlyllmWeb.backend.services.user_service import UserService
from tinlyllmWeb.backend.services.model_config_service import model_config_service
from tinlyllmWeb.backend.utils.jwt import get_current_user, get_current_admin
from tinlyllmWeb.backend.utils.response import success_response, error_response
from tinlyllmWeb.backend.models.database import PointsLogType
from tinlyllmWeb.backend.config import settings
from tinlyllmWeb.backend.api.device import manager

router = APIRouter(prefix="/api/deployments", tags=["部署管理"])


class DeploymentInfo(BaseModel):
    id: int
    model_id: int
    model_name: str
    base_model: str
    device_id: int
    port: int
    status: str
    api_url: str
    created_at: str
    expires_at: str
    last_used_at: str


@router.post("/create", summary="部署模型")
async def create_deployment(
    model_id: int,
    hours: int = 24,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    print(f"[DEBUG] 创建部署，model_id: {model_id}, hours: {hours}")
    
    if hours < 24:
        return error_response(message="最低部署24小时", code=400)
    
    if hours > 720:
        return error_response(message="最长部署720小时（30天）", code=400)
    
    model = ModelService.get_model_by_id(db, model_id)
    
    if not model or model.user_id != current_user.id:
        return error_response(message="模型不存在", code=404)
    
    if model.status != "trained":
        return error_response(message="模型未训练完成", code=400)
    
    model_config = model_config_service.get_model_by_name(model.base_model)
    if not model_config:
        return error_response(message="模型配置不存在", code=400)
    
    deploy_config = model_config.get("deploy_cost", {})
    base_points_per_day = deploy_config.get("base_points_per_day", 1)
    base_data_threshold = deploy_config.get("base_data_threshold", 1000)
    additional_points_per_5000 = deploy_config.get("additional_points_per_5000", 1)
    
    training_task = db.query(TrainingTask).filter(TrainingTask.model_id == model.id).first()
    dataset_sample_count = 0
    if training_task and training_task.dataset:
        dataset_sample_count = training_task.dataset.sample_count or 0
    
    import math
    if dataset_sample_count <= base_data_threshold:
        deploy_cost_per_day = base_points_per_day
    else:
        extra_data = dataset_sample_count - base_data_threshold
        extra_points = math.ceil(extra_data / 5000) * additional_points_per_5000
        deploy_cost_per_day = base_points_per_day + extra_points
    
    deploy_cost = math.ceil(deploy_cost_per_day * (hours / 24))
    min_hours = 24
    
    print(f"[DEBUG] 部署费用计算: deploy_cost_per_day={deploy_cost_per_day}, hours={hours}, total_cost={deploy_cost}")
    
    if current_user.points < deploy_cost:
        return error_response(message=f"积分不足，需要{deploy_cost}积分（{hours}小时）", code=400)
    
    success = UserService.deduct_points(
        db=db,
        user_id=current_user.id,
        amount=deploy_cost,
        log_type=PointsLogType.DEPLOY,
        description=f"部署模型：{model.model_name}（{deploy_cost}积分/天）"
    )
    
    if not success:
        return error_response(message="扣除积分失败", code=400)
    
    deployment = DeploymentService.create_deployment(db, current_user.id, model_id, min_hours, 0)
    
    if not deployment:
        UserService.add_points(
            db=db,
            user_id=current_user.id,
            amount=deploy_cost,
            log_type=PointsLogType.REFUND,
            description="部署失败退款"
        )
        return error_response(message="没有可用的设备", code=400)
    
    device = deployment.device
    
    if device:
        deployment_data = {
            "type": "command",
            "command": "start_deployment",
            "deployment_data": {
                "deployment_id": deployment.id,
                "model_id": deployment.model_id,
                "model_name": model.model_name,
                "base_model": model.base_model,
                "lora_path": model.lora_path,
                "port": deployment.port
            }
        }
        print(f"[Deployment] 向设备 {device.device_name} (ID:{device.id}) 推送部署任务")
        await manager.send_message(device.device_key, deployment_data)
    
    if device and device.mode == "frp" and device.frp_server:
        frp_port = 32000 + deployment.id
        api_url = f"http://{device.frp_server.split(':')[0]}:{frp_port}/v1"
    else:
        api_url = f"http://{deployment.device.ip if deployment.device else '127.0.0.1'}:{deployment.port}/v1"
    
    return success_response(
        message="部署任务已创建",
        data={
            "deployment_id": deployment.id,
            "model_id": deployment.model_id,
            "port": deployment.port,
            "api_key": deployment.api_key,
            "api_url": api_url,
            "cost": deploy_cost,
            "status": deployment.status.value,
            "expires_at": deployment.expires_at.isoformat()
        }
    )


@router.get("/calculate", summary="计算部署费用")
async def calculate_deployment_cost(
    model_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    print(f"[DEBUG] 计算部署费用，model_id: {model_id}, user_id: {current_user.id}")
    
    model = ModelService.get_model_by_id(db, model_id)
    
    if not model:
        print(f"[DEBUG] 模型不存在，model_id: {model_id}")
        return error_response(message="模型不存在", code=404)
    
    if model.user_id != current_user.id:
        print(f"[DEBUG] 模型不属于当前用户，model.user_id: {model.user_id}, current_user.id: {current_user.id}")
        return error_response(message="模型不存在", code=404)
    
    model_config = model_config_service.get_model_by_name(model.base_model)
    if not model_config:
        print(f"[DEBUG] 模型配置不存在，base_model: {model.base_model}")
        return error_response(message="模型配置不存在", code=400)
    
    deploy_config = model_config.get("deploy_cost", {})
    base_points_per_day = deploy_config.get("base_points_per_day", 1)
    base_data_threshold = deploy_config.get("base_data_threshold", 1000)
    additional_points_per_5000 = deploy_config.get("additional_points_per_5000", 1)
    
    print(f"[DEBUG] 部署配置: base_points_per_day={base_points_per_day}, base_data_threshold={base_data_threshold}, additional_points_per_5000={additional_points_per_5000}")
    
    training_task = db.query(TrainingTask).filter(TrainingTask.model_id == model.id).first()
    dataset_sample_count = 0
    
    if training_task:
        print(f"[DEBUG] 找到训练任务，task_id: {training_task.id}")
        if training_task.dataset:
            dataset_sample_count = training_task.dataset.sample_count or 0
            print(f"[DEBUG] 数据集样本数: {dataset_sample_count}")
        else:
            print(f"[DEBUG] 训练任务没有关联数据集")
    else:
        print(f"[DEBUG] 没有找到训练任务")
    
    import math
    if dataset_sample_count <= base_data_threshold:
        deploy_cost_per_day = base_points_per_day
    else:
        extra_data = dataset_sample_count - base_data_threshold
        extra_points = math.ceil(extra_data / 5000) * additional_points_per_5000
        deploy_cost_per_day = base_points_per_day + extra_points
    
    print(f"[DEBUG] 计算结果: deploy_cost_per_day={deploy_cost_per_day}")
    
    return success_response(
        message="计算成功",
        data={
            "cost": deploy_cost_per_day,
            "dataset_sample_count": dataset_sample_count
        }
    )


@router.get("/", summary="获取用户部署列表")
async def get_deployments(
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    from tinlyllmWeb.backend.models.database import DeploymentStatus
    from datetime import timedelta
    
    deployments = DeploymentService.get_user_deployments(db, current_user.id, skip, limit)
    
    result = []
    for deployment in deployments:
        model = deployment.model
        device = deployment.device
        
        if deployment.status == DeploymentStatus.DEPLOYING:
            timeout_minutes = 5
            if deployment.created_at < datetime.utcnow() - timedelta(minutes=timeout_minutes):
                print(f"[Deployment] 部署 {deployment.id} 超时，标记为FAILED并退款")
                
                deployment.status = DeploymentStatus.FAILED
                
                if device:
                    device.vram_used = max(0, (device.vram_used or 0) - deployment.vram_used)
                    device.vram_free = (device.vram_total or 0) - device.vram_used
                    device.updated_at = datetime.utcnow()
                
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
        
        if deployment.status == DeploymentStatus.ACTIVE:
            if device and device.mode == "frp" and device.frp_server:
                frp_port = 32000 + deployment.id
                api_url = f"http://{device.frp_server.split(':')[0]}:{frp_port}/v1"
            else:
                api_url = f"http://{device.ip if device else '127.0.0.1'}:{deployment.port}/v1"
        else:
            api_url = ""
        result.append({
            "id": deployment.id,
            "model_id": deployment.model_id,
            "model_name": model.model_name if model else "",
            "base_model": model.base_model if model else "",
            "device_id": deployment.device_id,
            "device_name": device.device_name if device else "",
            "port": deployment.port,
            "api_key": deployment.api_key,
            "api_url": api_url,
            "status": deployment.status.value,
            "created_at": deployment.created_at.isoformat(),
            "expires_at": deployment.expires_at.isoformat(),
            "last_used_at": deployment.last_used_at.isoformat() if deployment.last_used_at else None
        })
    
    return success_response(message="获取成功", data=result)


@router.get("/{deployment_id}", summary="获取部署详情")
async def get_deployment(
    deployment_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    deployment = DeploymentService.get_deployment_by_id(db, deployment_id)
    
    if not deployment or deployment.user_id != current_user.id:
        return error_response(message="部署不存在", code=404)
    
    model = deployment.model
    device = deployment.device
    
    return success_response(
        message="获取成功",
        data={
            "id": deployment.id,
            "model_id": deployment.model_id,
            "model_name": model.model_name if model else "",
            "base_model": model.base_model if model else "",
            "device_id": deployment.device_id,
            "device_name": device.device_name if device else "",
            "port": deployment.port,
            "status": deployment.status.value,
            "created_at": deployment.created_at.isoformat(),
            "expires_at": deployment.expires_at.isoformat(),
            "last_used_at": deployment.last_used_at.isoformat() if deployment.last_used_at else None
        }
    )


@router.post("/{deployment_id}/stop", summary="停止部署")
async def stop_deployment(
    deployment_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    deployment = db.query(Deployment).filter(Deployment.id == deployment_id).first()
    
    if not deployment or deployment.user_id != current_user.id:
        return error_response(message="部署不存在", code=404)
    
    device = deployment.device
    
    success = DeploymentService.stop_deployment(db, deployment_id, current_user.id)
    
    if not success:
        return error_response(message="停止失败", code=400)
    
    if device:
        stop_data = {
            "type": "command",
            "command": "stop_deployment",
            "deployment_id": deployment_id
        }
        print(f"[Deployment] 向设备 {device.device_name} (ID:{device.id}) 发送停止部署命令")
        await manager.send_message(device.device_key, stop_data)
    
    return success_response(message="停止成功")


@router.post("/{deployment_id}/extend", summary="续期部署")
async def extend_deployment(
    deployment_id: int,
    hours: int = Query(24, description="续期时长（小时）", ge=24, le=720),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    print(f"[DEBUG] 续期部署，deployment_id: {deployment_id}, hours: {hours}")
    
    deployment = db.query(Deployment).filter(Deployment.id == deployment_id).first()
    
    if not deployment or deployment.user_id != current_user.id:
        return error_response(message="部署不存在", code=404)
    
    from tinlyllmWeb.backend.models.database import DeploymentStatus
    if deployment.status != DeploymentStatus.ACTIVE:
        return error_response(message="只有活跃的部署才能续期", code=400)
    
    model = deployment.model
    if not model:
        return error_response(message="模型不存在", code=404)
    
    model_config = model_config_service.get_model_by_name(model.base_model)
    if not model_config:
        return error_response(message="模型配置不存在", code=400)
    
    deploy_config = model_config.get("deploy_cost", {})
    base_points_per_day = deploy_config.get("base_points_per_day", 1)
    base_data_threshold = deploy_config.get("base_data_threshold", 1000)
    additional_points_per_5000 = deploy_config.get("additional_points_per_5000", 1)
    
    training_task = db.query(TrainingTask).filter(TrainingTask.model_id == model.id).first()
    dataset_sample_count = 0
    if training_task and training_task.dataset:
        dataset_sample_count = training_task.dataset.sample_count or 0
    
    import math
    if dataset_sample_count <= base_data_threshold:
        deploy_cost_per_day = base_points_per_day
    else:
        extra_data = dataset_sample_count - base_data_threshold
        extra_points = math.ceil(extra_data / 5000) * additional_points_per_5000
        deploy_cost_per_day = base_points_per_day + extra_points
    
    extend_cost = math.ceil(deploy_cost_per_day * (hours / 24))
    
    print(f"[DEBUG] 续期费用计算: deploy_cost_per_day={deploy_cost_per_day}, hours={hours}, extend_cost={extend_cost}")
    
    if current_user.points < extend_cost:
        return error_response(message=f"积分不足，需要{extend_cost}积分（{hours}小时）", code=400)
    
    success = UserService.deduct_points(
        db=db,
        user_id=current_user.id,
        amount=extend_cost,
        log_type=PointsLogType.DEPLOY,
        description=f"部署续期：{model.model_name}（+{hours}小时，{extend_cost}积分）"
    )
    
    if not success:
        return error_response(message="扣除积分失败", code=400)
    
    success = DeploymentService.extend_deployment(db, deployment_id, hours)
    
    if not success:
        UserService.add_points(
            db=db,
            user_id=current_user.id,
            amount=extend_cost,
            log_type=PointsLogType.REFUND,
            description="续期失败退款"
        )
        return error_response(message="续期失败", code=400)
    
    db.refresh(deployment)
    
    return success_response(
        message="续期成功",
        data={
            "deployment_id": deployment_id,
            "hours_added": hours,
            "cost": extend_cost,
            "new_expires_at": deployment.expires_at.isoformat()
        }
    )


@router.get("/all", summary="获取所有部署（管理员）")
async def get_all_deployments(
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    deployments = DeploymentService.get_all_deployments(db, skip, limit)
    
    result = []
    for deployment in deployments:
        model = deployment.model
        device = deployment.device
        user = deployment.user
        result.append({
            "id": deployment.id,
            "user_id": deployment.user_id,
            "username": user.username if user else "",
            "model_id": deployment.model_id,
            "model_name": model.model_name if model else "",
            "base_model": model.base_model if model else "",
            "device_id": deployment.device_id,
            "device_name": device.device_name if device else "",
            "port": deployment.port,
            "status": deployment.status.value,
            "created_at": deployment.created_at.isoformat(),
            "expires_at": deployment.expires_at.isoformat(),
            "last_used_at": deployment.last_used_at.isoformat() if deployment.last_used_at else None
        })
    
    return success_response(message="获取成功", data=result)
