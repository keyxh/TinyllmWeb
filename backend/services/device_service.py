from typing import List, Optional
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import secrets

from tinlyllmWeb.backend.models.database import Device, DeviceStatus, TrainingTask, Deployment, DeploymentStatus


class DeviceService:
    @staticmethod
    def generate_device_key() -> str:
        return secrets.token_urlsafe(32)
    
    @staticmethod
    def register_device(
        db: Session,
        device_name: str,
        ip: str,
        port: int,
        gpu_info: str,
        vram_total: int,
        mode: str = "normal",
        frp_server: str = None
    ) -> Optional[Device]:
        device_key = DeviceService.generate_device_key()
        
        device = Device(
            device_name=device_name,
            device_key=device_key,
            ip=ip,
            port=port,
            gpu_info=gpu_info,
            vram_total=vram_total,
            vram_used=0,
            vram_free=vram_total,
            status=DeviceStatus.ONLINE,
            mode=mode,
            frp_server=frp_server,
            last_heartbeat=datetime.utcnow()
        )
        db.add(device)
        db.commit()
        db.refresh(device)
        return device
    
    @staticmethod
    def update_device_info(
        db: Session,
        device_id: int,
        device_name: str = None,
        ip: str = None,
        port: int = None,
        gpu_info: str = None,
        vram_total: int = None,
        mode: str = None,
        frp_server: str = None
    ) -> bool:
        device = db.query(Device).filter(Device.id == device_id).first()
        if not device:
            return False
        
        if device_name is not None:
            device.device_name = device_name
        if ip is not None:
            device.ip = ip
        if port is not None:
            device.port = port
        if gpu_info is not None:
            device.gpu_info = gpu_info
        if vram_total is not None:
            device.vram_total = vram_total
        if mode is not None:
            device.mode = mode
        if frp_server is not None:
            device.frp_server = frp_server
        
        device.updated_at = datetime.utcnow()
        db.commit()
        return True
    
    @staticmethod
    def get_device_by_key(db: Session, device_key: str) -> Optional[Device]:
        return db.query(Device).filter(Device.device_key == device_key).first()
    
    @staticmethod
    def get_device_by_id(db: Session, device_id: int) -> Optional[Device]:
        return db.query(Device).filter(Device.id == device_id).first()
    
    @staticmethod
    def update_heartbeat(db: Session, device_id: int, vram_used: int, vram_free: int) -> bool:
        device = db.query(Device).filter(Device.id == device_id).first()
        if not device:
            return False
        
        device.vram_used = vram_used
        device.vram_free = vram_free
        device.last_heartbeat = datetime.utcnow()
        device.updated_at = datetime.utcnow()
        
        if device.status == DeviceStatus.OFFLINE:
            device.status = DeviceStatus.ONLINE
        
        db.commit()
        return True
    
    @staticmethod
    def get_all_devices(db: Session, skip: int = 0, limit: int = 100) -> List[Device]:
        return db.query(Device).order_by(Device.created_at.desc()).offset(skip).limit(limit).all()
    
    @staticmethod
    def get_online_devices(db: Session) -> List[Device]:
        return db.query(Device).filter(
            Device.status == DeviceStatus.ONLINE
        ).all()
    
    @staticmethod
    def check_offline_devices(db: Session, timeout_minutes: int = 5) -> List[Device]:
        timeout = datetime.utcnow() - timedelta(minutes=timeout_minutes)
        offline_devices = db.query(Device).filter(
            Device.last_heartbeat < timeout,
            Device.status != DeviceStatus.OFFLINE
        ).all()
        
        for device in offline_devices:
            device.status = DeviceStatus.OFFLINE
            device.updated_at = datetime.utcnow()
            
            running_tasks = db.query(TrainingTask).filter(
                TrainingTask.device_id == device.id,
                TrainingTask.status == "running"
            ).all()
            
            for task in running_tasks:
                task.status = "pending"
                task.device_id = None
            
            active_deployments = db.query(Deployment).filter(
                Deployment.device_id == device.id,
                Deployment.status == DeploymentStatus.ACTIVE
            ).all()
            
            for deployment in active_deployments:
                deployment.status = DeploymentStatus.UNAVAILABLE
        
        db.commit()
        return offline_devices
    
    @staticmethod
    def delete_device(db: Session, device_id: int) -> bool:
        device = db.query(Device).filter(Device.id == device_id).first()
        if not device:
            return False
        
        has_running_tasks = db.query(TrainingTask).filter(
            TrainingTask.device_id == device_id,
            TrainingTask.status == "running"
        ).first()
        
        if has_running_tasks:
            return False
        
        has_active_deployments = db.query(Deployment).filter(
            Deployment.device_id == device_id,
            Deployment.status == DeploymentStatus.ACTIVE
        ).first()
        
        if has_active_deployments:
            return False
        
        db.delete(device)
        db.commit()
        return True
