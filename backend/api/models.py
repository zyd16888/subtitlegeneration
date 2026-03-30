"""
模型管理 API 端点
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from sqlalchemy.orm import Session

from models.base import get_db
from services.model_manager import ModelManager, DownloadProgress, DownloadStatus, SUPPORTED_LANGUAGES
from services.config_manager import ConfigManager
from config.settings import settings

router = APIRouter(prefix="/api/models", tags=["models"])


def _get_model_manager() -> ModelManager:
    return ModelManager(models_dir=settings.model_storage_dir)


class ModelInfo(BaseModel):
    model_config = {"protected_namespaces": ()}

    id: str
    name: str
    type: str  # online | offline
    model_type: str  # transducer | whisper
    languages: List[str]
    size: str
    installed: bool
    active: bool
    download_count: int = 0


class ModelDownloadProgressResponse(BaseModel):
    model_config = {"protected_namespaces": ()}

    model_id: str
    progress: int
    status: str
    error: Optional[str] = None


class LanguageInfo(BaseModel):
    code: str
    name: str


@router.get("", response_model=List[ModelInfo])
async def list_models(db: Session = Depends(get_db)):
    """列出所有可用模型（含安装状态和激活状态）"""
    manager = _get_model_manager()
    config_manager = ConfigManager(db)
    config = await config_manager.get_config()
    models = manager.list_models(active_model_id=config.asr_model_id)
    return models


@router.post("/refresh", response_model=List[ModelInfo])
async def refresh_models(db: Session = Depends(get_db)):
    """从 GitHub 刷新模型列表"""
    manager = _get_model_manager()
    manager.registry.refresh()
    config_manager = ConfigManager(db)
    config = await config_manager.get_config()
    models = manager.list_models(active_model_id=config.asr_model_id)
    return models


@router.post("/{model_id}/download", response_model=ModelDownloadProgressResponse)
async def download_model(model_id: str):
    """开始下载指定模型"""
    manager = _get_model_manager()
    progress = manager.start_download(model_id)
    if progress.status == DownloadStatus.FAILED:
        raise HTTPException(status_code=400, detail=progress.error)
    return ModelDownloadProgressResponse(
        model_id=progress.model_id,
        progress=progress.progress,
        status=progress.status.value,
        error=progress.error,
    )


@router.get("/{model_id}/progress", response_model=ModelDownloadProgressResponse)
async def get_download_progress(model_id: str):
    """查询模型下载进度"""
    manager = _get_model_manager()
    progress = manager.get_download_progress(model_id)
    return ModelDownloadProgressResponse(
        model_id=progress.model_id,
        progress=progress.progress,
        status=progress.status.value,
        error=progress.error,
    )


@router.post("/{model_id}/delete")
async def delete_model(model_id: str, db: Session = Depends(get_db)):
    """删除已下载的模型"""
    manager = _get_model_manager()

    # 如果正在使用该模型，先清除配置
    config_manager = ConfigManager(db)
    config = await config_manager.get_config()
    if config.asr_model_id == model_id:
        config.asr_model_id = None
        config.asr_model_path = None
        await config_manager.partial_update_config(config, {"asr_model_id", "asr_model_path"})

    deleted = manager.delete_model(model_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="模型未安装")
    return {"message": f"模型 {model_id} 已删除"}


@router.post("/{model_id}/activate")
async def activate_model(model_id: str, db: Session = Depends(get_db)):
    """激活（启用）指定模型为当前 ASR 模型"""
    manager = _get_model_manager()
    if not manager._is_installed(model_id):
        raise HTTPException(status_code=400, detail="模型未安装，请先下载")

    model_path = manager.get_model_path(model_id)
    if not model_path:
        raise HTTPException(status_code=500, detail="模型路径异常")

    config_manager = ConfigManager(db)
    config = await config_manager.get_config()
    config.asr_model_id = model_id
    config.asr_model_path = str(model_path)
    config.asr_engine = "sherpa-onnx"
    await config_manager.partial_update_config(
        config, {"asr_model_id", "asr_model_path", "asr_engine"}
    )
    return {"message": f"已启用模型 {model_id}", "model_path": str(model_path)}


@router.get("/storage-info")
async def get_storage_info():
    """诊断端点：查看模型存储路径和目录内容"""
    manager = _get_model_manager()
    models_dir = manager.models_dir

    contents = []
    if models_dir.exists():
        for item in sorted(models_dir.iterdir()):
            if item.is_dir():
                sub_files = [f.name for f in item.iterdir()][:20]
                contents.append({"name": item.name, "type": "dir", "files": sub_files})
            else:
                contents.append({"name": item.name, "type": "file", "size": item.stat().st_size})

    return {
        "models_dir": str(models_dir),
        "exists": models_dir.exists(),
        "contents": contents,
    }


@router.get("/languages", response_model=List[LanguageInfo])
async def list_languages():
    """列出所有支持的语言"""
    return [LanguageInfo(code=code, name=name) for code, name in SUPPORTED_LANGUAGES.items()]
