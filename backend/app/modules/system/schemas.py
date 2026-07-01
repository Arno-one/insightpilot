from pydantic import BaseModel, Field


class UpdateRolePermissionsRequest(BaseModel):
    permission_codes: list[str] = Field(..., description="角色最新权限编码列表")


class UpdateUserRolesRequest(BaseModel):
    role_ids: list[str] = Field(..., min_length=1, description="用户最新角色 ID 列表")
