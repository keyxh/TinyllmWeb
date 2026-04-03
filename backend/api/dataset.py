from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List
import os
import uuid

from tinlyllmWeb.backend.models.database import get_db, User, Dataset
from tinlyllmWeb.backend.services.dataset_service import DatasetService
from tinlyllmWeb.backend.utils.jwt import get_current_user, get_current_admin
from tinlyllmWeb.backend.utils.response import success_response, error_response
from tinlyllmWeb.backend.config import settings

router = APIRouter(prefix="/api/datasets", tags=["数据集管理"])


class DatasetInfo(BaseModel):
    id: int
    filename: str
    size: int
    sample_count: int
    created_at: str


@router.post("/upload", summary="上传训练数据集")
async def upload_dataset(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if not file.filename.endswith('.jsonl'):
        return error_response(message="只支持JSONL格式文件", code=400)
    
    os.makedirs(settings.DATASETS_PATH, exist_ok=True)
    
    file_id = str(uuid.uuid4())
    filename = f"{file_id}_{file.filename}"
    file_path = os.path.join(settings.DATASETS_PATH, filename)
    
    try:
        content = await file.read()
        with open(file_path, 'wb') as f:
            f.write(content)
        
        is_valid, message, sample_count = DatasetService.validate_jsonl(file_path)
        
        if not is_valid:
            os.remove(file_path)
            return error_response(message=message, code=400)
        
        dataset = DatasetService.create_dataset(
            db=db,
            user_id=current_user.id,
            filename=file.filename,
            file_path=file_path,
            size=len(content)
        )
        
        return success_response(
            message="上传成功",
            data={
                "id": dataset.id,
                "filename": dataset.filename,
                "size": dataset.size,
                "sample_count": dataset.sample_count,
                "created_at": dataset.created_at.isoformat()
            }
        )
        
    except Exception as e:
        if os.path.exists(file_path):
            os.remove(file_path)
        return error_response(message=f"上传失败：{str(e)}", code=500)


@router.get("/", summary="获取用户数据集列表")
async def get_datasets(
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    datasets = DatasetService.get_user_datasets(db, current_user.id, skip, limit)
    
    return success_response(
        message="获取成功",
        data=[
            {
                "id": dataset.id,
                "filename": dataset.filename,
                "size": dataset.size,
                "sample_count": dataset.sample_count,
                "created_at": dataset.created_at.isoformat()
            }
            for dataset in datasets
        ]
    )


@router.get("/{dataset_id}", summary="获取数据集详情")
async def get_dataset(
    dataset_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    dataset = DatasetService.get_dataset_by_id(db, dataset_id)
    
    if not dataset or dataset.user_id != current_user.id:
        return error_response(message="数据集不存在", code=404)
    
    return success_response(
        message="获取成功",
        data={
            "id": dataset.id,
            "filename": dataset.filename,
            "size": dataset.size,
            "sample_count": dataset.sample_count,
            "created_at": dataset.created_at.isoformat()
        }
    )


@router.delete("/{dataset_id}", summary="删除数据集")
async def delete_dataset(
    dataset_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    success = DatasetService.delete_dataset(db, dataset_id, current_user.id)
    
    if not success:
        return error_response(message="删除失败，数据集可能正在被使用", code=400)
    
    return success_response(message="删除成功")


@router.delete("/admin/{dataset_id}", summary="删除数据集（管理员）")
async def admin_delete_dataset(
    dataset_id: int,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    success = DatasetService.delete_dataset(db, dataset_id)
    
    if not success:
        return error_response(message="删除失败，数据集可能正在被使用", code=400)
    
    return success_response(message="删除成功")


@router.get("/all", summary="获取所有数据集（管理员）")
async def get_all_datasets(
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    datasets = DatasetService.get_all_datasets(db, skip, limit)
    
    result = []
    for dataset in datasets:
        result.append({
            "id": dataset.id,
            "username": dataset.user.username if dataset.user else "",
            "filename": dataset.filename,
            "size": dataset.size,
            "sample_count": dataset.sample_count,
            "created_at": dataset.created_at.isoformat()
        })
    
    return success_response(message="获取成功", data=result)


@router.get("/{dataset_id}/download", summary="下载数据集文件")
async def download_dataset(
    dataset_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    dataset = DatasetService.get_dataset_by_id(db, dataset_id)
    
    if not dataset:
        return error_response(message="数据集不存在", code=404)
    
    if not os.path.exists(dataset.file_path):
        return error_response(message="数据集文件不存在", code=404)
    
    return FileResponse(
        path=dataset.file_path,
        filename=dataset.filename,
        media_type="application/octet-stream"
    )
