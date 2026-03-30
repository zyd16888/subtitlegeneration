# Emby API 修复说明

## 问题描述

在使用 Emby API 时遇到以下错误：
- 获取媒体库列表失败（返回 500 错误）
- 获取媒体项列表失败（返回 500 错误）
- 错误日志显示"获取媒体库列表失败: "和"获取媒体项列表失败: "，但没有具体错误信息

## 根本原因

通过实际测试 Emby API，发现以下问题：

### 1. 媒体类型筛选参数处理

前端可能传递 `item_type="all"` 来表示不筛选类型，但 Emby API 不接受这个值。

原代码：
```python
if item_type:
    params["IncludeItemTypes"] = item_type  # ❌ 会传递 "all"
```

修复后：
```python
if item_type and item_type != "all":
    params["IncludeItemTypes"] = item_type  # ✅ 过滤掉 "all"
```

### 2. 错误处理不够详细

原代码只记录了简单的错误信息，没有记录 HTTP 状态码和响应内容，导致难以调试。

修复后：
```python
except httpx.HTTPStatusError as e:
    logger.error(f"获取媒体库列表失败 (HTTP {e.response.status_code}): {e}")
    logger.error(f"响应内容: {e.response.text}")
    raise Exception(f"Emby API 错误 (HTTP {e.response.status_code}): {e.response.text}")
```

### 3. VirtualFolders API 字段说明

经过实际测试，Emby 的 `/Library/VirtualFolders` API 返回的媒体库对象**同时包含 `Id` 和 `ItemId` 字段，且值相同**。

测试结果示例：
```json
{
  "Name": "擦边短剧",
  "CollectionType": "tvshows",
  "ItemId": "160087",
  "Id": "160087"
}
```

因此使用 `Id` 或 `ItemId` 都可以正常工作。

## 修改文件

1. `backend/services/emby_connector.py`
   - 修复 `get_media_items()` 方法，过滤 `item_type="all"`
   - 改进错误处理，记录详细的 HTTP 错误信息

## 测试验证

创建了测试脚本来验证修复：

1. `backend/tests/test_emby_direct.py` - 直接测试 Emby API（不依赖数据库）

```bash
python backend/tests/test_emby_direct.py <EMBY_URL> <API_KEY>
```

测试内容：
1. 测试 Emby 连接
2. 获取媒体库列表并显示原始响应
3. 获取媒体项列表
4. 按媒体库ID筛选媒体项

## 参考资料

- [Emby API - VirtualFolders](https://betadev.emby.media/reference/RestAPI/LibraryStructureService/getLibraryVirtualfoldersQuery.html)
- [Emby API - Items](https://dev.emby.media/reference/RestAPI/ItemsService/getItems.html)
- [Emby API - Library Service](https://dev.emby.media/reference/RestAPI/LibraryService.html)

## 相关问题

这次修复解决了以下用户报告的问题：
- Library 页面无法加载媒体库列表
- 选择媒体库后无法加载媒体项
- 按类型筛选时出现错误

## 后续改进建议

1. 添加 API 响应缓存，减少对 Emby 服务器的请求
2. 实现分页参数传递给 Emby API（目前是获取所有结果后在后端分页）
3. 添加更多的错误重试机制
4. 支持更多的筛选条件（年份、评分等）
