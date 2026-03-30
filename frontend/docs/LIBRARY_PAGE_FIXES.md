# Library 页面修复说明

## 修复的问题

### 1. 媒体项全量拉取导致超时
**问题**: 后端虽然接收分页参数，但先获取所有数据再手动分页，导致大型媒体库加载超时。

**解决方案**: 
- 修改 `EmbyConnector.get_media_items()` 使用 Emby API 的原生分页参数 `StartIndex` 和 `Limit`
- 返回值改为 `tuple[List[MediaItem], int]`，包含媒体项列表和总数
- 后端 API 直接使用 Emby 返回的 `TotalRecordCount`

### 2. 未选择媒体库时仍然加载媒体项
**问题**: 前端在没有选择媒体库时也会触发 API 请求，导致不必要的加载和错误。

**解决方案**:
- 在 `fetchMediaItems()` 中添加 `!selectedLibrary` 检查
- 未选择媒体库时直接返回，不发起请求
- 显示友好提示 "请先选择一个媒体库"

### 3. 媒体项图片不显示和名称显示错误
**问题**: 
- MediaItem 数据模型缺少图片 URL 字段
- 图片URL缺少API Key参数导致无法访问
- Episode类型显示的是集数（"1"、"2"）而不是剧集名称

**解决方案**:
- 在 `MediaItem` 数据类添加 `image_url` 字段
- 在 `from_emby_response()` 中构建完整的图片 URL：
  - 对于Episode类型，优先使用Series的Primary图片
  - 否则使用自己的Primary图片
  - 最后尝试Backdrop图片
  - 添加 `api_key` 参数到URL
- 改进名称显示逻辑：
  - 对于Episode类型，组合SeriesName + 季集信息（如"剧名 S01E02"）
  - 其他类型使用原始Name字段
- 前端使用 `<img>` 标签显示图片，添加错误处理

### 4. SSL证书验证导致连接失败
**问题**: 使用HTTPS的Emby服务器（特别是自签名证书）会导致连接失败。

**解决方案**:
- 在 `EmbyConnector.__init__()` 中设置 `verify=False` 禁用SSL验证
- 支持自签名证书和内网HTTPS服务器

## 修改的文件

### 后端
- `backend/services/emby_connector.py`
  - 添加 `image_url` 字段到 `MediaItem`
  - 修改 `get_media_items()` 支持原生分页
  - 在 API 请求中添加 `SeriesName`, `SeriesId`, `SeriesPrimaryImageTag`, `IndexNumber`, `ParentIndexNumber` 字段
  - 改进 `from_emby_response()` 方法：
    - 智能处理Episode类型的名称显示
    - 构建完整的图片URL（包含API Key）
    - 优先使用Series图片（对于Episode）
  - 禁用SSL验证以支持自签名证书
  
- `backend/api/media.py`
  - 添加 `image_url` 到 `MediaItemResponse`
  - 更新 `/api/media` 端点使用新的分页逻辑

### 前端
- `frontend/src/types/api.ts`
  - 添加 `image_url?` 到 `MediaItem` 接口

- `frontend/src/pages/Library.tsx`
  - 修改 `fetchMediaItems()` 添加媒体库选择检查
  - 更新卡片封面显示图片
  - 添加图片加载错误处理
  - 添加未选择媒体库的提示

## 性能改进

- 使用 Emby API 原生分页，避免全量数据传输
- 减少不必要的 API 请求
- 图片懒加载和错误处理
- 支持HTTPS连接（包括自签名证书）

## 显示改进

- Episode类型显示完整的剧集信息（如"剧名 S01E02"）
- 使用Series的封面图片，视觉效果更统一
- 图片URL包含认证信息，可以正常加载

## 测试建议

1. 测试大型媒体库（1000+ 项）的加载速度
2. 验证未选择媒体库时不会发起请求
3. 检查图片是否正确显示（特别是Episode类型）
4. 验证Episode名称显示格式（应该是"剧名 S01E02"）
5. 测试分页功能是否正常工作
6. 测试HTTPS Emby服务器连接
