# TaskManager 使用指南

## 概述

TaskManager 服务负责管理字幕生成任务的完整生命周期，包括创建、查询、更新、取消和重试任务。

## 功能特性

- ✅ 创建新的字幕生成任务
- ✅ 查询单个任务或任务列表
- ✅ 更新任务状态和进度
- ✅ 取消正在处理的任务
- ✅ 重试失败的任务
- ✅ 获取任务统计信息
- ✅ 支持按状态筛选和分页

## 快速开始

### 初始化

```python
from backend.models.base import SessionLocal
from backend.services.task_manager import TaskManager

# 创建数据库会话
db = SessionLocal()

# 创建 TaskManager 实例
task_manager = TaskManager(db)
```

### 创建任务

```python
# 创建新任务
task = await task_manager.create_task(
    media_item_id="emby-item-123",
    media_item_title="My Movie",
    video_path="/media/movies/my_movie.mp4"
)

print(f"Created task: {task.id}")
print(f"Status: {task.status}")  # PENDING
print(f"Progress: {task.progress}%")  # 0
```

### 查询任务

```python
# 获取单个任务
task = await task_manager.get_task("task-id-123")
if task:
    print(f"Task {task.id}: {task.status} - {task.progress}%")
else:
    print("Task not found")

# 获取所有任务
all_tasks = await task_manager.list_tasks()
print(f"Total tasks: {len(all_tasks)}")

# 按状态筛选
from backend.models.task import TaskStatus

pending_tasks = await task_manager.list_tasks(status=TaskStatus.PENDING)
processing_tasks = await task_manager.list_tasks(status=TaskStatus.PROCESSING)
completed_tasks = await task_manager.list_tasks(status=TaskStatus.COMPLETED)

# 分页查询
page1 = await task_manager.list_tasks(limit=10, offset=0)
page2 = await task_manager.list_tasks(limit=10, offset=10)
```

### 更新任务状态

```python
from backend.models.task import TaskStatus

# 更新为处理中
await task_manager.update_task_status(
    task_id="task-id-123",
    status=TaskStatus.PROCESSING,
    progress=20
)

# 更新进度
await task_manager.update_task_status(
    task_id="task-id-123",
    status=TaskStatus.PROCESSING,
    progress=50
)

# 标记为完成
await task_manager.update_task_status(
    task_id="task-id-123",
    status=TaskStatus.COMPLETED,
    progress=100
)

# 标记为失败并记录错误
await task_manager.update_task_status(
    task_id="task-id-123",
    status=TaskStatus.FAILED,
    error_message="Audio extraction failed: file not found"
)
```

### 取消任务

```python
# 取消任务（仅适用于 PENDING 或 PROCESSING 状态）
success = await task_manager.cancel_task("task-id-123")

if success:
    print("Task cancelled successfully")
else:
    print("Cannot cancel task (not found or already completed)")
```

### 重试失败的任务

```python
# 重试失败的任务（创建新任务）
new_task = await task_manager.retry_task("failed-task-id")

if new_task:
    print(f"Created retry task: {new_task.id}")
    print(f"Original task: {failed_task_id}")
else:
    print("Cannot retry task (not found or not in FAILED status)")
```

### 获取统计信息

```python
# 获取任务统计
stats = await task_manager.get_statistics()

print(f"Total tasks: {stats.total}")
print(f"Pending: {stats.pending}")
print(f"Processing: {stats.processing}")
print(f"Completed: {stats.completed}")
print(f"Failed: {stats.failed}")
print(f"Cancelled: {stats.cancelled}")
```

## 完整示例：字幕生成流程

```python
from backend.models.base import SessionLocal
from backend.models.task import TaskStatus
from backend.services.task_manager import TaskManager

async def subtitle_generation_workflow():
    db = SessionLocal()
    task_manager = TaskManager(db)
    
    try:
        # 1. 创建任务
        task = await task_manager.create_task(
            media_item_id="emby-123",
            media_item_title="Anime Episode 01",
            video_path="/media/anime/episode01.mp4"
        )
        print(f"Task created: {task.id}")
        
        # 2. 开始处理
        await task_manager.update_task_status(
            task.id,
            TaskStatus.PROCESSING,
            progress=0
        )
        
        # 3. 音频提取阶段
        print("Extracting audio...")
        await task_manager.update_task_status(
            task.id,
            TaskStatus.PROCESSING,
            progress=20
        )
        
        # 4. ASR 识别阶段
        print("Running ASR...")
        await task_manager.update_task_status(
            task.id,
            TaskStatus.PROCESSING,
            progress=60
        )
        
        # 5. 翻译阶段
        print("Translating...")
        await task_manager.update_task_status(
            task.id,
            TaskStatus.PROCESSING,
            progress=90
        )
        
        # 6. 生成字幕文件
        print("Generating subtitle file...")
        await task_manager.update_task_status(
            task.id,
            TaskStatus.PROCESSING,
            progress=95
        )
        
        # 7. 完成
        await task_manager.update_task_status(
            task.id,
            TaskStatus.COMPLETED,
            progress=100
        )
        print("Task completed successfully!")
        
    except Exception as e:
        # 处理错误
        await task_manager.update_task_status(
            task.id,
            TaskStatus.FAILED,
            error_message=str(e)
        )
        print(f"Task failed: {e}")
    
    finally:
        db.close()

# 运行工作流
import asyncio
asyncio.run(subtitle_generation_workflow())
```

## 任务状态说明

| 状态 | 说明 | 可转换到 |
|------|------|----------|
| PENDING | 待处理 | PROCESSING, CANCELLED |
| PROCESSING | 处理中 | COMPLETED, FAILED, CANCELLED |
| COMPLETED | 已完成 | - |
| FAILED | 失败 | - (可通过 retry_task 创建新任务) |
| CANCELLED | 已取消 | - |

## 进度值说明

进度值范围：0-100

建议的进度划分：
- 0-20%: 音频提取
- 20-60%: ASR 语音识别
- 60-90%: 翻译
- 90-95%: 生成字幕文件
- 95-100%: Emby 回写

## 注意事项

1. **数据库会话管理**：确保在使用完 TaskManager 后关闭数据库会话
2. **任务取消**：只能取消 PENDING 或 PROCESSING 状态的任务
3. **任务重试**：只能重试 FAILED 状态的任务，会创建新的任务实例
4. **进度边界**：进度值会自动限制在 0-100 范围内
5. **完成时间**：当任务状态变为 COMPLETED、FAILED 或 CANCELLED 时，会自动设置完成时间

## 测试

运行测试：

```bash
pytest backend/test_task_manager.py -v
```

测试覆盖：
- ✅ 创建任务
- ✅ 查询任务（单个和列表）
- ✅ 按状态筛选
- ✅ 分页查询
- ✅ 更新任务状态和进度
- ✅ 进度边界检查
- ✅ 取消任务（各种状态）
- ✅ 重试任务（各种状态）
- ✅ 获取统计信息

## API 集成示例

在 FastAPI 中使用：

```python
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from backend.models.base import get_db
from backend.services.task_manager import TaskManager

router = APIRouter()

@router.post("/tasks")
async def create_task(
    media_item_id: str,
    media_item_title: str,
    video_path: str,
    db: Session = Depends(get_db)
):
    task_manager = TaskManager(db)
    task = await task_manager.create_task(
        media_item_id=media_item_id,
        media_item_title=media_item_title,
        video_path=video_path
    )
    return task

@router.get("/tasks")
async def list_tasks(
    status: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db)
):
    task_manager = TaskManager(db)
    tasks = await task_manager.list_tasks(
        status=TaskStatus(status) if status else None,
        limit=limit,
        offset=offset
    )
    return tasks

@router.get("/stats")
async def get_statistics(db: Session = Depends(get_db)):
    task_manager = TaskManager(db)
    stats = await task_manager.get_statistics()
    return stats
```

## 相关文档

- [Task 模型定义](../models/task.py)
- [数据库配置](../models/base.py)
- [Celery 任务集成](../tasks/subtitle_tasks.py)
