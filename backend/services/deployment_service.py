from typing import List, Optional
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import random
import secrets
import string

from tinlyllmWeb.backend.models.database import Deployment, Model, Device, DeploymentStatus, DeviceStatus, ModelStatus, TrainingTask
from tinlyllmWeb.backend.config import settings


class DeploymentService:
    @staticmethod
    def _generate_api_key() -> str:
        alphabet = string.ascii_letters + string.digits
        return 'sk-' + ''.join(secrets.choice(alphabet) for _ in range(32))
    
    @staticmethod
    def create_deployment(db: Session, user_id: int, model_id: int, hours: int = 12, vram_required: int = 2048) -> Optional[Deployment]:
        model = db.query(Model).filter(Model.id == model_id).first()
        if not model or model.status != ModelStatus.TRAINED:
            return None
        
        existing = db.query(Deployment).filter(
            Deployment.model_id == model_id,
            Deployment.status == DeploymentStatus.ACTIVE
        ).first()
        
        if existing:
            return existing
        
        training_task = db.query(TrainingTask).filter(
            TrainingTask.model_id == model_id,
            TrainingTask.status == "completed"
        ).first()
        
        device = None
        if training_task and training_task.device_id:
            device = db.query(Device).filter(
                Device.id == training_task.device_id,
                Device.status == DeviceStatus.ONLINE
            ).first()
            if device:
                print(f"[Deployment] 使用训练时使用的设备: {device.device_name} (ID:{device.id})")
        
        if not device:
            device = DeploymentService._select_device(db, vram_required)
            if not device:
                return None
        
        port = DeploymentService._allocate_port(db)
        if not port:
            return None
        
        api_key = DeploymentService._generate_api_key()
        
        if device.mode == "frp" and device.frp_server:
            frp_port = 32000 + model_id
            api_url = f"http://{device.frp_server.split(':')[0]}:{frp_port}/v1"
        else:
            api_url = f"http://{device.ip}:{port}/v1"
        
        deployment = Deployment(
            user_id=user_id,
            model_id=model_id,
            device_id=device.id,
            port=port,
            vram_used=vram_required,
            api_key=api_key,
            api_url=api_url,
            status=DeploymentStatus.DEPLOYING,
            expires_at=datetime.utcnow() + timedelta(hours=hours)
        )
        
        device.vram_used = (device.vram_used or 0) + vram_required
        device.vram_free = (device.vram_total or 0) - device.vram_used
        device.updated_at = datetime.utcnow()
        
        db.add(deployment)
        db.commit()
        db.refresh(deployment)
        
        return deployment
    
    @staticmethod
    def _select_device(db: Session, vram_required: int) -> Optional[Device]:
        devices = db.query(Device).filter(
            Device.status == DeviceStatus.ONLINE
        ).all()
        
        if not devices:
            return None
        
        devices.sort(key=lambda d: d.vram_free, reverse=True)
        return devices[0]
    
    @staticmethod
    def _allocate_port(db: Session) -> Optional[int]:
        used_ports = db.query(Deployment.port).filter(
            Deployment.status == DeploymentStatus.ACTIVE
        ).all()
        
        used_port_set = {p[0] for p in used_ports}
        
        for port in range(settings.API_PORT_START, settings.API_PORT_END + 1):
            if port not in used_port_set:
                return port
        
        return None
    
    @staticmethod
    def get_deployment_by_id(db: Session, deployment_id: int) -> Optional[Deployment]:
        return db.query(Deployment).filter(Deployment.id == deployment_id).first()
    
    @staticmethod
    def get_user_deployments(db: Session, user_id: int, skip: int = 0, limit: int = 100) -> List[Deployment]:
        return db.query(Deployment).filter(
            Deployment.user_id == user_id
        ).order_by(Deployment.created_at.desc()).offset(skip).limit(limit).all()
    
    @staticmethod
    def get_all_deployments(db: Session, skip: int = 0, limit: int = 100) -> List[Deployment]:
        return db.query(Deployment).order_by(Deployment.created_at.desc()).offset(skip).limit(limit).all()
    
    @staticmethod
    def stop_deployment(db: Session, deployment_id: int, user_id: int) -> bool:
        deployment = db.query(Deployment).filter(
            Deployment.id == deployment_id,
            Deployment.user_id == user_id
        ).first()
        
        if not deployment:
            return False
        
        deployment.status = DeploymentStatus.STOPPED
        
        device = db.query(Device).filter(Device.id == deployment.device_id).first()
        if device:
            device.vram_used = max(0, (device.vram_used or 0) - deployment.vram_used)
            device.vram_free = (device.vram_total or 0) - device.vram_used
            device.updated_at = datetime.utcnow()
        
        db.commit()
        return True
    
    @staticmethod
    def mark_unavailable(db: Session, deployment_id: int) -> bool:
        deployment = db.query(Deployment).filter(Deployment.id == deployment_id).first()
        if not deployment:
            return False
        
        deployment.status = DeploymentStatus.UNAVAILABLE
        
        device = db.query(Device).filter(Device.id == deployment.device_id).first()
        if device:
            device.vram_used = max(0, (device.vram_used or 0) - deployment.vram_used)
            device.vram_free = (device.vram_total or 0) - device.vram_used
            device.status = DeviceStatus.OFFLINE
            device.updated_at = datetime.utcnow()
        
        db.commit()
        return True
    
    @staticmethod
    def update_last_used(db: Session, deployment_id: int) -> bool:
        deployment = db.query(Deployment).filter(Deployment.id == deployment_id).first()
        if not deployment:
            return False
        
        deployment.last_used_at = datetime.utcnow()
        db.commit()
        return True
    
    @staticmethod
    def extend_deployment(db: Session, deployment_id: int, hours: int) -> bool:
        deployment = db.query(Deployment).filter(Deployment.id == deployment_id).first()
        if not deployment:
            return False
        
        deployment.expires_at = deployment.expires_at + timedelta(hours=hours)
        db.commit()
        return True
    
    @staticmethod
    def check_expired_deployments(db: Session) -> List[Deployment]:
        now = datetime.utcnow()
        expired = db.query(Deployment).filter(
            Deployment.status == DeploymentStatus.ACTIVE,
            Deployment.expires_at <= now
        ).all()
        
        for deployment in expired:
            deployment.status = DeploymentStatus.STOPPED
            
            device = db.query(Device).filter(Device.id == deployment.device_id).first()
            if device:
                device.vram_used = max(0, (device.vram_used or 0) - deployment.vram_used)
                device.vram_free = (device.vram_total or 0) - device.vram_used
                device.updated_at = datetime.utcnow()
        
        db.commit()
        return expired
