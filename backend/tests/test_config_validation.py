"""
测试配置验证功能
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from main import app
from models.base import Base, get_db
from models.config import SystemConfig


# 创建测试数据库
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_config_validation.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    """覆盖数据库依赖"""
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(scope="function")
def client():
    """创建测试客户端"""
    # 创建表
    Base.metadata.create_all(bind=engine)
    
    client = TestClient(app)
    yield client
    
    # 清理
    Base.metadata.drop_all(bind=engine)


def test_validate_config_empty(client):
    """测试空配置验证"""
    response = client.get("/api/config/validate")
    assert response.status_code == 200
    
    data = response.json()
    assert data["is_valid"] is False
    assert len(data["missing_fields"]) > 0
    assert "Emby Server URL" in data["missing_fields"]
    assert "Emby API Key" in data["missing_fields"]


def test_validate_config_partial_emby(client):
    """测试部分 Emby 配置"""
    # 只配置 Emby URL
    client.patch("/api/config", json={"emby_url": "http://localhost:8096"})
    
    response = client.get("/api/config/validate")
    assert response.status_code == 200
    
    data = response.json()
    assert data["is_valid"] is False
    assert "Emby API Key" in data["missing_fields"]


def test_validate_config_sherpa_onnx_without_model(client):
    """测试 Sherpa-ONNX 引擎但没有模型路径"""
    # 配置 Emby 和 ASR 引擎
    client.patch("/api/config", json={
        "emby_url": "http://localhost:8096",
        "emby_api_key": "test_key",
        "asr_engine": "sherpa-onnx"
    })
    
    response = client.get("/api/config/validate")
    assert response.status_code == 200
    
    data = response.json()
    assert data["is_valid"] is False
    assert "ASR 模型路径" in data["missing_fields"]


def test_validate_config_cloud_asr_without_credentials(client):
    """测试云端 ASR 但没有凭证"""
    # 先配置完整的 Emby 和 ASR 基础
    client.patch("/api/config", json={
        "emby_url": "http://localhost:8096",
        "emby_api_key": "test_key",
        "asr_engine": "sherpa-onnx",
        "asr_model_path": "/path/to/model",
        "translation_service": "openai",
        "openai_api_key": "sk-test",
        "openai_model": "gpt-4"
    })
    
    # 然后切换到云端 ASR（这会导致缺少云端凭证）
    # 注意：partial_update 会验证，所以这个请求会失败
    # 我们直接测试验证 API 在数据库中手动设置的情况
    
    # 直接通过数据库设置（绕过验证）
    from models.config import SystemConfig
    db = next(override_get_db())
    config = db.query(SystemConfig).filter(SystemConfig.key == "asr_engine").first()
    if config:
        config.value = '"cloud"'
    else:
        db.add(SystemConfig(key="asr_engine", value='"cloud"'))
    
    # 删除云端 ASR 凭证
    db.query(SystemConfig).filter(SystemConfig.key == "cloud_asr_url").delete()
    db.query(SystemConfig).filter(SystemConfig.key == "cloud_asr_api_key").delete()
    db.commit()
    db.close()
    
    response = client.get("/api/config/validate")
    assert response.status_code == 200
    
    data = response.json()
    assert data["is_valid"] is False
    assert "云端 ASR URL" in data["missing_fields"]
    assert "云端 ASR API Key" in data["missing_fields"]


def test_validate_config_openai_without_key(client):
    """测试 OpenAI 翻译但没有 API Key"""
    # 配置 Emby、ASR 和翻译服务
    client.patch("/api/config", json={
        "emby_url": "http://localhost:8096",
        "emby_api_key": "test_key",
        "asr_engine": "sherpa-onnx",
        "asr_model_path": "/path/to/model",
        "translation_service": "openai"
    })
    
    response = client.get("/api/config/validate")
    assert response.status_code == 200
    
    data = response.json()
    assert data["is_valid"] is False
    assert "OpenAI API Key" in data["missing_fields"]


def test_validate_config_complete(client):
    """测试完整配置"""
    # 配置所有必需项
    client.patch("/api/config", json={
        "emby_url": "http://localhost:8096",
        "emby_api_key": "test_key",
        "asr_engine": "sherpa-onnx",
        "asr_model_path": "/path/to/model",
        "translation_service": "openai",
        "openai_api_key": "sk-test",
        "openai_model": "gpt-4"
    })
    
    response = client.get("/api/config/validate")
    assert response.status_code == 200
    
    data = response.json()
    assert data["is_valid"] is True
    assert len(data["missing_fields"]) == 0
    assert "完整" in data["message"]


def test_validate_config_deepseek(client):
    """测试 DeepSeek 翻译配置"""
    # 配置 DeepSeek
    client.patch("/api/config", json={
        "emby_url": "http://localhost:8096",
        "emby_api_key": "test_key",
        "asr_engine": "sherpa-onnx",
        "asr_model_path": "/path/to/model",
        "translation_service": "deepseek",
        "deepseek_api_key": "test_deepseek_key"
    })
    
    response = client.get("/api/config/validate")
    assert response.status_code == 200
    
    data = response.json()
    assert data["is_valid"] is True
    assert len(data["missing_fields"]) == 0


def test_validate_config_local_llm(client):
    """测试本地 LLM 翻译配置"""
    # 配置本地 LLM
    client.patch("/api/config", json={
        "emby_url": "http://localhost:8096",
        "emby_api_key": "test_key",
        "asr_engine": "cloud",
        "cloud_asr_url": "http://localhost:5000",
        "cloud_asr_api_key": "test_asr_key",
        "translation_service": "local",
        "local_llm_url": "http://localhost:11434"
    })
    
    response = client.get("/api/config/validate")
    assert response.status_code == 200
    
    data = response.json()
    assert data["is_valid"] is True
    assert len(data["missing_fields"]) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
