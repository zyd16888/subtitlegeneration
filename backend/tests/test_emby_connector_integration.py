"""
EmbyConnector 集成测试示例

注意：这些测试需要实际的 Emby Server 才能运行
在 CI/CD 环境中应该跳过这些测试
"""
import pytest
import os
from backend.services.emby_connector import EmbyConnector


# 标记为集成测试，默认跳过
pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_INTEGRATION_TESTS"),
    reason="集成测试需要设置 RUN_INTEGRATION_TESTS 环境变量"
)


@pytest.fixture
def emby_url():
    """从环境变量获取 Emby URL"""
    return os.getenv("EMBY_URL", "http://localhost:8096")


@pytest.fixture
def emby_api_key():
    """从环境变量获取 Emby API Key"""
    return os.getenv("EMBY_API_KEY", "")


@pytest.mark.asyncio
async def test_real_connection(emby_url, emby_api_key):
    """测试真实的 Emby 连接"""
    if not emby_api_key:
        pytest.skip("需要设置 EMBY_API_KEY 环境变量")
    
    async with EmbyConnector(emby_url, emby_api_key) as connector:
        result = await connector.test_connection()
        assert result is True


@pytest.mark.asyncio
async def test_real_get_libraries(emby_url, emby_api_key):
    """测试获取真实的媒体库列表"""
    if not emby_api_key:
        pytest.skip("需要设置 EMBY_API_KEY 环境变量")
    
    async with EmbyConnector(emby_url, emby_api_key) as connector:
        libraries = await connector.get_libraries()
        assert isinstance(libraries, list)
        
        if libraries:
            # 验证第一个媒体库的结构
            lib = libraries[0]
            assert hasattr(lib, "id")
            assert hasattr(lib, "name")
            assert hasattr(lib, "type")


@pytest.mark.asyncio
async def test_real_get_media_items(emby_url, emby_api_key):
    """测试获取真实的媒体项列表"""
    if not emby_api_key:
        pytest.skip("需要设置 EMBY_API_KEY 环境变量")
    
    async with EmbyConnector(emby_url, emby_api_key) as connector:
        # 先获取媒体库
        libraries = await connector.get_libraries()
        if not libraries:
            pytest.skip("没有可用的媒体库")
        
        # 获取第一个媒体库的媒体项
        items = await connector.get_media_items(library_id=libraries[0].id)
        assert isinstance(items, list)
        
        if items:
            # 验证第一个媒体项的结构
            item = items[0]
            assert hasattr(item, "id")
            assert hasattr(item, "name")
            assert hasattr(item, "type")
