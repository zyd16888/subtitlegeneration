"""短期签名 URL 工具。"""
from datetime import datetime, timedelta

from jose import JWTError, jwt

from config.settings import settings


def create_asr_audio_token(task_id: str, filename: str, expires_minutes: int = 30) -> str:
    payload = {
        "scope": "asr_audio",
        "task_id": task_id,
        "filename": filename,
        "exp": datetime.utcnow() + timedelta(minutes=expires_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def verify_asr_audio_token(token: str, task_id: str, filename: str) -> None:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except JWTError as e:
        raise ValueError("无效或已过期的音频访问令牌") from e

    if payload.get("scope") != "asr_audio":
        raise ValueError("无效的音频访问令牌")
    if payload.get("task_id") != task_id or payload.get("filename") != filename:
        raise ValueError("音频访问令牌与请求文件不匹配")
