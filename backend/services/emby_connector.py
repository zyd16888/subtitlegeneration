"""
Emby 连接器服务

负责与 Emby Server 通信，获取媒体库信息和管理字幕文件
"""
import httpx
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class Library:
    """媒体库数据类"""
    id: str
    name: str
    type: str  # Movie, Series, etc.
    
    @classmethod
    def from_emby_response(cls, data: Dict[str, Any]) -> "Library":
        """从 Emby API 响应创建 Library 对象"""
        # Emby VirtualFolders API 返回 Id 和 ItemId 字段（值相同）
        return cls(
            id=data.get("Id", ""),
            name=data.get("Name", ""),
            type=data.get("CollectionType", "")
        )


@dataclass
class MediaItem:
    """媒体项数据类"""
    id: str
    name: str
    type: str
    path: Optional[str] = None
    has_subtitles: bool = False
    image_url: Optional[str] = None
    
    @classmethod
    def from_emby_response(cls, data: Dict[str, Any], base_url: str = "", api_key: str = "") -> "MediaItem":
        """从 Emby API 响应创建 MediaItem 对象"""
        # 检查是否有字幕
        has_subtitles = False
        if "MediaStreams" in data:
            has_subtitles = any(
                stream.get("Type") == "Subtitle" 
                for stream in data.get("MediaStreams", [])
            )
        
        # 获取显示名称
        # 对于Episode类型，使用SeriesName + 季集信息
        item_type = data.get("Type", "")
        name = data.get("Name", "")
        if item_type == "Episode":
            series_name = data.get("SeriesName", "")
            season_num = data.get("ParentIndexNumber")
            episode_num = data.get("IndexNumber")
            if series_name:
                if season_num and episode_num:
                    name = f"{series_name} S{season_num:02d}E{episode_num:02d}"
                elif episode_num:
                    name = f"{series_name} E{episode_num}"
                else:
                    name = series_name
        
        # 构建图片URL
        image_url = None
        item_id = data.get("Id", "")
        if item_id and base_url:
            # 对于Episode，优先使用Series的Primary图片
            if item_type == "Episode" and data.get("SeriesId") and data.get("SeriesPrimaryImageTag"):
                series_id = data.get("SeriesId")
                image_url = f"{base_url}/Items/{series_id}/Images/Primary"
            # 否则使用自己的Primary图片
            elif data.get("ImageTags", {}).get("Primary"):
                image_url = f"{base_url}/Items/{item_id}/Images/Primary"
            # 最后尝试Backdrop
            elif data.get("BackdropImageTags") and len(data.get("BackdropImageTags", [])) > 0:
                image_url = f"{base_url}/Items/{item_id}/Images/Backdrop/0"
            
            # 添加API Key参数
            if image_url and api_key:
                image_url = f"{image_url}?api_key={api_key}"
        
        return cls(
            id=item_id,
            name=name,
            type=item_type,
            path=data.get("Path"),
            has_subtitles=has_subtitles,
            image_url=image_url
        )


class EmbyConnector:
    """
    Emby 连接器
    
    提供与 Emby Server 通信的接口，包括：
    - 连接测试
    - 获取媒体库列表
    - 获取媒体项列表
    - 获取媒体文件路径
    - 触发元数据刷新
    """
    
    def __init__(self, base_url: str, api_key: str):
        """
        初始化 Emby 连接器
        
        Args:
            base_url: Emby Server URL (例如: http://localhost:8096)
            api_key: Emby API Key
        """
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        # 禁用SSL验证以支持自签名证书
        self.client = httpx.AsyncClient(timeout=30.0, verify=False)
        
    async def __aenter__(self):
        """异步上下文管理器入口"""
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        await self.client.aclose()
    
    def _get_headers(self) -> Dict[str, str]:
        """获取请求头"""
        return {
            "X-Emby-Token": self.api_key,
            "Accept": "application/json"
        }
    
    async def test_connection(self) -> bool:
        """
        测试 Emby 连接是否有效
        
        Returns:
            bool: 连接成功返回 True，否则返回 False
        """
        try:
            url = f"{self.base_url}/System/Info"
            response = await self.client.get(url, headers=self._get_headers())
            response.raise_for_status()
            
            data = response.json()
            logger.info(f"成功连接到 Emby Server: {data.get('ServerName', 'Unknown')}")
            return True
            
        except httpx.HTTPStatusError as e:
            logger.error(f"Emby 连接失败 (HTTP {e.response.status_code}): {e}")
            return False
        except Exception as e:
            logger.error(f"Emby 连接失败: {e}")
            return False
    
    async def get_libraries(self) -> List[Library]:
        """
        获取所有媒体库
        
        Returns:
            List[Library]: 媒体库列表
        """
        try:
            url = f"{self.base_url}/Library/VirtualFolders"
            response = await self.client.get(url, headers=self._get_headers())
            response.raise_for_status()
            
            data = response.json()
            libraries = [Library.from_emby_response(item) for item in data]
            logger.info(f"获取到 {len(libraries)} 个媒体库")
            return libraries
            
        except httpx.HTTPStatusError as e:
            logger.error(f"获取媒体库列表失败 (HTTP {e.response.status_code}): {e}")
            logger.error(f"响应内容: {e.response.text}")
            raise Exception(f"Emby API 错误 (HTTP {e.response.status_code}): {e.response.text}")
        except Exception as e:
            logger.error(f"获取媒体库列表失败: {e}")
            raise

    
    async def get_media_items(
        self,
        library_id: Optional[str] = None,
        item_type: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> tuple[List[MediaItem], int]:
        """
        获取媒体项列表，支持筛选和分页
        
        Args:
            library_id: 媒体库 ID（可选）
            item_type: 媒体类型（可选，例如: Movie, Episode, Series）
            search: 搜索关键词（可选）
            limit: 每页数量
            offset: 偏移量
        
        Returns:
            tuple[List[MediaItem], int]: (媒体项列表, 总数)
        """
        try:
            url = f"{self.base_url}/Items"
            params = {
                "Recursive": "true",
                "Fields": "Path,MediaStreams,ImageTags,BackdropImageTags,SeriesName,SeriesId,SeriesPrimaryImageTag,IndexNumber,ParentIndexNumber",
                "StartIndex": str(offset),
                "Limit": str(limit)
            }
            
            if library_id:
                params["ParentId"] = library_id
            
            # 如果没有指定类型或类型为 "all"，排除 Episode，只显示 Movie 和 Series
            if not item_type or item_type == "all":
                params["IncludeItemTypes"] = "Movie,Series"
            elif item_type:
                params["IncludeItemTypes"] = item_type
            
            if search:
                params["SearchTerm"] = search
            
            response = await self.client.get(
                url,
                headers=self._get_headers(),
                params=params
            )
            response.raise_for_status()
            
            data = response.json()
            total = data.get("TotalRecordCount", 0)
            items = [
                MediaItem.from_emby_response(item, self.base_url, self.api_key) 
                for item in data.get("Items", [])
            ]
            logger.info(f"获取到 {len(items)} 个媒体项 (共 {total} 个)")
            return items, total
            
        except httpx.HTTPStatusError as e:
            logger.error(f"获取媒体项列表失败 (HTTP {e.response.status_code}): {e}")
            logger.error(f"响应内容: {e.response.text}")
            raise Exception(f"Emby API 错误 (HTTP {e.response.status_code}): {e.response.text}")
        except Exception as e:
            logger.error(f"获取媒体项列表失败: {e}")
            raise
    
    async def get_media_item(self, item_id: str) -> MediaItem:
        """
        获取单个媒体项详情
        
        Args:
            item_id: 媒体项 ID
        
        Returns:
            MediaItem: 媒体项对象
        """
        try:
            url = f"{self.base_url}/Users/{await self._get_user_id()}/Items/{item_id}"
            response = await self.client.get(url, headers=self._get_headers())
            response.raise_for_status()
            
            data = response.json()
            return MediaItem.from_emby_response(data, self.base_url, self.api_key)
            
        except Exception as e:
            logger.error(f"获取媒体项详情失败 (ID: {item_id}): {e}")
            raise
    
    async def get_series_episodes(self, series_id: str) -> List[MediaItem]:
        """
        获取剧集下的所有集
        
        Args:
            series_id: 剧集 ID
        
        Returns:
            List[MediaItem]: 该剧集下的所有集列表
        """
        try:
            url = f"{self.base_url}/Shows/{series_id}/Episodes"
            params = {
                "Fields": "Path,MediaStreams,ImageTags,BackdropImageTags,SeriesName,SeriesId,SeriesPrimaryImageTag,IndexNumber,ParentIndexNumber",
                "UserId": await self._get_user_id()
            }
            
            response = await self.client.get(
                url,
                headers=self._get_headers(),
                params=params
            )
            response.raise_for_status()
            
            data = response.json()
            episodes = [
                MediaItem.from_emby_response(item, self.base_url, self.api_key) 
                for item in data.get("Items", [])
            ]
            logger.info(f"获取到剧集 {series_id} 的 {len(episodes)} 集")
            return episodes
            
        except httpx.HTTPStatusError as e:
            logger.error(f"获取剧集集数失败 (HTTP {e.response.status_code}): {e}")
            logger.error(f"响应内容: {e.response.text}")
            raise Exception(f"Emby API 错误 (HTTP {e.response.status_code}): {e.response.text}")
        except Exception as e:
            logger.error(f"获取剧集集数失败 (Series ID: {series_id}): {e}")
            raise
    
    async def get_media_file_path(self, item_id: str) -> str:
        """
        获取媒体文件的物理路径
        
        Args:
            item_id: 媒体项 ID
        
        Returns:
            str: 媒体文件的物理路径
        """
        try:
            url = f"{self.base_url}/Items/{item_id}"
            params = {"Fields": "Path"}
            
            response = await self.client.get(
                url,
                headers=self._get_headers(),
                params=params
            )
            response.raise_for_status()
            
            data = response.json()
            path = data.get("Path")
            
            if not path:
                raise ValueError(f"媒体项 {item_id} 没有物理路径")
            
            logger.info(f"获取到媒体文件路径: {path}")
            return path
            
        except Exception as e:
            logger.error(f"获取媒体文件路径失败 (ID: {item_id}): {e}")
            raise
    
    async def refresh_metadata(self, item_id: str) -> bool:
        """
        触发 Emby 刷新媒体项元数据
        
        Args:
            item_id: 媒体项 ID
        
        Returns:
            bool: 刷新成功返回 True，否则返回 False
        """
        try:
            url = f"{self.base_url}/Items/{item_id}/Refresh"
            params = {
                "Recursive": "false",
                "MetadataRefreshMode": "Default",
                "ImageRefreshMode": "Default",
                "ReplaceAllMetadata": "false",
                "ReplaceAllImages": "false"
            }
            
            response = await self.client.post(
                url,
                headers=self._get_headers(),
                params=params
            )
            response.raise_for_status()
            
            logger.info(f"成功触发媒体项刷新 (ID: {item_id})")
            return True
            
        except Exception as e:
            logger.error(f"触发媒体项刷新失败 (ID: {item_id}): {e}")
            return False
    
    async def _get_user_id(self) -> str:
        """
        获取当前用户 ID
        
        Returns:
            str: 用户 ID
        """
        try:
            url = f"{self.base_url}/Users"
            response = await self.client.get(url, headers=self._get_headers())
            response.raise_for_status()
            
            users = response.json()
            if not users:
                raise ValueError("没有找到任何用户")
            
            # 返回第一个用户的 ID
            return users[0]["Id"]
            
        except Exception as e:
            logger.error(f"获取用户 ID 失败: {e}")
            raise
    
    async def close(self):
        """关闭 HTTP 客户端"""
        await self.client.aclose()
