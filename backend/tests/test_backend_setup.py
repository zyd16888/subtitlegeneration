"""
测试后端核心功能
用于任务12的检查点验证
"""
import sys
import asyncio
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def test_imports():
    """测试所有核心模块是否可以导入"""
    print("=" * 60)
    print("测试 1: 检查模块导入")
    print("=" * 60)
    
    try:
        # 测试配置
        from backend.config.settings import settings
        print("✓ 配置模块导入成功")
        print(f"  - 应用名称: {settings.app_name}")
        print(f"  - Redis URL: {settings.redis_url}")
        print(f"  - 数据库 URL: {settings.database_url}")
        
        # 测试数据库模型
        from backend.models.base import Base, get_db, init_db
        from backend.models.task import Task
        from backend.models.config import SystemConfig
        print("✓ 数据库模型导入成功")
        
        # 测试服务
        from backend.services.config_manager import ConfigManager
        from backend.services.emby_connector import EmbyConnector
        from backend.services.audio_extractor import AudioExtractor
        from backend.services.asr_engine import ASREngine, SherpaOnnxEngine, CloudASREngine
        from backend.services.translation_service import TranslationService, OpenAITranslator
        from backend.services.subtitle_generator import SubtitleGenerator
        from backend.services.task_manager import TaskManager
        print("✓ 服务模块导入成功")
        
        # 测试 API
        from backend.api import media, tasks, config, stats
        print("✓ API 模块导入成功")
        
        # 测试 Celery 任务
        from backend.tasks.celery_app import celery_app
        from backend.tasks.subtitle_tasks import generate_subtitle_task
        print("✓ Celery 任务模块导入成功")
        
        # 测试工具
        from backend.utils.logger import setup_logger, get_logger
        print("✓ 工具模块导入成功")
        
        print("\n所有模块导入成功！\n")
        return True
    except Exception as e:
        print(f"✗ 模块导入失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_redis_connection():
    """测试 Redis 连接"""
    print("=" * 60)
    print("测试 2: 检查 Redis 连接")
    print("=" * 60)
    
    try:
        import redis
        from backend.config.settings import settings
        
        # 解析 Redis URL
        r = redis.from_url(settings.redis_url)
        
        # 测试连接
        r.ping()
        print("✓ Redis 连接成功")
        
        # 测试基本操作
        r.set("test_key", "test_value")
        value = r.get("test_key")
        assert value.decode() == "test_value"
        r.delete("test_key")
        print("✓ Redis 读写操作正常")
        
        # 获取 Redis 信息
        info = r.info()
        print(f"  - Redis 版本: {info.get('redis_version', 'unknown')}")
        print(f"  - 已用内存: {info.get('used_memory_human', 'unknown')}")
        
        print("\nRedis 连接测试通过！\n")
        return True
    except Exception as e:
        print(f"✗ Redis 连接失败: {e}")
        print("  请确保 Redis 服务正在运行在 localhost:6379")
        return False


def test_database():
    """测试数据库初始化"""
    print("=" * 60)
    print("测试 3: 检查数据库初始化")
    print("=" * 60)
    
    try:
        from backend.models.base import init_db, get_db
        from backend.models.task import Task, TaskStatus
        from backend.models.config import SystemConfig
        from sqlalchemy import inspect
        
        # 初始化数据库
        init_db()
        print("✓ 数据库初始化成功")
        
        # 检查表是否创建
        db = next(get_db())
        inspector = inspect(db.bind)
        tables = inspector.get_table_names()
        
        expected_tables = ['tasks', 'system_config']
        for table in expected_tables:
            if table in tables:
                print(f"✓ 表 '{table}' 已创建")
            else:
                print(f"✗ 表 '{table}' 未找到")
                return False
        
        # 测试基本的数据库操作
        # 创建一个测试任务
        import uuid
        test_task = Task(
            id=str(uuid.uuid4()),
            media_item_id="test_item_123",
            status=TaskStatus.PENDING,
            progress=0
        )
        db.add(test_task)
        db.commit()
        print("✓ 数据库写入操作成功")
        
        # 查询任务
        task = db.query(Task).filter_by(media_item_id="test_item_123").first()
        assert task is not None
        assert task.status == TaskStatus.PENDING
        print("✓ 数据库查询操作成功")
        
        # 删除测试数据
        db.delete(task)
        db.commit()
        print("✓ 数据库删除操作成功")
        
        print("\n数据库测试通过！\n")
        return True
    except Exception as e:
        print(f"✗ 数据库测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_services():
    """测试核心服务"""
    print("=" * 60)
    print("测试 4: 检查核心服务")
    print("=" * 60)
    
    try:
        from backend.services.config_manager import ConfigManager
        from backend.services.task_manager import TaskManager
        from backend.models.base import get_db
        from backend.models.task import Task
        
        db = next(get_db())
        
        # 测试 ConfigManager
        config_manager = ConfigManager(db)
        config = await config_manager.get_config()
        print("✓ ConfigManager 初始化成功")
        print(f"  - 当前配置: ASR={config.asr_engine}, 翻译={config.translation_service}")
        
        # 测试 TaskManager
        task_manager = TaskManager(db)
        
        # 创建测试任务
        task = await task_manager.create_task(
            media_item_id="test_media_item_456",
            media_item_title="测试视频",
            video_path="/path/to/test.mp4"
        )
        print(f"✓ TaskManager 创建任务成功 (ID: {task.id})")
        
        # 更新任务状态
        from backend.models.task import TaskStatus
        await task_manager.update_task_status(task.id, TaskStatus.PROCESSING, 50)
        updated_task = await task_manager.get_task(task.id)
        assert updated_task.status == TaskStatus.PROCESSING
        assert updated_task.progress == 50
        print("✓ TaskManager 更新任务成功")
        
        # 获取任务列表
        tasks = await task_manager.list_tasks()
        assert len(tasks) > 0
        print(f"✓ TaskManager 查询任务列表成功 (共 {len(tasks)} 个任务)")
        
        # 获取统计信息
        stats = await task_manager.get_statistics()
        print(f"✓ TaskManager 获取统计信息成功")
        print(f"  - 总任务数: {stats.total}")
        print(f"  - 成功: {stats.completed}, 失败: {stats.failed}, 进行中: {stats.processing}")
        
        # 清理测试数据
        db.query(Task).filter_by(media_item_id="test_media_item_456").delete()
        db.commit()
        
        print("\n核心服务测试通过！\n")
        return True
    except Exception as e:
        print(f"✗ 核心服务测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_fastapi_app():
    """测试 FastAPI 应用"""
    print("=" * 60)
    print("测试 5: 检查 FastAPI 应用")
    print("=" * 60)
    
    try:
        from fastapi.testclient import TestClient
        from backend.main import app
        
        client = TestClient(app)
        
        # 测试根路径
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        print("✓ 根路径 (/) 响应正常")
        
        # 测试健康检查
        response = client.get("/health")
        assert response.status_code == 200
        print("✓ 健康检查 (/health) 响应正常")
        
        # 测试获取配置
        response = client.get("/api/config")
        assert response.status_code == 200
        print("✓ 获取配置 API (/api/config) 响应正常")
        
        # 测试获取任务列表
        response = client.get("/api/tasks")
        assert response.status_code == 200
        print("✓ 获取任务列表 API (/api/tasks) 响应正常")
        
        # 测试获取统计信息
        response = client.get("/api/stats")
        assert response.status_code == 200
        data = response.json()
        print("✓ 获取统计信息 API (/api/stats) 响应正常")
        print(f"  - 统计数据: {data}")
        
        print("\nFastAPI 应用测试通过！\n")
        return True
    except Exception as e:
        print(f"✗ FastAPI 应用测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_celery_config():
    """测试 Celery 配置"""
    print("=" * 60)
    print("测试 6: 检查 Celery 配置")
    print("=" * 60)
    
    try:
        from backend.tasks.celery_app import celery_app
        from backend.tasks.subtitle_tasks import generate_subtitle_task
        
        # 检查 Celery 配置
        print(f"✓ Celery 应用初始化成功")
        print(f"  - Broker: {celery_app.conf.broker_url}")
        print(f"  - Backend: {celery_app.conf.result_backend}")
        
        # 检查任务是否注册
        registered_tasks = list(celery_app.tasks.keys())
        print(f"✓ 已注册 {len(registered_tasks)} 个任务")
        
        # 检查字幕生成任务
        if 'backend.tasks.subtitle_tasks.generate_subtitle_task' in registered_tasks:
            print("✓ 字幕生成任务已注册")
        else:
            print("✗ 字幕生成任务未注册")
            return False
        
        print("\nCelery 配置测试通过！\n")
        print("注意: 要运行 Celery worker，请在另一个终端执行:")
        print("  conda activate ame")
        print("  cd backend")
        print("  celery -A tasks.celery_app worker --loglevel=info --pool=solo")
        print()
        return True
    except Exception as e:
        print(f"✗ Celery 配置测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("后端核心功能测试 - 任务12检查点")
    print("=" * 60 + "\n")
    
    results = []
    
    # 运行所有测试
    results.append(("模块导入", test_imports()))
    results.append(("Redis 连接", test_redis_connection()))
    results.append(("数据库", test_database()))
    results.append(("核心服务", asyncio.run(test_services())))
    results.append(("FastAPI 应用", asyncio.run(test_fastapi_app())))
    results.append(("Celery 配置", test_celery_config()))
    
    # 打印总结
    print("=" * 60)
    print("测试总结")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✓ 通过" if result else "✗ 失败"
        print(f"{name:20s}: {status}")
    
    print(f"\n总计: {passed}/{total} 测试通过")
    
    if passed == total:
        print("\n🎉 所有测试通过！后端核心功能正常工作。")
        return 0
    else:
        print(f"\n⚠️  有 {total - passed} 个测试失败，请检查上述错误信息。")
        return 1


if __name__ == "__main__":
    sys.exit(main())
