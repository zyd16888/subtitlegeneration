# Task 16: Library 页面实现文档

## 概述

本文档记录了 Task 16 "Library 页面" 的实现细节。

## 实现的功能

### 16.1 实现 Library 页面组件 ✅

**文件:** `frontend/src/pages/Library.tsx`

**实现的功能:**
- ✅ 显示媒体库筛选器（媒体库、类型、搜索）
- ✅ 显示媒体项网格视图（缩略图、标题、字幕状态）
- ✅ 实现媒体项选择功能（多选）
- ✅ 全选/取消全选功能
- ✅ 响应式布局（支持不同屏幕尺寸）

**需求覆盖:** 9.1, 9.2, 9.3

**关键实现:**

1. **筛选器组件**
   - 媒体库下拉选择器：从 API 获取媒体库列表
   - 类型下拉选择器：电影、剧集、单集
   - 搜索框：支持按名称搜索

2. **媒体项网格视图**
   - 使用 Ant Design Card 组件展示媒体项
   - 显示缩略图占位符（PlayCircleOutlined 图标）
   - 显示媒体项标题和类型
   - 显示字幕状态图标：
     - ✅ 绿色勾号：已有字幕
     - ❌ 红色叉号：无字幕

3. **选择功能**
   - 每个媒体项卡片左上角有复选框
   - 支持单个选择和批量选择
   - 全选/取消全选功能
   - 选中的卡片有蓝色边框高亮

### 16.2 实现生成字幕功能 ✅

**实现的功能:**
- ✅ 添加"生成字幕"按钮
- ✅ 实现批量创建任务
- ✅ 显示任务创建成功提示
- ✅ 按钮状态管理（禁用/加载中）

**需求覆盖:** 9.4, 9.5, 15.1

**关键实现:**

1. **生成字幕按钮**
   - 位于操作栏右侧
   - 显示当前选中的媒体项数量
   - 未选中任何项时禁用
   - 点击时显示加载状态

2. **批量任务创建**
   - 调用 `api.tasks.createTasks()` API
   - 传递选中的媒体项 ID 数组
   - 成功后显示成功消息
   - 失败后显示错误消息
   - 任务创建后清空选择

### 16.3 实现分页功能 ✅

**实现的功能:**
- ✅ 使用 Ant Design Pagination 组件
- ✅ 实现分页数据加载
- ✅ 支持每页显示数量调整
- ✅ 支持快速跳转到指定页

**需求覆盖:** 9.2

**关键实现:**

1. **分页组件**
   - 显示总数、当前页、每页数量
   - 支持切换每页显示数量（10/20/50/100）
   - 支持快速跳转
   - 显示总数统计

2. **分页数据加载**
   - 根据当前页和每页数量计算 offset
   - 筛选条件改变时重置到第一页
   - 分页改变时重新加载数据
   - 加载时显示 Spin 加载指示器

## 状态管理

```typescript
// 筛选状态
const [libraries, setLibraries] = useState<Library[]>([]);
const [selectedLibrary, setSelectedLibrary] = useState<string | undefined>();
const [selectedType, setSelectedType] = useState<string | undefined>();
const [searchText, setSearchText] = useState<string>('');

// 数据状态
const [mediaItems, setMediaItems] = useState<MediaItem[]>([]);
const [selectedItems, setSelectedItems] = useState<string[]>([]);

// UI 状态
const [loading, setLoading] = useState(false);
const [error, setError] = useState<string | null>(null);
const [generating, setGenerating] = useState(false);

// 分页状态
const [currentPage, setCurrentPage] = useState(1);
const [pageSize, setPageSize] = useState(20);
const [total, setTotal] = useState(0);
```

## API 集成

### 使用的 API 端点

1. **GET /api/libraries**
   - 获取媒体库列表
   - 在组件挂载时调用

2. **GET /api/media**
   - 获取媒体项列表
   - 支持筛选参数：library_id, item_type, search
   - 支持分页参数：limit, offset

3. **POST /api/tasks**
   - 创建字幕生成任务
   - 请求体：{ media_item_ids: string[] }

## 用户交互流程

### 浏览媒体库流程
1. 用户打开 Library 页面
2. 系统加载媒体库列表和默认媒体项
3. 用户可以通过筛选器筛选媒体项
4. 用户可以通过搜索框搜索媒体项
5. 用户可以通过分页浏览更多媒体项

### 生成字幕流程
1. 用户选择一个或多个媒体项
2. 点击"生成字幕"按钮
3. 系统创建字幕生成任务
4. 显示成功消息
5. 清空选择状态

## 响应式设计

使用 Ant Design Grid 系统实现响应式布局：

```typescript
<Col xs={24} sm={12} md={8} lg={6} xl={4}>
  // 媒体项卡片
</Col>
```

- **xs (< 576px):** 1 列
- **sm (≥ 576px):** 2 列
- **md (≥ 768px):** 3 列
- **lg (≥ 992px):** 4 列
- **xl (≥ 1200px):** 6 列

## 错误处理

1. **API 错误**
   - 显示 Alert 组件提示错误信息
   - 可关闭的错误提示

2. **空状态**
   - 无媒体项时显示 Empty 组件

3. **加载状态**
   - 数据加载时显示 Spin 组件

## 性能优化

1. **useEffect 依赖管理**
   - 媒体库列表只在组件挂载时加载一次
   - 媒体项列表在筛选条件或分页改变时重新加载

2. **选择状态管理**
   - 筛选条件改变时清空选择
   - 任务创建成功后清空选择

## 验证

### 功能验证

✅ **16.1 Library 页面组件**
- 媒体库筛选器正常工作
- 类型筛选器正常工作
- 搜索功能正常工作
- 媒体项网格视图正常显示
- 字幕状态图标正确显示
- 多选功能正常工作

✅ **16.2 生成字幕功能**
- "生成字幕"按钮正常工作
- 批量创建任务成功
- 成功提示正常显示
- 按钮状态正确管理

✅ **16.3 分页功能**
- 分页组件正常显示
- 分页切换正常工作
- 每页数量调整正常工作
- 快速跳转正常工作

### 构建验证

```bash
cd frontend
pnpm run build
```

✅ 构建成功，无 TypeScript 错误

## 后续改进建议

1. **缩略图支持**
   - 当前使用占位符图标
   - 可以集成 Emby 的缩略图 API

2. **虚拟滚动**
   - 对于大量媒体项，可以使用虚拟滚动优化性能

3. **高级筛选**
   - 添加更多筛选条件（年份、评分等）
   - 添加排序功能

4. **批量操作**
   - 添加批量删除字幕功能
   - 添加批量下载字幕功能

## 相关文件

- `frontend/src/pages/Library.tsx` - Library 页面组件
- `frontend/src/services/api.ts` - API 服务层
- `frontend/src/types/api.ts` - API 类型定义
- `.kiro/specs/emby-subtitle-generator/requirements.md` - 需求文档
- `.kiro/specs/emby-subtitle-generator/design.md` - 设计文档
