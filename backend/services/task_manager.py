"""
任务管理服务

负责管理字幕生成任务的生命周期，包括创建、查询、更新、取消和重试任务。
"""
from typing import List, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
import uuid

from models.task import Task, TaskStatus


class TaskStatistics:
    """任务统计信息"""
    def __init__(
        self,
        total: int,
        pending: int,
        processing: int,
        completed: int,
        failed: int,
        cancelled: int
    ):
        self.total = total
        self.pending = pending
        self.processing = processing
        self.completed = completed
        self.failed = failed
        self.cancelled = cancelled


class TaskManager:
    """
    任务管理器
    
    管理字幕生成任务的完整生命周期，包括：
    - 创建新任务
    - 查询任务状态
    - 更新任务进度
    - 取消和重试任务
    - 获取统计信息
    """
    
    def __init__(self, db_session: Session):
        """
        初始化任务管理器
        
        Args:
            db_session: SQLAlchemy 数据库会话
        """
        self.db = db_session
    
    async def create_task(
        self,
        media_item_id: str,
        media_item_title: str,
        video_path: str
    ) -> Task:
        """
        创建新的字幕生成任务
        
        Args:
            media_item_id: Emby 媒体项 ID
            media_item_title: 媒体项标题
            video_path: 视频文件路径
            
        Returns:
            创建的任务对象
        """
        task = Task(
            id=str(uuid.uuid4()),
            media_item_id=media_item_id,
            media_item_title=media_item_title,
            video_path=video_path,
            status=TaskStatus.PENDING,
            progress=0,
            created_at=datetime.utcnow()
        )
        
        self.db.add(task)
        self.db.commit()
        self.db.refresh(task)
        
        return task
    
    async def get_task(self, task_id: str) -> Optional[Task]:
        """
        获取任务详情
        
        Args:
            task_id: 任务 ID
            
        Returns:
            任务对象，如果不存在则返回 None
        """
        return self.db.query(Task).filter(Task.id == task_id).first()
    
    async def list_tasks(
        self,
        status: Optional[TaskStatus] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Task]:
        """
        获取任务列表
        
        Args:
            status: 可选的状态筛选
            limit: 返回的最大任务数
            offset: 分页偏移量
            
        Returns:
            任务列表
        """
        query = self.db.query(Task)
        
        if status is not None:
            query = query.filter(Task.status == status)
        
        query = query.order_by(desc(Task.created_at))
        query = query.limit(limit).offset(offset)
        
        return query.all()

    async def update_task_status(
        self,
        task_id: str,
        status: TaskStatus,
        progress: Optional[int] = None,
        error_message: Optional[str] = None
    ) -> Optional[Task]:
        """
        更新任务状态和进度
        
        Args:
            task_id: 任务 ID
            status: 新的任务状态
            progress: 可选的进度值 (0-100)
            error_message: 可选的错误信息
            
        Returns:
            更新后的任务对象，如果任务不存在则返回 None
        """
        task = await self.get_task(task_id)
        
        if task is None:
            return None
        
        task.status = status
        
        if progress is not None:
            task.progress = max(0, min(100, progress))  # 确保进度在 0-100 之间
        
        if error_message is not None:
            task.error_message = error_message
        
        # 如果任务完成或失败，设置完成时间
        if status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
            task.completed_at = datetime.utcnow()
        
        self.db.commit()
        self.db.refresh(task)
        
        return task
    
    async def cancel_task(self, task_id: str) -> bool:
        """
        取消任务
        
        只能取消处于 PENDING 或 PROCESSING 状态的任务
        
        Args:
            task_id: 任务 ID
            
        Returns:
            是否成功取消任务
        """
        task = await self.get_task(task_id)
        
        if task is None:
            return False
        
        # 只能取消待处理或处理中的任务
        if task.status not in [TaskStatus.PENDING, TaskStatus.PROCESSING]:
            return False
        
        task.status = TaskStatus.CANCELLED
        task.completed_at = datetime.utcnow()
        
        self.db.commit()
        
        return True
    
    async def retry_task(self, task_id: str) -> Optional[Task]:
        """
        重试失败的任务
        
        创建一个新任务，复制原任务的媒体项信息
        
        Args:
            task_id: 原任务 ID
            
        Returns:
            新创建的任务对象，如果原任务不存在或不是失败状态则返回 None
        """
        original_task = await self.get_task(task_id)
        
        if original_task is None:
            return None
        
        # 只能重试失败的任务
        if original_task.status != TaskStatus.FAILED:
            return None
        
        # 创建新任务
        new_task = await self.create_task(
            media_item_id=original_task.media_item_id,
            media_item_title=original_task.media_item_title,
            video_path=original_task.video_path
        )
        
        return new_task
    
    async def get_statistics(self) -> TaskStatistics:
        """
        获取任务统计信息
        
        Returns:
            任务统计对象，包含各状态的任务数量
        """
        # 查询各状态的任务数量
        total = self.db.query(func.count(Task.id)).scalar() or 0
        pending = self.db.query(func.count(Task.id)).filter(Task.status == TaskStatus.PENDING).scalar() or 0
        processing = self.db.query(func.count(Task.id)).filter(Task.status == TaskStatus.PROCESSING).scalar() or 0
        completed = self.db.query(func.count(Task.id)).filter(Task.status == TaskStatus.COMPLETED).scalar() or 0
        failed = self.db.query(func.count(Task.id)).filter(Task.status == TaskStatus.FAILED).scalar() or 0
        cancelled = self.db.query(func.count(Task.id)).filter(Task.status == TaskStatus.CANCELLED).scalar() or 0
        
        return TaskStatistics(
            total=total,
            pending=pending,
            processing=processing,
            completed=completed,
            failed=failed,
            cancelled=cancelled
        )
