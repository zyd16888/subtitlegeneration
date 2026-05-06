"""
FastAPI 应用入口
"""
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
import traceback
import time
import os
from pathlib import Path

from api import media, tasks, config, stats, models, worker, auth, asr_audio, subtitle_search
from models.base import init_db
from utils.logger import setup_logger, get_logger
from config.settings import settings

# 配置日志系统
setup_logger(
    name="subtitle_service",
    log_level=settings.log_level,
    log_file=settings.log_file,
    log_to_console=True,
    log_to_file=True
)
logger = get_logger("subtitle_service")

# 创建 FastAPI 应用
app = FastAPI(
    title="Emby AI 字幕生成服务",
    description="自动为视频生成多语言字幕的服务",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc"
)

# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应该配置具体的前端地址
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 请求日志中间件
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """
    记录所有 API 请求和响应
    
    Requirements: 13.1
    """
    # 记录请求开始
    start_time = time.time()
    request_id = id(request)
    
    logger.info(
        f"请求开始 [ID: {request_id}] {request.method} {request.url.path} "
        f"客户端: {request.client.host if request.client else 'unknown'}"
    )
    
    # 处理请求
    try:
        response = await call_next(request)
        
        # 计算处理时间
        process_time = time.time() - start_time
        
        # 记录响应
        logger.info(
            f"请求完成 [ID: {request_id}] {request.method} {request.url.path} "
            f"状态码: {response.status_code} 耗时: {process_time:.3f}s"
        )
        
        # 添加处理时间到响应头
        response.headers["X-Process-Time"] = str(process_time)
        
        return response
    except Exception as e:
        # 记录异常
        process_time = time.time() - start_time
        logger.error(
            f"请求异常 [ID: {request_id}] {request.method} {request.url.path} "
            f"耗时: {process_time:.3f}s 错误: {str(e)}"
        )
        raise


# 全局异常处理器 - HTTP 异常
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """
    处理 HTTP 异常
    
    返回标准化的错误响应
    Requirements: 14.4
    """
    logger.warning(
        f"HTTP 异常: {exc.status_code} - {exc.detail} "
        f"路径: {request.url.path}"
    )
    
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": "HTTP Error",
            "status_code": exc.status_code,
            "message": exc.detail,
            "path": str(request.url.path)
        }
    )


# 全局异常处理器 - 请求验证错误
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    处理请求验证错误
    
    返回标准化的错误响应
    Requirements: 14.4
    """
    logger.warning(
        f"请求验证失败: {request.url.path} "
        f"错误: {exc.errors()}"
    )
    
    return JSONResponse(
        status_code=422,
        content={
            "error": "Validation Error",
            "status_code": 422,
            "message": "请求参数验证失败",
            "details": exc.errors(),
            "path": str(request.url.path)
        }
    )


# 全局异常处理器 - 未处理的异常
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    全局异常处理器
    
    捕获所有未处理的异常，记录日志并返回标准错误响应
    Requirements: 13.3, 14.4
    """
    # 记录完整的错误堆栈信息
    error_traceback = traceback.format_exc()
    logger.error(
        f"未处理的异常: {type(exc).__name__}: {str(exc)}\n"
        f"请求路径: {request.method} {request.url.path}\n"
        f"客户端: {request.client.host if request.client else 'unknown'}\n"
        f"异常堆栈:\n{error_traceback}"
    )
    
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal Server Error",
            "status_code": 500,
            "message": "服务器内部错误",
            "detail": str(exc) if settings.debug else "请联系管理员",
            "path": str(request.url.path)
        }
    )


# 启动事件
@app.on_event("startup")
async def startup_event():
    """
    应用启动时执行
    
    初始化数据库
    """
    logger.info("正在启动 Emby AI 中文字幕生成服务...")
    
    try:
        # 初始化数据库
        init_db()
        logger.info("数据库初始化完成")
    except Exception as e:
        logger.error(f"数据库初始化失败: {e}")
        raise

    # ── 启动清理：处理上次运行残留的任务 ─────────────────────────────
    # 1. CANCELLED 任务：revoke 掉可能还在 broker 中排队的消息
    # 2. PROCESSING/PENDING 任务：服务已重启，这些任务不会继续执行，标记为 FAILED
    try:
        from models.base import SessionLocal as _StartupSession
        from models.task import Task as _TaskModel, TaskStatus as _TS
        from config.time_utils import utc_now as _utc_now

        _sdb = _StartupSession()
        try:
            # Revoke 已取消的任务（防止 broker 重新投递）
            cancelled = _sdb.query(_TaskModel).filter(
                _TaskModel.status == _TS.CANCELLED
            ).all()
            if cancelled:
                from tasks.celery_app import celery_app as _celery
                for t in cancelled:
                    try:
                        _celery.control.revoke(t.id, terminate=True)
                    except Exception:
                        pass
                logger.info(f"启动清理：revoke {len(cancelled)} 个已取消任务的 broker 消息")

            # 将残留的 PROCESSING/PENDING 任务标记为 FAILED
            stale = _sdb.query(_TaskModel).filter(
                _TaskModel.status.in_([_TS.PROCESSING, _TS.PENDING])
            ).all()
            for t in stale:
                t.status = _TS.FAILED
                t.completed_at = _utc_now()
                t.error_message = "服务重启，任务被中断"
                try:
                    _celery.control.revoke(t.id, terminate=True)
                except Exception:
                    pass
            if stale:
                _sdb.commit()
                logger.info(f"启动清理：{len(stale)} 个残留任务标记为 FAILED")
        finally:
            _sdb.close()
    except Exception as e:
        logger.warning(f"启动清理失败（不影响服务启动）: {e}")

    # 自动拉起 Celery worker（由主后端进程托管）
    try:
        from services.worker_manager import get_worker_manager
        result = get_worker_manager().start()
        logger.info(f"Celery worker 自动启动: {result.get('message')}")
    except Exception as e:
        logger.warning(f"Celery worker 自动启动失败（可在 UI 手动启动）: {e}")

    # 恢复 Telegram Bot（仅在 UI 中标记为启用时自动启动）
    try:
        from models.base import SessionLocal
        from services.config_manager import ConfigManager
        db = SessionLocal()
        try:
            config = await ConfigManager(db).get_config()
            if config.telegram_bot_enabled and config.telegram_bot_token:
                from tgbot.bot import start_bot
                await start_bot()
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"Telegram Bot 恢复启动失败（服务继续运行）: {e}")

    logger.info("服务启动完成")


# 关闭事件
@app.on_event("shutdown")
async def shutdown_event():
    """
    应用关闭时执行
    """
    logger.info("正在关闭 Emby AI 中文字幕生成服务...")

    # 停止 Telegram Bot
    try:
        from tgbot.bot import stop_bot
        await stop_bot()
    except Exception as e:
        logger.warning(f"Telegram Bot 停止失败: {e}")

    # 停止 Celery worker
    try:
        from services.worker_manager import get_worker_manager
        get_worker_manager().stop()
    except Exception as e:
        logger.warning(f"Celery worker 停止失败: {e}")


# 注册路由（auth 不需要保护）
app.include_router(auth.router)

# 需要认证保护的路由
app.include_router(media.router)
app.include_router(media.image_router)
app.include_router(tasks.router)
app.include_router(config.router)
app.include_router(stats.router)
app.include_router(models.router)
app.include_router(worker.router)
app.include_router(asr_audio.router)
app.include_router(subtitle_search.router)


# ========== 托管前端静态文件 ==========
# 静态文件目录（Docker 构建时从 frontend/dist 复制）
STATIC_DIR = Path(__file__).parent / "static"

if STATIC_DIR.exists():
    # 挂载静态资源目录（JS、CSS、图片等）
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")


# 根路径：返回前端 index.html
@app.get("/")
async def root():
    """返回前端页面或健康检查"""
    if STATIC_DIR.exists():
        return FileResponse(STATIC_DIR / "index.html")
    return {
        "status": "ok",
        "message": "Emby AI 中文字幕生成服务正在运行",
        "version": "1.0.0"
    }


# SPA 路由回退：所有非 API 路由返回 index.html
@app.get("/{full_path:path}")
async def spa_fallback(full_path: str):
    """
    SPA 路由回退
    
    非 API 路由和静态资源的请求返回 index.html，让前端路由处理
    """
    # API 路由由各自的 router 处理，这里不应该匹配到
    if full_path.startswith("api/") or full_path.startswith("docs") or full_path.startswith("redoc"):
        raise HTTPException(status_code=404, detail="Not found")
    
    # 检查是否是静态文件请求
    file_path = STATIC_DIR / full_path
    if file_path.exists() and file_path.is_file():
        return FileResponse(file_path)
    
    # SPA 回退到 index.html
    if STATIC_DIR.exists():
        return FileResponse(STATIC_DIR / "index.html")
    
    raise HTTPException(status_code=404, detail="Not found")


@app.get("/health")
async def health_check():
    """健康检查端点"""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
