"""
EmbyConnector 单元测试
"""
import pytest
import httpx
from unittest.mock import AsyncMock, patch, MagicMock
from backend.services.emby_connector import EmbyConnector, Library, MediaItem


@pytest.fixture
def emby_connector():
    """创建 EmbyConnector 实例"""
    return EmbyConnector(
        base_url="http://localhost:8096",
        api_key="test_api_key"
    )


@pytest.fixture
def mock_httpx_client():
    """创建 mock httpx 客户端"""
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    return mock_client


class TestEmbyConnector:
    """EmbyConnector 测试类"""
    
    @pytest.mark.asyncio
    async def test_init(self, emby_connector):
        """测试初始化"""
        assert emby_connector.base_url == "http://localhost:8096"
        assert emby_connector.api_key == "test_api_key"
        assert isinstance(emby_connector.client, httpx.AsyncClient)
        await emby_connector.close()
    
    @pytest.mark.asyncio
    async def test_init_strips_trailing_slash(self):
        """测试初始化时去除尾部斜杠"""
        connector = EmbyConnector(
            base_url="http://localhost:8096/",
            api_key="test_api_key"
        )
        assert connector.base_url == "http://localhost:8096"
        await connector.close()
    
    def test_get_headers(self, emby_connector):
        """测试获取请求头"""
        headers = emby_connector._get_headers()
        assert headers["X-Emby-Token"] == "test_api_key"
        assert headers["Accept"] == "application/json"
    
    @pytest.mark.asyncio
    async def test_test_connection_success(self, emby_connector, mock_httpx_client):
        """测试连接成功"""
        # Mock 响应
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"ServerName": "Test Server"}
        mock_httpx_client.get.return_value = mock_response
        
        emby_connector.client = mock_httpx_client
        
        result = await emby_connector.test_connection()
        
        assert result is True
        mock_httpx_client.get.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_test_connection_failure(self, emby_connector, mock_httpx_client):
        """测试连接失败"""
        # Mock 响应抛出异常
        mock_httpx_client.get.side_effect = httpx.HTTPStatusError(
            "Not Found",
            request=MagicMock(),
            response=MagicMock(status_code=404)
        )
        
        emby_connector.client = mock_httpx_client
        
        result = await emby_connector.test_connection()
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_get_libraries_success(self, emby_connector, mock_httpx_client):
        """测试获取媒体库列表成功"""
        # Mock 响应
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"Id": "lib1", "Name": "Movies", "CollectionType": "movies"},
            {"Id": "lib2", "Name": "TV Shows", "CollectionType": "tvshows"}
        ]
        mock_httpx_client.get.return_value = mock_response
        
        emby_connector.client = mock_httpx_client
        
        libraries = await emby_connector.get_libraries()
        
        assert len(libraries) == 2
        assert libraries[0].id == "lib1"
        assert libraries[0].name == "Movies"
        assert libraries[1].id == "lib2"
        assert libraries[1].name == "TV Shows"

    
    @pytest.mark.asyncio
    async def test_get_media_items_no_filters(self, emby_connector, mock_httpx_client):
        """测试获取媒体项列表（无筛选）"""
        # Mock 响应
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "Items": [
                {
                    "Id": "item1",
                    "Name": "Movie 1",
                    "Type": "Movie",
                    "Path": "/path/to/movie1.mp4",
                    "MediaStreams": []
                },
                {
                    "Id": "item2",
                    "Name": "Movie 2",
                    "Type": "Movie",
                    "Path": "/path/to/movie2.mp4",
                    "MediaStreams": [{"Type": "Subtitle"}]
                }
            ]
        }
        mock_httpx_client.get.return_value = mock_response
        
        emby_connector.client = mock_httpx_client
        
        items = await emby_connector.get_media_items()
        
        assert len(items) == 2
        assert items[0].id == "item1"
        assert items[0].has_subtitles is False
        assert items[1].id == "item2"
        assert items[1].has_subtitles is True
    
    @pytest.mark.asyncio
    async def test_get_media_items_with_filters(self, emby_connector, mock_httpx_client):
        """测试获取媒体项列表（带筛选）"""
        # Mock 响应
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"Items": []}
        mock_httpx_client.get.return_value = mock_response
        
        emby_connector.client = mock_httpx_client
        
        await emby_connector.get_media_items(
            library_id="lib1",
            item_type="Movie",
            search="test"
        )
        
        # 验证调用参数
        call_args = mock_httpx_client.get.call_args
        params = call_args.kwargs["params"]
        assert params["ParentId"] == "lib1"
        assert params["IncludeItemTypes"] == "Movie"
        assert params["SearchTerm"] == "test"
    
    @pytest.mark.asyncio
    async def test_get_media_file_path_success(self, emby_connector, mock_httpx_client):
        """测试获取媒体文件路径成功"""
        # Mock 响应
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "Id": "item1",
            "Path": "/path/to/video.mp4"
        }
        mock_httpx_client.get.return_value = mock_response
        
        emby_connector.client = mock_httpx_client
        
        path = await emby_connector.get_media_file_path("item1")
        
        assert path == "/path/to/video.mp4"
    
    @pytest.mark.asyncio
    async def test_get_media_file_path_no_path(self, emby_connector, mock_httpx_client):
        """测试获取媒体文件路径失败（无路径）"""
        # Mock 响应
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"Id": "item1"}
        mock_httpx_client.get.return_value = mock_response
        
        emby_connector.client = mock_httpx_client
        
        with pytest.raises(ValueError, match="没有物理路径"):
            await emby_connector.get_media_file_path("item1")
    
    @pytest.mark.asyncio
    async def test_refresh_metadata_success(self, emby_connector, mock_httpx_client):
        """测试刷新元数据成功"""
        # Mock 响应
        mock_response = MagicMock()
        mock_response.status_code = 204
        mock_httpx_client.post.return_value = mock_response
        
        emby_connector.client = mock_httpx_client
        
        result = await emby_connector.refresh_metadata("item1")
        
        assert result is True
        mock_httpx_client.post.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_refresh_metadata_failure(self, emby_connector, mock_httpx_client):
        """测试刷新元数据失败"""
        # Mock 响应抛出异常
        mock_httpx_client.post.side_effect = httpx.HTTPStatusError(
            "Server Error",
            request=MagicMock(),
            response=MagicMock(status_code=500)
        )
        
        emby_connector.client = mock_httpx_client
        
        result = await emby_connector.refresh_metadata("item1")
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_context_manager(self):
        """测试异步上下文管理器"""
        async with EmbyConnector("http://localhost:8096", "test_key") as connector:
            assert connector is not None
            assert isinstance(connector, EmbyConnector)


class TestLibrary:
    """Library 数据类测试"""
    
    def test_from_emby_response(self):
        """测试从 Emby 响应创建 Library 对象"""
        data = {
            "Id": "lib1",
            "Name": "Movies",
            "CollectionType": "movies"
        }
        
        library = Library.from_emby_response(data)
        
        assert library.id == "lib1"
        assert library.name == "Movies"
        assert library.type == "movies"


class TestMediaItem:
    """MediaItem 数据类测试"""
    
    def test_from_emby_response_with_subtitles(self):
        """测试从 Emby 响应创建 MediaItem 对象（有字幕）"""
        data = {
            "Id": "item1",
            "Name": "Movie 1",
            "Type": "Movie",
            "Path": "/path/to/movie.mp4",
            "MediaStreams": [
                {"Type": "Video"},
                {"Type": "Audio"},
                {"Type": "Subtitle"}
            ]
        }
        
        item = MediaItem.from_emby_response(data)
        
        assert item.id == "item1"
        assert item.name == "Movie 1"
        assert item.type == "Movie"
        assert item.path == "/path/to/movie.mp4"
        assert item.has_subtitles is True
    
    def test_from_emby_response_without_subtitles(self):
        """测试从 Emby 响应创建 MediaItem 对象（无字幕）"""
        data = {
            "Id": "item2",
            "Name": "Movie 2",
            "Type": "Movie",
            "MediaStreams": [
                {"Type": "Video"},
                {"Type": "Audio"}
            ]
        }
        
        item = MediaItem.from_emby_response(data)
        
        assert item.has_subtitles is False
