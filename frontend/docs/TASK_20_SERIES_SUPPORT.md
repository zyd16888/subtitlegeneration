# Task 20: 剧集支持和单独配置（更新版）

## 概述

改进 Library 页面，统一所有媒体类型的交互方式：所有媒体项（电影、剧集、单集）都通过点击打开配置对话框，支持单独配置 ASR 引擎和翻译服务。

## 需求

1. 剧集合并显示：同一个剧集（Series）在 Library 页面显示为一个卡片（即使类型选"全部"）
2. 统一交互：所有媒体项都通过点击打开配置对话框
3. 剧集二级展开：点击剧集卡片后，打开对话框显示该剧集下的所有集（Episodes）
4. 电影配置：点击电影卡片后，打开配置对话框，可以单独配置
5. 单独配置：每个媒体项/集都可以单独选择 ASR 引擎、翻译服务和模型
6. 全局配置：设置页面保持全局配置，作为默认值

## 实现内容

### 1. 后端改动

#### 1.1 Emby 连接器 (`backend/services/emby_connector.py`)

添加获取剧集下所有集的方法：

```python
async def get_series_episodes(self, series_id: str) -> List[MediaItem]:
    """
    获取剧集下的所有集
    
    Args:
        series_id: 剧集 ID
    
    Returns:
        List[MediaItem]: 该剧集下的所有集列表
    """
```

使用 Emby API 的 `/Shows/{series_id}/Episodes` 端点获取剧集的所有集。

#### 1.2 媒体 API (`backend/api/media.py`)

添加新的 API 端点：

```python
@router.get("/series/{series_id}/episodes", response_model=List[MediaItemResponse])
async def get_series_episodes(series_id: str, emby: EmbyConnector = Depends(get_emby_connector)):
    """获取剧集下的所有集"""
```

#### 1.3 任务 API (`backend/api/tasks.py`)

扩展任务创建请求模型，支持两种模式：

```python
class TaskConfigRequest(BaseModel):
    """单个任务配置"""
    media_item_id: str
    asr_engine: Optional[str] = None
    translation_service: Optional[str] = None
    openai_model: Optional[str] = None

class CreateTaskRequest(BaseModel):
    """创建任务请求模型"""
    media_item_ids: Optional[List[str]] = None  # 批量创建，使用全局配置
    tasks: Optional[List[TaskConfigRequest]] = None  # 单独配置每个任务
```

更新任务创建逻辑，支持传递自定义配置到 Celery 任务。

#### 1.4 Celery 任务 (`backend/tasks/subtitle_tasks.py`)

扩展 `generate_subtitle_task` 函数签名，支持可选的配置覆盖：

```python
def generate_subtitle_task(
    self,
    task_id: str,
    media_item_id: str,
    video_path: str,
    asr_engine: str = None,
    translation_service: str = None,
    openai_model: str = None
):
```

如果提供了自定义配置，则覆盖全局配置；否则使用全局配置。

### 2. 前端改动

#### 2.1 API 类型定义 (`frontend/src/types/api.ts`)

添加任务配置类型：

```typescript
export interface TaskConfig {
  media_item_id: string;
  asr_engine?: 'sherpa-onnx' | 'cloud';
  translation_service?: 'openai' | 'deepseek' | 'local';
  openai_model?: string;
}

export interface CreateTaskRequest {
  media_item_ids?: string[]; // 批量创建，使用全局配置
  tasks?: TaskConfig[]; // 单独配置每个任务
}
```

#### 2.2 API 服务 (`frontend/src/services/api.ts`)

添加获取剧集集数的方法：

```typescript
getSeriesEpisodes: async (seriesId: string): Promise<MediaItem[]> => {
  const response = await this.client.get<MediaItem[]>(
    `/api/series/${seriesId}/episodes`
  );
  return response.data;
}
```

#### 2.3 单个媒体项配置对话框 (`frontend/src/components/MediaConfigModal.tsx`)

新建组件，用于电影等单个媒体项的配置，功能包括：

- 显示媒体项信息（缩略图、名称、类型、字幕状态）
- 显示当前全局配置作为参考
- 提供 ASR 引擎、翻译服务、模型的下拉选择
- 生成字幕按钮，将配置传递给父组件

#### 2.4 剧集详情对话框 (`frontend/src/components/SeriesEpisodesModal.tsx`)

新建组件，功能包括：

- 显示剧集下的所有集（表格形式）
- 显示每一集的缩略图、名称、字幕状态
- 支持多选集
- 为每一集提供 ASR 引擎、翻译服务、模型的下拉选择
- 显示当前全局配置作为参考
- 生成字幕按钮，将选中的集和配置传递给父组件

#### 2.5 Library 页面 (`frontend/src/pages/Library.tsx`)

改进功能：

1. 移除多选和批量操作功能
2. 统一所有媒体类型的交互：
   - 剧集（Series）：点击打开剧集详情对话框
   - 其他类型（Movie、Episode）：点击打开单个媒体项配置对话框

3. 添加媒体项点击处理：
   ```typescript
   const handleItemClick = (item: MediaItem) => {
     if (item.type === 'Series') {
       setSelectedSeries({ id: item.id, name: item.name });
       setSeriesModalVisible(true);
     } else {
       setSelectedMediaItem(item);
       setMediaConfigModalVisible(true);
     }
   }
   ```

4. 添加单个媒体项生成字幕处理：
   ```typescript
   const handleMediaItemGenerateSubtitle = async (task: TaskConfig) => {
     const createdTasks = await api.tasks.createTasks({ tasks: [task] });
     message.success('成功创建字幕生成任务');
   }
   ```

5. 添加剧集生成字幕处理：
   ```typescript
   const handleSeriesGenerateSubtitles = async (tasks: TaskConfig[]) => {
     const createdTasks = await api.tasks.createTasks({ tasks });
     message.success(`成功创建 ${createdTasks.length} 个字幕生成任务`);
   }
   ```

6. 在卡片描述中提示可点击：
   ```typescript
   description={
     <div style={{ fontSize: 11, color: '#999' }}>
       {item.type === 'Series' ? '剧集 (点击查看)' : `${item.type} (点击配置)`}
     </div>
   }
   ```

## 使用流程

### 电影/单集生成（单独配置）

1. 在 Library 页面选择媒体库和类型
2. 点击电影或单集卡片
3. 在弹出的配置对话框中：
   - 查看媒体项信息
   - 选择 ASR 引擎（可选，不选则使用全局配置）
   - 选择翻译服务（可选，不选则使用全局配置）
   - 选择模型（可选，不选则使用全局配置）
4. 点击"生成字幕"按钮
5. 系统创建任务，使用指定的配置或全局配置

### 剧集生成（单独配置）

1. 在 Library 页面选择媒体库，类型选择"剧集"
2. 点击剧集卡片
3. 在弹出的对话框中：
   - 查看该剧集下的所有集
   - 勾选要生成字幕的集
   - 为每一集选择 ASR 引擎（可选，不选则使用全局配置）
   - 为每一集选择翻译服务（可选，不选则使用全局配置）
   - 为每一集选择模型（可选，不选则使用全局配置）
4. 点击"生成字幕"按钮
5. 系统为每一集创建任务，使用指定的配置或全局配置

## 技术细节

### 配置优先级

1. 任务级配置（最高优先级）：在剧集详情对话框中为单集指定的配置
2. 全局配置（默认）：在设置页面配置的系统默认值

### API 调用流程

```
前端 Library 页面
  ↓ 点击剧集
前端 SeriesEpisodesModal
  ↓ 调用 api.media.getSeriesEpisodes(seriesId)
后端 /api/series/{series_id}/episodes
  ↓ 调用 emby.get_series_episodes(series_id)
Emby API /Shows/{series_id}/Episodes
  ↓ 返回集列表
前端显示集列表
  ↓ 用户选择集和配置
  ↓ 点击生成字幕
前端调用 api.tasks.createTasks({ tasks: [...] })
后端 /api/tasks (POST)
  ↓ 为每个任务创建数据库记录
  ↓ 提交 Celery 任务，传递自定义配置
Celery Worker 执行任务
  ↓ 使用自定义配置或全局配置
  ↓ 完成字幕生成
```

## 测试建议

1. 测试剧集列表显示：验证剧集在 Library 页面正确合并显示
2. 测试剧集点击：验证点击剧集后正确打开详情对话框
3. 测试集列表加载：验证详情对话框正确显示所有集
4. 测试配置选择：验证可以为每一集单独选择配置
5. 测试任务创建：验证使用自定义配置创建任务成功
6. 测试任务执行：验证任务使用正确的配置执行
7. 测试全局配置回退：验证未指定配置时使用全局配置

## 改进建议

1. 添加批量配置功能：在剧集详情对话框中添加"应用到所有"按钮
2. 添加配置预设：允许用户保存常用配置组合
3. 添加季筛选：对于多季剧集，支持按季筛选
4. 添加配置验证：在创建任务前验证配置的有效性
5. 添加配置提示：显示每个配置选项的说明和建议

## 相关文件

### 后端
- `backend/services/emby_connector.py` - Emby 连接器
- `backend/api/media.py` - 媒体 API
- `backend/api/tasks.py` - 任务 API
- `backend/tasks/subtitle_tasks.py` - Celery 任务

### 前端
- `frontend/src/types/api.ts` - API 类型定义
- `frontend/src/services/api.ts` - API 服务
- `frontend/src/components/MediaConfigModal.tsx` - 单个媒体项配置对话框
- `frontend/src/components/SeriesEpisodesModal.tsx` - 剧集详情对话框
- `frontend/src/pages/Library.tsx` - Library 页面
- `frontend/src/components/index.ts` - 组件导出

## 完成日期

2026-03-30
