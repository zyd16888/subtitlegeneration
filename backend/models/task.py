"""
任务数据模型
"""
from sqlalchemy import Column, String, Integer, BigInteger, DateTime, Enum as SQLEnum, Text, Float, JSON
from enum import Enum
from .base import Base
from config.time_utils import utc_now, ensure_utc


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
    
    # 基本信息
    id = Column(String, primary_key=True, index=True)
    media_item_id = Column(String, nullable=False, index=True, comment="Emby 媒体项 ID")
    media_item_title = Column(String, nullable=True, comment="媒体项标题")
    video_path = Column(String, nullable=True, comment="视频文件路径或 URL")
    
    # 用户追踪信息
    telegram_user_id = Column(BigInteger, nullable=True, index=True, comment="提交任务的 Telegram 用户 ID")
    telegram_username = Column(String, nullable=True, comment="Telegram 用户名")
    telegram_display_name = Column(String, nullable=True, comment="Telegram 显示名称")
    emby_username = Column(String, nullable=True, comment="关联的 Emby 用户名")
    
    # 状态信息
    status = Column(
        SQLEnum(TaskStatus),
        nullable=False,
        default=TaskStatus.PENDING,
        index=True,
        comment="任务状态"
    )
    progress = Column(Integer, nullable=False, default=0, comment="任务进度 (0-100)")
    
    # 时间信息
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, comment="创建时间")
    started_at = Column(DateTime(timezone=True), nullable=True, comment="开始处理时间")
    completed_at = Column(DateTime(timezone=True), nullable=True, comment="完成时间")
    
    # 错误信息
    error_message = Column(Text, nullable=True, comment="错误信息")
    error_stage = Column(String, nullable=True, comment="错误发生的阶段")
    
    # 配置信息（记录任务使用的配置）
    asr_engine = Column(String, nullable=True, comment="使用的 ASR 引擎")
    asr_model_id = Column(String, nullable=True, comment="使用的 ASR 模型 ID")
    translation_service = Column(String, nullable=True, comment="使用的翻译服务")
    source_language = Column(String, nullable=True, comment="源语言")
    target_language = Column(String, nullable=True, comment="目标语言")
    
    # 结果信息
    subtitle_path = Column(String, nullable=True, comment="生成的字幕文件路径")
    segment_count = Column(Integer, nullable=True, comment="识别的字幕段落数")
    audio_duration = Column(Float, nullable=True, comment="音频时长（秒）")
    processing_time = Column(Float, nullable=True, comment="处理耗时（秒）")
    
    # 扩展信息（JSON 格式，存储更多细节）
    extra_info = Column(JSON, nullable=True, comment="扩展信息")
    
    def __repr__(self):
        return f"<Task(id={self.id}, status={self.status}, progress={self.progress})>"
    
    def to_dict(self):
        """转换为字典，方便 API 返回"""
        return {
            "id": self.id,
            "media_item_id": self.media_item_id,
            "media_item_title": self.media_item_title,
            "video_path": self.video_path,
            "telegram_user_id": self.telegram_user_id,
            "telegram_username": self.telegram_username,
            "telegram_display_name": self.telegram_display_name,
            "emby_username": self.emby_username,
            "status": self.status.value if isinstance(self.status, TaskStatus) else self.status,
            "progress": self.progress,
            "created_at": ensure_utc(self.created_at).isoformat() if self.created_at else None,
            "started_at": ensure_utc(self.started_at).isoformat() if self.started_at else None,
            "completed_at": ensure_utc(self.completed_at).isoformat() if self.completed_at else None,
            "error_message": self.error_message,
            "error_stage": self.error_stage,
            "asr_engine": self.asr_engine,
            "asr_model_id": self.asr_model_id,
            "translation_service": self.translation_service,
            "source_language": self.source_language,
            "target_language": self.target_language,
            "subtitle_path": self.subtitle_path,
            "segment_count": self.segment_count,
            "audio_duration": self.audio_duration,
            "processing_time": self.processing_time,
            "extra_info": self.extra_info,
        }
