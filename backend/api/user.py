from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import datetime, timedelta

from tinlyllmWeb.backend.models.database import get_db, User, PointsLog, PointsLogType
from tinlyllmWeb.backend.services.user_service import UserService
from tinlyllmWeb.backend.utils.jwt import get_current_user, get_current_admin
from tinlyllmWeb.backend.utils.response import success_response, error_response
from tinlyllmWeb.backend.utils.auth import get_password_hash, verify_password
from tinlyllmWeb.backend.config import settings

router = APIRouter(prefix="/api/user", tags=["用户管理"])


class UserInfo(BaseModel):
    id: int
    username: str
    email: Optional[str]
    points: float
    role: str
    created_at: str


class UpdateUserInfo(BaseModel):
    username: Optional[str] = Field(None, min_length=3, max_length=50, description="用户名")
    password: Optional[str] = Field(None, min_length=6, max_length=50, description="密码")


class PointsLogInfo(BaseModel):
    id: int
    type: str
    amount: float
    description: Optional[str]
    created_at: str


@router.get("/info", summary="获取当前用户信息")
async def get_user_info(current_user: User = Depends(get_current_user)):
    return success_response(
        message="获取成功",
        data={
            "id": current_user.id,
            "username": current_user.username,
            "email": current_user.email,
            "points": current_user.points,
            "role": current_user.role,
            "created_at": current_user.created_at.isoformat()
        }
    )


@router.put("/info", summary="更新用户信息")
async def update_user_info(
    user_data: UpdateUserInfo,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.id == current_user.id).first()
    
    if not user:
        return error_response(message="用户不存在", code=404)
    
    if user_data.username:
        existing_user = db.query(User).filter(
            User.username == user_data.username,
            User.id != current_user.id
        ).first()
        if existing_user:
            return error_response(message="用户名已存在", code=400)
        user.username = user_data.username
    
    if user_data.password:
        user.password = get_password_hash(user_data.password)
    
    user.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(user)
    
    return success_response(
        message="更新成功",
        data={
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "points": user.points,
            "role": user.role
        }
    )


@router.post("/checkin", summary="签到")
async def checkin(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.id == current_user.id).first()
    
    if not user:
        return error_response(message="用户不存在", code=404)
    
    now = datetime.utcnow()
    
    if user.last_checkin_at:
        last_checkin_date = user.last_checkin_at.date()
        today = now.date()
        if last_checkin_date >= today:
            return error_response(message="今日已签到", code=400)
    
    user.last_checkin_at = now
    user.points += settings.CHECKIN_REWARD
    user.updated_at = now
    
    points_log = PointsLog(
        user_id=user.id,
        log_type=PointsLogType.CHECKIN,
        amount=settings.CHECKIN_REWARD,
        description="每日签到奖励"
    )
    db.add(points_log)
    
    db.commit()
    db.refresh(user)
    
    return success_response(
        message="签到成功",
        data={
            "points": user.points,
            "reward": settings.CHECKIN_REWARD
        }
    )


@router.get("/points/logs", summary="获取积分日志")
async def get_points_logs(
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    logs = UserService.get_points_logs(db, current_user.id, limit)
    
    return success_response(
        message="获取成功",
        data=[
            {
                "id": log.id,
                "type": log.type.value,
                "amount": log.amount,
                "description": log.description,
                "created_at": log.created_at.isoformat()
            }
            for log in logs
        ]
    )


@router.get("/all", summary="获取所有用户（管理员）")
async def get_all_users(
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    users = UserService.get_all_users(db, skip, limit)
    
    return success_response(
        message="获取成功",
        data=[
            {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "points": user.points,
                "role": user.role.value,
                "status": user.status.value,
                "created_at": user.created_at.isoformat()
            }
            for user in users
        ]
    )


@router.post("/{user_id}/ban", summary="封禁用户（管理员）")
async def ban_user(
    user_id: int,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    success = UserService.ban_user(db, user_id)
    
    if not success:
        return error_response(message="封禁失败", code=400)
    
    return success_response(message="封禁成功")


@router.post("/{user_id}/unban", summary="解封用户（管理员）")
async def unban_user(
    user_id: int,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    success = UserService.unban_user(db, user_id)
    
    if not success:
        return error_response(message="解封失败", code=400)
    
    return success_response(message="解封成功")
