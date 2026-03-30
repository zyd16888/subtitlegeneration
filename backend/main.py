"""
FastAPI 应用入口
"""
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
import traceback
import time

from api import media, tasks, config, stats, models
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
    
    logger.info("服务启动完成")


# 关闭事件
@app.on_event("shutdown")
async def shutdown_event():
    """
    应用关闭时执行
    """
    logger.info("正在关闭 Emby AI 中文字幕生成服务...")


# 注册路由
app.include_router(media.router)
app.include_router(tasks.router)
app.include_router(config.router)
app.include_router(stats.router)
app.include_router(models.router)


# 根路径
@app.get("/")
async def root():
    """健康检查端点"""
    return {
        "status": "ok",
        "message": "Emby AI 中文字幕生成服务正在运行",
        "version": "1.0.0"
    }


@app.get("/health")
async def health_check():
    """健康检查端点"""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
