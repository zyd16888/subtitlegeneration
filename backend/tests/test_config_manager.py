"""
ConfigManager 服务测试脚本
"""
import sys
import os
import asyncio

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.models import init_db, SessionLocal
from backend.services import ConfigManager, SystemConfigData


async def test_config_manager():
    """测试配置管理器"""
    print("初始化数据库...")
    init_db()
    print("✓ 数据库初始化成功")
    
    # 创建数据库会话
    db = SessionLocal()
    
    try:
        # 创建配置管理器
        config_manager = ConfigManager(db)
        print("\n✓ 创建 ConfigManager 实例")
        
        # 测试获取默认配置
        print("\n测试获取配置...")
        config = await config_manager.get_config()
        print(f"✓ 获取配置成功: asr_engine={config.asr_engine}, translation_service={config.translation_service}")
        
        # 测试更新配置
        print("\n测试更新配置...")
        config.emby_url = "http://localhost:8096"
        config.emby_api_key = "test_api_key_123"
        config.openai_api_key = "sk-test123"
        
        updated_config = await config_manager.update_config(config)
        print(f"✓ 更新配置成功: emby_url={updated_config.emby_url}")
        
        # 测试配置验证 - 有效配置
        print("\n测试配置验证（有效配置）...")
        valid_config = SystemConfigData(
            emby_url="http://localhost:8096",
            emby_api_key="test_key",
            asr_engine="sherpa-onnx",
            asr_model_path="/path/to/model",
            translation_service="openai",
            openai_api_key="sk-test"
        )
        validation_result = await config_manager.validate_config(valid_config)
        assert validation_result.valid, f"配置应该有效，但验证失败: {validation_result.errors}"
        print(f"✓ 配置验证通过")
        
        # 测试配置验证 - 无效配置（缺少 API Key）
        print("\n测试配置验证（无效配置）...")
        invalid_config = SystemConfigData(
            emby_url="http://localhost:8096",
            # 缺少 emby_api_key
            asr_engine="sherpa-onnx",
            # 缺少 asr_model_path
            translation_service="openai"
            # 缺少 openai_api_key
        )
        validation_result = await config_manager.validate_config(invalid_config)
        assert not validation_result.valid, "配置应该无效"
        print(f"✓ 配置验证正确识别错误: {validation_result.errors}")
        
        # 测试 URL 格式验证
        print("\n测试 URL 格式验证...")
        try:
            invalid_url_config = SystemConfigData(
                emby_url="invalid-url",  # 无效的 URL 格式
                emby_api_key="test_key"
            )
            print("❌ URL 验证失败 - 应该抛出异常")
        except ValueError as e:
            print(f"✓ URL 格式验证正确: {e}")
        
        print("\n✅ 所有 ConfigManager 测试通过!")
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(test_config_manager())
