from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
import os
import aiofiles
import uuid
import json

from tinlyllmWeb.backend.models.database import get_db, User, CommunityPost, CommunityPostStatus
from tinlyllmWeb.backend.utils.jwt import get_current_user, get_current_admin
from tinlyllmWeb.backend.utils.response import success_response, error_response

router = APIRouter(prefix="/api/community", tags=["社区"])

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "tinlyllmWeb", "frontend", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}


def allowed_file(filename: str) -> bool:
    ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    return ext in ALLOWED_EXTENSIONS


@router.post("/upload/image", summary="上传图片")
async def upload_image(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    if not file.filename:
        return error_response(message="请选择图片文件", code=400)
    
    if not allowed_file(file.filename):
        return error_response(message="不支持的图片格式，支持：png、jpg、jpeg、gif、webp", code=400)
    
    try:
        file_ext = file.filename.rsplit('.', 1)[1].lower()
        new_filename = f"{uuid.uuid4().hex}.{file_ext}"
        file_path = os.path.join(UPLOAD_DIR, new_filename)
        
        async with aiofiles.open(file_path, 'wb') as f:
            content = await file.read()
            await f.write(content)
        
        image_url = f"/uploads/{new_filename}"
        print(f"[Community] 图片上传成功: {image_url}")
        
        return success_response(
            message="上传成功",
            data={
                "url": image_url,
                "filename": new_filename
            }
        )
    except Exception as e:
        print(f"[Community] 图片上传失败: {e}")
        return error_response(message=f"上传失败: {str(e)}", code=500)


@router.delete("/upload/image/{filename}", summary="删除图片")
async def delete_image(
    filename: str,
    db: Session = Depends(get_db)
):
    try:
        file_path = os.path.join(UPLOAD_DIR, filename)
        if os.path.exists(file_path):
            os.remove(file_path)
            return success_response(message="删除成功")
        else:
            return error_response(message="文件不存在", code=404)
    except Exception as e:
        return error_response(message=f"删除失败: {str(e)}", code=500)


@router.get("/uploads/{filename}", summary="获取上传的图片")
async def get_uploaded_image(filename: str):
    file_path = os.path.join(UPLOAD_DIR, filename)
    if os.path.exists(file_path):
        return FileResponse(file_path)
    return error_response(message="图片不存在", code=404)


class CreatePostRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200, description="标题")
    content: str = Field(..., min_length=1, description="内容")
    images: Optional[str] = Field(None, description="图片URL列表（逗号分隔）")
    app_url: Optional[str] = Field(None, description="应用地址")
    api_url: Optional[str] = Field(None, description="API地址")


class UpdatePostRequest(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200, description="标题")
    content: Optional[str] = Field(None, min_length=1, description="内容")
    images: Optional[str] = Field(None, description="图片URL列表（逗号分隔）")
    app_url: Optional[str] = Field(None, description="应用地址")
    api_url: Optional[str] = Field(None, description="API地址")


class PostInfo(BaseModel):
    id: int
    user_id: int
    username: str
    title: str
    content: str
    images: Optional[str]
    app_url: Optional[str]
    api_url: Optional[str]
    created_at: str
    updated_at: str


@router.post("/posts", summary="创建帖子")
async def create_post(
    post_data: CreatePostRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    post = CommunityPost(
        user_id=current_user.id,
        title=post_data.title,
        content=post_data.content,
        images=post_data.images,
        app_url=post_data.app_url,
        api_url=post_data.api_url,
        status=CommunityPostStatus.ACTIVE
    )
    
    db.add(post)
    db.commit()
    db.refresh(post)
    
    return success_response(
        message="发布成功",
        data={
            "id": post.id,
            "title": post.title,
            "content": post.content,
            "created_at": post.created_at.isoformat()
        }
    )


@router.get("/posts", summary="获取帖子列表")
async def get_posts(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    posts = db.query(CommunityPost).filter(
        CommunityPost.status == CommunityPostStatus.ACTIVE
    ).order_by(CommunityPost.created_at.desc()).offset(skip).limit(limit).all()
    
    result = []
    for post in posts:
        result.append({
            "id": post.id,
            "user_id": post.user_id,
            "username": post.user.username if post.user else "",
            "title": post.title,
            "content": post.content,
            "images": post.images,
            "app_url": post.app_url,
            "api_url": post.api_url,
            "created_at": post.created_at.isoformat(),
            "updated_at": post.updated_at.isoformat()
        })
    
    return success_response(message="获取成功", data=result)


@router.get("/posts/{post_id}", summary="获取帖子详情")
async def get_post(
    post_id: int,
    db: Session = Depends(get_db)
):
    post = db.query(CommunityPost).filter(
        CommunityPost.id == post_id,
        CommunityPost.status == CommunityPostStatus.ACTIVE
    ).first()
    
    if not post:
        return error_response(message="帖子不存在", code=404)
    
    return success_response(
        message="获取成功",
        data={
            "id": post.id,
            "user_id": post.user_id,
            "username": post.user.username if post.user else "",
            "title": post.title,
            "content": post.content,
            "images": post.images,
            "app_url": post.app_url,
            "api_url": post.api_url,
            "created_at": post.created_at.isoformat(),
            "updated_at": post.updated_at.isoformat()
        }
    )


@router.put("/posts/{post_id}", summary="更新帖子")
async def update_post(
    post_id: int,
    post_data: UpdatePostRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    post = db.query(CommunityPost).filter(
        CommunityPost.id == post_id,
        CommunityPost.user_id == current_user.id
    ).first()
    
    if not post:
        return error_response(message="帖子不存在", code=404)
    
    if post_data.title:
        post.title = post_data.title
    if post_data.content:
        post.content = post_data.content
    if post_data.images is not None:
        post.images = post_data.images
    if post_data.app_url is not None:
        post.app_url = post_data.app_url
    if post_data.api_url is not None:
        post.api_url = post_data.api_url
    
    post.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(post)
    
    return success_response(
        message="更新成功",
        data={
            "id": post.id,
            "title": post.title,
            "content": post.content,
            "updated_at": post.updated_at.isoformat()
        }
    )


@router.delete("/posts/{post_id}", summary="删除帖子")
async def delete_post(
    post_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    post = db.query(CommunityPost).filter(
        CommunityPost.id == post_id,
        CommunityPost.user_id == current_user.id
    ).first()
    
    if not post:
        return error_response(message="帖子不存在", code=404)
    
    post.status = CommunityPostStatus.DELETED
    post.updated_at = datetime.utcnow()
    db.commit()
    
    return success_response(message="删除成功")


@router.get("/my-posts", summary="获取我的帖子")
async def get_my_posts(
    skip: int = 0,
    limit: int = 50,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    posts = db.query(CommunityPost).filter(
        CommunityPost.user_id == current_user.id,
        CommunityPost.status == CommunityPostStatus.ACTIVE
    ).order_by(CommunityPost.created_at.desc()).offset(skip).limit(limit).all()
    
    result = []
    for post in posts:
        result.append({
            "id": post.id,
            "title": post.title,
            "content": post.content,
            "images": post.images,
            "app_url": post.app_url,
            "api_url": post.api_url,
            "created_at": post.created_at.isoformat(),
            "updated_at": post.updated_at.isoformat()
        })
    
    return success_response(message="获取成功", data=result)


@router.delete("/admin/posts/{post_id}", summary="删除帖子（管理员）")
async def admin_delete_post(
    post_id: int,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    post = db.query(CommunityPost).filter(CommunityPost.id == post_id).first()
    
    if not post:
        return error_response(message="帖子不存在", code=404)
    
    post.status = CommunityPostStatus.DELETED
    post.updated_at = datetime.utcnow()
    db.commit()
    
    return success_response(message="删除成功")


@router.get("/admin/posts", summary="获取所有帖子（管理员）")
async def admin_get_posts(
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    posts = db.query(CommunityPost).order_by(CommunityPost.created_at.desc()).offset(skip).limit(limit).all()
    
    result = []
    for post in posts:
        result.append({
            "id": post.id,
            "user_id": post.user_id,
            "username": post.user.username if post.user else "",
            "title": post.title,
            "content": post.content,
            "images": post.images,
            "app_url": post.app_url,
            "api_url": post.api_url,
            "status": post.status.value,
            "created_at": post.created_at.isoformat(),
            "updated_at": post.updated_at.isoformat()
        })
    
    return success_response(message="获取成功", data=result)
