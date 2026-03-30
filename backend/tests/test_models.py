"""
数据库模型单元测试

测试 Task 和 SystemConfig 模型的 CRUD 操作
需求: 12.1, 12.2
"""
import pytest
import uuid
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from backend.models.base import Base
from backend.models.task import Task, TaskStatus
from backend.models.config import SystemConfig


@pytest.fixture
def db_session():
    """创建测试数据库会话"""
    # 使用内存数据库进行测试
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    session = TestSessionLocal()
    try:
        yield session
    finally:
        session.close()


class TestTaskModel:
    """测试 Task 模型的 CRUD 操作"""
    
    def test_create_task(self, db_session: Session):
        """测试创建任务"""
        task_id = str(uuid.uuid4())
        task = Task(
            id=task_id,
            media_item_id="test_media_123",
            media_item_title="测试视频",
            video_path="/path/to/video.mp4",
            status=TaskStatus.PENDING,
            progress=0
        )
        
        db_session.add(task)
        db_session.commit()
        
        # 验证任务已创建
        assert task.id == task_id
        assert task.media_item_id == "test_media_123"
        assert task.status == TaskStatus.PENDING
        assert task.progress == 0
        assert task.created_at is not None
        assert task.completed_at is None
        assert task.error_message is None
    
    def test_read_task(self, db_session: Session):
        """测试读取任务"""
        task_id = str(uuid.uuid4())
        task = Task(
            id=task_id,
            media_item_id="test_media_456",
            media_item_title="另一个测试视频",
            video_path="/path/to/another.mp4",
            status=TaskStatus.PROCESSING,
            progress=50
        )
        
        db_session.add(task)
        db_session.commit()
        
        # 通过 ID 查询任务
        retrieved_task = db_session.query(Task).filter(Task.id == task_id).first()
        
        assert retrieved_task is not None
        assert retrieved_task.id == task_id
        assert retrieved_task.media_item_id == "test_media_456"
        assert retrieved_task.media_item_title == "另一个测试视频"
        assert retrieved_task.status == TaskStatus.PROCESSING
        assert retrieved_task.progress == 50
    
    def test_update_task(self, db_session: Session):
        """测试更新任务"""
        task_id = str(uuid.uuid4())
        task = Task(
            id=task_id,
            media_item_id="test_media_789",
            status=TaskStatus.PENDING,
            progress=0
        )
        
        db_session.add(task)
        db_session.commit()
        
        # 更新任务状态和进度
        task.status = TaskStatus.PROCESSING
        task.progress = 75
        db_session.commit()
        
        # 验证更新
        updated_task = db_session.query(Task).filter(Task.id == task_id).first()
        assert updated_task.status == TaskStatus.PROCESSING
        assert updated_task.progress == 75
        
        # 更新为完成状态
        task.status = TaskStatus.COMPLETED
        task.progress = 100
        task.completed_at = datetime.utcnow()
        db_session.commit()
        
        # 验证完成状态
        completed_task = db_session.query(Task).filter(Task.id == task_id).first()
        assert completed_task.status == TaskStatus.COMPLETED
        assert completed_task.progress == 100
        assert completed_task.completed_at is not None
    
    def test_delete_task(self, db_session: Session):
        """测试删除任务"""
        task_id = str(uuid.uuid4())
        task = Task(
            id=task_id,
            media_item_id="test_media_delete",
            status=TaskStatus.PENDING
        )
        
        db_session.add(task)
        db_session.commit()
        
        # 验证任务存在
        assert db_session.query(Task).filter(Task.id == task_id).first() is not None
        
        # 删除任务
        db_session.delete(task)
        db_session.commit()
        
        # 验证任务已删除
        assert db_session.query(Task).filter(Task.id == task_id).first() is None
    
    def test_task_status_enum(self, db_session: Session):
        """测试任务状态枚举"""
        task_id = str(uuid.uuid4())
        
        # 测试所有状态
        for status in TaskStatus:
            task = Task(
                id=f"{task_id}_{status.value}",
                media_item_id=f"test_{status.value}",
                status=status
            )
            db_session.add(task)
        
        db_session.commit()
        
        # 验证所有状态都已保存
        for status in TaskStatus:
            task = db_session.query(Task).filter(
                Task.id == f"{task_id}_{status.value}"
            ).first()
            assert task is not None
            assert task.status == status
    
    def test_task_error_message(self, db_session: Session):
        """测试任务错误信息"""
        task_id = str(uuid.uuid4())
        error_msg = "测试错误: 音频提取失败"
        
        task = Task(
            id=task_id,
            media_item_id="test_error",
            status=TaskStatus.FAILED,
            error_message=error_msg
        )
        
        db_session.add(task)
        db_session.commit()
        
        # 验证错误信息
        failed_task = db_session.query(Task).filter(Task.id == task_id).first()
        assert failed_task.status == TaskStatus.FAILED
        assert failed_task.error_message == error_msg
    
    def test_query_tasks_by_status(self, db_session: Session):
        """测试按状态查询任务"""
        # 创建不同状态的任务
        tasks = [
            Task(id=str(uuid.uuid4()), media_item_id="m1", status=TaskStatus.PENDING),
            Task(id=str(uuid.uuid4()), media_item_id="m2", status=TaskStatus.PROCESSING),
            Task(id=str(uuid.uuid4()), media_item_id="m3", status=TaskStatus.COMPLETED),
            Task(id=str(uuid.uuid4()), media_item_id="m4", status=TaskStatus.PENDING),
        ]
        
        for task in tasks:
            db_session.add(task)
        db_session.commit()
        
        # 查询待处理任务
        pending_tasks = db_session.query(Task).filter(
            Task.status == TaskStatus.PENDING
        ).all()
        assert len(pending_tasks) == 2
        
        # 查询处理中任务
        processing_tasks = db_session.query(Task).filter(
            Task.status == TaskStatus.PROCESSING
        ).all()
        assert len(processing_tasks) == 1
        
        # 查询已完成任务
        completed_tasks = db_session.query(Task).filter(
            Task.status == TaskStatus.COMPLETED
        ).all()
        assert len(completed_tasks) == 1
    
    def test_query_tasks_by_media_item_id(self, db_session: Session):
        """测试按媒体项 ID 查询任务"""
        media_id = "test_media_unique"
        
        # 为同一媒体项创建多个任务
        tasks = [
            Task(id=str(uuid.uuid4()), media_item_id=media_id, status=TaskStatus.FAILED),
            Task(id=str(uuid.uuid4()), media_item_id=media_id, status=TaskStatus.COMPLETED),
            Task(id=str(uuid.uuid4()), media_item_id="other_media", status=TaskStatus.PENDING),
        ]
        
        for task in tasks:
            db_session.add(task)
        db_session.commit()
        
        # 查询特定媒体项的任务
        media_tasks = db_session.query(Task).filter(
            Task.media_item_id == media_id
        ).all()
        assert len(media_tasks) == 2


class TestSystemConfigModel:
    """测试 SystemConfig 模型的存储和读取"""
    
    def test_create_config(self, db_session: Session):
        """测试创建配置"""
        config = SystemConfig(
            key="emby_url",
            value="http://localhost:8096",
            description="Emby 服务器地址"
        )
        
        db_session.add(config)
        db_session.commit()
        
        # 验证配置已创建
        assert config.key == "emby_url"
        assert config.value == "http://localhost:8096"
        assert config.description == "Emby 服务器地址"
    
    def test_read_config(self, db_session: Session):
        """测试读取配置"""
        config = SystemConfig(
            key="emby_api_key",
            value="test_api_key_12345",
            description="Emby API 密钥"
        )
        
        db_session.add(config)
        db_session.commit()
        
        # 通过键查询配置
        retrieved_config = db_session.query(SystemConfig).filter(
            SystemConfig.key == "emby_api_key"
        ).first()
        
        assert retrieved_config is not None
        assert retrieved_config.key == "emby_api_key"
        assert retrieved_config.value == "test_api_key_12345"
        assert retrieved_config.description == "Emby API 密钥"
    
    def test_update_config(self, db_session: Session):
        """测试更新配置"""
        config = SystemConfig(
            key="asr_engine",
            value="sherpa-onnx",
            description="ASR 引擎类型"
        )
        
        db_session.add(config)
        db_session.commit()
        
        # 更新配置值
        config.value = "cloud-asr"
        db_session.commit()
        
        # 验证更新
        updated_config = db_session.query(SystemConfig).filter(
            SystemConfig.key == "asr_engine"
        ).first()
        assert updated_config.value == "cloud-asr"
    
    def test_delete_config(self, db_session: Session):
        """测试删除配置"""
        config = SystemConfig(
            key="temp_config",
            value="temp_value"
        )
        
        db_session.add(config)
        db_session.commit()
        
        # 验证配置存在
        assert db_session.query(SystemConfig).filter(
            SystemConfig.key == "temp_config"
        ).first() is not None
        
        # 删除配置
        db_session.delete(config)
        db_session.commit()
        
        # 验证配置已删除
        assert db_session.query(SystemConfig).filter(
            SystemConfig.key == "temp_config"
        ).first() is None
    
    def test_config_without_description(self, db_session: Session):
        """测试创建没有描述的配置"""
        config = SystemConfig(
            key="simple_config",
            value="simple_value"
        )
        
        db_session.add(config)
        db_session.commit()
        
        # 验证配置
        retrieved_config = db_session.query(SystemConfig).filter(
            SystemConfig.key == "simple_config"
        ).first()
        assert retrieved_config is not None
        assert retrieved_config.description is None
    
    def test_multiple_configs(self, db_session: Session):
        """测试存储多个配置"""
        configs = [
            SystemConfig(key="config1", value="value1", description="配置1"),
            SystemConfig(key="config2", value="value2", description="配置2"),
            SystemConfig(key="config3", value="value3", description="配置3"),
        ]
        
        for config in configs:
            db_session.add(config)
        db_session.commit()
        
        # 验证所有配置都已保存
        all_configs = db_session.query(SystemConfig).all()
        assert len(all_configs) >= 3
        
        # 验证每个配置
        for i in range(1, 4):
            config = db_session.query(SystemConfig).filter(
                SystemConfig.key == f"config{i}"
            ).first()
            assert config is not None
            assert config.value == f"value{i}"
    
    def test_config_key_uniqueness(self, db_session: Session):
        """测试配置键的唯一性"""
        config1 = SystemConfig(key="unique_key", value="value1")
        db_session.add(config1)
        db_session.commit()
        
        # 尝试创建相同键的配置
        config2 = SystemConfig(key="unique_key", value="value2")
        db_session.add(config2)
        
        # 应该抛出异常
        with pytest.raises(Exception):
            db_session.commit()
        
        db_session.rollback()
    
    def test_get_all_configs(self, db_session: Session):
        """测试获取所有配置"""
        configs = [
            SystemConfig(key="emby_url", value="http://localhost:8096"),
            SystemConfig(key="emby_api_key", value="key123"),
            SystemConfig(key="asr_engine", value="sherpa-onnx"),
            SystemConfig(key="translation_service", value="openai"),
        ]
        
        for config in configs:
            db_session.add(config)
        db_session.commit()
        
        # 获取所有配置
        all_configs = db_session.query(SystemConfig).all()
        assert len(all_configs) >= 4
        
        # 验证配置键
        config_keys = [c.key for c in all_configs]
        assert "emby_url" in config_keys
        assert "emby_api_key" in config_keys
        assert "asr_engine" in config_keys
        assert "translation_service" in config_keys
