# 设置页面改进说明

## 修改内容

### 1. 支持分开保存配置

之前的问题：保存 Emby 配置时，如果 OpenAI 相关配置未填写，会导致保存失败。

解决方案：
- 后端新增 `PATCH /api/config` 接口，支持部分更新配置
- 前端设置页面添加三个保存按钮：
  - "保存 Emby 配置" - 只保存 Emby 相关配置
  - "保存翻译配置" - 只保存翻译服务相关配置
  - "保存所有配置" - 保存全部配置

### 2. Library 页面友好提示

之前的问题：没有 Emby 配置时，Library 页面会报错。

解决方案：
- 检测 Emby 是否已配置
- 未配置时显示友好的警告提示
- 提供"前往设置页面"的快捷链接
- 避免在未配置时尝试加载媒体库数据

## 技术实现

### 后端修改

1. `backend/api/config.py`
   - 新增 `partial_update_config` 端点（PATCH 方法）
   - 支持接收部分配置字段并更新

2. `backend/services/config_manager.py`
   - 新增 `partial_update_config` 方法
   - 新增 `validate_partial_config` 方法
   - 只验证和更新指定的配置字段

### 前端修改

1. `frontend/src/services/api.ts`
   - 新增 `partialUpdateConfig` 方法
   - 使用 PATCH 请求更新部分配置

2. `frontend/src/pages/Settings.tsx`
   - 拆分保存逻辑为三个独立函数：
     - `handleSaveEmby` - 保存 Emby 配置
     - `handleSaveTranslation` - 保存翻译配置
     - `handleSaveAll` - 保存所有配置
   - 在 Emby 和翻译配置卡片上添加独立的保存按钮

3. `frontend/src/pages/Library.tsx`
   - 新增 `embyConfigured` 状态
   - 在获取媒体库失败时检测是否为配置问题
   - 显示配置提示而不是错误信息
   - 未配置时不尝试加载媒体项

## 使用说明

### 分开保存配置

1. 打开设置页面
2. 填写 Emby 配置后，点击"保存 Emby 配置"按钮
3. 稍后填写翻译服务配置后，点击"保存翻译配置"按钮
4. 或者填写完所有配置后，点击"保存所有配置"按钮

### Library 页面提示

1. 首次使用时，如果未配置 Emby，会看到黄色警告提示
2. 点击"前往设置页面"链接快速跳转到设置页面
3. 配置完成后，返回 Library 页面即可正常使用
