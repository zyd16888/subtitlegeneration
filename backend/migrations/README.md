# 数据库迁移

本目录包含数据库迁移脚本，用于更新**已有数据库**的结构。

## 重要说明

- **新安装的系统**：无需运行迁移脚本
  - SQLAlchemy 的 `init_db()` 会根据模型定义自动创建完整的表结构
  - 所有字段都会在初始化时创建
  
- **已运行的系统**：需要运行迁移脚本
  - 用于给现有数据库添加新字段
  - 不影响现有数据

## 迁移历史

### 2026-04-07: 添加 Telegram 用户追踪

**文件**: `migrate_add_telegram_tracking.py`

**目的**: 在任务表中添加 Telegram 用户追踪字段，以便在网页管理界面查看任务提交者信息。

**新增字段**:
- `telegram_user_id` (BIGINT): Telegram 用户 ID
- `telegram_username` (VARCHAR): Telegram 用户名
- `telegram_display_name` (VARCHAR): Telegram 显示名称
- `emby_username` (VARCHAR): 关联的 Emby 用户名

**运行方式**:
```bash
cd backend
python -m migrations.migrate_add_telegram_tracking
```

**影响**:
- 任务列表页面将显示提交用户信息
- 任务详情页面将显示完整的用户信息
- 支持按用户筛选任务（未来功能）

## 注意事项

1. 迁移脚本会自动检查字段是否已存在，避免重复执行
2. 所有新字段都是可选的（nullable），不影响现有数据
3. 为 `telegram_user_id` 创建了索引以提高查询性能
4. 现有任务的用户字段将为空，新创建的任务会自动填充


## 工作原理

### 新系统初始化流程

```
启动应用 (main.py)
    ↓
调用 init_db()
    ↓
SQLAlchemy 读取所有模型定义 (models/*.py)
    ↓
执行 Base.metadata.create_all()
    ↓
自动创建所有表和字段（包括新字段）
    ↓
✓ 数据库就绪
```

### 已有系统迁移流程

```
已有数据库（旧表结构）
    ↓
运行迁移脚本
    ↓
ALTER TABLE 添加新字段
    ↓
CREATE INDEX 创建索引
    ↓
✓ 数据库更新完成
```

## 如何判断是否需要迁移？

运行以下命令检查：

```bash
# 检查 tasks 表是否存在 telegram_user_id 字段
sqlite3 backend/subtitle_service.db "PRAGMA table_info(tasks);" | grep telegram_user_id

# 如果有输出 = 字段已存在，无需迁移
# 如果无输出 = 需要运行迁移脚本
```

或者直接运行迁移脚本，它会自动检查并跳过已存在的字段。

## 迁移脚本的安全性

所有迁移脚本都设计为：
- **幂等性**：可以多次运行，不会重复添加字段
- **非破坏性**：只添加字段，不删除或修改现有数据
- **可回滚**：保留备份可以随时恢复
