# EmbyConnector 使用说明

## 概述

`EmbyConnector` 是一个用于与 Emby Server 通信的服务类，提供了以下功能：

- 测试 Emby 连接
- 获取媒体库列表
- 获取媒体项列表（支持筛选）
- 获取媒体文件路径
- 触发元数据刷新

## 基本使用

### 初始化连接器

```python
from backend.services.emby_connector import EmbyConnector

# 创建连接器实例
connector = EmbyConnector(
    base_url="http://localhost:8096",
    api_key="your_api_key_here"
)
```

### 使用异步上下文管理器（推荐）

```python
async with EmbyConnector(base_url, api_key) as connector:
    # 测试连接
    is_connected = await connector.test_connection()
    if is_connected:
        print("成功连接到 Emby Server")
```

### 测试连接

```python
async def test_emby_connection():
    async with EmbyConnector(base_url, api_key) as connector:
        result = await connector.test_connection()
        return result  # True 表示连接成功
```

### 获取媒体库列表

```python
async def get_all_libraries():
    async with EmbyConnector(base_url, api_key) as connector:
        libraries = await connector.get_libraries()
        
        for lib in libraries:
            print(f"媒体库: {lib.name} (ID: {lib.id}, 类型: {lib.type})")
        
        return libraries
```

### 获取媒体项列表

```python
async def get_movies():
    async with EmbyConnector(base_url, api_key) as connector:
        # 获取所有媒体项
        all_items = await connector.get_media_items()
        
        # 按媒体库筛选
        library_items = await connector.get_media_items(library_id="lib_id")
        
        # 按类型筛选
        movies = await connector.get_media_items(item_type="Movie")
        
        # 搜索
        search_results = await connector.get_media_items(search="关键词")
        
        # 组合筛选
        filtered_items = await connector.get_media_items(
            library_id="lib_id",
            item_type="Movie",
            search="关键词"
        )
        
        return filtered_items
```

### 获取媒体文件路径

```python
async def get_video_path(item_id: str):
    async with EmbyConnector(base_url, api_key) as connector:
        try:
            path = await connector.get_media_file_path(item_id)
            print(f"视频文件路径: {path}")
            return path
        except ValueError as e:
            print(f"错误: {e}")
            return None
```

### 刷新媒体项元数据

```python
async def refresh_item(item_id: str):
    async with EmbyConnector(base_url, api_key) as connector:
        success = await connector.refresh_metadata(item_id)
        if success:
            print("元数据刷新成功")
        else:
            print("元数据刷新失败")
        return success
```

## 完整示例

```python
import asyncio
from backend.services.emby_connector import EmbyConnector

async def main():
    base_url = "http://localhost:8096"
    api_key = "your_api_key"
    
    async with EmbyConnector(base_url, api_key) as connector:
        # 1. 测试连接
        if not await connector.test_connection():
            print("无法连接到 Emby Server")
            return
        
        # 2. 获取媒体库
        libraries = await connector.get_libraries()
        print(f"找到 {len(libraries)} 个媒体库")
        
        # 3. 获取第一个媒体库的媒体项
        if libraries:
            items = await connector.get_media_items(
                library_id=libraries[0].id,
                item_type="Movie"
            )
            print(f"找到 {len(items)} 个电影")
            
            # 4. 获取第一个媒体项的文件路径
            if items:
                path = await connector.get_media_file_path(items[0].id)
                print(f"文件路径: {path}")
                
                # 5. 刷新元数据
                await connector.refresh_metadata(items[0].id)

if __name__ == "__main__":
    asyncio.run(main())
```

## 数据结构

### Library

```python
@dataclass
class Library:
    id: str          # 媒体库 ID
    name: str        # 媒体库名称
    type: str        # 媒体库类型（movies, tvshows 等）
```

### MediaItem

```python
@dataclass
class MediaItem:
    id: str                      # 媒体项 ID
    name: str                    # 媒体项名称
    type: str                    # 媒体项类型（Movie, Episode 等）
    path: Optional[str]          # 文件路径（可选）
    has_subtitles: bool          # 是否有字幕
```

## 错误处理

所有方法都会在发生错误时记录日志。对于关键操作，建议使用 try-except 捕获异常：

```python
async def safe_get_libraries():
    async with EmbyConnector(base_url, api_key) as connector:
        try:
            libraries = await connector.get_libraries()
            return libraries
        except Exception as e:
            print(f"获取媒体库失败: {e}")
            return []
```

## 注意事项

1. **异步操作**: 所有方法都是异步的，需要使用 `await` 关键字
2. **资源管理**: 推荐使用异步上下文管理器（`async with`）自动管理连接
3. **错误日志**: 所有错误都会记录到日志中，便于调试
4. **API Key**: 确保 API Key 有足够的权限访问 Emby API
5. **超时设置**: HTTP 客户端默认超时为 30 秒

## 测试

运行单元测试：

```bash
pytest backend/test_emby_connector.py -v
```

运行集成测试（需要真实的 Emby Server）：

```bash
export RUN_INTEGRATION_TESTS=1
export EMBY_URL=http://localhost:8096
export EMBY_API_KEY=your_api_key
pytest backend/test_emby_connector_integration.py -v
```
