"""
Telegram Bot 生命周期管理

Bot 不随 FastAPI 自动启动，由 UI 页面通过 API 控制启停。
配置全部从数据库（SystemConfigData）读取，不使用环境变量。
"""
import logging
import time
from typing import Optional

from telegram import Update
from telegram.ext import Application

from models.base import SessionLocal
from services.config_manager import ConfigManager

logger = logging.getLogger(__name__)

_application: Optional[Application] = None
_started_at: Optional[float] = None


async def _load_config_from_db() -> tuple[Optional[str], list[int]]:
    """从数据库加载 Telegram 配置"""
    db = SessionLocal()
    try:
        config_manager = ConfigManager(db)
        config = await config_manager.get_config()

        bot_token = config.telegram_bot_token or None
        admin_ids = []
        admin_ids_str = config.telegram_admin_ids or ""
        for id_str in admin_ids_str.split(","):
            id_str = id_str.strip()
            if id_str.isdigit():
                admin_ids.append(int(id_str))

        return bot_token, admin_ids
    finally:
        db.close()


def get_application() -> Optional[Application]:
    """获取当前 Bot Application 实例"""
    return _application


def is_running() -> bool:
    """Bot 是否正在运行"""
    return _application is not None and _application.running


def get_status() -> dict:
    """获取 Bot 运行状态"""
    running = is_running()
    uptime = None
    if running and _started_at is not None:
        uptime = round(time.time() - _started_at, 1)
    return {
        "running": running,
        "uptime_seconds": uptime,
    }


async def start_bot() -> dict:
    """
    启动 Telegram Bot。

    Returns:
        状态字典 {"running": bool, "message": str}
    """
    global _application, _started_at

    if is_running():
        return {"running": True, "message": "Bot 已在运行中"}

    bot_token, admin_ids = await _load_config_from_db()

    if not bot_token:
        return {"running": False, "message": "Bot Token 未配置，请先填写 Token"}

    try:
        _application = Application.builder().token(bot_token).build()

        # 存储管理员 ID 到 bot_data
        _application.bot_data["admin_ids"] = admin_ids

        # 注册所有 handlers
        from .handlers import register_handlers
        register_handlers(_application, admin_ids)

        # 注册通知轮询任务
        from .services.notification import check_task_notifications
        _application.job_queue.run_repeating(
            check_task_notifications,
            interval=30,
            first=10,
            name="task_notification_check",
        )

        # 启动 Bot
        await _application.initialize()
        await _application.start()
        await _application.updater.start_polling(
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES,
        )

        _started_at = time.time()
        logger.info("Telegram Bot 已启动")
        return {"running": True, "message": "Bot 启动成功"}

    except Exception as e:
        logger.error(f"Telegram Bot 启动失败: {e}")
        _application = None
        _started_at = None
        return {"running": False, "message": f"启动失败: {str(e)}"}


async def stop_bot() -> dict:
    """
    停止 Telegram Bot。

    Returns:
        状态字典 {"running": bool, "message": str}
    """
    global _application, _started_at

    if not is_running():
        _application = None
        _started_at = None
        return {"running": False, "message": "Bot 未在运行"}

    try:
        if _application.updater and _application.updater.running:
            await _application.updater.stop()
        await _application.stop()
        await _application.shutdown()
        logger.info("Telegram Bot 已停止")
        return {"running": False, "message": "Bot 已停止"}
    except Exception as e:
        logger.error(f"Telegram Bot 停止失败: {e}")
        return {"running": False, "message": f"停止异常: {str(e)}"}
    finally:
        _application = None
        _started_at = None
