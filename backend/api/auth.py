"""
认证 API
"""
from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel

from services.auth import (
    authenticate_user,
    create_access_token,
    Token,
    get_current_user
)
from config.settings import settings

router = APIRouter(prefix="/api/auth", tags=["认证"])


class LoginRequest(BaseModel):
    """登录请求"""
    username: str
    password: str


class AuthStatusResponse(BaseModel):
    """认证状态响应"""
    auth_enabled: bool
    logged_in: bool
    username: str | None = None


@router.post("/login", response_model=Token)
async def login(request: LoginRequest):
    """
    用户登录
    
    返回 JWT token
    """
    if not settings.auth_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="认证未启用"
        )
    
    if not authenticate_user(request.username, request.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token = create_access_token(data={"sub": request.username})
    return Token(access_token=access_token)


@router.get("/status", response_model=AuthStatusResponse)
async def auth_status(current_user: str | None = Depends(get_current_user)):
    """
    获取认证状态
    
    前端用于判断是否需要显示登录页面
    """
    return AuthStatusResponse(
        auth_enabled=settings.auth_enabled,
        logged_in=current_user is not None,
        username=current_user
    )


@router.post("/logout")
async def logout():
    """
    登出
    
    JWT 无状态，前端删除 token 即可
    """
    return {"message": "登出成功"}
