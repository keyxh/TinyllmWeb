from typing import List, Optional
from sqlalchemy.orm import Session
from datetime import datetime
import json

from tinlyllmWeb.backend.models.database import (
    TrainingTask, Model, Dataset, Device, ModelStatus, TaskStatus, DeviceStatus, PointsLogType
)
from tinlyllmWeb.backend.services.user_service import UserService
from tinlyllmWeb.backend.services.model_config_service import model_config_service
from tinlyllmWeb.backend.config import settings


class TrainingService:
    @staticmethod
    def create_training_task(
        db: Session,
        user_id: int,
        dataset_id: int,
        model_name: str,
        base_model: str,
        training_params: dict
    ) -> Optional[TrainingTask]:
        model = Model(
            user_id=user_id,
            model_name=model_name,
            base_model=base_model,
            status=ModelStatus.TRAINING,
            training_params=json.dumps(training_params)
        )
        db.add(model)
        db.commit()
        db.refresh(model)
        
        task = TrainingTask(
            user_id=user_id,
            model_id=model.id,
            dataset_id=dataset_id,
            status=TaskStatus.PENDING
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        
        return task
    
    @staticmethod
    def get_training_task_by_id(db: Session, task_id: int) -> Optional[TrainingTask]:
        return db.query(TrainingTask).filter(TrainingTask.id == task_id).first()
    
    @staticmethod
    def get_user_training_tasks(db: Session, user_id: int, skip: int = 0, limit: int = 100) -> List[TrainingTask]:
        return db.query(TrainingTask).filter(
            TrainingTask.user_id == user_id,
            TrainingTask.status != TaskStatus.CANCELLED
        ).order_by(TrainingTask.created_at.desc()).offset(skip).limit(limit).all()
    
    @staticmethod
    def get_pending_tasks(db: Session) -> List[TrainingTask]:
        return db.query(TrainingTask).filter(
            TrainingTask.status == TaskStatus.PENDING
        ).order_by(TrainingTask.created_at.asc()).all()
    
    @staticmethod
    def assign_task_to_device(db: Session, task_id: int, device_id: int) -> bool:
        task = db.query(TrainingTask).filter(TrainingTask.id == task_id).first()
        if not task:
            return False
        
        device = db.query(Device).filter(Device.id == device_id).first()
        if not device or device.status != DeviceStatus.ONLINE:
            return False
        
        task.device_id = device_id
        task.status = TaskStatus.RUNNING
        task.started_at = datetime.utcnow()
        
        device.status = DeviceStatus.BUSY
        device.updated_at = datetime.utcnow()
        
        db.commit()
        return True
    
    @staticmethod
    def delete_task(db: Session, task_id: int, user_id: int) -> bool:
        task = db.query(TrainingTask).filter(
            TrainingTask.id == task_id,
            TrainingTask.user_id == user_id
        ).first()
        
        if not task:
            return False
        
        if task.status in [TaskStatus.PENDING, TaskStatus.RUNNING]:
            return False
        
        model = db.query(Model).filter(Model.id == task.model_id).first()
        if model:
            model.status = ModelStatus.DELETED
            model.updated_at = datetime.utcnow()
        
        task.status = TaskStatus.CANCELLED
        task.completed_at = datetime.utcnow()
        
        db.commit()
        return True
    
    @staticmethod
    def update_task_progress(db: Session, task_id: int, progress: float, log: Optional[str] = None) -> bool:
        task = db.query(TrainingTask).filter(TrainingTask.id == task_id).first()
        if not task:
            return False
        
        task.progress = progress
        if log:
            if task.logs:
                task.logs += "\n" + log
            else:
                task.logs = log
        db.commit()
        return True
    
    @staticmethod
    def complete_task(db: Session, task_id: int, lora_path: str) -> bool:
        task = db.query(TrainingTask).filter(TrainingTask.id == task_id).first()
        if not task:
            return False
        
        task.status = TaskStatus.COMPLETED
        task.completed_at = datetime.utcnow()
        
        model = db.query(Model).filter(Model.id == task.model_id).first()
        if model:
            model.status = ModelStatus.TRAINED
            model.device_id = task.device_id
            model.lora_path = lora_path
            model.updated_at = datetime.utcnow()
        
        device = db.query(Device).filter(Device.id == task.device_id).first()
        if device:
            device.status = DeviceStatus.ONLINE
            device.updated_at = datetime.utcnow()
        
        db.commit()
        return True
    
    @staticmethod
    def fail_task(db: Session, task_id: int, error_message: str) -> bool:
        task = db.query(TrainingTask).filter(TrainingTask.id == task_id).first()
        if not task:
            return False
        
        task.status = TaskStatus.FAILED
        task.error_message = error_message
        task.completed_at = datetime.utcnow()
        
        model = db.query(Model).filter(Model.id == task.model_id).first()
        if model:
            model.status = ModelStatus.FAILED
            model.updated_at = datetime.utcnow()
            
            model_config = model_config_service.get_model_by_name(model.base_model)
            if model_config:
                training_cost = model_config.get("training_cost", {}).get("min", 30.0)
                UserService.add_points(
                    db=db,
                    user_id=task.user_id,
                    amount=training_cost,
                    log_type=PointsLogType.REFUND,
                    description=f"训练失败退款：{model.model_name}"
                )
        
        device = db.query(Device).filter(Device.id == task.device_id).first()
        if device:
            device.status = DeviceStatus.ONLINE
            device.updated_at = datetime.utcnow()
        
        db.commit()
        return True
    
    @staticmethod
    def cancel_task(db: Session, task_id: int, user_id: int) -> bool:
        task = db.query(TrainingTask).filter(
            TrainingTask.id == task_id,
            TrainingTask.user_id == user_id
        ).first()
        
        if not task:
            return False
        
        if task.status not in [TaskStatus.PENDING, TaskStatus.RUNNING]:
            return False
        
        task.status = TaskStatus.CANCELLED
        task.completed_at = datetime.utcnow()
        
        model = db.query(Model).filter(Model.id == task.model_id).first()
        if model:
            model.status = ModelStatus.FAILED
            model.updated_at = datetime.utcnow()
        
        device = db.query(Device).filter(Device.id == task.device_id).first()
        if device:
            device.status = DeviceStatus.ONLINE
            device.updated_at = datetime.utcnow()
        
        db.commit()
        return True
    
    @staticmethod
    def get_all_training_tasks(db: Session, skip: int = 0, limit: int = 100) -> List[TrainingTask]:
        return db.query(TrainingTask).order_by(TrainingTask.created_at.desc()).offset(skip).limit(limit).all()
    
    @staticmethod
    def restart_task(db: Session, task_id: int, user_id: int) -> bool:
        task = db.query(TrainingTask).filter(
            TrainingTask.id == task_id,
            TrainingTask.user_id == user_id
        ).first()
        
        if not task:
            return False
        
        if task.status not in [TaskStatus.FAILED, TaskStatus.CANCELLED]:
            return False
        
        task.status = TaskStatus.PENDING
        task.progress = 0.0
        task.error_message = None
        task.started_at = None
        task.completed_at = None
        
        model = db.query(Model).filter(Model.id == task.model_id).first()
        if model:
            model.status = ModelStatus.TRAINING
            model.updated_at = datetime.utcnow()
        
        db.commit()
        return True
