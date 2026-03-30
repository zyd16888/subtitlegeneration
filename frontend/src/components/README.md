# Components

可复用的 React 组件库

## Layout.tsx

应用主布局组件，使用 Ant Design Layout 组件实现。

### 功能特性

- **侧边栏导航**: 包含四个主要菜单项（Dashboard, Library, Tasks, Settings）
- **可折叠侧边栏**: 支持展开/折叠，节省屏幕空间
- **顶部导航栏**: 显示应用标题
- **响应式设计**: 使用 Ant Design 主题系统
- **路由集成**: 使用 React Router 的 `useNavigate` 和 `useLocation` 实现导航

### 使用方式

Layout 组件作为路由的父组件使用，通过 `<Outlet />` 渲染子路由内容。

```tsx
<Route path="/" element={<Layout />}>
  <Route index element={<Dashboard />} />
  <Route path="library" element={<Library />} />
  <Route path="tasks" element={<Tasks />} />
  <Route path="settings" element={<Settings />} />
</Route>
```

## TaskStatusBadge.tsx

任务状态徽章组件，显示带图标的彩色状态标签。

### Props

- `status: TaskStatus` - 任务状态（pending, processing, completed, failed, cancelled）

### 使用方式

```tsx
import TaskStatusBadge from '../components/TaskStatusBadge';

<TaskStatusBadge status="processing" />
```

### 状态样式

- **pending**: 灰色，时钟图标
- **processing**: 蓝色，旋转同步图标
- **completed**: 绿色，勾选图标
- **failed**: 红色，错误图标
- **cancelled**: 灰色，关闭图标

## ProgressBar.tsx

任务进度条组件，根据任务状态显示不同样式的进度条。

### Props

- `progress: number` - 进度百分比 (0-100)
- `status: TaskStatus` - 任务状态
- `size?: 'small' | 'default'` - 进度条大小（默认: 'small'）
- `showInfo?: boolean` - 是否显示进度文字（默认: true）

### 使用方式

```tsx
import ProgressBar from '../components/ProgressBar';

<ProgressBar progress={50} status="processing" />
<ProgressBar progress={75} status="processing" size="default" showInfo={false} />
```

### 进度条状态

- **completed**: 成功状态（绿色）
- **failed/cancelled**: 异常状态（红色）
- **processing**: 活动状态（蓝色动画）
- **pending**: 普通状态（灰色）

## MediaItemCard.tsx

媒体项卡片组件，显示媒体项的缩略图、标题、类型和字幕状态。

### Props

- `item: MediaItem` - 媒体项数据
- `selected: boolean` - 是否被选中
- `onSelect: (itemId: string, checked: boolean) => void` - 选择状态改变回调

### 使用方式

```tsx
import MediaItemCard from '../components/MediaItemCard';

<MediaItemCard 
  item={mediaItem} 
  selected={selectedItems.includes(mediaItem.id)} 
  onSelect={handleItemSelect} 
/>
```

### 功能特性

- 显示媒体项缩略图占位符
- 左上角复选框用于选择
- 右上角显示字幕状态图标（绿色勾选/红色叉号）
- 选中时显示蓝色边框
- 悬停效果
- 标题过长时显示省略号

## ErrorBoundary.tsx

错误边界组件，捕获子组件树中的渲染错误并显示友好的错误提示。

### Props

- `children: ReactNode` - 要包裹的子组件

### 使用方式

```tsx
import ErrorBoundary from '../components/ErrorBoundary';

<ErrorBoundary>
  <YourComponent />
</ErrorBoundary>
```

### 功能特性

- 捕获子组件树中的 JavaScript 错误
- 显示友好的错误提示页面
- 提供"刷新页面"和"重试"按钮
- 开发环境下显示详细错误信息和组件堆栈
- 防止整个应用崩溃
- 记录错误到控制台

### 最佳实践

建议在应用的顶层或关键页面组件外包裹 ErrorBoundary：

```tsx
// App.tsx
<ErrorBoundary>
  <Router>
    <Routes>
      <Route path="/" element={<Layout />}>
        <Route index element={<Dashboard />} />
        {/* ... */}
      </Route>
    </Routes>
  </Router>
</ErrorBoundary>
```
