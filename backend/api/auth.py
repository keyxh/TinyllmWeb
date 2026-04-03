from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr, Field
from typing import Optional

from tinlyllmWeb.backend.models.database import get_db, User
from tinlyllmWeb.backend.services.user_service import UserService
from tinlyllmWeb.backend.services.email_service import email_service
from tinlyllmWeb.backend.utils.jwt import create_access_token
from tinlyllmWeb.backend.utils.response import success_response, error_response

router = APIRouter(prefix="/api/auth", tags=["认证"])


class SendVerificationCodeRequest(BaseModel):
    email: EmailStr = Field(..., description="邮箱")


class VerifyCodeLoginRequest(BaseModel):
    email: EmailStr = Field(..., description="邮箱")
    code: str = Field(..., min_length=6, max_length=6, description="验证码")


class EmailPasswordLoginRequest(BaseModel):
    email: EmailStr = Field(..., description="邮箱")
    password: str = Field(..., min_length=6, max_length=50, description="密码")


class UpdateProfileRequest(BaseModel):
    username: Optional[str] = Field(None, min_length=3, max_length=50, description="用户名")
    password: Optional[str] = Field(None, min_length=6, max_length=50, description="密码")


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    user: dict


@router.post("/send-verification-code", summary="发送验证码")
async def send_verification_code(request: SendVerificationCodeRequest, db: Session = Depends(get_db)):
    code = email_service.generate_verification_code()
    expires_at = email_service.get_verification_code_expires_at()
    
    email_service.save_verification_code(request.email, code, expires_at)
    
    success = email_service.send_verification_code(request.email, code)
    
    if not success:
        return error_response(message="发送验证码失败，请稍后重试", code=500)
    
    return success_response(message="验证码已发送")


@router.post("/verify-code-login", summary="验证码登录")
async def login_with_code(request: VerifyCodeLoginRequest, db: Session = Depends(get_db)):
    if not email_service.get_and_verify_code(request.email, request.code):
        return error_response(message="验证码错误或已过期", code=400)
    
    user = db.query(User).filter(User.email == request.email).first()
    
    if not user:
        import secrets
        import string
        from tinlyllmWeb.backend.utils.auth import get_password_hash
        
        random_password = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(12))
        user = User(
            username=request.email.split('@')[0],
            password=get_password_hash(random_password),
            email=request.email,
            points=10.0
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    
    access_token = create_access_token(data={"sub": user.username})
    
    return success_response(
        message="登录成功",
        data={
            "access_token": access_token,
            "token_type": "bearer",
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "points": user.points,
                "role": user.role
            }
        }
    )


@router.post("/login", summary="邮箱密码登录")
async def login(request: EmailPasswordLoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == request.email).first()
    
    if not user:
        return error_response(message="邮箱或密码错误", code=401)
    
    from tinlyllmWeb.backend.utils.auth import verify_password
    if not verify_password(request.password, user.password):
        return error_response(message="邮箱或密码错误", code=401)
    
    access_token = create_access_token(data={"sub": user.username})
    
    return success_response(
        message="登录成功",
        data={
            "access_token": access_token,
            "token_type": "bearer",
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "points": user.points,
                "role": user.role
            }
        }
    )


@router.post("/login/password", summary="邮箱密码登录")
async def login_with_password(request: EmailPasswordLoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == request.email).first()
    
    if not user:
        return error_response(message="邮箱或密码错误", code=401)
    
    from tinlyllmWeb.backend.utils.auth import verify_password
    if not verify_password(request.password, user.password):
        return error_response(message="邮箱或密码错误", code=401)
    
    access_token = create_access_token(data={"sub": user.username})
    
    return success_response(
        message="登录成功",
        data={
            "access_token": access_token,
            "token_type": "bearer",
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "points": user.points,
                "role": user.role
            }
        }
    )


@router.post("/token", summary="获取Token（OAuth2）")
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.email == form_data.username).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="邮箱或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    from tinlyllmWeb.backend.utils.auth import verify_password
    if not verify_password(form_data.password, user.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="邮箱或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token = create_access_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}
