# 数据库模型单元测试总结

## 任务 2.2: 编写数据库模型单元测试

### 实现内容

创建了完整的 pytest 单元测试套件，测试 Task 和 SystemConfig 模型的 CRUD 操作。

### 测试覆盖

#### Task 模型测试 (TestTaskModel)

1. **test_create_task** - 测试创建任务
   - 验证所有字段正确保存
   - 验证默认值（created_at, progress）
   - 验证可选字段（completed_at, error_message）

2. **test_read_task** - 测试读取任务
   - 通过 ID 查询任务
   - 验证所有字段正确读取

3. **test_update_task** - 测试更新任务
   - 更新状态和进度
   - 更新完成时间
   - 验证更新后的值

4. **test_delete_task** - 测试删除任务
   - 删除任务
   - 验证任务已从数据库移除

5. **test_task_status_enum** - 测试任务状态枚举
   - 测试所有状态值（PENDING, PROCESSING, COMPLETED, FAILED, CANCELLED）
   - 验证枚举正确存储和读取

6. **test_task_error_message** - 测试任务错误信息
   - 测试失败任务的错误信息存储

7. **test_query_tasks_by_status** - 测试按状态查询任务
   - 创建多个不同状态的任务
   - 按状态筛选查询

8. **test_query_tasks_by_media_item_id** - 测试按媒体项 ID 查询任务
   - 查询特定媒体项的所有任务

#### SystemConfig 模型测试 (TestSystemConfigModel)

1. **test_create_config** - 测试创建配置
   - 验证键值对正确保存
   - 验证描述字段

2. **test_read_config** - 测试读取配置
   - 通过键查询配置
   - 验证值正确读取

3. **test_update_config** - 测试更新配置
   - 更新配置值
   - 验证更新后的值

4. **test_delete_config** - 测试删除配置
   - 删除配置
   - 验证配置已从数据库移除

5. **test_config_without_description** - 测试创建没有描述的配置
   - 验证描述字段可选

6. **test_multiple_configs** - 测试存储多个配置
   - 创建多个配置项
   - 验证所有配置正确保存

7. **test_config_key_uniqueness** - 测试配置键的唯一性
   - 验证主键约束
   - 测试重复键抛出异常

8. **test_get_all_configs** - 测试获取所有配置
   - 查询所有配置项
   - 验证配置列表完整性

### 需求验证

**需求 12.1**: Database SHALL use SQLite to store Task information
- ✅ 使用 SQLite 内存数据库进行测试
- ✅ 验证 Task 模型的所有 CRUD 操作

**需求 12.2**: Database SHALL store each Task's fields
- ✅ 任务 ID (id)
- ✅ Media_Item ID (media_item_id)
- ✅ 状态 (status)
- ✅ 进度 (progress)
- ✅ 创建时间 (created_at)
- ✅ 完成时间 (completed_at)
- ✅ 错误信息 (error_message)

### 测试特性

1. **隔离性**: 每个测试使用独立的内存数据库会话
2. **完整性**: 覆盖所有 CRUD 操作
3. **边界测试**: 测试可选字段、枚举值、唯一性约束
4. **查询测试**: 测试按不同条件查询数据

### 运行测试

```bash
# 运行所有模型测试
pytest backend/tests/test_models.py -v

# 运行特定测试类
pytest backend/tests/test_models.py::TestTaskModel -v
pytest backend/tests/test_models.py::TestSystemConfigModel -v

# 运行特定测试
pytest backend/tests/test_models.py::TestTaskModel::test_create_task -v
```

### 测试统计

- **总测试数**: 16
- **Task 模型测试**: 8
- **SystemConfig 模型测试**: 8
- **覆盖率**: 100% CRUD 操作
