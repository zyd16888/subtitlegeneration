# 测试文件说明

本目录包含后端所有模块的测试文件。

## 测试文件列表

### 核心功能测试
- `test_backend_setup.py` - 后端核心功能完整验证测试（任务12检查点）

### 服务层测试
- `test_asr_engine.py` - ASR 语音识别引擎测试
- `test_audio_extractor.py` - 音频提取服务测试
- `test_config_manager.py` - 配置管理服务测试
- `test_emby_connector.py` - Emby 连接器单元测试
- `test_emby_connector_integration.py` - Emby 连接器集成测试
- `test_subtitle_generator.py` - 字幕生成服务测试
- `test_task_manager.py` - 任务管理服务测试
- `test_translation_service.py` - 翻译服务测试

### API 测试
- `test_api_endpoints.py` - API 端点测试

### 任务测试
- `test_celery_tasks.py` - Celery 异步任务测试
- `test_task_11_integration.py` - 任务11集成测试

### 模型测试
- `test_models.py` - 数据库模型单元测试（Task 和 SystemConfig 的 CRUD 操作）
  - 测试 Task 模型的创建、读取、更新、删除操作
  - 测试 SystemConfig 模型的存储和读取
  - 验证需求 12.1 和 12.2

### 工具测试
- `test_logger.py` - 日志工具测试
- `test_error_handling.py` - 错误处理测试

## 运行测试

### 运行所有测试
```bash
# 使用 pytest
pytest

# 或运行完整验证测试
python tests/test_backend_setup.py
```

### 运行特定测试文件
```bash
pytest tests/test_task_manager.py
pytest tests/test_emby_connector.py -v
```

### 运行特定测试函数
```bash
pytest tests/test_task_manager.py::test_create_task
```

### 查看测试覆盖率
```bash
pytest --cov=backend --cov-report=html
```

## 测试要求

1. 所有测试需要 Redis 服务运行在 localhost:6379
2. 使用 conda ame 环境
3. 确保已安装所有依赖：`pip install -r requirements.txt`

## 测试最佳实践

1. 每个服务/模块都应有对应的测试文件
2. 测试应该独立，不依赖其他测试的执行顺序
3. 使用 mock 来隔离外部依赖（如 Emby API、翻译 API）
4. 测试后清理创建的测试数据
5. 使用有意义的测试函数名称
