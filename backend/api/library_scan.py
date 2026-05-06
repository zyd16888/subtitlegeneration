"""
库批量字幕扫描 API。

只提供 start 端点；任务一旦创建，状态/进度/取消都复用 /api/tasks/{id}（依据 task_type 区分展示）。
"""
from __future__ import annotations

import logging
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from config.time_utils import utc_now
from models.base import get_db
from models.task import Task, TaskStatus
from services.auth import require_auth
from services.config_manager import ConfigManager

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/library-scan",
    tags=["library_scan"],
    dependencies=[Depends(require_auth)],
)


class LibraryScanStartRequest(BaseModel):
    """启动库扫描请求体。"""

    library_id: str = Field(..., description="Emby 媒体库 ID")
    target_languages: Optional[List[str]] = Field(
        None, description="目标语言列表，留空使用全局配置"
    )
    skip_if_has_subtitle: bool = Field(
        True, description="已有字幕的媒体项是否跳过"
    )
    max_items: int = Field(0, ge=0, le=10000, description="最多扫描数量，0 = 不限")
    concurrency: int = Field(3, ge=1, le=10, description="并发处理项数量")
    item_type: Optional[str] = Field(
        None, description="可选：仅扫指定类型（Movie / Episode）"
    )


class LibraryScanStartResponse(BaseModel):
    task_id: str
    library_id: str
    library_name: Optional[str] = None
    status: str = "pending"


@router.post("/start", response_model=LibraryScanStartResponse)
async def start_library_scan(
    request: LibraryScanStartRequest,
    db: Session = Depends(get_db),
):
    """创建库扫描任务并入队 Celery。"""
    config = await ConfigManager(db).get_config()

    if not config.subtitle_search_enabled:
        raise HTTPException(status_code=400, detail="字幕搜索未启用，无法发起库扫描")
    if not config.emby_url or not config.emby_api_key:
        raise HTTPException(status_code=400, detail="Emby 未配置")
    if not config.path_mappings:
        raise HTTPException(status_code=400, detail="未配置路径映射规则，无法将字幕落盘")

    target_languages = list(
        request.target_languages
        or config.target_languages
        or [config.target_language]
    )
    target_languages = [code for code in target_languages if code]
    if not target_languages:
        raise HTTPException(status_code=400, detail="未指定任何目标语言")

    # 拉一次库名做展示
    library_name: Optional[str] = None
    try:
        from services.emby_connector import EmbyConnector

        async with EmbyConnector(config.emby_url, config.emby_api_key) as emby:
            libraries = await emby.get_libraries()
            for lib in libraries:
                if lib.id == request.library_id:
                    library_name = lib.name
                    break
        if library_name is None:
            raise HTTPException(status_code=404, detail=f"媒体库 {request.library_id} 不存在")
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning(f"获取媒体库名称失败（继续启动）: {exc}")

    task_id = str(uuid.uuid4())
    extra_info = {
        "task_type": "library_subtitle_scan",
        "scan_request": {
            "library_id": request.library_id,
            "library_name": library_name,
            "target_languages": target_languages,
            "skip_if_has_subtitle": request.skip_if_has_subtitle,
            "max_items": request.max_items,
            "concurrency": request.concurrency,
            "item_type": request.item_type,
        },
    }

    task = Task(
        id=task_id,
        media_item_id=request.library_id,  # 占位，避免触发非空约束
        media_item_title=f"📚 扫描媒体库：{library_name or request.library_id}",
        video_path="",
        status=TaskStatus.PENDING,
        progress=0,
        created_at=utc_now(),
        target_language=target_languages[0],
        extra_info=extra_info,
    )
    db.add(task)
    db.commit()

    # 入队 Celery
    from tasks.library_scan_tasks import scan_library_task

    scan_library_task.apply_async(
        kwargs=dict(
            task_id=task_id,
            library_id=request.library_id,
            target_languages=target_languages,
            skip_if_has_subtitle=request.skip_if_has_subtitle,
            max_items=request.max_items,
            concurrency=request.concurrency,
            item_type=request.item_type,
        ),
        task_id=task_id,
    )

    logger.info(
        f"[{task_id}] 创建库扫描任务 library={request.library_id} "
        f"targets={target_languages} concurrency={request.concurrency}"
    )

    return LibraryScanStartResponse(
        task_id=task_id,
        library_id=request.library_id,
        library_name=library_name,
        status=TaskStatus.PENDING.value,
    )
