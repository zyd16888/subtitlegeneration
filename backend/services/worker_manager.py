"""
Celery Worker 生命周期管理

以子进程方式启动 celery worker，由 FastAPI 后端统一管理。
支持从 UI 控制启动 / 停止 / 重启，以及在配置变更后自动重启。
"""
import logging
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# backend/ 目录（celery 需在此目录下运行，才能 import tasks.celery_app）
_BACKEND_DIR = Path(__file__).resolve().parent.parent
_WORKER_POOL = "threads"
_WORKER_QUEUES = "celery,subtitle_generation"


def _load_worker_concurrency(default: int = 2) -> int:
    """读取当前 worker 并发数配置。"""
    try:
        from models.base import SessionLocal
        from models.config import SystemConfig

        db = SessionLocal()
        try:
            row = db.query(SystemConfig).filter(
                SystemConfig.key == "max_concurrent_tasks"
            ).first()
            if row and row.value:
                value = int(str(row.value).strip('"'))
                if 1 <= value <= 16:
                    return value
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"读取 worker 并发数失败，使用默认值 {default}: {e}")
    return default


class WorkerManager:
    """管理 celery worker 子进程的单例。"""

    def __init__(self) -> None:
        self._process: Optional[subprocess.Popen] = None
        self._started_at: Optional[float] = None
        self._lock = threading.Lock()

    # ── 状态查询 ────────────────────────────────────────────────
    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def status(self) -> Dict[str, Any]:
        running = self.is_running()
        if not running:
            # 进程已退出，清理句柄
            if self._process is not None and self._process.poll() is not None:
                self._process = None
                self._started_at = None
        return {
            "running": running,
            "pid": self._process.pid if running and self._process else None,
            "uptime_seconds": (
                int(time.time() - self._started_at)
                if running and self._started_at
                else None
            ),
        }

    # ── 生命周期 ────────────────────────────────────────────────
    def start(self) -> Dict[str, Any]:
        with self._lock:
            if self.is_running():
                return {"running": True, "message": "Worker 已在运行"}

            concurrency = _load_worker_concurrency()
            cmd = [
                sys.executable,
                "-m",
                "celery",
                "-A",
                "tasks.celery_app",
                "worker",
                "--loglevel=info",
                f"--pool={_WORKER_POOL}",
                f"--concurrency={concurrency}",
                f"--queues={_WORKER_QUEUES}",
            ]

            popen_kwargs: Dict[str, Any] = {
                "cwd": str(_BACKEND_DIR),
                "env": os.environ.copy(),
            }
            if os.name == "nt":
                # 新建进程组，允许后续发送 CTRL_BREAK_EVENT 优雅停止
                popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
            else:
                popen_kwargs["start_new_session"] = True

            try:
                self._process = subprocess.Popen(cmd, **popen_kwargs)
                self._started_at = time.time()
                logger.info(
                    f"Celery worker 已启动, PID={self._process.pid}, "
                    f"pool={_WORKER_POOL}, concurrency={concurrency}, queues={_WORKER_QUEUES}"
                )
                return {
                    "running": True,
                    "message": (
                        f"Worker 已启动 (PID {self._process.pid}, "
                        f"并发 {concurrency})"
                    ),
                }
            except Exception as e:
                logger.error(f"启动 Celery worker 失败: {e}")
                self._process = None
                self._started_at = None
                return {"running": False, "message": f"启动失败: {e}"}

    def stop(self, timeout: float = 30.0) -> Dict[str, Any]:
        with self._lock:
            if not self.is_running():
                self._process = None
                self._started_at = None
                return {"running": False, "message": "Worker 未运行"}

            proc = self._process
            assert proc is not None
            try:
                if os.name == "nt":
                    # Windows: 发送 CTRL_BREAK_EVENT 让 celery 优雅退出
                    try:
                        proc.send_signal(signal.CTRL_BREAK_EVENT)
                    except Exception:
                        proc.terminate()
                else:
                    # POSIX: 对整个进程组发 SIGTERM
                    try:
                        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                    except Exception:
                        proc.terminate()

                try:
                    proc.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    logger.warning("Worker 优雅停止超时，强制 kill")
                    if os.name == "nt":
                        proc.kill()
                    else:
                        try:
                            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                        except Exception:
                            proc.kill()
                    proc.wait(timeout=5)
            except Exception as e:
                logger.error(f"停止 worker 失败: {e}")
                return {
                    "running": self.is_running(),
                    "message": f"停止失败: {e}",
                }

            self._process = None
            self._started_at = None
            logger.info("Celery worker 已停止")
            return {"running": False, "message": "Worker 已停止"}

    def restart(self) -> Dict[str, Any]:
        self.stop()
        # 给 Redis 一点时间清理心跳、端口等
        time.sleep(0.5)
        return self.start()


# ── 单例 ────────────────────────────────────────────────────────
_manager: Optional[WorkerManager] = None


def get_worker_manager() -> WorkerManager:
    global _manager
    if _manager is None:
        _manager = WorkerManager()
    return _manager
