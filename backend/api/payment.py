from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, timedelta
import random
import uuid

from tinlyllmWeb.backend.models.database import get_db, User, PaymentOrder, PaymentStatus, PaymentMethod, PointsLog, PointsLogType
from tinlyllmWeb.backend.utils.jwt import get_current_user
from tinlyllmWeb.backend.utils.response import success_response, error_response

router = APIRouter(prefix="/api/payment", tags=["支付"])

POINTS_PER_YUAN = 10
ORDER_EXPIRE_MINUTES = 3
MAX_AMOUNT = 50.00
MIN_AMOUNT = 0.01


class CreateOrderRequest(BaseModel):
    points: int = Field(..., gt=0, description="要充值的积分数量")


class VerifyPaymentRequest(BaseModel):
    amount: float = Field(..., gt=0, description="支付金额")
    payway: str = Field(..., description="支付方式：0=微信，1=支付宝")
    content: str = Field(..., description="支付内容")


def generate_unique_amount(db: Session, target_amount: float, max_attempts: int = 50) -> Optional[float]:
    existing_amounts = set()
    active_orders = db.query(PaymentOrder).filter(
        PaymentOrder.status == PaymentStatus.PENDING,
        PaymentOrder.expires_at > datetime.utcnow()
    ).all()
    for order in active_orders:
        existing_amounts.add(order.amount)
    
    for _ in range(max_attempts):
        offset = random.uniform(-0.01, 0.01)
        test_amount = round(target_amount + offset, 2)
        if test_amount < MIN_AMOUNT or test_amount > MAX_AMOUNT:
            continue
        if test_amount not in existing_amounts:
            return test_amount
        offset -= 0.01
        if offset < -0.50:
            offset = 0.01
    
    return None


def cleanup_expired_orders(db: Session):
    expired_orders = db.query(PaymentOrder).filter(
        PaymentOrder.status == PaymentStatus.PENDING,
        PaymentOrder.expires_at < datetime.utcnow()
    ).all()
    for order in expired_orders:
        order.status = PaymentStatus.EXPIRED
        order.updated_at = datetime.utcnow()
    if expired_orders:
        db.commit()
        print(f"[Payment] 清理了 {len(expired_orders)} 个过期订单")


@router.post("/create-order", summary="创建充值订单")
async def create_order(
    request: CreateOrderRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    cleanup_expired_orders(db)
    
    target_amount = request.points / POINTS_PER_YUAN
    if target_amount > MAX_AMOUNT:
        return error_response(message=f"单次充值金额不能超过 {MAX_AMOUNT} 元", code=400)
    
    unique_amount = generate_unique_amount(db, target_amount)
    if unique_amount is None:
        return error_response(message="暂时无法生成唯一金额，请稍后重试", code=400)
    
    order_no = uuid.uuid4().hex[:24]
    expires_at = datetime.utcnow() + timedelta(minutes=ORDER_EXPIRE_MINUTES)
    
    order = PaymentOrder(
        order_no=order_no,
        user_id=current_user.id,
        amount=unique_amount,
        points=request.points,
        status=PaymentStatus.PENDING,
        method=PaymentMethod.WECHAT,
        expires_at=expires_at
    )
    
    db.add(order)
    db.commit()
    db.refresh(order)
    
    print(f"[Payment] 创建订单: order_no={order_no}, user_id={current_user.id}, amount={unique_amount}, points={request.points}")
    
    return success_response(
        message="订单创建成功",
        data={
            "order_no": order_no,
            "amount": unique_amount,
            "points": request.points,
            "expires_at": expires_at.isoformat(),
            "expires_in_seconds": ORDER_EXPIRE_MINUTES * 60
        }
    )


@router.post("/verify-payment", summary="验证支付（Android端调用）")
async def verify_payment(
    request: VerifyPaymentRequest,
    db: Session = Depends(get_db)
):
    cleanup_expired_orders(db)
    
    try:
        amount = float(request.amount)
    except (ValueError, TypeError):
        return error_response(message="金额格式错误", code=400)
    
    active_order = db.query(PaymentOrder).filter(
        PaymentOrder.status == PaymentStatus.PENDING,
        PaymentOrder.amount == amount,
        PaymentOrder.expires_at > datetime.utcnow()
    ).first()
    
    if not active_order:
        print(f"[Payment] 支付验证失败: 未找到匹配的订单，amount={amount}")
        return error_response(message="未找到匹配的订单或订单已过期", code=404)
    
    active_order.status = PaymentStatus.PAID
    active_order.updated_at = datetime.utcnow()
    
    user = db.query(User).filter(User.id == active_order.user_id).first()
    if user:
        user.points = (user.points or 0) + active_order.points
        
        points_log = PointsLog(
            user_id=user.id,
            log_type=PointsLogType.RECHARGE,
            amount=active_order.points,
            description=f"充值 {active_order.points} 积分（订单号：{active_order.order_no}）"
        )
        db.add(points_log)
    
    db.commit()
    
    print(f"[Payment] 支付验证成功: order_no={active_order.order_no}, user_id={user.id}, amount={amount}, points={active_order.points}")
    
    return success_response(
        message="支付验证成功",
        data={
            "order_no": active_order.order_no,
            "points": active_order.points,
            "new_balance": user.points if user else 0
        }
    )


@router.get("/orders", summary="获取我的订单列表")
async def get_orders(
    skip: int = 0,
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    orders = db.query(PaymentOrder).filter(
        PaymentOrder.user_id == current_user.id
    ).order_by(PaymentOrder.created_at.desc()).offset(skip).limit(limit).all()
    
    result = []
    for order in orders:
        result.append({
            "id": order.id,
            "order_no": order.order_no,
            "amount": order.amount,
            "points": order.points,
            "status": order.status.value,
            "method": order.method.value,
            "created_at": order.created_at.isoformat(),
            "updated_at": order.updated_at.isoformat(),
            "expires_at": order.expires_at.isoformat() if order.expires_at else None
        })
    
    return success_response(message="获取成功", data=result)


@router.get("/orders/{order_no}", summary="获取订单详情")
async def get_order(
    order_no: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    order = db.query(PaymentOrder).filter(
        PaymentOrder.order_no == order_no,
        PaymentOrder.user_id == current_user.id
    ).first()
    
    if not order:
        return error_response(message="订单不存在", code=404)
    
    return success_response(
        message="获取成功",
        data={
            "id": order.id,
            "order_no": order.order_no,
            "amount": order.amount,
            "points": order.points,
            "status": order.status.value,
            "method": order.method.value,
            "created_at": order.created_at.isoformat(),
            "updated_at": order.updated_at.isoformat(),
            "expires_at": order.expires_at.isoformat() if order.expires_at else None
        }
    )


@router.post("/orders/{order_no}/cancel", summary="取消订单")
async def cancel_order(
    order_no: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    order = db.query(PaymentOrder).filter(
        PaymentOrder.order_no == order_no,
        PaymentOrder.user_id == current_user.id,
        PaymentOrder.status == PaymentStatus.PENDING
    ).first()
    
    if not order:
        return error_response(message="订单不存在或已无法取消", code=404)
    
    order.status = PaymentStatus.CANCELLED
    order.updated_at = datetime.utcnow()
    db.commit()
    
    return success_response(message="订单已取消")
