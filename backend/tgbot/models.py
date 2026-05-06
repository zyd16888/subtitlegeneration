"""
Telegram 用户数据模型
"""
from sqlalchemy import Column, Integer, BigInteger, String, Boolean, DateTime, JSON

from models.base import Base
from config.time_utils import utc_now


class TelegramUser(Base):
    """Telegram Bot 用户模型，关联 Emby 账号"""
    __tablename__ = "telegram_users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False, index=True)
    telegram_username = Column(String, nullable=True)
    telegram_display_name = Column(String, nullable=True)

    # Emby 绑定
    emby_user_id = Column(String, nullable=True)
    emby_username = Column(String, nullable=True)

    # 权限
    is_admin = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)

    # 配额
    daily_task_limit = Column(Integer, nullable=True)  # null=使用全局默认值
    daily_task_count = Column(Integer, default=0)
    daily_count_reset_at = Column(DateTime(timezone=True), nullable=True)

    # 通知偏好
    notify_on_complete = Column(Boolean, default=True)
    notify_on_failure = Column(Boolean, default=True)

    # 任务偏好（覆盖全局配置；None 表示沿用全局）
    prefer_target_languages = Column(JSON, nullable=True, comment="覆盖全局 target_languages")
    prefer_keep_source_subtitle = Column(Boolean, nullable=True, comment="覆盖全局 keep_source_subtitle")

    # 时间
    created_at = Column(DateTime(timezone=True), default=utc_now)
    last_active_at = Column(DateTime(timezone=True), default=utc_now)

    def __repr__(self):
        return (
            f"<TelegramUser(id={self.id}, telegram_id={self.telegram_id}, "
            f"emby_username={self.emby_username})>"
        )


class TelegramAuditLog(Base):
    """Telegram Bot 操作审计日志。

    记录敏感/管理类动作（登录、封禁、广播等），供管理员追溯。
    """
    __tablename__ = "telegram_audit_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ts = Column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)
    tg_user_id = Column(BigInteger, nullable=False, index=True, comment="触发动作的 TG 用户 ID")
    action = Column(String, nullable=False, index=True, comment="动作分类: login/logout/cancel/retry/ban/...")
    target_id = Column(String, nullable=True, comment="操作目标 ID（用户 ID 或任务 ID）")
    payload = Column(JSON, nullable=True, comment="详细参数")

    def __repr__(self):
        return (
            f"<TelegramAuditLog(id={self.id}, ts={self.ts}, "
            f"tg_user_id={self.tg_user_id}, action={self.action}, target_id={self.target_id})>"
        )
