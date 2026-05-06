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
    """从数据库加载 Telegram 配置。

    admin_ids 来源 = telegram_admin_ids 配置 + DB 中 is_admin=True 的用户（去重）
    """
    db = SessionLocal()
    try:
        config_manager = ConfigManager(db)
        config = await config_manager.get_config()

        bot_token = config.telegram_bot_token or None
        admin_ids: list[int] = []
        admin_ids_str = config.telegram_admin_ids or ""
        for id_str in admin_ids_str.split(","):
            id_str = id_str.strip()
            if id_str.isdigit():
                admin_ids.append(int(id_str))

        from tgbot.models import TelegramUser
        for u in db.query(TelegramUser).filter(TelegramUser.is_admin == True).all():
            if u.telegram_id not in admin_ids:
                admin_ids.append(u.telegram_id)

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


def _build_user_commands() -> list:
    """普通用户命令列表（其他模块也可复用）。"""
    from telegram import BotCommand
    return [
        BotCommand("start", "开始使用"),
        BotCommand("help", "帮助信息"),
        BotCommand("me", "查看我的信息"),
        BotCommand("login", "绑定账号"),
        BotCommand("logout", "解除绑定"),
        BotCommand("tasks", "查看我的任务"),
        BotCommand("task_info", "任务详情 (用法: /task_info 任务ID)"),
        BotCommand("cancel", "取消任务 (用法: /cancel 任务ID)"),
        BotCommand("retry", "重试任务 (用法: /retry 任务ID)"),
        BotCommand("browse", "浏览媒体资源"),
        BotCommand("search", "搜索媒体 (支持过滤参数)"),
        BotCommand("recent", "最近添加的媒体"),
        BotCommand("no_subs", "无字幕媒体快捷列表"),
        BotCommand("config", "任务偏好（目标语言/保留源字幕）"),
        BotCommand("settings", "通知偏好"),
    ]


def _build_admin_commands() -> list:
    """管理员专用命令列表。"""
    from telegram import BotCommand
    return [
        BotCommand("stat", "系统统计"),
        BotCommand("queue", "队列详情"),
        BotCommand("task", "任务管理"),
        BotCommand("log", "任务日志 (用法: /log 任务ID [--all])"),
        BotCommand("user", "用户管理 (支持关键词搜索)"),
        BotCommand("ban", "封禁用户 (用法: /ban 用户ID)"),
        BotCommand("unban", "解封用户 (用法: /unban 用户ID)"),
        BotCommand("set_limit", "设置配额 (用法: /set_limit 用户ID 数量)"),
        BotCommand("reset_limit", "重置配额 (用法: /reset_limit 用户ID)"),
        BotCommand("promote", "提升管理员 (用法: /promote 用户ID)"),
        BotCommand("demote", "撤销管理员 (用法: /demote 用户ID)"),
        BotCommand("cancel_all", "取消所有待处理任务"),
        BotCommand("broadcast", "广播 (支持 --active-7d|--bound|--admins|--all)"),
        BotCommand("reload_config", "重新加载配置"),
        BotCommand("audit", "审计日志 (支持 --user --action --limit)"),
    ]


async def _register_commands(app: Application, admin_ids: list[int]) -> None:
    """注册 Bot 命令到 Telegram"""
    from telegram import BotCommandScopeDefault, BotCommandScopeChat
    from telegram.error import TelegramError

    user_commands = _build_user_commands()
    admin_commands = _build_admin_commands()

    try:
        # 注册普通用户命令（所有用户可见）
        await app.bot.set_my_commands(user_commands, scope=BotCommandScopeDefault())
        logger.info(f"已注册 {len(user_commands)} 个普通用户命令")

        # 为管理员额外注册管理员命令
        all_admin_commands = user_commands + admin_commands
        for admin_id in admin_ids:
            await app.bot.set_my_commands(
                all_admin_commands,
                scope=BotCommandScopeChat(chat_id=admin_id)
            )
        logger.info(f"已为 {len(admin_ids)} 个管理员注册 {len(all_admin_commands)} 个命令")

    except TelegramError as e:
        logger.warning(f"注册命令失败: {e}")


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

        # 启动前一次性标记历史任务为已通知（防止长时间停机后通知风暴）
        from .services.notification import (
            check_task_notifications,
            mark_pending_notifications_as_sent,
        )
        mark_pending_notifications_as_sent()

        # 注册通知轮询任务
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

        # 注册命令
        await _register_commands(_application, admin_ids)

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
