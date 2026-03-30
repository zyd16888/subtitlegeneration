"""
API 端点测试

测试所有 FastAPI 路由和端点的基本功能
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os
import tempfile

from backend.main import app
from backend.models.base import Base, get_db
from backend.models.config import SystemConfig
from backend.models.task import Task, TaskStatus

# 创建测试数据库
TEST_DATABASE_URL = "sqlite:///./test_api.db"
engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    """覆盖数据库依赖"""
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


# 覆盖依赖
app.dependency_overrides[get_db] = override_get_db

# 创建测试客户端
client = TestClient(app)


@pytest.fixture(scope="function", autouse=True)
def setup_database():
    """每个测试前设置数据库"""
    # 创建所有表
    Base.metadata.create_all(bind=engine)
    
    # 添加测试配置
    db = TestingSessionLocal()
    try:
        # 添加基本配置
        configs = [
            SystemConfig(key="emby_url", value="http://localhost:8096"),
            SystemConfig(key="emby_api_key", value="test_api_key"),
            SystemConfig(key="asr_engine", value="sherpa-onnx"),
            SystemConfig(key="asr_model_path", value="/path/to/model"),
            SystemConfig(key="translation_service", value="openai"),
            SystemConfig(key="openai_api_key", value="test_openai_key"),
            SystemConfig(key="openai_model", value="gpt-4"),
            SystemConfig(key="max_concurrent_tasks", value="2"),
            SystemConfig(key="temp_dir", value="/tmp/subtitle_service"),
        ]
        for config in configs:
            db.add(config)
        db.commit()
    finally:
        db.close()
    
    yield
    
    # 清理数据库
    Base.metadata.drop_all(bind=engine)


def test_root_endpoint():
    """测试根路径"""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "message" in data


def test_health_check():
    """测试健康检查端点"""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"


def test_get_config():
    """测试获取配置"""
    response = client.get("/api/config")
    assert response.status_code == 200
    data = response.json()
    assert data["emby_url"] == "http://localhost:8096"
    assert data["asr_engine"] == "sherpa-onnx"
    assert data["translation_service"] == "openai"


def test_update_config():
    """测试更新配置"""
    new_config = {
        "emby_url": "http://localhost:8096",
        "emby_api_key": "new_api_key",
        "asr_engine": "sherpa-onnx",
        "asr_model_path": "/new/path/to/model",
        "translation_service": "deepseek",
        "deepseek_api_key": "test_deepseek_key",
        "max_concurrent_tasks": 3,
        "temp_dir": "/tmp/subtitle_service"
    }
    
    response = client.put("/api/config", json=new_config)
    assert response.status_code == 200
    data = response.json()
    assert data["emby_api_key"] == "new_api_key"
    assert data["translation_service"] == "deepseek"


def test_get_tasks_empty():
    """测试获取空任务列表"""
    response = client.get("/api/tasks")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert len(data["items"]) == 0


def test_get_tasks_with_data():
    """测试获取任务列表（有数据）"""
    # 添加测试任务
    db = TestingSessionLocal()
    try:
        task = Task(
            id="test-task-1",
            media_item_id="media-1",
            media_item_title="Test Movie",
            video_path="/path/to/video.mp4",
            status=TaskStatus.PENDING,
            progress=0
        )
        db.add(task)
        db.commit()
    finally:
        db.close()
    
    response = client.get("/api/tasks")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["id"] == "test-task-1"


def test_get_task_by_id():
    """测试获取单个任务"""
    # 添加测试任务
    db = TestingSessionLocal()
    try:
        task = Task(
            id="test-task-2",
            media_item_id="media-2",
            media_item_title="Test Series",
            video_path="/path/to/series.mp4",
            status=TaskStatus.PROCESSING,
            progress=50
        )
        db.add(task)
        db.commit()
    finally:
        db.close()
    
    response = client.get("/api/tasks/test-task-2")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "test-task-2"
    assert data["status"] == "processing"
    assert data["progress"] == 50


def test_get_task_not_found():
    """测试获取不存在的任务"""
    response = client.get("/api/tasks/non-existent-task")
    assert response.status_code == 404


def test_cancel_task():
    """测试取消任务"""
    # 添加测试任务
    db = TestingSessionLocal()
    try:
        task = Task(
            id="test-task-3",
            media_item_id="media-3",
            media_item_title="Test Movie 3",
            video_path="/path/to/video3.mp4",
            status=TaskStatus.PENDING,
            progress=0
        )
        db.add(task)
        db.commit()
    finally:
        db.close()
    
    response = client.post("/api/tasks/test-task-3/cancel")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "cancelled"


def test_retry_task():
    """测试重试任务"""
    # 添加失败的测试任务
    db = TestingSessionLocal()
    try:
        task = Task(
            id="test-task-4",
            media_item_id="media-4",
            media_item_title="Test Movie 4",
            video_path="/path/to/video4.mp4",
            status=TaskStatus.FAILED,
            progress=50,
            error_message="Test error"
        )
        db.add(task)
        db.commit()
    finally:
        db.close()
    
    response = client.post("/api/tasks/test-task-4/retry")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "pending"
    assert data["media_item_id"] == "media-4"
    # 新任务应该有不同的 ID
    assert data["id"] != "test-task-4"


def test_get_statistics():
    """测试获取统计信息"""
    # 添加多个测试任务
    db = TestingSessionLocal()
    try:
        tasks = [
            Task(id="task-1", media_item_id="m1", status=TaskStatus.PENDING, progress=0),
            Task(id="task-2", media_item_id="m2", status=TaskStatus.PROCESSING, progress=50),
            Task(id="task-3", media_item_id="m3", status=TaskStatus.COMPLETED, progress=100),
            Task(id="task-4", media_item_id="m4", status=TaskStatus.FAILED, progress=30),
        ]
        for task in tasks:
            db.add(task)
        db.commit()
    finally:
        db.close()
    
    response = client.get("/api/stats")
    assert response.status_code == 200
    data = response.json()
    
    # 检查任务统计
    assert data["task_statistics"]["total"] == 4
    assert data["task_statistics"]["pending"] == 1
    assert data["task_statistics"]["processing"] == 1
    assert data["task_statistics"]["completed"] == 1
    assert data["task_statistics"]["failed"] == 1
    
    # 检查系统状态
    assert "system_status" in data
    assert "emby_connected" in data["system_status"]
    assert "asr_configured" in data["system_status"]
    assert "translation_configured" in data["system_status"]


if __name__ == "__main__":
    # 清理测试数据库
    if os.path.exists("test_api.db"):
        os.remove("test_api.db")
    
    # 运行测试
    pytest.main([__file__, "-v"])
