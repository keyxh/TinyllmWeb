from typing import List, Optional
from sqlalchemy.orm import Session
from datetime import datetime, timedelta

from tinlyllmWeb.backend.models.database import User, UserRole, UserStatus, PointsLog, PointsLogType
from tinlyllmWeb.backend.utils.auth import get_password_hash, verify_password
from tinlyllmWeb.backend.config import settings


class UserService:
    @staticmethod
    def create_user(db: Session, username: str, password: str, email: Optional[str] = None) -> User:
        user = User(
            username=username,
            password=get_password_hash(password),
            email=email,
            role=UserRole.USER,
            status=UserStatus.ACTIVE,
            points=settings.INITIAL_POINTS
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        
        points_log = PointsLog(
            user_id=user.id,
            log_type=PointsLogType.INITIAL,
            amount=settings.INITIAL_POINTS,
            description="注册赠送积分"
        )
        db.add(points_log)
        db.commit()
        
        return user
    
    @staticmethod
    def authenticate_user(db: Session, username: str, password: str) -> Optional[User]:
        user = db.query(User).filter(User.username == username).first()
        if not user:
            return None
        if not verify_password(password, user.password):
            return None
        if user.status != UserStatus.ACTIVE:
            return None
        return user
    
    @staticmethod
    def get_user_by_id(db: Session, user_id: int) -> Optional[User]:
        return db.query(User).filter(User.id == user_id).first()
    
    @staticmethod
    def get_user_by_username(db: Session, username: str) -> Optional[User]:
        return db.query(User).filter(User.username == username).first()
    
    @staticmethod
    def update_user_info(db: Session, user_id: int, email: Optional[str] = None) -> Optional[User]:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return None
        
        if email is not None:
            user.email = email
        
        user.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(user)
        return user
    
    @staticmethod
    def deduct_points(db: Session, user_id: int, amount: int, log_type: PointsLogType, description: str) -> bool:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return False
        
        if user.points < amount:
            return False
        
        user.points -= amount
        user.updated_at = datetime.utcnow()
        
        points_log = PointsLog(
            user_id=user_id,
            log_type=log_type,
            amount=-amount,
            description=description
        )
        db.add(points_log)
        db.commit()
        
        return True
    
    @staticmethod
    def add_points(db: Session, user_id: int, amount: int, log_type: PointsLogType, description: str) -> bool:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return False
        
        user.points += amount
        user.updated_at = datetime.utcnow()
        
        points_log = PointsLog(
            user_id=user_id,
            log_type=log_type,
            amount=amount,
            description=description
        )
        db.add(points_log)
        db.commit()
        
        return True
    
    @staticmethod
    def get_points_logs(db: Session, user_id: int, limit: int = 50) -> List[PointsLog]:
        return db.query(PointsLog).filter(
            PointsLog.user_id == user_id
        ).order_by(PointsLog.created_at.desc()).limit(limit).all()
    
    @staticmethod
    def get_all_users(db: Session, skip: int = 0, limit: int = 100) -> List[User]:
        return db.query(User).offset(skip).limit(limit).all()
    
    @staticmethod
    def ban_user(db: Session, user_id: int) -> bool:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return False
        
        user.status = UserStatus.BANNED
        user.updated_at = datetime.utcnow()
        db.commit()
        return True
    
    @staticmethod
    def unban_user(db: Session, user_id: int) -> bool:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return False
        
        user.status = UserStatus.ACTIVE
        user.updated_at = datetime.utcnow()
        db.commit()
        return True
