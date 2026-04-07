"""
Telegram 用户数据模型
"""
from sqlalchemy import Column, Integer, BigInteger, String, Boolean, DateTime

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

    # 时间
    created_at = Column(DateTime(timezone=True), default=utc_now)
    last_active_at = Column(DateTime(timezone=True), default=utc_now)

    def __repr__(self):
        return (
            f"<TelegramUser(id={self.id}, telegram_id={self.telegram_id}, "
            f"emby_username={self.emby_username})>"
        )
