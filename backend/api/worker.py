"""
Celery Worker 控制 API

供前端查询 / 启动 / 停止 / 重启后台任务 worker。
"""
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from services.worker_manager import get_worker_manager

router = APIRouter(prefix="/api/worker", tags=["worker"])


class WorkerStatusResponse(BaseModel):
    running: bool
    pid: Optional[int] = None
    uptime_seconds: Optional[int] = None
    message: Optional[str] = None


def _to_response(status: dict, message: Optional[str] = None) -> WorkerStatusResponse:
    return WorkerStatusResponse(
        running=status.get("running", False),
        pid=status.get("pid"),
        uptime_seconds=status.get("uptime_seconds"),
        message=message,
    )


@router.get("/status", response_model=WorkerStatusResponse)
async def worker_status():
    mgr = get_worker_manager()
    status = mgr.status()
    return _to_response(status, "运行中" if status["running"] else "未运行")


@router.post("/start", response_model=WorkerStatusResponse)
async def worker_start():
    mgr = get_worker_manager()
    result = mgr.start()
    return _to_response(mgr.status(), result.get("message"))


@router.post("/stop", response_model=WorkerStatusResponse)
async def worker_stop():
    mgr = get_worker_manager()
    result = mgr.stop()
    return _to_response(mgr.status(), result.get("message"))


@router.post("/restart", response_model=WorkerStatusResponse)
async def worker_restart():
    mgr = get_worker_manager()
    result = mgr.restart()
    return _to_response(mgr.status(), result.get("message"))
