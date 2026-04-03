from fastapi import APIRouter, Depends, Form
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

from tinlyllmWeb.backend.models.database import get_db, User, PaymentOrder, PaymentStatus, PointsLog, PointsLogType
from tinlyllmWeb.backend.utils.response import success_response, error_response

router = APIRouter(prefix="/api/pay", tags=["安卓支付"])


@router.post("/AndroidPayServer", summary="安卓支付验证")
async def android_pay_server(
    amount: str = Form(...),
    payway: str = Form(...),
    db: Session = Depends(get_db)
):
    try:
        amount_float = float(amount)
    except (ValueError, TypeError):
        return error_response(message="金额格式错误", code=400)
    
    print(f"[AndroidPay] 收到支付验证请求: amount={amount}, amount_float={amount_float}")
    
    active_orders = db.query(PaymentOrder).filter(
        PaymentOrder.status == PaymentStatus.PENDING,
        PaymentOrder.expires_at > datetime.utcnow()
    ).all()
    
    print(f"[AndroidPay] 待处理订单数量: {len(active_orders)}")
    for order in active_orders:
        print(f"[AndroidPay] 订单: order_no={order.order_no}, amount={order.amount}, user_id={order.user_id}")
    
    active_order = None
    for order in active_orders:
        order_amount_str = str(order.amount)
        print(f"[AndroidPay] 比较订单: order_no={order.order_no}, order_amount={order_amount_str}, order_amount_type={type(order.amount)}, request_amount={amount}, request_amount_type={type(amount)}")
        if order_amount_str == amount:
            active_order = order
            print(f"[AndroidPay] 找到匹配订单: order_no={order.order_no}, order_amount={order_amount_str}, request_amount={amount}")
            break
    
    if not active_order:
        print(f"[AndroidPay] 支付验证失败: 未找到匹配的订单，amount={amount_float}")
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
    
    print(f"[AndroidPay] 支付验证成功: order_no={active_order.order_no}, user_id={user.id if user else 0}, amount={amount_float}, points={active_order.points}")
    
    return success_response(
        message="支付验证成功",
        data={
            "order_no": active_order.order_no,
            "points": active_order.points,
            "new_balance": user.points if user else 0
        }
    )
