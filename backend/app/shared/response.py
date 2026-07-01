def success(data=None, msg: str = "success", total=None) -> dict:
    """统一成功响应，保持前后端联调时结构稳定。"""
    return {"code": 200, "msg": msg, "data": data, "total": total}
