"""
任务数据模型
"""
from sqlalchemy import Column, String, Integer, DateTime, Enum as SQLEnum, Text
from datetime import datetime
from enum import Enum
from .base import Base


class TaskStatus(str, Enum):
    """任务状态枚举"""
    PENDING = "pending"       # 待处理
    PROCESSING = "processing" # 处理中
    COMPLETED = "completed"   # 已完成
    FAILED = "failed"         # 失败
    CANCELLED = "cancelled"   # 已取消


class Task(Base):
    """
    字幕生成任务模型
    
    存储字幕生成任务的所有信息，包括状态、进度和错误信息
    """
    __tablename__ = "tasks"
    
    id = Column(String, primary_key=True, index=True)
    media_item_id = Column(String, nullable=False, index=True, comment="Emby 媒体项 ID")
    media_item_title = Column(String, nullable=True, comment="媒体项标题")
    video_path = Column(String, nullable=True, comment="视频文件路径")
    status = Column(
        SQLEnum(TaskStatus),
        nullable=False,
        default=TaskStatus.PENDING,
        index=True,
        comment="任务状态"
    )
    progress = Column(Integer, nullable=False, default=0, comment="任务进度 (0-100)")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, comment="创建时间")
    completed_at = Column(DateTime, nullable=True, comment="完成时间")
    error_message = Column(Text, nullable=True, comment="错误信息")
    
    def __repr__(self):
        return f"<Task(id={self.id}, status={self.status}, progress={self.progress})>"
