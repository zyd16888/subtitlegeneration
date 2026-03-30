"""
媒体库相关 API 端点
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel

from models.base import get_db
from services.emby_connector import EmbyConnector, Library, MediaItem
from services.config_manager import ConfigManager

router = APIRouter(prefix="/api", tags=["media"])


class LibraryResponse(BaseModel):
    """媒体库响应模型"""
    id: str
    name: str
    type: str
    
    class Config:
        from_attributes = True


class MediaItemResponse(BaseModel):
    """媒体项响应模型"""
    id: str
    name: str
    type: str
    path: Optional[str] = None
    has_subtitles: bool = False
    image_url: Optional[str] = None
    
    class Config:
        from_attributes = True


class PaginatedMediaResponse(BaseModel):
    """分页媒体项响应模型"""
    items: List[MediaItemResponse]
    total: int
    limit: int
    offset: int


async def get_emby_connector(db: Session = Depends(get_db)) -> EmbyConnector:
    """
    获取 Emby 连接器实例
    
    从配置中读取 Emby URL 和 API Key
    """
    config_manager = ConfigManager(db)
    config = await config_manager.get_config()
    
    if not config.emby_url or not config.emby_api_key:
        raise HTTPException(
            status_code=400,
            detail="Emby 连接未配置，请先在设置中配置 Emby URL 和 API Key"
        )
    
    return EmbyConnector(config.emby_url, config.emby_api_key)


@router.get("/libraries", response_model=List[LibraryResponse])
async def get_libraries(
    emby: EmbyConnector = Depends(get_emby_connector)
):
    """
    获取 Emby 媒体库列表
    
    Returns:
        媒体库列表
    """
    try:
        async with emby:
            libraries = await emby.get_libraries()
            return [
                LibraryResponse(
                    id=lib.id,
                    name=lib.name,
                    type=lib.type
                )
                for lib in libraries
            ]
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"获取媒体库列表失败: {str(e)}"
        )


@router.get("/media", response_model=PaginatedMediaResponse)
async def get_media_items(
    library_id: Optional[str] = Query(None, description="媒体库 ID"),
    item_type: Optional[str] = Query(None, description="媒体类型 (Movie, Episode 等)"),
    search: Optional[str] = Query(None, description="搜索关键词"),
    limit: int = Query(50, ge=1, le=200, description="每页数量"),
    offset: int = Query(0, ge=0, description="偏移量"),
    emby: EmbyConnector = Depends(get_emby_connector)
):
    """
    获取媒体项列表，支持筛选和分页
    
    Args:
        library_id: 可选的媒体库 ID 筛选
        item_type: 可选的媒体类型筛选
        search: 可选的搜索关键词
        limit: 每页返回的数量
        offset: 分页偏移量
        
    Returns:
        分页的媒体项列表
    """
    try:
        async with emby:
            # 使用 Emby API 的原生分页功能
            items, total = await emby.get_media_items(
                library_id=library_id,
                item_type=item_type,
                search=search,
                limit=limit,
                offset=offset
            )
            
            return PaginatedMediaResponse(
                items=[
                    MediaItemResponse(
                        id=item.id,
                        name=item.name,
                        type=item.type,
                        path=item.path,
                        has_subtitles=item.has_subtitles,
                        image_url=item.image_url
                    )
                    for item in items
                ],
                total=total,
                limit=limit,
                offset=offset
            )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"获取媒体项列表失败: {str(e)}"
        )


@router.get("/series/{series_id}/episodes", response_model=List[MediaItemResponse])
async def get_series_episodes(
    series_id: str,
    emby: EmbyConnector = Depends(get_emby_connector)
):
    """
    获取剧集下的所有集
    
    Args:
        series_id: 剧集 ID
        
    Returns:
        该剧集下的所有集列表
    """
    try:
        async with emby:
            episodes = await emby.get_series_episodes(series_id)
            return [
                MediaItemResponse(
                    id=episode.id,
                    name=episode.name,
                    type=episode.type,
                    path=episode.path,
                    has_subtitles=episode.has_subtitles,
                    image_url=episode.image_url
                )
                for episode in episodes
            ]
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"获取剧集集数失败: {str(e)}"
        )
