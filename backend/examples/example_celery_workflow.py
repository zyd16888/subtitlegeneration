"""
Celery 任务工作流示例

演示如何使用 Celery 任务进行字幕生成
"""
import asyncio
from backend.models.base import SessionLocal, engine, Base
from backend.services.task_manager import TaskManager
from backend.tasks.subtitle_tasks import generate_subtitle_task


async def example_create_and_submit_task():
    """
    示例：创建并提交字幕生成任务
    
    这个示例展示了完整的工作流：
    1. 创建数据库任务记录
    2. 提交 Celery 任务
    3. 查询任务状态
    """
    # 创建数据库表（如果不存在）
    Base.metadata.create_all(bind=engine)
    
    # 创建数据库会话
    db = SessionLocal()
    task_manager = TaskManager(db)
    
    try:
        # 1. 创建任务记录
        print("创建任务记录...")
        task = await task_manager.create_task(
            media_item_id="emby_item_12345",
            media_item_title="示例日语视频",
            video_path="/path/to/video.mp4"
        )
        print(f"任务已创建: ID={task.id}, 状态={task.status}")
        
        # 2. 提交 Celery 任务
        print("\n提交 Celery 任务...")
        celery_task = generate_subtitle_task.delay(
            task_id=task.id,
            media_item_id="emby_item_12345",
            video_path="/path/to/video.mp4"
        )
        print(f"Celery 任务已提交: ID={celery_task.id}")
        
        # 3. 查询任务状态
        print("\n查询任务状态...")
        task = await task_manager.get_task(task.id)
        print(f"当前状态: {task.status}")
        print(f"当前进度: {task.progress}%")
        
        # 4. 返回任务信息
        return {
            "task_id": task.id,
            "celery_task_id": celery_task.id,
            "status": task.status,
            "progress": task.progress
        }
        
    finally:
        db.close()


async def example_query_task_status(task_id: str):
    """
    示例：查询任务状态
    
    Args:
        task_id: 任务 ID
    """
    db = SessionLocal()
    task_manager = TaskManager(db)
    
    try:
        task = await task_manager.get_task(task_id)
        
        if task is None:
            print(f"任务不存在: {task_id}")
            return None
        
        print(f"任务 ID: {task.id}")
        print(f"媒体项: {task.media_item_title}")
        print(f"状态: {task.status}")
        print(f"进度: {task.progress}%")
        print(f"创建时间: {task.created_at}")
        
        if task.completed_at:
            print(f"完成时间: {task.completed_at}")
        
        if task.error_message:
            print(f"错误信息: {task.error_message}")
        
        return task
        
    finally:
        db.close()


async def example_cancel_task(task_id: str, celery_task_id: str):
    """
    示例：取消任务
    
    Args:
        task_id: 数据库任务 ID
        celery_task_id: Celery 任务 ID
    """
    from celery.result import AsyncResult
    
    db = SessionLocal()
    task_manager = TaskManager(db)
    
    try:
        # 1. 取消 Celery 任务
        print(f"取消 Celery 任务: {celery_task_id}")
        celery_task = AsyncResult(celery_task_id)
        celery_task.revoke(terminate=True)
        
        # 2. 更新数据库状态
        print(f"更新数据库任务状态: {task_id}")
        success = await task_manager.cancel_task(task_id)
        
        if success:
            print("任务已取消")
        else:
            print("任务无法取消（可能已完成或失败）")
        
        return success
        
    finally:
        db.close()


async def example_retry_failed_task(task_id: str):
    """
    示例：重试失败的任务
    
    Args:
        task_id: 原任务 ID
    """
    db = SessionLocal()
    task_manager = TaskManager(db)
    
    try:
        # 1. 获取原任务信息
        original_task = await task_manager.get_task(task_id)
        
        if original_task is None:
            print(f"任务不存在: {task_id}")
            return None
        
        print(f"原任务状态: {original_task.status}")
        
        # 2. 创建新任务（重试）
        new_task = await task_manager.retry_task(task_id)
        
        if new_task is None:
            print("任务无法重试（只能重试失败的任务）")
            return None
        
        print(f"新任务已创建: ID={new_task.id}")
        
        # 3. 提交新的 Celery 任务
        celery_task = generate_subtitle_task.delay(
            task_id=new_task.id,
            media_item_id=new_task.media_item_id,
            video_path=new_task.video_path
        )
        
        print(f"Celery 任务已提交: ID={celery_task.id}")
        
        return {
            "task_id": new_task.id,
            "celery_task_id": celery_task.id
        }
        
    finally:
        db.close()


async def example_batch_create_tasks(video_paths: list):
    """
    示例：批量创建任务
    
    Args:
        video_paths: 视频文件路径列表
    """
    db = SessionLocal()
    task_manager = TaskManager(db)
    
    try:
        tasks = []
        
        for i, video_path in enumerate(video_paths):
            # 创建任务记录
            task = await task_manager.create_task(
                media_item_id=f"emby_item_{i}",
                media_item_title=f"视频 {i+1}",
                video_path=video_path
            )
            
            # 提交 Celery 任务
            celery_task = generate_subtitle_task.delay(
                task_id=task.id,
                media_item_id=f"emby_item_{i}",
                video_path=video_path
            )
            
            tasks.append({
                "task_id": task.id,
                "celery_task_id": celery_task.id,
                "video_path": video_path
            })
            
            print(f"任务 {i+1}/{len(video_paths)} 已创建: {task.id}")
        
        print(f"\n批量创建完成，共 {len(tasks)} 个任务")
        return tasks
        
    finally:
        db.close()


async def example_get_statistics():
    """
    示例：获取任务统计信息
    """
    db = SessionLocal()
    task_manager = TaskManager(db)
    
    try:
        stats = await task_manager.get_statistics()
        
        print("任务统计信息:")
        print(f"  总任务数: {stats.total}")
        print(f"  待处理: {stats.pending}")
        print(f"  处理中: {stats.processing}")
        print(f"  已完成: {stats.completed}")
        print(f"  失败: {stats.failed}")
        print(f"  已取消: {stats.cancelled}")
        
        return stats
        
    finally:
        db.close()


if __name__ == "__main__":
    print("=== Celery 任务工作流示例 ===\n")
    
    # 示例 1: 创建并提交任务
    print("示例 1: 创建并提交任务")
    print("-" * 50)
    result = asyncio.run(example_create_and_submit_task())
    print(f"结果: {result}\n")
    
    # 示例 2: 查询任务状态
    # print("示例 2: 查询任务状态")
    # print("-" * 50)
    # asyncio.run(example_query_task_status("task_id_here"))
    # print()
    
    # 示例 3: 获取统计信息
    print("示例 3: 获取统计信息")
    print("-" * 50)
    asyncio.run(example_get_statistics())
    print()
    
    print("=== 示例完成 ===")
    print("\n注意:")
    print("1. 确保 Redis 服务正在运行")
    print("2. 确保 Celery worker 已启动")
    print("3. 修改示例中的文件路径为实际路径")
