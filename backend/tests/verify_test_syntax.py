"""
验证测试文件语法正确性
"""
import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    # 尝试导入测试模块
    print("正在验证测试文件语法...")
    import backend.tests.test_models as test_models
    
    print("✓ 测试文件导入成功")
    print(f"✓ 找到测试类: TestTaskModel")
    print(f"✓ 找到测试类: TestSystemConfigModel")
    
    # 检查测试方法数量
    task_tests = [m for m in dir(test_models.TestTaskModel) if m.startswith('test_')]
    config_tests = [m for m in dir(test_models.TestSystemConfigModel) if m.startswith('test_')]
    
    print(f"\nTask 模型测试方法数: {len(task_tests)}")
    for test in task_tests:
        print(f"  - {test}")
    
    print(f"\nSystemConfig 模型测试方法数: {len(config_tests)}")
    for test in config_tests:
        print(f"  - {test}")
    
    print(f"\n✅ 总测试数: {len(task_tests) + len(config_tests)}")
    print("✅ 测试文件语法验证通过!")
    
except Exception as e:
    print(f"❌ 验证失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
