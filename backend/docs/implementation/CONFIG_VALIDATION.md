# 配置验证功能实现文档

## 概述

实现了系统配置完整性验证功能，在用户尝试生成字幕前检查所有必需的配置项是否已填写。

## 功能特性

### 1. 后端 API

#### 新增端点：`GET /api/config/validate`

验证系统配置的完整性，检查以下配置项：

**Emby 配置**
- Emby Server URL
- Emby API Key

**ASR 引擎配置**
- ASR 引擎类型（必选）
- Sherpa-ONNX 模式：
  - ASR 模型路径
- 云端 ASR 模式：
  - 云端 ASR URL
  - 云端 ASR API Key

**翻译服务配置**
- 翻译服务类型（必选）
- OpenAI 模式：
  - OpenAI API Key
  - OpenAI 模型
- DeepSeek 模式：
  - DeepSeek API Key
- 本地 LLM 模式：
  - 本地 LLM URL

#### 响应格式

```json
{
  "is_valid": true,
  "missing_fields": [],
  "message": "所有配置完整，可以正常使用字幕生成功能"
}
```

或

```json
{
  "is_valid": false,
  "missing_fields": ["Emby Server URL", "ASR 模型路径", "OpenAI API Key"],
  "message": "配置不完整，缺少以下配置项: Emby Server URL, ASR 模型路径, OpenAI API Key"
}
```

### 2. 前端集成

#### Library 页面

- 页面加载时自动调用配置验证 API
- 如果配置不完整，显示警告提示框
- 警告框包含：
  - 缺少的配置项列表
  - 前往设置页面的链接
- 配置不完整时，生成字幕功能被禁用

#### MediaConfigModal 组件

- 接收配置验证状态作为 props
- 配置不完整时：
  - 显示警告提示
  - 禁用"生成字幕"按钮

#### SeriesEpisodesModal 组件

- 接收配置验证状态作为 props
- 配置不完整时：
  - 显示警告提示
  - 禁用"生成字幕"按钮

## 实现细节

### 后端实现

**文件：** `backend/api/config.py`

```python
@router.get("/config/validate", response_model=ConfigValidationResult)
async def validate_config(db: Session = Depends(get_db)):
    """验证系统配置是否完整"""
    config_manager = ConfigManager(db)
    config = await config_manager.get_config()
    missing_fields = []
    
    # 检查 Emby 配置
    if not config.emby_url:
        missing_fields.append("Emby Server URL")
    if not config.emby_api_key:
        missing_fields.append("Emby API Key")
    
    # 检查 ASR 引擎配置
    # ... (详见代码)
    
    # 检查翻译服务配置
    # ... (详见代码)
    
    is_valid = len(missing_fields) == 0
    return ConfigValidationResult(
        is_valid=is_valid,
        missing_fields=missing_fields,
        message=message
    )
```

### 前端实现

**文件：** `frontend/src/pages/Library.tsx`

```typescript
// 验证系统配置
const validateConfig = async () => {
  try {
    const result = await api.config.validateConfig();
    setConfigValid(result.is_valid);
    setConfigMessage(result.message);
  } catch (err: any) {
    console.error('验证配置失败:', err);
    setConfigValid(false);
    setConfigMessage('无法验证配置，请检查系统设置');
  }
};

// 页面加载时验证
useEffect(() => {
  fetchLibraries();
  validateConfig();
}, []);
```

**警告提示：**

```tsx
{!configValid && embyConfigured && (
  <Alert
    message="配置不完整"
    description={
      <div>
        {configMessage}
        <br />
        字幕生成功能不可用，请先完成相关配置。
        <br />
        <Button type="link" onClick={() => window.location.href = '/settings'}>
          前往设置页面
        </Button>
      </div>
    }
    type="warning"
    showIcon
    style={{ marginBottom: 24 }}
  />
)}
```

## 测试

### 测试文件

`backend/tests/test_config_validation.py`

### 测试用例

1. `test_validate_config_empty` - 测试空配置
2. `test_validate_config_partial_emby` - 测试部分 Emby 配置
3. `test_validate_config_sherpa_onnx_without_model` - 测试 Sherpa-ONNX 缺少模型
4. `test_validate_config_cloud_asr_without_credentials` - 测试云端 ASR 缺少凭证
5. `test_validate_config_openai_without_key` - 测试 OpenAI 缺少 API Key
6. `test_validate_config_complete` - 测试完整配置
7. `test_validate_config_deepseek` - 测试 DeepSeek 配置
8. `test_validate_config_local_llm` - 测试本地 LLM 配置

### 运行测试

```bash
cd backend
python -m pytest tests/test_config_validation.py -v
```

## 用户体验

### 配置完整时

- Library 页面正常显示媒体项
- 可以点击媒体项打开配置对话框
- 可以正常生成字幕

### 配置不完整时

- Library 页面显示黄色警告框
- 警告框明确指出缺少哪些配置项
- 提供快速跳转到设置页面的链接
- 媒体配置对话框中的"生成字幕"按钮被禁用
- 剧集对话框中的"生成字幕"按钮被禁用

## 相关文件

### 后端
- `backend/api/config.py` - 配置验证 API
- `backend/services/config_manager.py` - 配置管理器
- `backend/tests/test_config_validation.py` - 测试文件

### 前端
- `frontend/src/pages/Library.tsx` - Library 页面
- `frontend/src/components/MediaConfigModal.tsx` - 媒体配置对话框
- `frontend/src/components/SeriesEpisodesModal.tsx` - 剧集对话框
- `frontend/src/services/api.ts` - API 服务
- `frontend/src/types/api.ts` - 类型定义

## 未来改进

1. 实时配置验证：当用户在设置页面修改配置时，实时更新验证状态
2. 配置向导：为新用户提供配置向导，引导完成所有必需配置
3. 配置测试：在设置页面提供"测试配置"按钮，验证配置是否可用
4. 配置导入/导出：支持配置的导入和导出功能
