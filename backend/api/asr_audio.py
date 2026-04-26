"""Groq ASR 临时音频下载端点。"""
import os

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from models.base import get_db
from services.config_manager import ConfigManager
from services.signed_url import verify_asr_audio_token

router = APIRouter(prefix="/api", tags=["asr-audio"])


@router.get("/asr-audio/{task_id}/{filename}")
async def get_asr_audio(
    task_id: str,
    filename: str,
    token: str = Query(...),
    db: Session = Depends(get_db),
):
    """
    给云端 ASR 厂商拉取临时 FLAC 音频。

    不使用登录态，只接受短期签名 token；文件范围固定在
    {temp_dir}/tasks/{task_id}/groq_asr/{filename}。
    """
    try:
        verify_asr_audio_token(token, task_id, filename)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))

    if "/" in filename or "\\" in filename or not filename.endswith(".flac"):
        raise HTTPException(status_code=400, detail="非法音频文件名")

    config = await ConfigManager(db).get_config()
    task_dir = os.path.abspath(os.path.join(config.temp_dir, "tasks", task_id))
    audio_dir = os.path.abspath(os.path.join(task_dir, "groq_asr"))
    audio_path = os.path.abspath(os.path.join(audio_dir, filename))

    if not audio_path.startswith(audio_dir + os.sep):
        raise HTTPException(status_code=400, detail="非法音频路径")
    if not os.path.isfile(audio_path):
        raise HTTPException(status_code=404, detail="音频文件不存在")

    return FileResponse(audio_path, media_type="audio/flac", filename=filename)
