from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=128)


class CurrentUser(BaseModel):
    tenant_id: str
    user_id: str
    username: str
    real_name: str
    role_codes: list[str]
    permission_codes: list[str]
