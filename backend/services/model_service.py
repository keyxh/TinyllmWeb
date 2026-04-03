from typing import List, Optional
from sqlalchemy.orm import Session
from datetime import datetime

from tinlyllmWeb.backend.models.database import Model, ModelStatus, Deployment, DeploymentStatus


class ModelService:
    @staticmethod
    def get_model_by_id(db: Session, model_id: int) -> Optional[Model]:
        return db.query(Model).filter(Model.id == model_id).first()
    
    @staticmethod
    def get_user_models(db: Session, user_id: int, skip: int = 0, limit: int = 100) -> List[Model]:
        return db.query(Model).filter(
            Model.user_id == user_id,
            Model.status != ModelStatus.DELETED
        ).order_by(Model.created_at.desc()).offset(skip).limit(limit).all()
    
    @staticmethod
    def get_all_models(db: Session, skip: int = 0, limit: int = 100) -> List[Model]:
        return db.query(Model).filter(
            Model.status != ModelStatus.DELETED
        ).order_by(Model.created_at.desc()).offset(skip).limit(limit).all()
    
    @staticmethod
    def get_active_models(db: Session) -> List[Model]:
        return db.query(Model).filter(
            Model.status == ModelStatus.TRAINED
        ).all()
    
    @staticmethod
    def delete_model(db: Session, model_id: int, user_id: int) -> bool:
        model = db.query(Model).filter(
            Model.id == model_id,
            Model.user_id == user_id
        ).first()
        
        if not model:
            return False
        
        active_deployments = db.query(Deployment).filter(
            Deployment.model_id == model_id,
            Deployment.status == DeploymentStatus.ACTIVE
        ).first()
        
        if active_deployments:
            return False
        
        model.status = ModelStatus.DELETED
        model.updated_at = datetime.utcnow()
        db.commit()
        return True
    
    @staticmethod
    def get_model_by_name(db: Session, user_id: int, model_name: str) -> Optional[Model]:
        return db.query(Model).filter(
            Model.user_id == user_id,
            Model.model_name == model_name,
            Model.status != ModelStatus.DELETED
        ).first()
