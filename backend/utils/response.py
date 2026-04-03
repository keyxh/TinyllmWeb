import json
from typing import Dict, Any


def format_response(success: bool = True, message: str = "", data: Any = None, code: int = 200) -> Dict[str, Any]:
    return {
        "success": success,
        "message": message,
        "data": data,
        "code": code
    }


def success_response(message: str = "操作成功", data: Any = None) -> Dict[str, Any]:
    return format_response(success=True, message=message, data=data, code=200)


def error_response(message: str = "操作失败", code: int = 400, data: Any = None) -> Dict[str, Any]:
    return format_response(success=False, message=message, data=data, code=code)
