"""
Telegram Bot handlers 注册
"""
from telegram.ext import Application


def register_handlers(app: Application, admin_ids: list[int]) -> None:
    """注册所有 Bot handlers"""
    from .start import register as register_start
    from .auth import register as register_auth
    from .browse import register as register_browse
    from .inline import register as register_inline
    from .task import register as register_task
    from .admin import register as register_admin

    register_start(app)
    register_auth(app)
    register_browse(app)
    register_inline(app)
    register_task(app)
    register_admin(app, admin_ids)
