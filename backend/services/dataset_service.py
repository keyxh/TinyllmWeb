from typing import List, Optional
from sqlalchemy.orm import Session
from datetime import datetime
import os
import json

from tinlyllmWeb.backend.models.database import Dataset, TrainingTask, Model, ModelStatus, TaskStatus
from tinlyllmWeb.backend.config import settings


class DatasetService:
    @staticmethod
    def create_dataset(db: Session, user_id: int, filename: str, file_path: str, size: int) -> Optional[Dataset]:
        sample_count = DatasetService._count_samples(file_path)
        
        dataset = Dataset(
            user_id=user_id,
            filename=filename,
            file_path=file_path,
            size=size,
            sample_count=sample_count
        )
        db.add(dataset)
        db.commit()
        db.refresh(dataset)
        return dataset
    
    @staticmethod
    def _count_samples(file_path: str) -> int:
        count = 0
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        try:
                            json.loads(line)
                            count += 1
                        except:
                            pass
        except:
            pass
        return count
    
    @staticmethod
    def get_dataset_by_id(db: Session, dataset_id: int) -> Optional[Dataset]:
        return db.query(Dataset).filter(Dataset.id == dataset_id).first()
    
    @staticmethod
    def get_user_datasets(db: Session, user_id: int, skip: int = 0, limit: int = 100) -> List[Dataset]:
        return db.query(Dataset).filter(
            Dataset.user_id == user_id
        ).order_by(Dataset.created_at.desc()).offset(skip).limit(limit).all()
    
    @staticmethod
    def get_all_datasets(db: Session, skip: int = 0, limit: int = 100) -> List[Dataset]:
        return db.query(Dataset).order_by(
            Dataset.created_at.desc()
        ).offset(skip).limit(limit).all()
    
    @staticmethod
    def delete_dataset(db: Session, dataset_id: int, user_id: Optional[int] = None) -> bool:
        query = db.query(Dataset).filter(Dataset.id == dataset_id)
        
        if user_id is not None:
            query = query.filter(Dataset.user_id == user_id)
        
        dataset = query.first()
        
        if not dataset:
            return False
        
        has_training = db.query(TrainingTask).filter(
            TrainingTask.dataset_id == dataset_id,
            TrainingTask.status.in_([TaskStatus.PENDING, TaskStatus.RUNNING])
        ).first()
        
        if has_training:
            return False
        
        try:
            if os.path.exists(dataset.file_path):
                os.remove(dataset.file_path)
        except:
            pass
        
        db.delete(dataset)
        db.commit()
        return True
    
    @staticmethod
    def validate_jsonl(file_path: str) -> tuple[bool, str, int]:
        if not os.path.exists(file_path):
            return False, "文件不存在", 0
        
        sample_count = 0
        errors = []
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    if not line.strip():
                        continue
                    
                    try:
                        data = json.loads(line)
                        if not isinstance(data, dict):
                            errors.append(f"第{line_num}行：数据格式错误，应为JSON对象")
                            continue
                        
                        if "query" not in data or "response" not in data:
                            errors.append(f"第{line_num}行：缺少query或response字段")
                            continue
                        
                        if not data["query"].strip() or not data["response"].strip():
                            errors.append(f"第{line_num}行：query或response为空")
                            continue
                        
                        sample_count += 1
                        
                    except json.JSONDecodeError:
                        errors.append(f"第{line_num}行：JSON格式错误")
                        continue
            
            if sample_count == 0:
                return False, "没有有效的数据样本", 0
            
            if errors:
                return False, f"数据验证失败：{'; '.join(errors[:5])}", sample_count
            
            return True, "数据验证通过", sample_count
            
        except Exception as e:
            return False, f"读取文件失败：{str(e)}", 0
