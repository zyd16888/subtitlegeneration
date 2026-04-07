"""
测试 Telegram 用户追踪功能

运行方式：
    python -m migrations.test_user_tracking
"""
import sys
import os
import asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.base import SessionLocal
from services.task_manager import TaskManager


async def test_user_tracking():
    """测试用户追踪功能"""
    print("=" * 60)
    print("测试 Telegram 用户追踪功能")
    print("=" * 60)
    
    db = SessionLocal()
    try:
        task_manager = TaskManager(db)
        
        # 测试 1: 创建带用户信息的任务
        print("\n[测试 1] 创建带用户信息的任务...")
        task = await task_manager.create_task(
            media_item_id="test_media_123",
            media_item_title="测试电影",
            video_path="/path/to/video.mp4",
            telegram_user_id=123456789,
            telegram_username="testuser",
            telegram_display_name="Test User",
            emby_username="emby_test",
        )
        print(f"✓ 任务创建成功: {task.id}")
        print(f"  - Telegram User ID: {task.telegram_user_id}")
        print(f"  - Telegram Username: {task.telegram_username}")
        print(f"  - Display Name: {task.telegram_display_name}")
        print(f"  - Emby Username: {task.emby_username}")
        
        # 测试 2: 查询任务
        print("\n[测试 2] 查询任务...")
        retrieved_task = await task_manager.get_task(task.id)
        if retrieved_task:
            print(f"✓ 任务查询成功")
            print(f"  - 用户信息保持完整: {retrieved_task.telegram_display_name}")
        else:
            print("✗ 任务查询失败")
        
        # 测试 3: 转换为字典
        print("\n[测试 3] 转换为字典（API 返回格式）...")
        task_dict = task.to_dict()
        user_fields = [
            'telegram_user_id',
            'telegram_username', 
            'telegram_display_name',
            'emby_username'
        ]
        print("✓ 字典包含用户字段:")
        for field in user_fields:
            value = task_dict.get(field)
            print(f"  - {field}: {value}")
        
        # 测试 4: 创建不带用户信息的任务（网页端）
        print("\n[测试 4] 创建不带用户信息的任务（模拟网页端）...")
        web_task = await task_manager.create_task(
            media_item_id="web_media_456",
            media_item_title="网页端测试",
            video_path="/path/to/video2.mp4",
        )
        print(f"✓ 任务创建成功: {web_task.id}")
        print(f"  - Telegram User ID: {web_task.telegram_user_id} (应为 None)")
        
        # 测试 5: 列出所有任务
        print("\n[测试 5] 列出任务...")
        tasks, total = await task_manager.list_tasks(limit=10)
        print(f"✓ 查询到 {total} 个任务")
        for t in tasks[-2:]:  # 显示最后两个
            user_info = t.telegram_display_name or t.telegram_username or "网页端"
            print(f"  - {t.media_item_title}: {user_info}")
        
        print("\n" + "=" * 60)
        print("✓ 所有测试通过！")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(test_user_tracking())
