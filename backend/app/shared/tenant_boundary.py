from __future__ import annotations

from typing import Any, Mapping


def require_current_tenant(
    current_user: Mapping[str, Any],
    resource_tenant_id: Any,
    *,
    resource_name: str = "资源",
) -> None:
    """中文注释：统一租户边界守卫，失败时返回“不可见”语义，避免泄露跨租户资源存在性。"""
    current_tenant_id = current_user.get("tenant_id")
    if not current_tenant_id or str(current_tenant_id) != str(resource_tenant_id):
        raise ValueError(f"{resource_name} 不存在或无权访问")


def tenant_params(current_user: Mapping[str, Any], **extra: Any) -> dict[str, Any]:
    """中文注释：构造 SQL 参数时统一注入当前租户，减少手写参数遗漏。"""
    tenant_id = current_user.get("tenant_id")
    if not tenant_id:
        raise ValueError("当前用户缺少租户上下文")
    return {"tenant_id": tenant_id, **extra}
