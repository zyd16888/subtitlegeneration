"""
TaskManager 服务测试

测试任务管理器的所有功能，包括创建、查询、更新、取消和重试任务。
"""
import pytest
import asyncio
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.models.base import Base
from backend.models.task import Task, TaskStatus
from backend.services.task_manager import TaskManager, TaskStatistics


# 创建测试数据库
TEST_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture
def db_session():
    """创建测试数据库会话"""
    Base.metadata.create_all(bind=engine)
    session = TestSessionLocal()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def task_manager(db_session):
    """创建 TaskManager 实例"""
    return TaskManager(db_session)


@pytest.mark.asyncio
async def test_create_task(task_manager):
    """测试创建任务"""
    task = await task_manager.create_task(
        media_item_id="test-media-123",
        media_item_title="Test Movie",
        video_path="/path/to/video.mp4"
    )
    
    assert task is not None
    assert task.id is not None
    assert task.media_item_id == "test-media-123"
    assert task.media_item_title == "Test Movie"
    assert task.video_path == "/path/to/video.mp4"
    assert task.status == TaskStatus.PENDING
    assert task.progress == 0
    assert task.created_at is not None
    assert task.completed_at is None
    assert task.error_message is None


@pytest.mark.asyncio
async def test_get_task(task_manager):
    """测试获取任务"""
    # 创建任务
    created_task = await task_manager.create_task(
        media_item_id="test-media-456",
        media_item_title="Test Series",
        video_path="/path/to/series.mp4"
    )
    
    # 获取任务
    task = await task_manager.get_task(created_task.id)
    
    assert task is not None
    assert task.id == created_task.id
    assert task.media_item_id == "test-media-456"
    
    # 获取不存在的任务
    non_existent = await task_manager.get_task("non-existent-id")
    assert non_existent is None


@pytest.mark.asyncio
async def test_list_tasks(task_manager):
    """测试列出任务"""
    # 创建多个任务
    await task_manager.create_task("media-1", "Movie 1", "/path/1.mp4")
    await task_manager.create_task("media-2", "Movie 2", "/path/2.mp4")
    await task_manager.create_task("media-3", "Movie 3", "/path/3.mp4")
    
    # 列出所有任务
    tasks = await task_manager.list_tasks()
    assert len(tasks) == 3
    
    # 测试分页
    tasks_page1 = await task_manager.list_tasks(limit=2, offset=0)
    assert len(tasks_page1) == 2
    
    tasks_page2 = await task_manager.list_tasks(limit=2, offset=2)
    assert len(tasks_page2) == 1


@pytest.mark.asyncio
async def test_list_tasks_with_status_filter(task_manager):
    """测试按状态筛选任务"""
    # 创建不同状态的任务
    task1 = await task_manager.create_task("media-1", "Movie 1", "/path/1.mp4")
    task2 = await task_manager.create_task("media-2", "Movie 2", "/path/2.mp4")
    task3 = await task_manager.create_task("media-3", "Movie 3", "/path/3.mp4")
    
    # 更新任务状态
    await task_manager.update_task_status(task1.id, TaskStatus.PROCESSING, progress=50)
    await task_manager.update_task_status(task2.id, TaskStatus.COMPLETED, progress=100)
    
    # 筛选待处理任务
    pending_tasks = await task_manager.list_tasks(status=TaskStatus.PENDING)
    assert len(pending_tasks) == 1
    assert pending_tasks[0].id == task3.id
    
    # 筛选处理中任务
    processing_tasks = await task_manager.list_tasks(status=TaskStatus.PROCESSING)
    assert len(processing_tasks) == 1
    assert processing_tasks[0].id == task1.id
    
    # 筛选已完成任务
    completed_tasks = await task_manager.list_tasks(status=TaskStatus.COMPLETED)
    assert len(completed_tasks) == 1
    assert completed_tasks[0].id == task2.id


@pytest.mark.asyncio
async def test_update_task_status(task_manager):
    """测试更新任务状态"""
    task = await task_manager.create_task("media-1", "Movie 1", "/path/1.mp4")
    
    # 更新为处理中
    updated = await task_manager.update_task_status(
        task.id,
        TaskStatus.PROCESSING,
        progress=30
    )
    
    assert updated is not None
    assert updated.status == TaskStatus.PROCESSING
    assert updated.progress == 30
    assert updated.completed_at is None
    
    # 更新为已完成
    updated = await task_manager.update_task_status(
        task.id,
        TaskStatus.COMPLETED,
        progress=100
    )
    
    assert updated.status == TaskStatus.COMPLETED
    assert updated.progress == 100
    assert updated.completed_at is not None


@pytest.mark.asyncio
async def test_update_task_status_with_error(task_manager):
    """测试更新任务状态并设置错误信息"""
    task = await task_manager.create_task("media-1", "Movie 1", "/path/1.mp4")
    
    # 更新为失败状态
    updated = await task_manager.update_task_status(
        task.id,
        TaskStatus.FAILED,
        error_message="Audio extraction failed"
    )
    
    assert updated.status == TaskStatus.FAILED
    assert updated.error_message == "Audio extraction failed"
    assert updated.completed_at is not None


@pytest.mark.asyncio
async def test_update_task_status_progress_bounds(task_manager):
    """测试进度值边界检查"""
    task = await task_manager.create_task("media-1", "Movie 1", "/path/1.mp4")
    
    # 测试超过 100 的进度
    updated = await task_manager.update_task_status(
        task.id,
        TaskStatus.PROCESSING,
        progress=150
    )
    assert updated.progress == 100
    
    # 测试负数进度
    updated = await task_manager.update_task_status(
        task.id,
        TaskStatus.PROCESSING,
        progress=-10
    )
    assert updated.progress == 0


@pytest.mark.asyncio
async def test_cancel_task(task_manager):
    """测试取消任务"""
    # 创建待处理任务
    pending_task = await task_manager.create_task("media-1", "Movie 1", "/path/1.mp4")
    
    # 取消任务
    result = await task_manager.cancel_task(pending_task.id)
    assert result is True
    
    # 验证任务状态
    task = await task_manager.get_task(pending_task.id)
    assert task.status == TaskStatus.CANCELLED
    assert task.completed_at is not None


@pytest.mark.asyncio
async def test_cancel_processing_task(task_manager):
    """测试取消处理中的任务"""
    task = await task_manager.create_task("media-1", "Movie 1", "/path/1.mp4")
    await task_manager.update_task_status(task.id, TaskStatus.PROCESSING, progress=50)
    
    # 取消任务
    result = await task_manager.cancel_task(task.id)
    assert result is True
    
    # 验证任务状态
    updated_task = await task_manager.get_task(task.id)
    assert updated_task.status == TaskStatus.CANCELLED


@pytest.mark.asyncio
async def test_cancel_completed_task_fails(task_manager):
    """测试无法取消已完成的任务"""
    task = await task_manager.create_task("media-1", "Movie 1", "/path/1.mp4")
    await task_manager.update_task_status(task.id, TaskStatus.COMPLETED, progress=100)
    
    # 尝试取消已完成的任务
    result = await task_manager.cancel_task(task.id)
    assert result is False
    
    # 验证任务状态未改变
    updated_task = await task_manager.get_task(task.id)
    assert updated_task.status == TaskStatus.COMPLETED


@pytest.mark.asyncio
async def test_cancel_non_existent_task(task_manager):
    """测试取消不存在的任务"""
    result = await task_manager.cancel_task("non-existent-id")
    assert result is False


@pytest.mark.asyncio
async def test_retry_task(task_manager):
    """测试重试失败的任务"""
    # 创建并标记为失败的任务
    original_task = await task_manager.create_task("media-1", "Movie 1", "/path/1.mp4")
    await task_manager.update_task_status(
        original_task.id,
        TaskStatus.FAILED,
        error_message="Test error"
    )
    
    # 重试任务
    new_task = await task_manager.retry_task(original_task.id)
    
    assert new_task is not None
    assert new_task.id != original_task.id
    assert new_task.media_item_id == original_task.media_item_id
    assert new_task.media_item_title == original_task.media_item_title
    assert new_task.video_path == original_task.video_path
    assert new_task.status == TaskStatus.PENDING
    assert new_task.progress == 0
    assert new_task.error_message is None


@pytest.mark.asyncio
async def test_retry_non_failed_task(task_manager):
    """测试无法重试非失败状态的任务"""
    # 创建待处理任务
    task = await task_manager.create_task("media-1", "Movie 1", "/path/1.mp4")
    
    # 尝试重试待处理任务
    new_task = await task_manager.retry_task(task.id)
    assert new_task is None
    
    # 创建已完成任务
    completed_task = await task_manager.create_task("media-2", "Movie 2", "/path/2.mp4")
    await task_manager.update_task_status(completed_task.id, TaskStatus.COMPLETED, progress=100)
    
    # 尝试重试已完成任务
    new_task = await task_manager.retry_task(completed_task.id)
    assert new_task is None


@pytest.mark.asyncio
async def test_retry_non_existent_task(task_manager):
    """测试重试不存在的任务"""
    new_task = await task_manager.retry_task("non-existent-id")
    assert new_task is None


@pytest.mark.asyncio
async def test_get_statistics(task_manager):
    """测试获取任务统计信息"""
    # 创建不同状态的任务
    task1 = await task_manager.create_task("media-1", "Movie 1", "/path/1.mp4")
    task2 = await task_manager.create_task("media-2", "Movie 2", "/path/2.mp4")
    task3 = await task_manager.create_task("media-3", "Movie 3", "/path/3.mp4")
    task4 = await task_manager.create_task("media-4", "Movie 4", "/path/4.mp4")
    task5 = await task_manager.create_task("media-5", "Movie 5", "/path/5.mp4")
    
    # 更新任务状态
    await task_manager.update_task_status(task2.id, TaskStatus.PROCESSING, progress=50)
    await task_manager.update_task_status(task3.id, TaskStatus.COMPLETED, progress=100)
    await task_manager.update_task_status(task4.id, TaskStatus.FAILED, error_message="Error")
    await task_manager.cancel_task(task5.id)
    
    # 获取统计信息
    stats = await task_manager.get_statistics()
    
    assert stats.total == 5
    assert stats.pending == 1
    assert stats.processing == 1
    assert stats.completed == 1
    assert stats.failed == 1
    assert stats.cancelled == 1


@pytest.mark.asyncio
async def test_get_statistics_empty(task_manager):
    """测试空数据库的统计信息"""
    stats = await task_manager.get_statistics()
    
    assert stats.total == 0
    assert stats.pending == 0
    assert stats.processing == 0
    assert stats.completed == 0
    assert stats.failed == 0
    assert stats.cancelled == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
